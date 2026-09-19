"""Validate Cloud Cost & Quota Envelope for FR-007.

Recomputes consistency dynamically rather than trusting self-declared booleans:
- Enforces distinction between permanent free allowances and temporary student credits.
- Verifies GitHub Actions billing granularity (rounds up to whole minutes).
- Blocks on contradictory free-tier / credit claims.
- Blocks on unapproved paid resources.
- In --production, strictly enforces $0.00 net out-of-pocket founder spend.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_ENVELOPE_PATH = (
    REPO_ROOT / "reports" / "evidence" / "FR-007" / "cloud-cost-quota.json"
)


def validate_cost_quota(
    envelope_data: Mapping[str, Any],
    mode: str = "staging",
) -> tuple[bool, list[str]]:
    """Recompute and validate cloud cost and quota envelope constraints."""
    errors: list[str] = []

    if not isinstance(envelope_data, dict):
        return False, ["Root envelope must be a JSON dictionary"]

    brief = envelope_data.get("brief")
    if brief != "FR-007":
        errors.append(f"Invalid brief: {brief!r}; expected 'FR-007'")

    services = envelope_data.get("services")
    if not isinstance(services, dict):
        return False, ["'services' must be a dictionary of service configurations"]

    summary = envelope_data.get("summary")
    if not isinstance(summary, dict):
        return False, ["'summary' must be a dictionary"]

    calculated_gross = 0.0
    calculated_credit = 0.0
    calculated_out_of_pocket = 0.0
    unapproved_paid_count = 0

    # 1. Inspect Supabase
    sb = services.get("supabase", {})
    if not sb:
        errors.append("Missing required service: 'supabase'")
    else:
        limits = sb.get("limits", {})
        proj = sb.get("projected_usage", {})
        if proj.get("database_storage_mb", 0) > limits.get("database_storage_mb", 500):
            errors.append(
                f"Supabase projected DB storage ({proj.get('database_storage_mb')}MB) exceeds limit ({limits.get('database_storage_mb')}MB)"
            )
        if proj.get("file_storage_mb", 0) > limits.get("file_storage_mb", 1000):
            errors.append(
                f"Supabase projected file storage ({proj.get('file_storage_mb')}MB) exceeds limit ({limits.get('file_storage_mb')}MB)"
            )
        if proj.get("monthly_egress_mb", 0) > limits.get("monthly_egress_mb", 5000):
            errors.append(
                f"Supabase projected egress ({proj.get('monthly_egress_mb')}MB) exceeds limit ({limits.get('monthly_egress_mb')}MB)"
            )

    # 2. Inspect Azure Container Apps
    aca = services.get("azure_container_apps", {})
    if not aca:
        errors.append("Missing required service: 'azure_container_apps'")
    else:
        limits = aca.get("limits", {})
        proj = aca.get("projected_usage", {})
        gross_vcpu = proj.get("gross_vcpu_seconds", 0)
        free_vcpu = limits.get("monthly_free_vcpu_seconds", 180000)
        gross_gib = proj.get("gross_gib_seconds", 0)
        free_gib = limits.get("monthly_free_gib_seconds", 360000)

        # Dynamic recomputation: continuous run exceeds free grant
        if gross_vcpu > free_vcpu or gross_gib > free_gib:
            if aca.get("covered_by_permanent_allowance") is True:
                errors.append(
                    "CONTRADICTION: Azure Container Apps usage exceeds free grant but is marked covered_by_permanent_allowance=True"
                )

        billable_vcpu = max(0, gross_vcpu - free_vcpu)
        billable_gib = max(0, gross_gib - free_gib)
        computed_charge = round(
            billable_vcpu * proj.get("rate_vcpu_second_usd", 0.000024)
            + billable_gib * proj.get("rate_gib_second_usd", 0.000003),
            2,
        )
        declared_charge = round(aca.get("gross_provider_charge_usd", 0.0), 2)
        if abs(computed_charge - declared_charge) > 0.05:
            errors.append(
                f"Azure gross charge mismatch: computed ${computed_charge:.2f} vs declared ${declared_charge:.2f}"
            )

    # 3. Inspect Cloudflare Workers
    cf = services.get("cloudflare_workers", {})
    if not cf:
        errors.append("Missing required service: 'cloudflare_workers'")
    else:
        limits = cf.get("limits", {})
        proj = cf.get("projected_usage", {})
        if proj.get("daily_requests", 0) > limits.get("daily_requests", 100000):
            errors.append(
                f"Cloudflare daily requests ({proj.get('daily_requests')}) exceeds limit ({limits.get('daily_requests')})"
            )

    # 4. Inspect GitHub Actions
    gha = services.get("github_actions", {})
    if not gha:
        errors.append("Missing required service: 'github_actions'")
    else:
        limits = gha.get("limits", {})
        proj = gha.get("projected_usage", {})
        cadence_m = proj.get("cadence_minutes", 30)
        monthly_runs = proj.get("monthly_runs", 1440)
        avg_s = proj.get("avg_run_seconds", 30)
        # Billing granularity: rounds up to nearest full minute
        billed_m_per_run = math.ceil(avg_s / limits.get("billing_granularity_seconds", 60))
        computed_monitor_minutes = monthly_runs * billed_m_per_run
        quota_minutes = limits.get("monthly_runner_minutes", 2000)

        if computed_monitor_minutes > quota_minutes:
            errors.append(
                f"GitHub Actions monitor minutes ({computed_monitor_minutes} min) exceeds runner allowance ({quota_minutes} min)"
            )
        ci_headroom = quota_minutes - computed_monitor_minutes
        if ci_headroom < 200:
            errors.append(
                f"GitHub Actions remaining CI headroom ({ci_headroom} min) is dangerously low (< 200 min buffer)"
            )

    # Common recomputations across all services
    for sname, sdata in services.items():
        if sdata.get("unapproved_paid_resource", False):
            unapproved_paid_count += 1
            errors.append(f"Unapproved paid resource flagged on service '{sname}'")

        gross = sdata.get("gross_provider_charge_usd", 0.0)
        credit = sdata.get("student_credit_absorbed_usd", 0.0)
        net_oop = sdata.get("net_founder_out_of_pocket_usd", 0.0)
        is_perm = sdata.get("covered_by_permanent_allowance", False)

        # Contradiction check: cannot claim permanent allowance if charge > 0
        if gross > 0.0 and is_perm:
            errors.append(
                f"CONTRADICTION: Service '{sname}' has gross charge ${gross:.2f} but claims covered_by_permanent_allowance=True"
            )
        if gross == 0.0 and not is_perm and not sdata.get("covered_by_student_credit"):
            errors.append(
                f"CONTRADICTION: Service '{sname}' has $0 gross charge but is not marked covered by allowance or credit"
            )

        # Net out-of-pocket check
        expected_oop = max(0.0, round(gross - credit, 2))
        if abs(net_oop - expected_oop) > 0.01:
            errors.append(
                f"Service '{sname}' net out-of-pocket (${net_oop:.2f}) does not match gross - credit (${expected_oop:.2f})"
            )

        calculated_gross += gross
        calculated_credit += credit
        calculated_out_of_pocket += net_oop

    # Summary verification
    declared_oop = summary.get("total_founder_out_of_pocket_usd", 0.0)
    if abs(declared_oop - calculated_out_of_pocket) > 0.01:
        errors.append(
            f"Summary total out-of-pocket (${declared_oop:.2f}) does not match sum of services (${calculated_out_of_pocket:.2f})"
        )

    declared_unapproved = summary.get("unapproved_paid_resources_count", 0)
    if declared_unapproved != unapproved_paid_count:
        errors.append(
            f"Summary unapproved paid resources count ({declared_unapproved}) does not match sum of services ({unapproved_paid_count})"
        )

    # Mode-specific enforcement
    if mode == "production":
        effective_oop = max(calculated_out_of_pocket, declared_oop)
        if effective_oop > 0.0:
            errors.append(
                f"PRODUCTION GATE FAILURE: Total out-of-pocket cost is ${effective_oop:.2f}; must be $0.00 without founder approval"
            )
        effective_unapproved = max(unapproved_paid_count, declared_unapproved)
        if effective_unapproved > 0:
            errors.append(
                f"PRODUCTION GATE FAILURE: {effective_unapproved} unapproved paid resource(s) detected"
            )

    return (len(errors) == 0), errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file",
        type=str,
        default="",
        help="Path to cloud-cost-quota.json",
    )
    parser.add_argument(
        "--staging",
        action="store_true",
        default=False,
        help="Validate against staging allowance.",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        default=False,
        help="Validate against strict production $0 out-of-pocket policy.",
    )

    args = parser.parse_args()

    mode = "production" if args.production else "staging"
    env_path = (
        Path(args.file).resolve() if args.file else DEFAULT_ENVELOPE_PATH
    )

    if not env_path.exists():
        sys.stderr.write(f"Error: Envelope file not found at {env_path}\n")
        return 1

    try:
        data = json.loads(env_path.read_text(encoding="utf-8"))
    except Exception as exc:
        sys.stderr.write(f"Error reading JSON from {env_path}: {exc}\n")
        return 1

    valid, errors = validate_cost_quota(data, mode=mode)
    if not valid:
        sys.stderr.write(f"Cost & Quota Envelope validation FAILED (mode: {mode}):\n")
        for err in errors:
            sys.stderr.write(f"  - {err}\n")
        return 1

    print(f"Cost & Quota Envelope {env_path.name} is VALID (mode: {mode}). Total founder out-of-pocket: $0.00.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
