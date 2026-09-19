"""Validate the FR-007 hard zero-dollar cloud cost/quota envelope.

ADR-0023 is intentionally stricter than "no Founder out-of-pocket spend":
every approved runtime provider must have a declared gross charge of $0.00.
Credits do not count as free and Azure is explicitly excluded.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENVELOPE_PATH = REPO_ROOT / "reports" / "evidence" / "FR-007" / "cloud-cost-quota.json"
APPROVED_PROVIDERS = {"Supabase", "Cloudflare", "GitHub"}


def _number(value: Any, default: float = 0.0) -> float:
    return float(default if value is None else value)


def validate_cost_quota(
    envelope_data: Mapping[str, Any],
    mode: str = "staging",
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(envelope_data, dict):
        return False, ["Root envelope must be a JSON dictionary"]
    if envelope_data.get("brief") != "FR-007":
        errors.append("Invalid or missing brief; expected FR-007")
    if envelope_data.get("architecture_authority") != "ADR-0023":
        errors.append("Cost envelope must name ADR-0023 as architecture authority")

    policy = envelope_data.get("policy")
    services = envelope_data.get("services")
    summary = envelope_data.get("summary")
    if not isinstance(policy, dict):
        errors.append("'policy' must be a dictionary")
        policy = {}
    if not isinstance(services, dict):
        return False, errors + ["'services' must be a dictionary"]
    if not isinstance(summary, dict):
        return False, errors + ["'summary' must be a dictionary"]

    if _number(policy.get("gross_provider_charge_must_equal_usd")) != 0.0:
        errors.append("Gross-provider-charge policy must equal $0.00")
    if _number(policy.get("founder_out_of_pocket_must_equal_usd")) != 0.0:
        errors.append("Founder out-of-pocket policy must equal $0.00")
    if policy.get("student_or_trial_credit_allowed") is not False:
        errors.append("Student/trial credits must be forbidden")
    if policy.get("paid_overage_allowed") is not False:
        errors.append("Paid overage must be forbidden")
    if set(policy.get("approved_providers", [])) != APPROVED_PROVIDERS:
        errors.append("Approved provider set must be exactly Supabase, Cloudflare, GitHub")

    total_gross = 0.0
    total_credit = 0.0
    total_oop = 0.0
    unapproved_paid = 0
    seen_providers: set[str] = set()

    for service_name, service in services.items():
        if not isinstance(service, dict):
            errors.append(f"Service '{service_name}' must be a dictionary")
            continue
        provider = service.get("provider")
        if provider not in APPROVED_PROVIDERS:
            errors.append(f"Unapproved provider '{provider}' on service '{service_name}'")
        else:
            seen_providers.add(provider)

        gross = _number(service.get("gross_provider_charge_usd"))
        credit = _number(service.get("student_credit_absorbed_usd"))
        oop = _number(service.get("net_founder_out_of_pocket_usd"))
        total_gross += gross
        total_credit += credit
        total_oop += oop

        if gross != 0.0:
            errors.append(f"Service '{service_name}' gross provider charge must be $0.00, got ${gross:.2f}")
        if credit != 0.0 or service.get("covered_by_student_credit") is True:
            errors.append(f"Service '{service_name}' may not depend on student/trial credits")
        if oop != 0.0:
            errors.append(f"Service '{service_name}' Founder out-of-pocket must be $0.00, got ${oop:.2f}")
        if service.get("covered_by_permanent_allowance") is not True:
            errors.append(f"Service '{service_name}' must be covered by a permanent/no-charge allowance")
        if service.get("unapproved_paid_resource") is True:
            unapproved_paid += 1
            errors.append(f"Unapproved paid resource flagged on service '{service_name}'")

    missing = APPROVED_PROVIDERS - seen_providers
    if missing:
        errors.append("Missing approved provider coverage: " + ", ".join(sorted(missing)))

    sb = services.get("supabase", {})
    if sb:
        limits = sb.get("limits", {})
        usage = sb.get("projected_usage", {})
        pairs = (
            ("database_storage_mb", 500),
            ("file_storage_mb", 1000),
            ("monthly_egress_mb", 5000),
            ("active_projects", 2),
            ("edge_function_invocations_monthly", 500000),
        )
        for key, fallback in pairs:
            if _number(usage.get(key)) > _number(limits.get(key), fallback):
                errors.append(f"Supabase projected {key} exceeds Free limit")

    cf = services.get("cloudflare", {})
    if cf:
        limits = cf.get("limits", {})
        usage = cf.get("projected_usage", {})
        if _number(usage.get("worker_requests_daily")) > _number(limits.get("worker_requests_daily"), 100000):
            errors.append("Cloudflare projected Worker requests exceed Free daily limit")
        if _number(usage.get("cpu_ms_per_http_request_target")) > _number(limits.get("cpu_ms_per_http_request"), 10):
            errors.append("Cloudflare projected Worker CPU exceeds Free per-request limit")
        if _number(usage.get("cron_triggers")) > _number(limits.get("cron_triggers_per_account"), 5):
            errors.append("Cloudflare projected cron triggers exceed Free limit")

    gha = services.get("github_actions", {})
    if gha:
        limits = gha.get("limits", {})
        usage = gha.get("projected_usage", {})
        if usage.get("repository_visibility") != limits.get(
            "repository_visibility_required_for_unmetered_standard_runner_minutes"
        ):
            errors.append("GitHub zero-dollar runner assumption requires the repository to remain public")
        if usage.get("runner_class") != "standard_ubuntu":
            errors.append("GitHub zero-dollar runtime permits standard Ubuntu runners only")
        if limits.get("larger_runners_allowed") is not False:
            errors.append("GitHub larger runners must be explicitly forbidden")
        max_artifact = _number(usage.get("encrypted_backup_artifact_max_mb"))
        storage = _number(limits.get("pro_artifact_storage_mb"), 1000)
        if max_artifact <= 0 or max_artifact > storage:
            errors.append("Encrypted backup artifact cap must be positive and within included artifact storage")

    if _number(summary.get("total_gross_provider_charge_usd")) != total_gross:
        errors.append("Summary gross provider charge does not match service total")
    if _number(summary.get("total_student_credit_applied_usd")) != total_credit:
        errors.append("Summary student credit does not match service total")
    if _number(summary.get("total_founder_out_of_pocket_usd")) != total_oop:
        errors.append("Summary Founder out-of-pocket does not match service total")
    if summary.get("credit_dependency") is not False:
        errors.append("Summary must declare credit_dependency=false")
    if summary.get("all_within_permanent_free_allowance") is not True:
        errors.append("Summary must declare all_within_permanent_free_allowance=true")
    if int(summary.get("unapproved_paid_resources_count", -1)) != unapproved_paid:
        errors.append("Summary unapproved paid-resource count does not match services")
    if "Azure" not in summary.get("excluded_providers", []):
        errors.append("Summary must explicitly exclude Azure")

    # Staging and production deliberately use the same hard-zero rule.
    if mode not in {"staging", "production"}:
        errors.append(f"Unsupported mode: {mode}")

    return not errors, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=str, default="", help="Path to cloud-cost-quota.json")
    parser.add_argument("--staging", action="store_true", default=False)
    parser.add_argument("--production", action="store_true", default=False)
    args = parser.parse_args()
    mode = "production" if args.production else "staging"
    path = Path(args.file).resolve() if args.file else DEFAULT_ENVELOPE_PATH
    if not path.exists():
        sys.stderr.write(f"Error: Envelope file not found at {path}\n")
        return 1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        sys.stderr.write(f"Error reading JSON from {path}: {exc}\n")
        return 1
    valid, errors = validate_cost_quota(data, mode=mode)
    if not valid:
        sys.stderr.write(f"Cost & Quota Envelope validation FAILED (mode: {mode}):\n")
        for error in errors:
            sys.stderr.write(f"  - {error}\n")
        return 1
    print(f"Cost & Quota Envelope {path.name} is VALID (mode: {mode}). Gross spend: $0.00.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
