"""Dual-Track Inbound Response Classifier with Stable Canonical Event Identity."""
from __future__ import annotations

import hashlib
import re
from matching.models import Track
from .models import (
    ExtractedDeadline,
    InboundMessageEvidence,
    InboundSignal,
    SignalCategory,
    SignalPriority,
)

CLASSIFIER_VERSION = "1.0.0"


class ResponseClassifier:
    """Classifies inbound message evidence into canonical signal categories with high-priority recall."""

    @classmethod
    def compute_signal_id(cls, message_content_hash: str, category: SignalCategory, track: Track) -> str:
        """Create deterministic stable signal identity from immutable evidence and material classification."""
        payload = f"{message_content_hash}:{category.value}:{track.value}:{CLASSIFIER_VERSION}".encode("utf-8")
        return f"sig-{hashlib.sha256(payload).hexdigest()[:16]}"

    @classmethod
    def extract_deadline(cls, text: str) -> ExtractedDeadline | None:
        """Extract explicit deadline snippets from text without hallucinating precision."""
        lower = text.lower()
        patterns = [
            r"by\s+([a-zA-Z]+\s+\d{1,2}(?:,\s+\d{4})?)",
            r"before\s+([a-zA-Z]+\s+\d{1,2}(?:,\s+\d{4})?)",
            r"deadline\s*(?:is|:)?\s*([a-zA-Z]+\s+\d{1,2}(?:,\s+\d{4})?)",
            r"within\s+(\d+\s+(?:days|hours|business days))",
            r"complete\s+by\s+([a-zA-Z]+\s+\d{1,2})",
            r"respond\s+by\s+([a-zA-Z]+\s+\d{1,2})",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                snippet = m.group(0)
                is_amb = any(w in snippet.lower() for w in ("tomorrow", "soon", "eod", "end of day", "next week", "few days"))
                return ExtractedDeadline(
                    raw_snippet=snippet,
                    iso_timestamp=None,
                    is_ambiguous=is_amb,
                    requires_human_verification=True,
                )
        if any(w in lower for w in ("deadline", "respond within", "action required within", "time-sensitive")):
            return ExtractedDeadline(
                raw_snippet="Time-sensitive response indicated in message",
                iso_timestamp=None,
                is_ambiguous=True,
                requires_human_verification=True,
            )
        return None

    @classmethod
    def extract_references(cls, text: str) -> tuple[str, ...]:
        """Extract current requisition / application / proposal IDs, ignoring quoted threads where possible."""
        clean_text = text.split("-----Original Message-----")[0].split("On ")[0]
        refs: set[str] = set()
        for m in re.finditer(r"(?:req(?:uisition)?|app(?:lication)?|ref(?:erence)?|proposal|tender|notice)\s*(?:#|id|:)?\s*([A-Za-z0-9\-_]{4,30})", clean_text, re.IGNORECASE):
            refs.add(m.group(1).strip())
        for m in re.finditer(r"\b(?:APP|REQ|JOB|PROP|TED|UNGM|SOW|WB)-[A-Za-z0-9\-]+\b", clean_text):
            refs.add(m.group(0).strip())
        return tuple(sorted(refs))

    @classmethod
    def extract_organization_and_role(cls, evidence: InboundMessageEvidence) -> tuple[str, str]:
        """Extract candidate organization and role title from subject and headers."""
        text = f"{evidence.subject} {evidence.body_text[:500]}"
        org = ""
        role = ""
        m_org = re.search(r"\b(?:at|with|for)\s+([A-Z][A-Za-z0-9\s&]{2,25})\b", evidence.subject)
        if m_org:
            org = m_org.group(1).strip()
        m_role = re.search(r"(?:application for|regarding|role:?|position:?)\s+([A-Za-z0-9\s\-_/]{3,35})", evidence.subject, re.IGNORECASE)
        if m_role:
            role = m_role.group(1).strip()
        return org, role

    def classify(self, evidence: InboundMessageEvidence) -> InboundSignal:
        """Classify evidence into a high-confidence InboundSignal with evidence-backed timestamp."""
        subject_lower = evidence.subject.lower()
        body_lower = evidence.body_text.lower()
        full_text = f"{subject_lower} {body_lower}"
        detected_at = evidence.received_at
        deadline = self.extract_deadline(evidence.body_text)
        refs = self.extract_references(evidence.body_text + " " + evidence.subject)
        org, role = self.extract_organization_and_role(evidence)

        # 1. NOISE & MARKETING (Filter first for explicit marketing indicators)
        if any(k in full_text for k in ("unsubscribe", "job alert", "recommended jobs", "newsletter", "weekly digest", "promoted jobs", "promoted bids", "premium features", "sponsored", "automated platform notice", "system maintenance")):
            cat = SignalCategory.MARKETING if any(k in full_text for k in ("unsubscribe", "newsletter", "weekly digest", "promoted jobs", "promoted bids", "premium features")) else SignalCategory.GENERIC_NON_ACTIONABLE_PLATFORM_NOTIFICATION
            track = Track.EMPLOYMENT
            sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
            return InboundSignal(
                signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                provider_message_id=evidence.provider_message_id, category=cat,
                priority=SignalPriority.NOISE, track=track, confidence=0.90,
                summary="Marketing or automated platform notification", sender_email=evidence.sender_email,
                detected_at=detected_at, deadline=None, extracted_references=(),
                extracted_organization="", extracted_role_title="", requires_founder_action=False,
            )

        # 2. PROCUREMENT / TENDER TRACK SIGNALS
        if any(k in full_text for k in ("tender", "procurement", "rfp", "request for proposal", "eoi", "ungm", "ted.europa", "contract award", "world bank", "rfp wb-", "sow-")):
            if any(k in full_text for k in ("amendment", "corrigendum", "addendum", "rectification")):
                cat = SignalCategory.PROCUREMENT_AMENDMENT
                track = Track.PROCUREMENT
                sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=cat,
                    priority=SignalPriority.HIGH, track=track, confidence=0.95,
                    summary=f"Procurement amendment published for tender {refs[0] if refs else ''}",
                    sender_email=evidence.sender_email, detected_at=detected_at, deadline=deadline,
                    extracted_references=refs, extracted_organization=org, extracted_role_title=role,
                    requires_founder_action=True, action_description="Review procurement amendment and revised terms",
                )
            if any(k in full_text for k in ("deadline extended", "deadline postponed", "submission deadline has been extended", "deadline change")):
                cat = SignalCategory.PROCUREMENT_DEADLINE_CHANGE
                track = Track.PROCUREMENT
                sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=cat,
                    priority=SignalPriority.URGENT, track=track, confidence=0.95,
                    summary="Procurement submission deadline modified", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=True,
                    action_description="Review updated submission deadline",
                )
            if any(k in full_text for k in ("contract awarded", "notice of award", "we are pleased to award", "award decision", "intent to award")):
                cat = SignalCategory.AWARD_OR_WIN
                track = Track.PROCUREMENT
                sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=cat,
                    priority=SignalPriority.URGENT, track=track, confidence=0.98,
                    summary="Procurement tender / contract award notification", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=True,
                    action_description="Review contract award notice and next steps",
                )
            if any(k in full_text for k in ("clarification requested", "request for clarification", "please clarify", "questions regarding your bid", "clarification on your proposal")):
                cat = SignalCategory.CLARIFICATION_REQUEST
                track = Track.PROCUREMENT
                sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=cat,
                    priority=SignalPriority.URGENT, track=track, confidence=0.96,
                    summary="Procurement clarification request requiring response", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=True,
                    action_description="Prepare and submit requested tender clarifications",
                )
            if any(k in full_text for k in ("shortlisted", "you have been shortlisted", "selected for the next round")):
                cat = SignalCategory.SHORTLIST_OR_INVITATION
                track = Track.PROCUREMENT
                sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=cat,
                    priority=SignalPriority.HIGH, track=track, confidence=0.95,
                    summary="Tender proposal shortlisted", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=True,
                    action_description="Review shortlist notice and prepare next stage documents",
                )
            if any(k in full_text for k in ("not selected for contract award", "not selected your proposal", "regret to inform you that your proposal was not selected")):
                cat = SignalCategory.PROPOSAL_REJECTION
                track = Track.PROCUREMENT
                sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=cat,
                    priority=SignalPriority.LOW, track=track, confidence=0.95,
                    summary="Tender proposal rejected", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=False,
                )
            if any(k in full_text for k in ("proposal received", "bid submitted successfully", "acknowledgement of tender submission", "receipt of bid")):
                cat = SignalCategory.PROPOSAL_CONFIRMATION
                track = Track.PROCUREMENT
                sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=cat,
                    priority=SignalPriority.LOW, track=track, confidence=0.95,
                    summary="Tender / proposal submission receipt confirmed", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=False,
                )

        # 3. FREELANCE / INDEPENDENT CLIENT SIGNALS
        if any(k in full_text for k in ("freelance", "contract proposal", "consulting proposal", "statement of work", "discovery call", "contract progress", "deliverable accepted", "client feedback", "client response", "regarding your proposal")):
            if any(k in full_text for k in ("contract progress", "deliverable accepted", "milestone approved", "sow signed")):
                cat = SignalCategory.CONTRACT_PROGRESS
                track = Track.FREELANCE
                sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=cat,
                    priority=SignalPriority.HIGH, track=track, confidence=0.95,
                    summary="Client contract progress / milestone update", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=True,
                    action_description="Review contract progress and next deliverables",
                )
            if any(k in full_text for k in ("discovery call", "schedule a call to discuss", "let's have a brief call", "introductory meeting")):
                cat = SignalCategory.DISCOVERY_CALL_OR_MEETING_REQUEST
                track = Track.FREELANCE
                sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=cat,
                    priority=SignalPriority.URGENT, track=track, confidence=0.96,
                    summary="Client requested discovery call / project discussion", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=True,
                    action_description="Respond to client meeting / discovery call request",
                )
            if any(k in full_text for k in ("shortlisted", "you have been shortlisted", "selected for the next round of evaluation")):
                cat = SignalCategory.SHORTLIST_OR_INVITATION
                track = Track.FREELANCE
                sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=cat,
                    priority=SignalPriority.HIGH, track=track, confidence=0.95,
                    summary="Proposal shortlisted by client", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=True,
                    action_description="Review shortlist notice and prepare next deliverables",
                )
            if any(k in full_text for k in ("not selected your proposal", "decided to move forward with another consultant", "regret to inform you that your proposal")):
                cat = SignalCategory.PROPOSAL_REJECTION
                track = Track.FREELANCE
                sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=cat,
                    priority=SignalPriority.LOW, track=track, confidence=0.95,
                    summary="Freelance / client proposal rejected", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=False,
                )
            if any(k in full_text for k in ("client response", "regarding your proposal", "client feedback", "client message", "reviewed your proposal", "reviewed your consulting proposal")):
                cat = SignalCategory.CLIENT_OR_BUYER_RESPONSE
                track = Track.FREELANCE
                sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=cat,
                    priority=SignalPriority.HIGH, track=track, confidence=0.92,
                    summary="Direct client / buyer response received", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=True,
                    action_description="Review client message and respond",
                )

        # 4. HIGH-PRIORITY EMPLOYMENT SIGNALS
        # Offer
        if any(k in full_text for k in ("job offer", "offer of employment", "pleased to offer you the position", "formal offer letter", "congratulations on your offer")):
            cat = SignalCategory.OFFER
            track = Track.EMPLOYMENT
            sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
            return InboundSignal(
                signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                provider_message_id=evidence.provider_message_id, category=cat,
                priority=SignalPriority.URGENT, track=track, confidence=0.98,
                summary=f"Formal job offer received for {role or 'role'} at {org or 'company'}",
                sender_email=evidence.sender_email, detected_at=detected_at, deadline=deadline,
                extracted_references=refs, extracted_organization=org, extracted_role_title=role,
                requires_founder_action=True, action_description="Review job offer terms and deadline",
            )

        # Interview Request / Reschedule
        if any(k in full_text for k in (
            "invitation to interview", "schedule an interview", "like to invite you for an interview",
            "would love to speak with you", "schedule a chat", "calendar invite", "select a time for your interview",
            "interview availability", "book a slot", "screening call", "technical interview", "reschedule our interview",
            "rescheduling your interview", "new time for our interview",
        )):
            cat = SignalCategory.INTERVIEW_REQUEST
            track = Track.EMPLOYMENT
            sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
            return InboundSignal(
                signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                provider_message_id=evidence.provider_message_id, category=cat,
                priority=SignalPriority.URGENT, track=track, confidence=0.98,
                summary=f"Interview request / scheduling from {evidence.sender_name or evidence.sender_email} for {role or 'position'}",
                sender_email=evidence.sender_email, detected_at=detected_at, deadline=deadline,
                extracted_references=refs, extracted_organization=org, extracted_role_title=role,
                requires_founder_action=True, action_description="Select interview time slot or reply to scheduler",
            )

        # Assessment / Take-home Test
        if any(k in full_text for k in ("assessment test", "take-home assignment", "coding challenge", "hackerrank", "codility", "complete the following assessment", "technical assessment")):
            cat = SignalCategory.ASSESSMENT
            track = Track.EMPLOYMENT
            sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
            return InboundSignal(
                signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                provider_message_id=evidence.provider_message_id, category=cat,
                priority=SignalPriority.HIGH, track=track, confidence=0.96,
                summary=f"Candidate assessment / test requested by {org or 'company'}",
                sender_email=evidence.sender_email, detected_at=detected_at, deadline=deadline,
                extracted_references=refs, extracted_organization=org, extracted_role_title=role,
                requires_founder_action=True, action_description="Review and complete candidate assessment before deadline",
            )

        # Recruiter Human Outreach / Direct Inquiry
        if any(k in full_text for k in ("came across your profile", "impressed by your background", "reaching out regarding an opportunity", "would you be open to", "let me know if you are interested")):
            cat = SignalCategory.RECRUITER_OUTREACH
            track = Track.EMPLOYMENT
            sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
            return InboundSignal(
                signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                provider_message_id=evidence.provider_message_id, category=cat,
                priority=SignalPriority.HIGH, track=track, confidence=0.92,
                summary=f"Direct recruiter outreach from {evidence.sender_name or evidence.sender_email}",
                sender_email=evidence.sender_email, detected_at=detected_at, deadline=deadline,
                extracted_references=refs, extracted_organization=org, extracted_role_title=role,
                requires_founder_action=True, action_description="Review recruiter outreach and respond if interested",
            )

        # Information / Clarification Request
        if any(k in full_text for k in ("please provide your updated", "additional information required", "need a copy of your", "clarify your availability", "please answer the following questions", "additional information")):
            cat = SignalCategory.INFORMATION_REQUEST
            track = Track.EMPLOYMENT
            sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
            return InboundSignal(
                signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                provider_message_id=evidence.provider_message_id, category=cat,
                priority=SignalPriority.HIGH, track=track, confidence=0.90,
                summary="Additional candidate information requested", sender_email=evidence.sender_email,
                detected_at=detected_at, deadline=deadline, extracted_references=refs,
                extracted_organization=org, extracted_role_title=role, requires_founder_action=True,
                action_description="Provide requested candidate details",
            )

        # 5. ROUTINE EMPLOYMENT SIGNALS
        # Rejection
        if any(k in full_text for k in (
            "thank you for your interest, but", "decided to pursue other candidates",
            "not moving forward with your application", "decided not to proceed",
            "regret to inform you", "unfortunately, we will not be moving forward",
            "after careful consideration, we have chosen",
        )):
            cat = SignalCategory.REJECTION
            track = Track.EMPLOYMENT
            sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
            return InboundSignal(
                signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                provider_message_id=evidence.provider_message_id, category=cat,
                priority=SignalPriority.LOW, track=track, confidence=0.96,
                summary=f"Application rejected for {role or 'role'} at {org or 'company'}",
                sender_email=evidence.sender_email, detected_at=detected_at, deadline=deadline,
                extracted_references=refs, extracted_organization=org, extracted_role_title=role,
                requires_founder_action=False,
            )

        # Application Confirmation
        if any(k in full_text for k in (
            "thank you for applying", "application received", "we have received your application",
            "successfully submitted your application", "your application has been submitted",
            "confirmation of your application", "thanks for submitting your application",
        )):
            cat = SignalCategory.APPLICATION_CONFIRMATION
            track = Track.EMPLOYMENT
            sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
            return InboundSignal(
                signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                provider_message_id=evidence.provider_message_id, category=cat,
                priority=SignalPriority.LOW, track=track, confidence=0.97,
                summary=f"Application confirmation received for {role or 'role'} at {org or 'company'}",
                sender_email=evidence.sender_email, detected_at=detected_at, deadline=deadline,
                extracted_references=refs, extracted_organization=org, extracted_role_title=role,
                requires_founder_action=False,
            )

        # 6. UNCLASSIFIED / REVIEW REQUIRED
        cat = SignalCategory.UNCLASSIFIED
        track = Track.EMPLOYMENT
        sig_id = self.compute_signal_id(evidence.message_content_hash, cat, track)
        return InboundSignal(
            signal_id=sig_id, message_content_hash=evidence.message_content_hash,
            provider_message_id=evidence.provider_message_id, category=cat,
            priority=SignalPriority.MEDIUM, track=track, confidence=0.50,
            summary=f"Unclassified inbound message: {evidence.subject}",
            sender_email=evidence.sender_email, detected_at=detected_at, deadline=deadline,
            extracted_references=refs, extracted_organization=org, extracted_role_title=role,
            requires_founder_action=True, action_description="Review unclassified inbound correspondence",
        )
