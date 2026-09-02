/**
 * Synthetic fixture data for the mock API layer. Every name, organization,
 * and value here is obviously invented — no real person, employer, or
 * contact detail appears anywhere in this file.
 */
import type {
  ActionHistoryEntry,
  ActionState,
  ConstraintOutcome,
  Decision,
  FeedbackHistoryEntry,
  FeedbackLabel,
  FilterMode,
  OpportunityField,
  QualificationConstraint,
  DimensionScore,
  SourceHealth,
  Track,
  TruthSection,
  TruthValidatorSummary,
} from "@/lib/contract/types"

/** Internal seed shape: the union of everything the list and detail
 * endpoints need, kept in one place per opportunity so the mock store can
 * answer both from a single mutable record. */
export interface SeedOpportunity {
  id: string
  title: string
  organization: string
  source_id: string
  source_url: string
  track: Track
  decision: Decision
  fit_score: number | null
  top_reasons: string[]
  deadline: string | null
  posted_date: string | null
  is_stale: boolean
  action_state: ActionState
  feedback_label: FeedbackLabel | null
  description: string
  reverified_at: string | null
  fields: OpportunityField[]
  constraints: QualificationConstraint[]
  dimension_scores: DimensionScore[]
  strengths: string[]
  gaps: string[]
  unknowns: string[]
  uncertainty_penalty: number
  explanation: string
  policy_version: string
  evaluated_at: string | null
  truth_pack_hash: string | null
  evidence_links: string[]
  action_history: ActionHistoryEntry[]
  feedback_history: FeedbackHistoryEntry[]
  /** claim validator rejects artifact generation for this opportunity, per
   * the mock's fixed synthetic policy (used to exercise the 409 path). */
  artifact_claims_rejected: boolean
}

function constraint(
  name: string,
  outcome: ConstraintOutcome,
  reason: string,
  opts: Partial<QualificationConstraint> = {}
): QualificationConstraint {
  return {
    constraint_name: name,
    outcome,
    reason,
    required_field: opts.required_field ?? null,
    founder_fact: opts.founder_fact ?? null,
    is_hard_failure: opts.is_hard_failure ?? outcome === "FAIL",
    provenance_pointer: opts.provenance_pointer ?? null,
  }
}

function dim(
  dimension: string,
  score: number,
  weight: number,
  rationale: string
): DimensionScore {
  return { dimension, score, weight, weighted_score: score * weight, rationale }
}

export function buildDefaultOpportunities(): SeedOpportunity[] {
  return [
    {
      id: "opp-001",
      title: "Senior Localization Program Manager",
      organization: "Northwind Regional Cooperative (synthetic)",
      source_id: "src-jobboard-alpha",
      source_url: "https://jobs.example.org/postings/opp-001",
      track: "employment",
      decision: "qualified",
      fit_score: 88,
      top_reasons: [
        "5+ years program management matches required experience band",
        "Arabic/English bilingual requirement satisfied",
        "Prior MENA remote-team leadership evidenced",
      ],
      deadline: "2026-09-20",
      posted_date: "2026-08-29",
      is_stale: false,
      action_state: null,
      feedback_label: null,
      description:
        "Synthetic posting: lead a distributed localization program across four MENA markets.",
      reverified_at: "2026-09-01T08:00:00Z",
      fields: [
        {
          field_name: "title",
          value: "Senior Localization Program Manager",
          raw_value: "Sr. Localization Program Manager",
          derivation_type: "normalized",
          raw_pointer: "listing.title",
          rule_id: "title-normalize-v1",
          record_checksum: "sha256:aaaa1111",
        },
        {
          field_name: "deadline",
          value: "2026-09-20",
          raw_value: "Sep 20, 2026",
          derivation_type: "parsed_date",
          raw_pointer: "listing.close_date",
          rule_id: "date-parse-v2",
          record_checksum: "sha256:bbbb2222",
        },
      ],
      constraints: [
        constraint("work_authorization", "PASS", "Founder holds an eligible regional work permit.", {
          founder_fact: "truth.identity.work_authorization",
          provenance_pointer: "truth#identity.work_authorization",
        }),
        constraint("minimum_experience_years", "PASS", "8 years recorded against a 5 year minimum.", {
          required_field: "employment.years_experience",
          founder_fact: "truth.employment[*].duration",
        }),
        constraint("language_requirement", "PASS", "Bilingual Arabic/English evidenced by prior roles.", {
          founder_fact: "truth.skills.languages",
        }),
      ],
      dimension_scores: [
        dim("relevance", 0.92, 0.4, "Core responsibilities closely match recent roles."),
        dim("seniority_fit", 0.86, 0.3, "Level matches; scope slightly larger than prior roles."),
        dim("compensation_alignment", 0.8, 0.3, "Posted band is within founder's stated range."),
      ],
      strengths: ["Direct domain match", "Language requirement fully met"],
      gaps: ["No prior experience with this specific CMS vendor"],
      unknowns: [],
      uncertainty_penalty: 0,
      explanation:
        "High confidence match: every hard constraint passed and dimension scores are consistently strong.",
      policy_version: "policy-2026.3",
      evaluated_at: "2026-09-01T08:05:00Z",
      truth_pack_hash: "sha256:truthpack-mock-0001",
      evidence_links: ["https://jobs.example.org/postings/opp-001"],
      action_history: [],
      feedback_history: [],
      artifact_claims_rejected: false,
    },
    {
      id: "opp-002",
      title: "Field Operations Lead — Emergency Response",
      organization: "Coastal Relief Trust (synthetic)",
      source_id: "src-ngo-board",
      source_url: "https://jobs.example.org/postings/opp-002",
      track: "employment",
      decision: "ineligible",
      fit_score: 12,
      top_reasons: [
        "Requires an active driving license class the founder does not hold",
        "On-site presence required; founder's evidenced location is remote-only",
        "Certification requirement could not be verified from truth pack",
      ],
      deadline: "2026-09-10",
      posted_date: "2026-08-20",
      is_stale: false,
      action_state: "dismissed",
      feedback_label: "eligibility_wrong",
      description:
        "Synthetic posting: on-site emergency logistics coordination role requiring a heavy-vehicle license.",
      reverified_at: "2026-08-31T09:00:00Z",
      fields: [
        {
          field_name: "location_requirement",
          value: "On-site, Coastal Region",
          raw_value: "Must relocate to Coastal Region within 30 days",
          derivation_type: "normalized",
          raw_pointer: "listing.location",
          rule_id: "location-normalize-v1",
          record_checksum: "sha256:cccc3333",
        },
      ],
      constraints: [
        constraint(
          "driving_license_class",
          "FAIL",
          "Posting requires class-C license; truth pack records no driving license.",
          {
            required_field: "identity.driving_license_class",
            founder_fact: null,
            is_hard_failure: true,
            provenance_pointer: "truth#identity.driving_license_class",
          }
        ),
        constraint("location_relocation", "PASS", "Founder's preferences allow relocation for this region.", {
          founder_fact: "truth.preferences.relocation_regions",
        }),
        constraint(
          "field_certification",
          "UNKNOWN",
          "Posting references a field-response certification the truth pack does not confirm or deny.",
          {
            required_field: "certifications.field_response",
            founder_fact: null,
            is_hard_failure: false,
            provenance_pointer: null,
          }
        ),
      ],
      dimension_scores: [
        dim("relevance", 0.35, 0.4, "Some operational overlap but different domain focus."),
        dim("seniority_fit", 0.5, 0.3, "Level roughly matches."),
        dim("compensation_alignment", 0.2, 0.3, "Posted band well below founder's stated minimum."),
      ],
      strengths: ["Operational leadership experience transfers"],
      gaps: ["No driving license on file", "No confirmed field certification"],
      unknowns: ["field_response certification status"],
      uncertainty_penalty: 0.05,
      explanation:
        "Disqualified on a hard constraint (driving license). Certification status is unknown, not failed, and did not by itself decide the outcome.",
      policy_version: "policy-2026.3",
      evaluated_at: "2026-08-31T09:05:00Z",
      truth_pack_hash: "sha256:truthpack-mock-0001",
      evidence_links: ["https://jobs.example.org/postings/opp-002"],
      action_history: [],
      feedback_history: [
        {
          id: "fb-002-1",
          feedback_label: "eligibility_wrong",
          structured_reason: "eligibility_wrong",
          notes: "License requirement seems mis-scraped from a different posting.",
          created_at: "2026-08-31T10:00:00Z",
        },
      ],
      artifact_claims_rejected: true,
    },
    {
      id: "opp-003",
      title: "Independent Grant Writing Contract",
      organization: "Levant Policy Studio (synthetic)",
      source_id: "src-freelance-board",
      source_url: "https://jobs.example.org/postings/opp-003",
      track: "freelance",
      decision: "uncertain",
      fit_score: 55,
      top_reasons: [
        "Scope partially overlaps with prior grant-writing evidence",
        "Engagement length is unconfirmed in the posting",
        "Rate structure could not be matched against truth pack preferences",
      ],
      deadline: "2026-09-25",
      posted_date: "2026-08-28",
      is_stale: false,
      action_state: null,
      feedback_label: null,
      description:
        "Synthetic posting: short-term grant writing engagement, scope and duration not fully specified.",
      reverified_at: "2026-09-01T07:00:00Z",
      fields: [
        {
          field_name: "engagement_length",
          value: null,
          raw_value: "flexible",
          derivation_type: "unparsed",
          raw_pointer: "listing.duration",
          rule_id: null,
          record_checksum: "sha256:dddd4444",
        },
      ],
      constraints: [
        constraint(
          "engagement_length_within_preference",
          "UNKNOWN",
          "Posting does not state a fixed duration; truth pack preference could not be evaluated.",
          { required_field: "preferences.engagement_length" }
        ),
        constraint(
          "rate_meets_minimum",
          "UNKNOWN",
          "Posting has no published rate; truth pack minimum rate could not be compared.",
          { required_field: "preferences.minimum_rate" }
        ),
        constraint("subject_matter_match", "PASS", "Grant writing experience is directly evidenced.", {
          founder_fact: "truth.employment[2].achievements",
        }),
      ],
      dimension_scores: [
        dim("relevance", 0.7, 0.4, "Subject matter matches well."),
        dim("seniority_fit", 0.6, 0.3, "Cannot fully assess without a defined scope."),
        dim("compensation_alignment", 0.3, 0.3, "No rate published; scored conservatively."),
      ],
      strengths: ["Directly relevant grant-writing history"],
      gaps: [],
      unknowns: ["engagement length", "rate"],
      uncertainty_penalty: 0.25,
      explanation:
        "Two soft constraints could not be resolved either way (UNKNOWN, not FAIL). The decision is uncertain rather than qualified or ineligible until the founder or a source update resolves them.",
      policy_version: "policy-2026.3",
      evaluated_at: "2026-09-01T07:05:00Z",
      truth_pack_hash: "sha256:truthpack-mock-0001",
      evidence_links: ["https://jobs.example.org/postings/opp-003"],
      action_history: [],
      feedback_history: [],
      artifact_claims_rejected: false,
    },
    {
      id: "opp-004",
      title: "Data Governance Advisor (Procurement Notice)",
      organization: "Regional Statistics Authority (synthetic)",
      source_id: "src-ted-search",
      source_url: "https://ted.example.org/notices/opp-004",
      track: "procurement",
      decision: null,
      fit_score: null,
      top_reasons: [],
      deadline: "2026-10-05",
      posted_date: "2026-09-02",
      is_stale: false,
      action_state: null,
      feedback_label: null,
      description:
        "Synthetic notice: newly discovered procurement opportunity, not yet evaluated against the truth pack.",
      reverified_at: null,
      fields: [
        {
          field_name: "title",
          value: "Data Governance Advisor (Procurement Notice)",
          raw_value: "DATA GOVERNANCE ADVISOR",
          derivation_type: "normalized",
          raw_pointer: "notice.title",
          rule_id: "title-normalize-v1",
          record_checksum: "sha256:eeee5555",
        },
      ],
      constraints: [],
      dimension_scores: [],
      strengths: [],
      gaps: [],
      unknowns: [],
      uncertainty_penalty: 0,
      explanation: "",
      policy_version: "",
      evaluated_at: null,
      truth_pack_hash: null,
      evidence_links: ["https://ted.example.org/notices/opp-004"],
      action_history: [],
      feedback_history: [],
      artifact_claims_rejected: false,
    },
    {
      id: "opp-005",
      title: "Regional Partnerships Contractor",
      organization: "Desert Bloom Cooperative (synthetic)",
      source_id: "src-jobboard-alpha",
      source_url: "https://jobs.example.org/postings/opp-005",
      track: "contract",
      decision: "qualified",
      fit_score: 71,
      top_reasons: [
        "Partnership development background matches",
        "Posting has not been reverified in 14 days — treat details as provisional",
        "Contract length matches founder's stated preference",
      ],
      deadline: "2026-09-15",
      posted_date: "2026-08-10",
      is_stale: true,
      action_state: null,
      feedback_label: null,
      description:
        "Synthetic posting: six-month partnerships contract. Source has not re-verified this listing recently.",
      reverified_at: "2026-08-18T12:00:00Z",
      fields: [
        {
          field_name: "contract_length",
          value: "6 months",
          raw_value: "6 mo",
          derivation_type: "normalized",
          raw_pointer: "listing.duration",
          rule_id: "duration-normalize-v1",
          record_checksum: "sha256:ffff6666",
        },
      ],
      constraints: [
        constraint("contract_length_within_preference", "PASS", "6 months is within the founder's stated range."),
        constraint("remote_allowed", "PASS", "Posting explicitly allows remote work."),
      ],
      dimension_scores: [
        dim("relevance", 0.75, 0.4, "Solid overlap with partnerships experience."),
        dim("seniority_fit", 0.7, 0.3, "Matches mid-senior scope."),
        dim("compensation_alignment", 0.68, 0.3, "Within range but near the lower bound."),
      ],
      strengths: ["Remote-friendly", "Duration matches preference"],
      gaps: ["Compensation is at the low end of the acceptable range"],
      unknowns: [],
      uncertainty_penalty: 0,
      explanation:
        "Qualifies on all hard constraints. Flagged stale because the source has not reverified this posting in over a week — treat deadline and status as provisional.",
      policy_version: "policy-2026.3",
      evaluated_at: "2026-08-18T12:05:00Z",
      truth_pack_hash: "sha256:truthpack-mock-0001",
      evidence_links: ["https://jobs.example.org/postings/opp-005"],
      action_history: [],
      feedback_history: [],
      artifact_claims_rejected: false,
    },
    {
      id: "opp-006",
      title: "Program Evaluation Lead",
      organization: "Amber Horizon Foundation (synthetic)",
      source_id: "src-ngo-board",
      source_url: "https://jobs.example.org/postings/opp-006",
      track: "employment",
      decision: "qualified",
      fit_score: 90,
      top_reasons: [
        "Directly matches prior program evaluation role",
        "Founder has already applied to this opportunity",
        "Strong compensation alignment",
      ],
      deadline: "2026-09-18",
      posted_date: "2026-08-25",
      is_stale: false,
      action_state: "submitted",
      feedback_label: "good_match",
      description: "Synthetic posting: lead evaluation function for a multi-country program.",
      reverified_at: "2026-08-30T08:00:00Z",
      fields: [
        {
          field_name: "title",
          value: "Program Evaluation Lead",
          raw_value: "Program Evaluation Lead",
          derivation_type: "normalized",
          raw_pointer: "listing.title",
          rule_id: "title-normalize-v1",
          record_checksum: "sha256:1111aaaa",
        },
      ],
      constraints: [
        constraint("minimum_experience_years", "PASS", "10 years recorded against a 6 year minimum."),
        constraint("work_authorization", "PASS", "Founder holds an eligible regional work permit."),
      ],
      dimension_scores: [
        dim("relevance", 0.95, 0.4, "Near-exact match to prior role."),
        dim("seniority_fit", 0.9, 0.3, "Matches evidenced seniority."),
        dim("compensation_alignment", 0.85, 0.3, "Within preferred band."),
      ],
      strengths: ["Direct domain match", "Compensation alignment"],
      gaps: [],
      unknowns: [],
      uncertainty_penalty: 0,
      explanation: "High-confidence match; founder has already marked this applied.",
      policy_version: "policy-2026.3",
      evaluated_at: "2026-08-30T08:05:00Z",
      truth_pack_hash: "sha256:truthpack-mock-0001",
      evidence_links: ["https://jobs.example.org/postings/opp-006"],
      action_history: [
        {
          action_id: "act-006-1",
          action_status: "submitted",
          execution_mode: "dry_run",
          created_at: "2026-08-30T09:00:00Z",
          updated_at: "2026-08-30T09:00:00Z",
          notes: "Founder-attested: applied directly on the organization's site.",
        },
      ],
      feedback_history: [
        {
          id: "fb-006-1",
          feedback_label: "good_match",
          structured_reason: "good_match",
          notes: null,
          created_at: "2026-08-30T09:01:00Z",
        },
      ],
      artifact_claims_rejected: false,
    },
    {
      id: "opp-007",
      title: "Compliance Monitoring Consultant",
      organization: "Tidewater Advisory Group (synthetic)",
      source_id: "src-freelance-board",
      source_url: "https://jobs.example.org/postings/opp-007",
      track: "contract",
      decision: "ineligible",
      fit_score: 30,
      top_reasons: [
        "Requires an in-country professional license the founder does not hold",
        "Founder previously flagged this listing's eligibility as mis-scraped",
      ],
      deadline: "2026-09-05",
      posted_date: "2026-08-15",
      is_stale: false,
      action_state: "dismissed",
      feedback_label: "eligibility_wrong",
      description: "Synthetic posting: compliance monitoring role requiring a specific professional license.",
      reverified_at: "2026-08-29T08:00:00Z",
      fields: [],
      constraints: [
        constraint(
          "professional_license",
          "FAIL",
          "Posting requires an active compliance license; truth pack records none.",
          { required_field: "certifications.compliance_license", is_hard_failure: true }
        ),
      ],
      dimension_scores: [
        dim("relevance", 0.4, 0.4, "Partial subject-matter overlap."),
        dim("seniority_fit", 0.5, 0.3, "Roughly matches."),
        dim("compensation_alignment", 0.4, 0.3, "Below preferred range."),
      ],
      strengths: [],
      gaps: ["No compliance license on file"],
      unknowns: [],
      uncertainty_penalty: 0,
      explanation: "Disqualified on a single hard constraint.",
      policy_version: "policy-2026.3",
      evaluated_at: "2026-08-29T08:05:00Z",
      truth_pack_hash: "sha256:truthpack-mock-0001",
      evidence_links: ["https://jobs.example.org/postings/opp-007"],
      action_history: [],
      feedback_history: [
        {
          id: "fb-007-1",
          feedback_label: "eligibility_wrong",
          structured_reason: "eligibility_wrong",
          notes: null,
          created_at: "2026-08-29T09:00:00Z",
        },
      ],
      artifact_claims_rejected: false,
    },
    {
      id: "opp-008",
      title: "Youth Skills Program Coordinator",
      organization: "Cedar Valley Trust (synthetic)",
      source_id: "src-ngo-board",
      source_url: "https://jobs.example.org/postings/opp-008",
      track: "employment",
      decision: "qualified",
      fit_score: 45,
      top_reasons: [
        "Some overlap with prior youth-program experience",
        "Founder snoozed this opportunity for later review",
        "Compensation below stated preference",
      ],
      deadline: "2026-09-30",
      posted_date: "2026-08-22",
      is_stale: false,
      action_state: "snoozed",
      feedback_label: null,
      description: "Synthetic posting: coordinate a regional youth skills program.",
      reverified_at: "2026-08-27T08:00:00Z",
      fields: [],
      constraints: [
        constraint("minimum_experience_years", "PASS", "4 years recorded against a 3 year minimum."),
      ],
      dimension_scores: [
        dim("relevance", 0.55, 0.4, "Adjacent but not identical domain."),
        dim("seniority_fit", 0.5, 0.3, "Slightly below evidenced seniority."),
        dim("compensation_alignment", 0.3, 0.3, "Below preferred band."),
      ],
      strengths: ["Adjacent domain experience"],
      gaps: ["Compensation below preference"],
      unknowns: [],
      uncertainty_penalty: 0,
      explanation: "Qualifies but scores modestly; founder chose to snooze rather than act now.",
      policy_version: "policy-2026.3",
      evaluated_at: "2026-08-27T08:05:00Z",
      truth_pack_hash: "sha256:truthpack-mock-0001",
      evidence_links: ["https://jobs.example.org/postings/opp-008"],
      action_history: [],
      feedback_history: [],
      artifact_claims_rejected: false,
    },
    {
      id: "opp-009",
      title: "Digital Inclusion Strategy Consultant",
      organization: "Falcon Ridge Institute (synthetic)",
      source_id: "src-freelance-board",
      source_url: "https://jobs.example.org/postings/opp-009",
      track: "freelance",
      decision: "qualified",
      fit_score: 76,
      top_reasons: [
        "Strategy consulting background matches closely",
        "Founder flagged this as a likely duplicate of opp-005",
        "Rate and duration both within preference",
      ],
      deadline: "2026-09-22",
      posted_date: "2026-08-30",
      is_stale: false,
      action_state: null,
      feedback_label: "duplicate_issue",
      description: "Synthetic posting: digital inclusion strategy engagement.",
      reverified_at: "2026-08-31T08:00:00Z",
      fields: [],
      constraints: [
        constraint("rate_meets_minimum", "PASS", "Published rate exceeds the founder's stated minimum."),
      ],
      dimension_scores: [
        dim("relevance", 0.8, 0.4, "Strong strategy-consulting overlap."),
        dim("seniority_fit", 0.75, 0.3, "Matches evidenced seniority."),
        dim("compensation_alignment", 0.72, 0.3, "Comfortably within range."),
      ],
      strengths: ["Rate and scope both align"],
      gaps: [],
      unknowns: [],
      uncertainty_penalty: 0,
      explanation: "Strong match; founder suspects this may duplicate another listing.",
      policy_version: "policy-2026.3",
      evaluated_at: "2026-08-31T08:05:00Z",
      truth_pack_hash: "sha256:truthpack-mock-0001",
      evidence_links: ["https://jobs.example.org/postings/opp-009"],
      action_history: [],
      feedback_history: [
        {
          id: "fb-009-1",
          feedback_label: "duplicate_issue",
          structured_reason: "duplicate_issue",
          notes: "Looks like the same engagement posted under two organizations.",
          created_at: "2026-08-31T09:30:00Z",
        },
      ],
      artifact_claims_rejected: false,
    },
  ]
}

export function buildNoTruthPackOpportunities(): SeedOpportunity[] {
  // Discovery still runs without a truth pack; nothing has been evaluated.
  return buildDefaultOpportunities()
    .slice(0, 3)
    .map((o) => ({
      ...o,
      decision: null,
      fit_score: null,
      top_reasons: [],
      constraints: [],
      dimension_scores: [],
      evaluated_at: null,
      truth_pack_hash: null,
      explanation: "",
      policy_version: "",
    }))
}

export function buildSourcesHealth(scenario: "polled" | "idle"): SourceHealth[] {
  const base: Array<Omit<SourceHealth, "last_poll" | "last_status" | "last_record_count">> = [
    { source_id: "src-jobboard-alpha", name: "Alpha Job Board (synthetic)", category: "employment", read_policy: "allowed" },
    { source_id: "src-ngo-board", name: "NGO Careers Board (synthetic)", category: "employment", read_policy: "allowed" },
    { source_id: "src-freelance-board", name: "Freelance Registry (synthetic)", category: "freelance", read_policy: "allowed" },
    { source_id: "src-ted-search", name: "TED Notice Search (synthetic mirror)", category: "procurement", read_policy: "allowed" },
    { source_id: "src-restricted-portal", name: "Restricted Partner Portal (synthetic)", category: "employment", read_policy: "disabled" },
  ]

  if (scenario === "idle") {
    return base.map((s) => ({
      ...s,
      last_poll: null,
      last_status: null,
      last_record_count: null,
    }))
  }

  return base.map((s, i) => ({
    ...s,
    last_poll: s.read_policy === "disabled" ? null : "2026-09-02T06:00:00Z",
    last_status: s.read_policy === "disabled" ? null : i === 1 ? "parse_empty" : "ok",
    last_record_count: s.read_policy === "disabled" ? null : i === 1 ? 0 : 12 + i * 4,
  }))
}

export function truthValidatorOk(): TruthValidatorSummary {
  return { ok: true, error_count: 0, findings: [] }
}

export function truthSectionsComplete(): TruthSection[] {
  return [
    { section: "identity", present: true, count: 1 },
    { section: "employment", present: true, count: 4 },
    { section: "education", present: true, count: 2 },
    { section: "certifications", present: true, count: 3 },
    { section: "skills", present: true, count: 12 },
    { section: "capability_profile", present: true, count: 1 },
    { section: "preferences", present: true, count: 1 },
    { section: "red_list", present: true, count: 2 },
    { section: "answer_library", present: true, count: 6 },
  ]
}

export function truthSectionsMissing(): TruthSection[] {
  return [
    { section: "identity", present: false, count: 0 },
    { section: "employment", present: false, count: 0 },
    { section: "education", present: false, count: 0 },
    { section: "certifications", present: false, count: 0 },
    { section: "skills", present: false, count: 0 },
    { section: "capability_profile", present: false, count: 0 },
    { section: "preferences", present: false, count: 0 },
    { section: "red_list", present: false, count: 0 },
    { section: "answer_library", present: false, count: 0 },
  ]
}

/**
 * D3 — founder-controlled filters (contract: `reports/evidence/FR-005/
 * d3-contract.md` §3). Named filters, seeded with the exact defaults the
 * Master specified: only `red_lines` and `excluded_industries` hide by
 * default, everything else labels or ranks, and `min_fit_score` /
 * `compensation_floor` start disabled.
 *
 * The mock's per-opportunity match predicates below are a synthetic stand
 * -in for the real API's Python evaluation loop (`api/routes_api.py`,
 * evaluated per the contract doc) — they exist only so the drawer has
 * something true and internally consistent to show against the fixture
 * set, not as a claim about real filter semantics. Each predicate is
 * derived from a real field already on `SeedOpportunity` (never a bare
 * hard-coded id list) so toggling params (e.g. `min_fit_score.threshold`)
 * visibly changes the affected set, the same way it will against the real
 * API.
 */
export interface FounderFilterDefinition {
  filter_id: string
  description: string
  default_enabled: boolean
  default_mode: FilterMode
  default_params: Record<string, unknown>
}

export const FOUNDER_FILTER_DEFINITIONS: FounderFilterDefinition[] = [
  {
    filter_id: "geo_eligibility",
    description:
      "Opportunities that fail the qualifier's geographic eligibility constraint.",
    default_enabled: true,
    default_mode: "label_only",
    default_params: {},
  },
  {
    filter_id: "work_mode_onsite",
    description:
      "Opportunities that fail the qualifier's on-site work-mode constraint.",
    default_enabled: true,
    default_mode: "label_only",
    default_params: {},
  },
  {
    filter_id: "red_lines",
    description: "Opportunities matching a red line in your truth pack.",
    default_enabled: true,
    default_mode: "hide",
    default_params: {},
  },
  {
    filter_id: "excluded_industries",
    description: "Opportunities in an industry your truth pack excludes.",
    default_enabled: true,
    default_mode: "hide",
    default_params: {},
  },
  {
    filter_id: "track_preference",
    description: "Opportunities outside your preferred track order.",
    default_enabled: true,
    default_mode: "rank_only",
    default_params: {},
  },
  {
    filter_id: "target_roles",
    description: "Opportunities that do not match a career target role.",
    default_enabled: true,
    default_mode: "rank_only",
    default_params: {},
  },
  {
    filter_id: "premium_fulltime_onsite",
    description:
      "Full-time, on-site opportunities below your premium compensation threshold.",
    default_enabled: true,
    default_mode: "rank_only",
    default_params: {},
  },
  {
    filter_id: "stale_postings",
    description: "Opportunities not recently reverified by their source.",
    default_enabled: true,
    default_mode: "label_only",
    default_params: {},
  },
  {
    filter_id: "min_fit_score",
    description: "Opportunities below a minimum fit score you set.",
    default_enabled: false,
    default_mode: "hide",
    default_params: { threshold: 50 },
  },
  {
    filter_id: "compensation_floor",
    description: "Opportunities below a compensation floor you set.",
    default_enabled: false,
    default_mode: "rank_only",
    default_params: { monthly_minimum: 50000, currency: "EGP" },
  },
]

function dimensionScore(o: SeedOpportunity, dimension: string): number | null {
  const d = o.dimension_scores.find((d) => d.dimension === dimension)
  return d ? d.score : null
}

/** Returns whether `filterId` currently matches `o`, given the live
 * `params` for that filter (only `min_fit_score.threshold` varies the
 * result today). See the module doc above for what this stands in for. */
export function evaluateFounderFilter(
  filterId: string,
  o: SeedOpportunity,
  params: Record<string, unknown>
): boolean {
  switch (filterId) {
    case "geo_eligibility":
    case "work_mode_onsite":
      return /relocate|on-site/i.test(o.description)
    case "red_lines":
      return o.constraints.some((c) => c.outcome === "FAIL" && c.is_hard_failure)
    case "excluded_industries":
      return o.track === "procurement"
    case "track_preference":
      return o.track !== "employment"
    case "target_roles":
      return o.decision !== "qualified"
    case "premium_fulltime_onsite": {
      const comp = dimensionScore(o, "compensation_alignment")
      return o.track === "employment" && comp !== null && comp < 0.5
    }
    case "compensation_floor": {
      const comp = dimensionScore(o, "compensation_alignment")
      return comp !== null && comp < 0.5
    }
    case "stale_postings":
      return o.is_stale
    case "min_fit_score": {
      const threshold = Number(params.threshold ?? 50)
      return o.fit_score !== null && o.fit_score < threshold
    }
    default:
      return false
  }
}
