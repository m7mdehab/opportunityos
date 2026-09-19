"""Static, credential-free validator for the FR-007 Cloudflare Workers staging package."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_FOUNDATIONAL = (
    "r2_buckets",
    "kv_namespaces",
    "d1_databases",
    "vectorize",
    "hyperdrive",
    "queues",
    "analytics_engine_datasets",
)
FORBIDDEN_NETWORK_OPS = (
    "custom_domains",
    "routes",
    "zone_id",
    "zone_name",
    "dns",
    "cutover",
)


def validate_cloudflare_package(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    web_dir = root / "web"
    workflows_dir = root / ".github" / "workflows"

    # 1. Check open-next.config.ts and wrangler.jsonc exist
    open_next_config = web_dir / "open-next.config.ts"
    if not open_next_config.is_file():
        errors.append("missing open-next.config.ts")
    else:
        text = open_next_config.read_text(encoding="utf-8")
        if "r2IncrementalCache" in text:
            errors.append("paid R2 cache dependency must not be enabled in open-next.config.ts")

    wrangler_file = web_dir / "wrangler.jsonc"
    if not wrangler_file.is_file():
        errors.append("missing web/wrangler.jsonc")
    else:
        w_text = wrangler_file.read_text(encoding="utf-8")
        for token in FORBIDDEN_FOUNDATIONAL:
            if f'"{token}"' in w_text or f"'{token}'" in w_text:
                errors.append(f"forbidden foundational Cloudflare resource in wrangler.jsonc: {token}")
        for token in FORBIDDEN_NETWORK_OPS:
            if f'"{token}"' in w_text or f"'{token}'" in w_text:
                errors.append(f"production DNS or domain cutover forbidden in wrangler.jsonc: {token}")
        if '"OPPORTUNITYOS_CLOUD_EDGE"' not in w_text or '"1"' not in w_text:
            errors.append("wrangler.jsonc must mark the deployed runtime as OPPORTUNITYOS_CLOUD_EDGE=1")
        if '"opportunityos-web-staging"' not in w_text:
            errors.append("wrangler.jsonc must target Worker name opportunityos-web-staging")

    # 2. Check same-origin /api proxy route handler exists
    api_proxy_route = web_dir / "app" / "api" / "[...path]" / "route.ts"
    if not api_proxy_route.is_file():
        errors.append("missing same-origin API proxy handler at web/app/api/[...path]/route.ts")
    else:
        proxy_text = api_proxy_route.read_text(encoding="utf-8")
        if "OPPORTUNITYOS_API_ORIGIN" not in proxy_text:
            errors.append("proxy route handler must reference OPPORTUNITYOS_API_ORIGIN")
        if "parsed.protocol !== \"https:\"" not in proxy_text:
            errors.append("proxy route handler must enforce parsed HTTPS upstream origin")
        if 'OPPORTUNITYOS_CLOUD_EDGE === "1"' not in proxy_text:
            errors.append("proxy route handler must distinguish cloud edge from local development")
        if "OPPORTUNITYOS_API_ORIGIN is required on the cloud edge" in proxy_text:
            errors.append("false-green legacy error detected: cloud edge must not require external API origin")
        if "NEXT_PUBLIC_SUPABASE_URL" not in proxy_text and "SUPABASE_URL" not in proxy_text:
            errors.append("proxy route handler must support Supabase-backed request path")
        if "handleSupabaseNativeRequest" not in proxy_text:
            errors.append("proxy route handler must provide functional Supabase-native request routing")
        if "localhost" not in proxy_text:
            errors.append("local-development API fallback contract is missing")
        if "getSetCookie" not in proxy_text:
            errors.append("proxy must preserve multiple Set-Cookie response headers")

    # 3. Check browser client code uses relative /api routes, never hardcoded localhost/origin
    client_ts = web_dir / "lib" / "api" / "client.ts"
    if not client_ts.is_file():
        errors.append("missing web/lib/api/client.ts")
    else:
        client_text = client_ts.read_text(encoding="utf-8")
        if "http://localhost" in client_text or "https://" in client_text:
            errors.append("browser client.ts must use relative /api paths, never hardcoded absolute origin")

    # 4. Check Playwright staging configuration exists and satisfies requirements
    staging_pw_config = web_dir / "playwright.staging.config.ts"
    if not staging_pw_config.is_file():
        errors.append("missing web/playwright.staging.config.ts")
    else:
        pw_text = staging_pw_config.read_text(encoding="utf-8")
        if "OPOS_STAGING_WEB_URL" not in pw_text:
            errors.append("playwright.staging.config.ts must accept OPOS_STAGING_WEB_URL")
        if "E2E_FOUNDER_PASSWORD" not in pw_text:
            errors.append("playwright.staging.config.ts must accept E2E_FOUNDER_PASSWORD")
        if "webServer:" in pw_text or "webServer :" in pw_text:
            errors.append("playwright.staging.config.ts must not define a local webServer")
        if "Mobile 390px" not in pw_text and "390" not in pw_text:
            errors.append("playwright.staging.config.ts must include a 390px mobile project")
        if "Desktop Chrome" not in pw_text:
            errors.append("playwright.staging.config.ts must include Desktop Chrome")

    # 5. Check staging workflow
    workflow_file = workflows_dir / "fr007-cloudflare-staging-deploy.yml"
    if not workflow_file.is_file():
        errors.append("missing .github/workflows/fr007-cloudflare-staging-deploy.yml")
    else:
        wf_text = workflow_file.read_text(encoding="utf-8")
        if "workflow_dispatch:" not in wf_text:
            errors.append("staging workflow must provide workflow_dispatch")
        for trigger in ("push:", "pull_request:", "schedule:", "workflow_run:", "repository_dispatch:"):
            if re.search(rf"^\s*{re.escape(trigger)}", wf_text, re.MULTILINE):
                errors.append(f"automatic trigger forbidden in staging workflow: {trigger}")
        if "environment: fr007-staging" not in wf_text:
            errors.append("staging workflow must target protected environment fr007-staging")
        if "VALIDATE" not in wf_text or "DEPLOY_STAGING" not in wf_text or "SMOKE_STAGING" not in wf_text:
            errors.append("staging workflow must provide VALIDATE, DEPLOY_STAGING, and SMOKE_STAGING modes")
        if "acknowledge_staging_deployment" not in wf_text:
            errors.append("staging workflow must require explicit acknowledge_staging_deployment")
        if 'DEPLOY_STAGING requires explicit acknowledgement.' not in wf_text:
            errors.append("DEPLOY_STAGING must fail, not silently skip, without acknowledgement")
        if 'OPPORTUNITYOS_API_ORIGIN must be a non-empty HTTPS origin' not in wf_text:
            errors.append("DEPLOY_STAGING must fail closed when API origin is invalid or non-HTTPS")
        if 'CLOUDFLARE_API_TOKEN is required.' not in wf_text or 'CLOUDFLARE_ACCOUNT_ID is required.' not in wf_text:
            errors.append("DEPLOY_STAGING must validate Cloudflare credentials before mutation")
        if 'tokens/verify' not in wf_text:
            errors.append("DEPLOY_STAGING must verify Cloudflare token readiness against the Cloudflare API")
        if 'OPOS_STAGING_WEB_URL must be a non-empty HTTPS URL.' not in wf_text:
            errors.append("SMOKE_STAGING must require an HTTPS staging URL")
        if "NEXT_PUBLIC_SUPABASE_URL" not in wf_text:
            errors.append("staging workflow must support browser-safe NEXT_PUBLIC_SUPABASE_URL")
        if "NEXT_PUBLIC_SUPABASE_ANON_KEY" not in wf_text:
            errors.append("staging workflow must support browser-safe NEXT_PUBLIC_SUPABASE_ANON_KEY")
        for bad_word in ("dns", "cutover", "zone", "custom_domain"):
            if bad_word in wf_text.lower():
                errors.append(f"forbidden network cutover term in workflow: {bad_word}")

    return errors


def main() -> None:
    errors = validate_cloudflare_package()
    if errors:
        print(f"Cloudflare deployment validation failed with {len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    print("Cloudflare deployment validation passed cleanly.")


if __name__ == "__main__":
    main()