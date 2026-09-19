# FR-007 W18 — Antigravity: Cloudflare / Browser / Reliability / Soak Closure Evidence Report

- **Date:** 2026-09-19
- **Branch:** `work/fr007-antigravity-edge-closure`
- **Executor:** Antigravity (Gemini 3.8)
- **Role:** Frontend / Cloud-Edge / Reliability / Observability Executor
- **Governing Architecture:** ADR-0023 (Zero-Dollar Founder Runtime), ADR-0024 (Fixed CV Portfolio Selection), BRIEF-FR-007, AGENTS.md
- **Status:** **IMPLEMENTATION, HARNESS HARDENING, AND LOCAL/PACKAGE GATES COMPLETE; AWAITING OVERSEER STAGING DISPATCH**

---

## 1. Executive Summary

This report completes Antigravity's W18 edge, browser, deployment, observability, reliability, and soak closure batch under ADR-0023 and ADR-0024.

All tasks assigned under `reports/evidence/FR-007/orders/W18-antigravity-edge-closure.md` have been executed:
1. **Cloudflare Deployment Workflow Hardening:** Updated `.github/workflows/fr007-cloudflare-staging-deploy.yml` to support explicit branch/ref checkout, reusable `workflow_call`, account-owned Cloudflare deployment token verification (`/client/v4/accounts/$CF_ACCOUNT/tokens/verify`), and removed stale assumptions of a mandatory paid external API origin. OpenNext builds Next.js 16.3.4 into `.open-next/worker.js` cleanly.
2. **Staging Playwright E2E Suite:** Updated `web/tests/e2e/staging-smoke.spec.ts` to test unauthorized access rejection (redirection to `/login` and HTTP 401 on protected APIs), resilient login supporting both email/password and password-only forms, fixed CV preview/download per ADR-0024 (`cv-final.pdf` inline preview and attachment download with `%PDF` magic bytes), and optional generated artifact access (cover letters).
3. **Reliability & Failure-Isolation Proofs (A-4 through A-8):** Extended `scripts/fr007_reliability_proof.py` and `scripts/test_fr007_reliability_proof.py` to cover A-7 (Poll Now is non-blocking and due-only) and A-8 (schedule and cooldown state survive scheduler/runner restart without all-source restart storms).
4. **Observability & Incident Lifecycle:** Hardened `.github/workflows/fr007-cloud-observability.yml` by binding the protected GitHub environment (`fr007-staging`) and adding fallback variables (`vars.OPOS_STAGING_WEB_URL`). Probes web liveness, API reachability, database connectivity, queue health, scheduler lag, source freshness, and backup heartbeat.
5. **Cost & Quota Envelope Verification:** Enforced ADR-0023 hard zero-dollar invariants ($0.00 gross provider charge, $0.00 Founder out-of-pocket, 0 student credit dependency, Supabase Free + Cloudflare Free + GitHub standard runners only). Both `--staging` and `--production` modes pass cleanly.
6. **Soak Automation:** Verified fail-closed soak summary harness (`fr007_soak_verify.py` and `fetch_soak_artifacts.py`). Refuses to claim 7-day completion without >= 168 hours of consecutive elapsed evidence.
7. **Provider-Exit & Restore Proofs:** Portability and hosted data-plane test suites pass (23/23 tests).

---

## 2. Modified & Created Files

| File | Change Summary |
|------|----------------|
| `.github/workflows/fr007-cloudflare-staging-deploy.yml` | Added `ref` input and `workflow_call` trigger; explicit checkout of target ref; account-owned Cloudflare token verification; optional `OPPORTUNITYOS_API_ORIGIN` for zero-dollar mode; `E2E_FOUNDER_EMAIL` support. |
| `.github/workflows/fr007-cloud-observability.yml` | Bound `environment: fr007-staging` to ensure access to protected secrets; added `vars.OPOS_STAGING_WEB_URL` fallback. |
| `web/tests/e2e/staging-smoke.spec.ts` | Added unauthorized access rejection tests; resilient login supporting email and password; ADR-0024 fixed CV `cv-final.pdf` inline preview and attachment download verification; graceful cover letter checks. |
| `scripts/validate_cloudflare_deployment.py` | Added Worker name check (`opportunityos-web-staging`), token verification endpoint check, and updated origin message validation. |
| `scripts/test_validate_cloudflare_deployment.py` | Optimized test directory copy ignoring node_modules/.next (test speed 1.5s); verified all 5 contract tests. |
| `scripts/fr007_reliability_proof.py` | Extended `SCENARIOS` to include `A7` and `A8`; implemented `execute_a7_poll_now_probe`, `prove_a7`, `execute_a8_schedule_restart_probe`, and `prove_a8`. |
| `scripts/test_fr007_reliability_proof.py` | Added contract tests for A7 and A8; updated `DisposablePostgresReliabilityTests` to assert all five scenarios (A4-A8). |
| `docs/STATE.md` | Regenerated canonical state via `scripts/generate_state.py`. |
| `reports/evidence/FR-007/W18_ANTIGRAVITY_EDGE_CLOSURE.md` | This evidence document. |

---

## 3. Verification Test Matrix

All tests were executed locally and passed with zero defects:

| Test Suite / Command | Scope / Coverage | Result |
|----------------------|------------------|--------|
| `python scripts/validate_cloudflare_deployment.py` | Cloudflare package contract, forbidden resources, same-origin API proxy, relative paths, manual workflow | **PASS** |
| `python -m unittest scripts.test_validate_cloudflare_deployment -v` | Unit tests for Cloudflare deployment contract validator (5 tests) | **PASS** (5/5 in 1.1s) |
| `cd web; npm run lint` | ESLint across all web components, pages, hooks, and tests | **PASS** (0 errors, 0 warnings) |
| `cd web; npx opennextjs-cloudflare build --dangerouslyUseUnsupportedNextVersion` | Next.js 16.3.4 App Router Turbopack production build & Cloudflare Worker bundling | **PASS** (Worker saved in `.open-next/worker.js`) |
| `python -m unittest scripts.test_fr007_reliability_proof -v` | Reliability proof harness contract tests for A4, A5, A6, A7, and A8 (21 tests) | **PASS** (21/21 in 0.46s) |
| `python -m unittest scripts.test_fr007_cloud_monitor -v` | Cloud monitor, HTTP probes, alert sanitization, incident lifecycle, soak snapshot/verify, workflow contracts (69 tests) | **PASS** (69/69 in 4.0s) |
| `python scripts/validate_cloud_cost_quota.py --staging` | ADR-0023 zero-dollar cost/quota validation in staging mode | **PASS** (Gross spend: $0.00) |
| `python scripts/validate_cloud_cost_quota.py --production` | ADR-0023 zero-dollar cost/quota validation in production mode | **PASS** (Gross spend: $0.00) |
| `python scripts/validate_workflow_contracts.py` | Cloud observability workflow contract validation | **PASS** |
| `python -m unittest worker.test_runner worker.test_scheduler worker.test_postgres_queue_durability -v` | Worker runner, scheduler, and durability tests (58 tests) | **PASS** (43 passed, 15 skipped for live DB) |
| `python -m unittest opportunity.test_persistence storage.test_feed_query storage.test_feed_projection_service -v` | Persistence, feed query, and projection service tests (19 tests) | **PASS** (16 passed, 3 skipped for live DB) |
| `python -m unittest scripts.test_live_portability_proof scripts.test_hosted_data_plane_proof -v` | Portability and data plane proof tests (23 tests) | **PASS** (23/23 in 0.88s) |
| `python scripts/check_guard.py --allow-missing-patterns` | Repository and mirror boundary checks | **PASS** |
| `python scripts/check_repository.py` | Repository integrity, UTF-8 encoding, and hygiene checks | **PASS** |

---

## 4. Impact on Acceptance Criteria A-0 through A-17

| Criterion | Description | Status & W18 Evidence |
|-----------|-------------|------------------------|
| **A-0** | Truth Pack Integrity | **PASS** (hash-bound repository Truth Pack verified). |
| **A-1** | Source Parity & Policy | Pre-existing baseline preserved. |
| **A-2** | Opportunity Deduplication & Family Keys | Pre-existing baseline preserved; verified in persistence regression tests. |
| **A-3** | Evaluation & Matching Engine | Preserved; ADR-0024 fixed CV catalog integrated. |
| **A-4** | Feed/Search Usability without Active Workers | **PASS** (proven in `fr007_reliability_proof.py`). |
| **A-5** | Single-Source Failure Isolation | **PASS** (proven in `fr007_reliability_proof.py`). |
| **A-6** | Repeated Polling Idempotency | **PASS** (proven in `fr007_reliability_proof.py`). |
| **A-7** | Poll Now Non-Blocking & Due-Only | **PASS** (implemented and proven in `fr007_reliability_proof.py`). |
| **A-8** | Schedule/Cooldown Survival & No Restart Storm | **PASS** (implemented and proven in `fr007_reliability_proof.py`). |
| **A-9** | Zero-Dollar Runtime Economics | **PASS** ($0.00 gross provider charge enforced by `validate_cloud_cost_quota.py`). |
| **A-10** | External Observability & Probing | **READY FOR HOSTED RUN** (`fr007_cloud_monitor.py` verified across 69 tests). |
| **A-11** | Synthetic Alert & Incident Lifecycle | **READY FOR HOSTED RUN** (GitHub Issue creation, dedup, and resolution verified). |
| **A-12** | Backup & Restore Verification | Pre-existing baseline; restore harness verified in `test_live_portability_proof.py`. |
| **A-13** | Database Migration & RLS Security | Codex owns live migration/RLS (live Supabase at migration `0009_hosted_founder_auth`). |
| **A-14** | Durable Task Queue Durability | Covered by worker queue durability suite. |
| **A-15** | Portability & Provider-Exit Safety | **PASS** (covered by `test_hosted_data_plane_proof.py` and `test_live_portability_proof.py`). |
| **A-16** | Cloudflare Workers Staging Frontend | **READY FOR OVERSEER DISPATCH** (OpenNext builds cleanly, workflow hardened, browser smoke hardened). |
| **A-17** | >= 7-Day Continuous Host-Off Soak | **READY TO START** (`fr007_soak_verify.py` fail-closed verifier ready; waiting for staging deployment). |

---

## 5. Remaining Blockers & Protected Environment Prerequisites

The Antigravity batch has completed all tasks achievable in the non-secret development environment. The following items require protected execution in the GitHub `fr007-staging` environment:

1. **Staging Deployment Execution:**
   - Secrets required: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.
   - Variable: `vars.OPOS_STAGING_WEB_URL`.
2. **Staging Playwright Smoke Run:**
   - Requires live deployed Cloudflare Workers URL and `E2E_FOUNDER_PASSWORD` (and optional `E2E_FOUNDER_EMAIL`).
3. **Soak Duration:**
   - Requires >= 168 hours of real continuous operation post-deployment. Elapsed time is not fabricated.

---

## 6. Exact Overseer Provider Actions

The Overseer can execute staging deployment and validation with the following GitHub Actions dispatches:

### Step 1: Validate Cloudflare Package
```bash
gh workflow run fr007-cloudflare-staging-deploy.yml \
  --ref work/fr007-antigravity-edge-closure \
  -f mode=VALIDATE
```

### Step 2: Deploy to Cloudflare Workers Staging
```bash
gh workflow run fr007-cloudflare-staging-deploy.yml \
  --ref work/fr007-antigravity-edge-closure \
  -f mode=DEPLOY_STAGING \
  -f acknowledge_staging_deployment=true
```

### Step 3: Run Cloud Playwright Staging Smoke
```bash
gh workflow run fr007-cloudflare-staging-deploy.yml \
  --ref work/fr007-antigravity-edge-closure \
  -f mode=SMOKE_STAGING
```

### Step 4: Verify Synthetic Alert & Health Monitoring
```bash
# Synthetic Alert Verification
gh workflow run fr007-cloud-observability.yml \
  --ref work/fr007-antigravity-edge-closure \
  -f mode=TEST_ALERT \
  -f target_env=staging

# Start Routine 30-Minute Monitoring
gh workflow run fr007-cloud-observability.yml \
  --ref work/fr007-antigravity-edge-closure \
  -f mode=MONITOR \
  -f target_env=staging
```

---

*Note: Per AGENTS.md, this report does not self-declare FR-007 closed. Final verification and closure authority remains strictly with the Owner/Overseer.*
