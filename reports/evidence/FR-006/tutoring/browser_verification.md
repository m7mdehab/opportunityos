# Tutoring Founder Lane — Browser Walkthrough & Verification Evidence

## Scope
Verification of the Online Tutoring Founder Acquisition Lane in the local Founder Web Alpha dashboard.

## Verified Properties & Walkthrough Steps

1. **Dedicated Tutoring Acquisition Surface:**
   - URL: `http://localhost:3000/`
   - Header action button: `Tutoring Lane` toggles between the standard opportunity feed and the dedicated tutoring surface.
   - Header badge: `Track: Online Tutoring & Technical Mentorship — Founder Acquisition Lane`.

2. **Catalogued Platform Applications (6):**
   - Preply (`manual:tutoring:preply`) — Acquisition type: `platform_application`
   - Superprof (`manual:tutoring:superprof`) — Acquisition type: `platform_application`
   - Wyzant (`manual:tutoring:wyzant`) — Acquisition type: `platform_application`
   - Tutor.com (`manual:tutoring:tutor_com`) — Acquisition type: `platform_application`
   - Chegg Tutors (`manual:tutoring:chegg`) — Acquisition type: `platform_application`
   - Cambly (`manual:tutoring:cambly`) — Acquisition type: `platform_application`

3. **Status Workflow & Persistence:**
   - 6 distinct workflow statuses supported:
     * `not_started` (Default)
     * `preparing_profile`
     * `ready_to_apply`
     * `applied`
     * `approved`
     * `rejected_unavailable`
   - Status updates persist to backend `FounderFilterSettingRecord` via `PUT /api/tutoring/platforms/{platform_id}`.
   - Verified state change: Preply transitioned from `not_started` to `preparing_profile`. Metric counters in the top pipeline overview updated dynamically.

4. **Readiness Checklist:**
   - Platform cards display 5 readiness prerequisites:
     1. Founder profile photo and bio drafted
     2. Subject/skill areas selected
     3. Identity verification documents ready (platform-specific)
     4. Availability calendar defined
     5. Introductory/demo video recorded (where required)
   - Toggling checklist items immediately persists state and updates the dynamic `Next Action` banner (e.g. `Complete remaining readiness items (2/5 done)`).

5. **Truth-Locked Profile Bio & Skills Surface:**
   - Modal trigger: `View Truth-Locked Profile Bio & Skills`
   - Grounded in verified Truth Graph nodes only (no fabricated claims):
     * Approved Summaries: verified career summary with evidence backing.
     * Technical Skills: 38 verified skills (Python, Data Engineering, PyTorch, Distributed Systems, etc.).
     * Languages: verified native/bilingual proficiencies.
     * Evidence backing: 4 verifiable primary source citations.

6. **Durable Screenshot Reference:**
   - `reports/evidence/FR-006/screenshots/d8-tutoring-dashboard.png`
