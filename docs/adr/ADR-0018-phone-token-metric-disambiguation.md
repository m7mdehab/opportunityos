# ADR-0018 — Phone Token Metric Disambiguation in Claim Validator

- **Status:** accepted
- **Date:** 2026-09-07
- **Phase:** BRIEF-FR-006
- **Supersedes:** none
- **Superseded by:** none

## Context

In `truth/validator.py`, `_parse_structured_metrics_with_context` extracts numeric and quantified tokens from text to verify that every numeric claim is backed by an exact verified `MetricAssertion`.

However, the metric regular expression `(?<![\w-])(?:(?P<curr>[$€£])\s*)?(?P<val>\d+(?:[.,]\d+)?)...` parsed leading country codes in international phone numbers (e.g., leading country code `+20` in contact telephone numbers) as a numeric count metric (`20 count`). Because identity contact details do not carry metric assertions, `ClaimValidator._validate_metric_provenance` failed with:
`"claim metric '20 count' lacks an exact verified metric provenance node"`.

As an emergency workaround in BRIEF-FR-006 D1, `matching/document_model.py` defensively omitted the `identity.phone` field from compiled artifacts whenever it matched `_LEADING_METRIC_RE`, causing the founder's phone number to be systematically dropped from every generated CV and document.

## Decision

1. Update `truth/validator.py::_parse_structured_metrics_with_context` to recognize phone-shaped tokens (`\+?\d[\d\s\-\.\(\)]{5,}\d\b` with at least 7 digits) when `unit == "count"`, and excuse digit runs within them from being treated as quantified metrics.
2. Update `matching/document_model.py` so that `identity.phone` is no longer omitted from compiled identity blocks when it represents a valid phone number.
3. Add regression unit tests asserting that international phone formats are not parsed as metrics, while genuine count metrics (e.g., `team of 20`, `20 clients`, `increased by 20%`) remain strictly validated.

## Consequences

- **Positive:** International phone numbers in `identity.phone` are verified cleanly and included in generated CVs without being dropped.
- **Negative:** None; phone tokens require at least 7 digits and cannot have metric units (%, USD, hours, etc.), preventing metric circumvention.
- **Security & Truth Invariant:** Preserves fail-closed verification: genuine metrics cannot masquerade as phone numbers.

## Alternatives considered

- **Ad-hoc phone exemption list:** Hardcoding specific prefixes (`+20`, `+1`). Rejected because it fails for other country codes.
- **Requiring MetricAssertion for phone numbers:** Semantically incorrect; a phone number is contact metadata, not a quantified achievement.

## Required tests and rollback

- Tests in `truth/test_validator.py` and `matching/test_compiler.py`.
- Reversal: Revert changes to `truth/validator.py` and `matching/document_model.py`.
