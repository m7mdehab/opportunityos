# FR-007 Cloud Cost & Quota Control Plane

This document establishes the authoritative cost and quota envelope for OpportunityOS under BRIEF-FR-007.

In accordance with product principles and the Founder Acceptance Contract (§5, A-17):
1. **Zero Silent Spend**: No paid resources may be provisioned or configured without explicit written authorization from Mohammed.
2. **Quota Transparency**: All infrastructure choices must be backed by documented first-party tier limits and measured consumption estimates.
3. **Automated Verification**: Resource envelopes are tracked in machine-readable JSON (`reports/evidence/FR-007/cloud-cost-quota.json`) and validated deterministically via `scripts/validate_cloud_cost_quota.py`.

---

## 1. Service Breakdown & First-Party Quotas

| Service / Provider | Tier & Pricing Model | Quota / Hard Limits | Projected OPOS Consumption | Monthly Out-of-Pocket | Inactivity / Defense |
|---|---|---|---|---|---|
| **Supabase** (PostgreSQL, Auth, Storage) | Free Tier (Permanent Free Allowance) | - 500 MB Database storage<br>- 1 GB File storage<br>- 5 GB Monthly egress<br>- 2 Active projects<br>- Pauses after 7 days inactivity | - DB storage: ~45 MB<br>- File storage: ~120 MB<br>- Monthly egress: ~850 MB<br>- 1 Project active | **$0.00** | Probed every 30 minutes by external cloud monitor, eliminating inactivity pauses. |
| **Azure Container Apps** (API & Worker Engine) | Consumption Plan (Temporary Student Credit) | - 180,000 vCPU-seconds free/mo<br>- 360,000 GiB-seconds free/mo<br>- 2M HTTP requests free/mo<br>- $100 annual student credit buffer | - Allocation: 0.25 vCPU, 0.5 GiB<br>- Continuous runtime: 2,592,000 s/mo<br>- Billable vCPU-s: 468,000 ($11.23)<br>- Billable GiB-s: 936,000 ($2.81)<br>- Total Gross: $14.04/mo | **$0.00** (Absorbed by $100 annual student credit; NOT permanent free tier) | ACA scales to 1 min-instance for predictable polling and background processing. |
| **Cloudflare Workers** (Founder Alpha Web / Edge) | Workers Free Plan (Permanent Free Allowance) | - 100,000 Requests/day<br>- 10 ms CPU time per request<br>- 100 Worker scripts | - ~1,500 Requests/day<br>- ~3.5 ms CPU time/request<br>- 2 Worker routes | **$0.00** | Global edge CDN and serverless runtime; zero idle compute cost. |
| **GitHub Actions** (CI/CD & Observability) | Free Plan (Private Repo Allocation) | - 2,000 Linux runner minutes/mo<br>- Billed in whole minutes (rounded up) | - 30-min external monitor: 1,440 runs/mo<br>- Runner class: `ubuntu-slim`<br>- 1 billed min/run: 1,440 billed min/mo<br>- Remaining CI headroom: 560 min/mo | **$0.00** | 30-min cadence preserves 560 free minutes for PR and main CI. |

---

## 2. ACA Compute Sizing & Economics

Azure Container Apps Consumption pricing charges:
- **vCPU-seconds**: $0.000024 per vCPU-second above the 180,000 s free grant.
- **Memory GiB-seconds**: $0.000003 per GiB-second above the 360,000 s free grant.

For a continuous, single-instance deployment running 24x7 (30 days = 720 hours = 2,592,000 seconds) at minimal footprint (0.25 vCPU, 0.5 GiB RAM):
1. **vCPU Usage**:
   - Total vCPU-seconds: $2,592,000 \times 0.25 = 648,000\text{ s}$
   - Free grant deduction: $-180,000\text{ s}$
   - Net billable vCPU-seconds: $468,000\text{ s}$
   - vCPU Cost: $468,000 \times \$0.000024 = \$11.232$

2. **Memory Usage**:
   - Total GiB-seconds: $2,592,000 \times 0.5 = 1,296,000\text{ s}$
   - Free grant deduction: $-360,000\text{ s}$
   - Net billable GiB-seconds: $936,000\text{ s}$
   - Memory Cost: $936,000 \times \$0.000003 = \$2.808$

3. **Total Monthly Gross Cost**:
   $$\$11.232 + \$2.808 = \$14.04\text{ / month}$$

This gross charge ($14.04/month) is absorbed by the Founder's Azure for Students credit ($100/year grant). It is explicitly classified as a **temporary student credit**, not a permanent free tier allowance. Net out-of-pocket expenditure is **$0.00**.

---

## 3. Quota Defenses & Invariants

1. **Supabase Inactivity Pause Defense**:
   Supabase free tier projects pause after 7 consecutive days of inactivity. Our external monitor (`scripts/fr007_cloud_monitor.py`) runs every 30 minutes from GitHub Actions, querying public `/api/auth/me` and database queue status, ensuring the instance remains active without synthetic manual intervention.

2. **Actions Runner Billing Granularity & Headroom**:
   GitHub Actions bills job execution rounded up to the nearest whole minute. A 30-second job consumes 1 full billed minute. At a 15-minute cadence, 2,880 runs would consume 2,880 billed minutes, exceeding the 2,000-minute free allocation. By setting the external monitor cadence to **30 minutes** (`*/30 * * * *`), monthly monitor consumption is exactly 1,440 billed minutes, leaving **560 billed minutes** of safety buffer for regular repository PR checks, guard scans, and main branch builds.

3. **Production Validation Gate**:
   `scripts/validate_cloud_cost_quota.py` dynamically recomputes all figures and enforces consistency in CI:
   - In `--staging` mode, it validates that all declared services remain within documented free tier or student credit limits.
   - In `--production` mode, it strictly blocks on any unapproved paid resource or out-of-pocket cost > $0.00.

---

## 4. Exit and Portability Guarantee (A-15)

The chosen architecture maintains strict provider neutrality:
- Database: Standard PostgreSQL 16 schemas, migrations via Alembic, standard connection strings. Compatible with AWS RDS, Neon, DigitalOcean, or bare-metal PostgreSQL.
- Object Storage: Standard S3-compatible API or Supabase Storage abstraction.
- Web & API Containers: Standard Dockerfiles, deployable to AWS ECS, Google Cloud Run, Fly.io, or any Kubernetes cluster.
- Exit requires zero changes to core opportunity ingestion, scoring, or matching logic.
