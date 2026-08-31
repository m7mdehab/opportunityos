"""Complete Curated synthetic Gold Set of Inbound Message Evidence for Evaluation."""
from inbox.models import InboundMessageEvidence

GOLD_EMPLOYMENT_MESSAGES = (
    # 1. Confirmation
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-emp-001", thread_id="th-emp-001",
        sender_email="no-reply@greenhouse.io", sender_name="Acme Recruiting",
        recipient_email="founder@example.com",
        subject="Thank you for applying to Acme Corp - Senior Architect",
        snippet="We have received your application for the Senior Architect position...",
        body_text="Dear Candidate, thank you for applying to Acme Corp. We have received your application (Req #REQ-ACME-500) for Senior Architect. Our team will review your qualifications.",
        body_html="<p>Dear Candidate, thank you for applying...</p>",
        received_at="2026-08-30T10:00:00Z",
    ),
    # 2. Plain Rejection
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-emp-002", thread_id="th-emp-002",
        sender_email="recruiting@beta.example", sender_name="Beta Labs Talent",
        recipient_email="founder@example.com",
        subject="Update regarding your application at Beta Labs",
        snippet="Thank you for your interest, but we have decided to pursue other candidates...",
        body_text="Dear Candidate, thank you for your interest in Beta Labs. After careful consideration, we have decided not to proceed with your application at this time.",
        body_html="<p>Dear Candidate...</p>",
        received_at="2026-08-30T11:00:00Z",
    ),
    # 3. Recruiter Human Outreach
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-emp-003", thread_id="th-emp-003",
        sender_email="sara.recruiter@gamma.example", sender_name="Sara Jenkins",
        recipient_email="founder@example.com",
        subject="Exciting Opportunity at Gamma Systems - Lead Data Architect",
        snippet="I came across your profile and was very impressed by your background...",
        body_text="Hi there! I came across your profile and was very impressed by your background. I am reaching out regarding an opportunity for a Lead Data Architect at Gamma Systems. Would you be open to a brief conversation this week?",
        body_html="<p>Hi there...</p>",
        received_at="2026-08-30T12:00:00Z",
    ),
    # 4. Interview Request
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-emp-004", thread_id="th-emp-004",
        sender_email="scheduler@delta.example", sender_name="Delta Talent Operations",
        recipient_email="founder@example.com",
        subject="Invitation to Interview: Delta Corp - Staff Engineer",
        snippet="We would love to speak with you! Please schedule an interview...",
        body_text="Hello! We would love to speak with you regarding the Staff Engineer role (Req #REQ-DELTA-101). Please select a time for your interview using the scheduler link by September 5.",
        body_html="<p>Hello...</p>",
        received_at="2026-08-30T13:00:00Z",
    ),
    # 5. Interview Reschedule
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-emp-005", thread_id="th-emp-005",
        sender_email="scheduler@delta.example", sender_name="Delta Talent Operations",
        recipient_email="founder@example.com",
        subject="Rescheduling your interview: Delta Corp - Staff Engineer",
        snippet="We need to reschedule our interview to a new time...",
        body_text="Hi Candidate, we need to reschedule our interview for the Staff Engineer role (Req #REQ-DELTA-101). Please book a slot for next week.",
        body_html="<p>Hi Candidate...</p>",
        received_at="2026-08-30T13:30:00Z",
    ),
    # 6. Assessment with Deadline
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-emp-006", thread_id="th-emp-006",
        sender_email="evaluations@epsilon.example", sender_name="Epsilon Engineering",
        recipient_email="founder@example.com",
        subject="Technical Assessment for Epsilon - Principal Architect",
        snippet="Please complete the following assessment within 5 days...",
        body_text="Dear Candidate, as the next step in our interview process for Principal Architect, please complete the following assessment test on Hackerrank. Complete by September 8.",
        body_html="<p>Dear Candidate...</p>",
        received_at="2026-08-30T14:00:00Z",
    ),
    # 7. Information Request
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-emp-007", thread_id="th-emp-007",
        sender_email="hr@theta.example", sender_name="Theta HR",
        recipient_email="founder@example.com",
        subject="Additional Information Required - Theta Labs",
        snippet="Please clarify your availability and notice period...",
        body_text="Dear Candidate, please provide your updated portfolio and clarify your availability and notice period for our review.",
        body_html="<p>Dear Candidate...</p>",
        received_at="2026-08-30T14:30:00Z",
    ),
    # 8. Offer
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-emp-008", thread_id="th-emp-008",
        sender_email="vp.talent@zeta.example", sender_name="Zeta Talent",
        recipient_email="founder@example.com",
        subject="Offer of Employment - Zeta Global - Chief Architect",
        snippet="We are pleased to offer you the position of Chief Architect...",
        body_text="Dear Founder, we are pleased to offer you the position of Chief Architect at Zeta Global. Please find attached your formal offer letter. Please review and sign by September 10.",
        body_html="<p>Dear Founder...</p>",
        received_at="2026-08-30T15:00:00Z",
    ),
    # 9. Recruiter Marketing Disguised as Outreach (Noise)
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-emp-009", thread_id="th-emp-009",
        sender_email="marketing@recruiterhub.example", sender_name="Recruiter Hub Digest",
        recipient_email="founder@example.com",
        subject="I came across your profile - Top jobs this week newsletter",
        snippet="Check out our weekly digest of recommended jobs...",
        body_text="Hi there! I came across your profile and wanted to share our weekly digest of recommended jobs. Click unsubscribe to manage preferences.",
        body_html="<p>Weekly digest...</p>",
        received_at="2026-08-30T15:30:00Z",
    ),
    # 10. Automated Job Recommendations (Noise)
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-emp-010", thread_id="th-emp-010",
        sender_email="alerts@jobboard.example", sender_name="Job Board Alerts",
        recipient_email="founder@example.com",
        subject="New Job Alert: 10 jobs matching your preferences",
        snippet="Here are new recommended jobs for you...",
        body_text="Job Alert: 10 new positions match your search. Unsubscribe anytime.",
        body_html="<p>Job alerts...</p>",
        received_at="2026-08-30T15:45:00Z",
    ),
)

GOLD_INDEPENDENT_MESSAGES = (
    # 1. Proposal Confirmation
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-ind-001", thread_id="th-ind-001",
        sender_email="tenders@ted.europa.eu", sender_name="EU eTendering",
        recipient_email="founder@example.com",
        subject="Acknowledgement of tender submission - Notice TED-2026-00987",
        snippet="Your tender submission has been successfully received...",
        body_text="Official confirmation: Bid submitted successfully for procurement notice TED-2026-00987 (Data Infrastructure Framework).",
        body_html="<p>Official confirmation...</p>",
        received_at="2026-08-30T16:00:00Z",
    ),
    # 2. Genuine Client / Buyer Response
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-ind-002", thread_id="th-ind-002",
        sender_email="buyer@enterprise.example", sender_name="Enterprise Buyer",
        recipient_email="founder@example.com",
        subject="Client feedback regarding your proposal for Cloud Modernization",
        snippet="We reviewed your consulting proposal and have feedback...",
        body_text="Dear Consultant, we reviewed your proposal for Cloud Modernization and would like to discuss technical scope and pricing details.",
        body_html="<p>Dear Consultant...</p>",
        received_at="2026-08-30T16:30:00Z",
    ),
    # 3. Clarification with Deadline
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-ind-003", thread_id="th-ind-003",
        sender_email="procurement@un.example", sender_name="UN Procurement Division",
        recipient_email="founder@example.com",
        subject="Clarification requested on RFP #UNGM-9876",
        snippet="Please provide clarifications on your technical proposal...",
        body_text="Dear Bidder, questions regarding your bid on RFP UNGM-9876 have been raised by the evaluation committee. Please submit clarification on your proposal by September 6.",
        body_html="<p>Dear Bidder...</p>",
        received_at="2026-08-30T17:00:00Z",
    ),
    # 4. Shortlist / Invitation
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-ind-004", thread_id="th-ind-004",
        sender_email="tenders@gov.example", sender_name="Gov Tender Board",
        recipient_email="founder@example.com",
        subject="You have been shortlisted for Tender SOW-440",
        snippet="Your proposal has been shortlisted for the next round...",
        body_text="Official Notice: You have been shortlisted for the next round of evaluation on Tender SOW-440. Next stage briefing on September 12.",
        body_html="<p>Official Notice...</p>",
        received_at="2026-08-30T17:30:00Z",
    ),
    # 5. Discovery Call Request
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-ind-005", thread_id="th-ind-005",
        sender_email="client@clientcorp.example", sender_name="Client Executive",
        recipient_email="founder@example.com",
        subject="Discovery call regarding Data Engineering SOW",
        snippet="Let's schedule a call to discuss the project timeline...",
        body_text="Hi, we reviewed your consulting proposal for the Data Engineering SOW. Let's have a brief discovery call to discuss terms and kickoff dates this Thursday.",
        body_html="<p>Hi...</p>",
        received_at="2026-08-30T18:00:00Z",
    ),
    # 6. Proposal Rejection
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-ind-006", thread_id="th-ind-006",
        sender_email="eval@worldbank.example", sender_name="World Bank Tenders",
        recipient_email="founder@example.com",
        subject="Proposal evaluation outcome for RFP WB-552",
        snippet="Regret to inform you that your proposal was not selected...",
        body_text="Dear Bidder, we regret to inform you that your proposal for RFP WB-552 was not selected for contract award as another consultant scored higher.",
        body_html="<p>Dear Bidder...</p>",
        received_at="2026-08-30T18:30:00Z",
    ),
    # 7. Award / Win
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-ind-007", thread_id="th-ind-007",
        sender_email="procurement@eu.example", sender_name="EU Contracting Authority",
        recipient_email="founder@example.com",
        subject="Notice of Award Decision - Tender TED-2026-00987",
        snippet="We are pleased to award the contract to your organization...",
        body_text="Official Notice: We are pleased to award the framework contract for notice TED-2026-00987 to your entity following technical and financial evaluation.",
        body_html="<p>Official Notice...</p>",
        received_at="2026-08-30T19:00:00Z",
    ),
    # 8. Contract Progress Signal
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-ind-008", thread_id="th-ind-008",
        sender_email="pm@partnercorp.example", sender_name="Partner Corp PM",
        recipient_email="founder@example.com",
        subject="Contract progress: Milestone 1 deliverable accepted",
        snippet="Milestone 1 has been approved and SOW is updated...",
        body_text="Hi Founder, Milestone 1 deliverable accepted for our Data Engineering project. Contract progress recorded and payment initiated.",
        body_html="<p>Hi Founder...</p>",
        received_at="2026-08-30T19:30:00Z",
    ),
    # 9. Platform Marketing (Noise)
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-ind-009", thread_id="th-ind-009",
        sender_email="promo@freelanceplatform.example", sender_name="Freelance Promo",
        recipient_email="founder@example.com",
        subject="Promoted bids and premium features available now",
        snippet="Upgrade your account to get more bids...",
        body_text="Get 50% off premium freelance bids this week! Unsubscribe anytime.",
        body_html="<p>Promo...</p>",
        received_at="2026-08-30T20:00:00Z",
    ),
    # 10. Generic Platform Notification (Noise)
    InboundMessageEvidence(
        provider="gmail", provider_message_id="msg-ind-010", thread_id="th-ind-010",
        sender_email="system@portal.example", sender_name="Portal Admin",
        recipient_email="founder@example.com",
        subject="Automated platform notice: Scheduled system maintenance",
        snippet="Our portal will undergo scheduled maintenance...",
        body_text="Automated platform notice: Scheduled maintenance on Sunday from 02:00 to 04:00 UTC. No action required.",
        body_html="<p>Notice...</p>",
        received_at="2026-08-30T20:15:00Z",
    ),
)
