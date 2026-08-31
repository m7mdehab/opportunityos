"""Dual-Track Inbound Response Classifier with High-Priority Recall Guarantee."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from matching.models import Track
from .models import (
    ExtractedDeadline,
    InboundMessageEvidence,
    InboundSignal,
    SignalCategory,
    SignalPriority,
)


class ResponseClassifier:
    """Classifies inbound message evidence into canonical signal categories with high-priority recall."""

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
                    iso_timestamp=None,  # Do not hallucinate exact ISO timestamp without verified timezone/calendar resolution
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
        """Extract requisition / application / proposal IDs."""
        refs: set[str] = set()
        # Patterns like Req #12345, App ID: APP-9876, #987654, Ref: REF-001
        for m in re.finditer(r"(?:req(?:uisition)?|app(?:lication)?|ref(?:erence)?|proposal|tender|notice)\s*(?:#|id|:)?\s*([A-Za-z0-9\-_]{4,30})", text, re.IGNORECASE):
            refs.add(m.group(1).strip())
        for m in re.finditer(r"(?:APP|REQ|JOB|PROP|TED|UNGM)-[A-Za-z0-9\-]+", text):
            refs.add(m.group(0).strip())
        return tuple(sorted(refs))

    @classmethod
    def extract_organization_and_role(cls, evidence: InboundMessageEvidence) -> tuple[str, str]:
        """Extract candidate organization and role title from subject and headers."""
        text = f"{evidence.subject} {evidence.body_text[:500]}"
        org = ""
        role = ""
        # Regex for 'at <Org>' or 'with <Org>'
        m_org = re.search(r"(?:at|with|for)\s+([A-Z][A-Za-z0-9\s&]{2,25})", evidence.subject)
        if m_org:
            org = m_org.group(1).strip()
        # Regex for role: 'Application for <Role>', '<Role> Interview', '<Role> Role'
        m_role = re.search(r"(?:application for|regarding|role:?|position:?)\s+([A-Za-z0-9\s\-_/]{3,35})", evidence.subject, re.IGNORECASE)
        if m_role:
            role = m_role.group(1).strip()
        return org, role

    def classify(self, evidence: InboundMessageEvidence) -> InboundSignal:
        """Classify evidence into a high-confidence InboundSignal."""
        subject_lower = evidence.subject.lower()
        body_lower = evidence.body_text.lower()
        full_text = f"{subject_lower} {body_lower}"
        detected_at = datetime.now(timezone.utc).isoformat()
        sig_id = f"sig-{uuid.uuid4().hex[:12]}"
        deadline = self.extract_deadline(evidence.body_text)
        refs = self.extract_references(evidence.body_text + " " + evidence.subject)
        org, role = self.extract_organization_and_role(evidence)

        # 1. PROCUREMENT / TENDER TRACK SIGNALS
        if any(k in full_text for k in ("tender", "procurement", "rfp", "request for proposal", "eoi", "ungm", "ted.europa", "contract award")):
            if any(k in full_text for k in ("amendment", "corrigendum", "addendum", "rectification")):
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=SignalCategory.PROCUREMENT_AMENDMENT,
                    priority=SignalPriority.HIGH, track=Track.PROCUREMENT, confidence=0.95,
                    summary=f"Procurement amendment published for tender {refs[0] if refs else ''}",
                    sender_email=evidence.sender_email, detected_at=detected_at, deadline=deadline,
                    extracted_references=refs, extracted_organization=org, extracted_role_title=role,
                    requires_founder_action=True, action_description="Review procurement amendment and revised terms",
                )
            if any(k in full_text for k in ("deadline extended", "deadline postponed", "submission deadline has been extended", "deadline change")):
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=SignalCategory.PROCUREMENT_DEADLINE_CHANGE,
                    priority=SignalPriority.URGENT, track=Track.PROCUREMENT, confidence=0.95,
                    summary="Procurement submission deadline modified", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=True,
                    action_description="Review updated submission deadline",
                )
            if any(k in full_text for k in ("contract awarded", "notice of award", "we are pleased to award", "award decision", "intent to award")):
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=SignalCategory.AWARD_OR_WIN,
                    priority=SignalPriority.URGENT, track=Track.PROCUREMENT, confidence=0.98,
                    summary="Procurement tender / contract award notification", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=True,
                    action_description="Review contract award notice and next steps",
                )
            if any(k in full_text for k in ("clarification requested", "request for clarification", "please clarify", "questions regarding your bid", "clarification on your proposal")):
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=SignalCategory.CLARIFICATION_REQUEST,
                    priority=SignalPriority.URGENT, track=Track.PROCUREMENT, confidence=0.96,
                    summary="Procurement clarification request requiring response", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=True,
                    action_description="Prepare and submit requested tender clarifications",
                )
            if any(k in full_text for k in ("proposal received", "bid submitted successfully", "acknowledgement of tender submission", "receipt of bid")):
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=SignalCategory.PROPOSAL_CONFIRMATION,
                    priority=SignalPriority.LOW, track=Track.PROCUREMENT, confidence=0.95,
                    summary="Tender / proposal submission receipt confirmed", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=False,
                )

        # 2. FREELANCE / INDEPENDENT CLIENT SIGNALS
        if any(k in full_text for k in ("freelance", "contract proposal", "consulting proposal", "statement of work", "discovery call")):
            if any(k in full_text for k in ("discovery call", "schedule a call to discuss", "let's have a brief call", "introductory meeting")):
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=SignalCategory.DISCOVERY_CALL_OR_MEETING_REQUEST,
                    priority=SignalPriority.URGENT, track=Track.FREELANCE, confidence=0.96,
                    summary="Client requested discovery call / project discussion", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=True,
                    action_description="Respond to client meeting / discovery call request",
                )
            if any(k in full_text for k in ("shortlisted", "you have been shortlisted", "selected for the next round of evaluation")):
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=SignalCategory.SHORTLIST_OR_INVITATION,
                    priority=SignalPriority.HIGH, track=Track.FREELANCE, confidence=0.95,
                    summary="Proposal shortlisted by client", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=True,
                    action_description="Review shortlist notice and prepare next deliverables",
                )
            if any(k in full_text for k in ("not selected your proposal", "decided to move forward with another consultant", "regret to inform you that your proposal")):
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=SignalCategory.PROPOSAL_REJECTION,
                    priority=SignalPriority.LOW, track=Track.FREELANCE, confidence=0.95,
                    summary="Freelance / client proposal rejected", sender_email=evidence.sender_email,
                    detected_at=detected_at, deadline=deadline, extracted_references=refs,
                    extracted_organization=org, extracted_role_title=role, requires_founder_action=False,
                )

        # 3. HIGH-PRIORITY EMPLOYMENT SIGNALS
        # Offer
        if any(k in full_text for k in ("job offer", "offer of employment", "pleased to offer you the position", "formal offer letter", "congratulations on your offer")):
            return InboundSignal(
                signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                provider_message_id=evidence.provider_message_id, category=SignalCategory.OFFER,
                priority=SignalPriority.URGENT, track=Track.EMPLOYMENT, confidence=0.98,
                summary=f"Formal job offer received for {role or 'role'} at {org or 'company'}",
                sender_email=evidence.sender_email, detected_at=detected_at, deadline=deadline,
                extracted_references=refs, extracted_organization=org, extracted_role_title=role,
                requires_founder_action=True, action_description="Review job offer terms and deadline",
            )

        # Interview Request / Scheduling
        if any(k in full_text for k in (
            "invitation to interview", "schedule an interview", "like to invite you for an interview",
            "would love to speak with you", "schedule a chat", "calendar invite", "select a time for your interview",
            "interview availability", "book a slot", "screening call", "technical interview",
        )):
            return InboundSignal(
                signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                provider_message_id=evidence.provider_message_id, category=SignalCategory.INTERVIEW_REQUEST,
                priority=SignalPriority.URGENT, track=Track.EMPLOYMENT, confidence=0.98,
                summary=f"Interview request from {evidence.sender_name or evidence.sender_email} for {role or 'position'}",
                sender_email=evidence.sender_email, detected_at=detected_at, deadline=deadline,
                extracted_references=refs, extracted_organization=org, extracted_role_title=role,
                requires_founder_action=True, action_description="Select interview time slot or reply to scheduler",
            )

        # Assessment / Take-home Test
        if any(k in full_text for k in ("assessment test", "take-home assignment", "coding challenge", "hackerrank", "codility", "complete the following assessment", "technical assessment")):
            return InboundSignal(
                signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                provider_message_id=evidence.provider_message_id, category=SignalCategory.ASSESSMENT,
                priority=SignalPriority.HIGH, track=Track.EMPLOYMENT, confidence=0.96,
                summary=f"Candidate assessment / test requested by {org or 'company'}",
                sender_email=evidence.sender_email, detected_at=detected_at, deadline=deadline,
                extracted_references=refs, extracted_organization=org, extracted_role_title=role,
                requires_founder_action=True, action_description="Review and complete candidate assessment before deadline",
            )

        # Recruiter Human Outreach / Direct Inquiry
        if any(k in full_text for k in ("came across your profile", "impressed by your background", "reaching out regarding an opportunity", "would you be open to", "let me know if you are interested")):
            # Distinguish direct human recruiter outreach from automated marketing/job alerts
            if not any(k in full_text for k in ("job alerts", "recommended jobs for you", "unsubscribe", "newsletter", "top jobs this week")):
                return InboundSignal(
                    signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                    provider_message_id=evidence.provider_message_id, category=SignalCategory.RECRUITER_OUTREACH,
                    priority=SignalPriority.HIGH, track=Track.EMPLOYMENT, confidence=0.92,
                    summary=f"Direct recruiter outreach from {evidence.sender_name or evidence.sender_email}",
                    sender_email=evidence.sender_email, detected_at=detected_at, deadline=deadline,
                    extracted_references=refs, extracted_organization=org, extracted_role_title=role,
                    requires_founder_action=True, action_description="Review recruiter outreach and respond if interested",
                )

        # Information / Clarification Request
        if any(k in full_text for k in ("please provide your updated", "additional information required", "need a copy of your", "clarify your availability", "please answer the following questions")):
            return InboundSignal(
                signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                provider_message_id=evidence.provider_message_id, category=SignalCategory.INFORMATION_REQUEST,
                priority=SignalPriority.HIGH, track=Track.EMPLOYMENT, confidence=0.90,
                summary="Additional candidate information requested", sender_email=evidence.sender_email,
                detected_at=detected_at, deadline=deadline, extracted_references=refs,
                extracted_organization=org, extracted_role_title=role, requires_founder_action=True,
                action_description="Provide requested candidate details",
            )

        # 4. ROUTINE EMPLOYMENT SIGNALS
        # Rejection
        if any(k in full_text for k in (
            "thank you for your interest, but", "decided to pursue other candidates",
            "not moving forward with your application", "decided not to proceed",
            "regret to inform you", "unfortunately, we will not be moving forward",
            "after careful consideration, we have chosen",
        )):
            return InboundSignal(
                signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                provider_message_id=evidence.provider_message_id, category=SignalCategory.REJECTION,
                priority=SignalPriority.LOW, track=Track.EMPLOYMENT, confidence=0.96,
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
            return InboundSignal(
                signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                provider_message_id=evidence.provider_message_id, category=SignalCategory.APPLICATION_CONFIRMATION,
                priority=SignalPriority.LOW, track=Track.EMPLOYMENT, confidence=0.97,
                summary=f"Application confirmation received for {role or 'role'} at {org or 'company'}",
                sender_email=evidence.sender_email, detected_at=detected_at, deadline=deadline,
                extracted_references=refs, extracted_organization=org, extracted_role_title=role,
                requires_founder_action=False,
            )

        # 5. NOISE & MARKETING
        if any(k in full_text for k in ("unsubscribe", "job alert", "recommended jobs", "newsletter", "weekly digest", "promoted jobs", "sponsored")):
            return InboundSignal(
                signal_id=sig_id, message_content_hash=evidence.message_content_hash,
                provider_message_id=evidence.provider_message_id, category=SignalCategory.MARKETING,
                priority=SignalPriority.NOISE, track=Track.EMPLOYMENT, confidence=0.90,
                summary="Marketing or automated platform notification", sender_email=evidence.sender_email,
                detected_at=detected_at, deadline=None, extracted_references=(),
                extracted_organization="", extracted_role_title="", requires_founder_action=False,
            )

        # 6. UNCLASSIFIED / REVIEW REQUIRED (Fail-Closed toward review)
        return InboundSignal(
            signal_id=sig_id, message_content_hash=evidence.message_content_hash,
            provider_message_id=evidence.provider_message_id, category=SignalCategory.UNCLASSIFIED,
            priority=SignalPriority.MEDIUM, track=Track.EMPLOYMENT, confidence=0.50,
            summary=f"Unclassified inbound message: {evidence.subject}",
            sender_email=evidence.sender_email, detected_at=detected_at, deadline=deadline,
            extracted_references=refs, extracted_organization=org, extracted_role_title=role,
            requires_founder_action=True, action_description="Review unclassified inbound correspondence",
        )
