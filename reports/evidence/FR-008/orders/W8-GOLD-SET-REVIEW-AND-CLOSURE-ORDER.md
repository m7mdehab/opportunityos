# Wave 8 order — gold-set review, staging smoke, and closure

Status: ORDERED / NOT READY FOR EXECUTION
Integration base: `e4e03f4` (`work/fr008-incremental-delivery`)
W7.4 source: feature `0d9bcb3`, integration `202b3bc`
W7.4 evidence: `W7.4-DESKTOP-MOBILE-ACCESSIBILITY-REPORT.md`

## Objective

Complete Wave 8 acceptance only when the reviewed Founder employment gold set and a safe Founder review environment are explicitly available. Keep FR-008 marked partial until every closure criterion in the brief is evidenced and the Owner/Overseer issues terminal PASS.

## W8.1 — Reviewed gold set

Use at least 150 real employment jobs from the current corpus. Stratify across the role families, poor matches, work modes, geography/work-authorization clarity, and seniority listed in §11.2. Do not sample only easy cases. Record the Founder/Overseer labels and short rationale required by §11.3; do not invent Founder preferences. Keep review outputs privacy-safe and separate from job content.

## W8.2 — Full corpus and calibration metrics

Evaluate the brief’s §11.4 targets without changing their thresholds:

- 100% precision for hard-exclusion `ineligible` decisions, except a specific Founder-approved residual;
- at least 95% correct geography-feasibility classification;
- at least 90% correct target-family/tier classification;
- at least 90% of `definitely apply` / `likely apply` labels ranked above `probably skip` under Recommended;
- no remote-as-target-role predicate leakage;
- no verified dated employment record reported as absent;
- empirical interpretation for score bands;
- measured, itemized false positives and false negatives.

State sample-size limitations. Fix and retest every deterministic zero-tolerance defect before considering closure. Calibrate weights only against the reviewed labels; preserve before/after metrics and the chosen score-band interpretation.

## W8.3 — Founder review surface

Use the approved staging/review environment to smoke the complete hosted flow and the specific behaviors introduced across FR-008. Record the tested build, environment, and outcomes. Local mock success is not proof of hosted persistence or Founder acceptance. Do not deploy if no safe target is available or if the change would invalidate an active review checkpoint; create a narrower rollout/order if needed.

## W8.4 — Reconciliation and closure

Reconcile the implementation, metrics, regression/performance/security evidence, staging results, Founder feedback, progress report, and the brief’s closure list. Keep all gates visible. Do not write `docs/STATE.md` under this order; that file remains protected by the current operating constraints. Terminal PASS requires the Owner/Overseer decision after the other criteria are evidenced.

## Preconditions and boundaries

1. The user/Founder supplies or explicitly identifies an authorized review source containing the required reviewed labels and real-job sample, outside protected private paths. This order does not authorize opening anything under `private/` or reading Founder profile, CV, or truth-pack data.
2. An approved safe staging environment is available, the W7.4 checkpoint is deployed there when technically possible, and smoke access is authorized.
3. The gold-review harness is exercised against a synthetic fixture first; output is checked for personal data and raw job-content leakage before real labels are evaluated.
4. No corpus-wide backfill, production weight change, schema/migration, or staging deployment occurs unless separately authorized by the applicable brief/order and its safety prerequisites.

If any precondition is missing, record the blocker and stop before real-data evaluation, backfill, or staging smoke. Keep Founder-testable at 0% until a Founder can use the approved review surface. Do not claim terminal PASS from local-only checks.
