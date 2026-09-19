"""Static, credential-free validator for the FR-007 Azure staging package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
ROLES = ("api", "worker", "scheduler", "migrate")
FORBIDDEN = (
    "Microsoft.App/managedEnvironments",
    "Microsoft.ContainerRegistry",
    "Microsoft.DBforPostgreSQL",
    "Microsoft.Storage/storageAccounts",
    "Microsoft.Network/",
    "Microsoft.Cdn/",
    "private/truth_pack.yaml",
    "hostPath",
    "docker.sock",
)


def validate_image(image: str) -> list[str]:
    if not image or image == "latest" or image.endswith(":latest"):
        return ["image must be a non-latest immutable reference"]
    if not re.fullmatch(r"[^\s/@]+(?:/[^\s/@]+)+@sha256:[0-9a-fA-F]{64}", image):
        return ["image must match registry/repository@sha256:<64 hex>"]
    return []


def validate_package(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    azure = root / "infra" / "azure"
    try:
        contract = json.loads((azure / "contract.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["infra/azure/contract.json is missing or invalid"]
    roles = contract.get("roles")
    if not isinstance(roles, dict) or tuple(roles) != ROLES:
        errors.append("contract must represent exactly api, worker, scheduler, migrate")
    for relative in ("main.bicep", "modules/container-app.bicep", "modules/container-job.bicep"):
        path = azure / relative
        if not path.is_file():
            errors.append(f"missing deployment template: {relative}")
        else:
            text = path.read_text(encoding="utf-8")
            for token in FORBIDDEN:
                if token in text:
                    errors.append(f"forbidden foundational resource or local path: {token}")
            if "output " in text.lower():
                errors.append(f"secret-like or unapproved template output in {relative}")
    main = (azure / "main.bicep").read_text(encoding="utf-8") if (azure / "main.bicep").is_file() else ""
    app_module = (azure / "modules/container-app.bicep").read_text(encoding="utf-8") if (azure / "modules/container-app.bicep").is_file() else ""
    job_module = (azure / "modules/container-job.bicep").read_text(encoding="utf-8") if (azure / "modules/container-job.bicep").is_file() else ""
    if "existingManagedEnvironmentResourceId" not in main:
        errors.append("existing managed environment resource ID is required")
    if "deployApplicationRoles" not in main or "deployApplicationRoles=false" not in _workflow(root):
        errors.append("migration-first application rollout switch is missing")
    if not re.search(r"param image string", main):
        errors.append("immutable image parameter is missing")
    if not re.search(r"@secure\(\)\s*\nparam truthPackUri string", main):
        errors.append("Truth Pack URI must be a secure deployment parameter")
    for secret_name, env_name in (("truth-pack-uri", "OPPORTUNITYOS_TRUTH_PACK_URI"),
                                  ("truth-pack-auth-token", "OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN"),
                                  ("truth-pack-api-key", "OPPORTUNITYOS_TRUTH_PACK_API_KEY")):
        if f"secretRef: '{secret_name}'" not in app_module or f"{{ name: '{secret_name}'; value:" not in app_module:
            errors.append(f"{secret_name} must be injected through a Container Apps secret reference")
        if f"{{ name: '{env_name}'; secretRef: '{secret_name}' }}" not in app_module:
            errors.append(f"{env_name} must be wired from {secret_name}")
    for module_name, module_text in (("container app", app_module), ("migration job", job_module)):
        if "registry-password" not in module_text or "passwordSecretRef: 'registry-password'" not in module_text:
            errors.append(f"{module_name} must use a secret-backed private registry credential")
        if "registryServer" not in module_text or "registryUsername" not in module_text:
            errors.append(f"{module_name} private registry configuration is incomplete")
    if "GHCR_PULL_TOKEN" not in _workflow(root):
        errors.append("deployment workflow must inject a durable GHCR pull token for Azure")
    if "docker/build-push-action@v6" not in _workflow(root) or "steps.image.outputs.digest" not in _workflow(root):
        errors.append("deployment workflow must build and pin the staging image by digest")
    if "OPPORTUNITYOS_FOUNDER_PASSWORD_HASH: ${{ secrets.OPPORTUNITYOS_FOUNDER_PASSWORD_HASH }}" in _workflow(root):
        errors.append("deployment workflow must derive the cloud password hash from the staging login secret")
    if "founder-password-hash" not in app_module or "OPPORTUNITYOS_FOUNDER_PASSWORD_HASH" not in app_module:
        errors.append("API must use the hashed Founder password secret")
    if "{ name: 'OPPORTUNITYOS_FOUNDER_PASSWORD';" in app_module:
        errors.append("plaintext Founder password must not be deployed")
    if "OPPORTUNITYOS_PUBLIC_ORIGIN" not in app_module:
        errors.append("API public origin configuration is missing")
    if "OPPORTUNITYOS_TRUTH_PACK" in job_module:
        errors.append("migration job must not receive Truth Pack credentials")
    if "secrets:" not in job_module or "{ name: 'cloud-database-url'; value: cloudDatabaseUrl }" not in job_module:
        errors.append("migration job must declare the cloud database secret it references")
    if "manualTriggerConfig:" not in job_module or "parallelism: 1" not in job_module or "replicaCompletionCount: 1" not in job_module:
        errors.append("migration job must be a serialized manual one-shot execution")
    for role in ROLES:
        spec = roles.get(role, {}) if isinstance(roles, dict) else {}
        if spec.get("commandRole") != role:
            errors.append(f"{role} command does not map to container_entrypoint role")
        if role == "api" and not (spec.get("externalIngress") is True and spec.get("targetPort") == 8000):
            errors.append("api must be the only external ingress on port 8000")
        if role in ("worker", "scheduler") and spec.get("externalIngress") is not False:
            errors.append(f"{role} must not have public ingress")
        if role == "scheduler" and (spec.get("minReplicas"), spec.get("maxReplicas")) != (1, 1):
            errors.append("scheduler must be a strict singleton")
        if role == "migrate" and spec.get("kind") != "containerJob":
            errors.append("migrate must be a one-shot container job")
    workflow = _workflow(root)
    if "workflow_dispatch:" not in workflow:
        errors.append("workflow_dispatch is required")
    for trigger in ("push:", "pull_request:", "schedule:", "workflow_run:", "repository_dispatch:"):
        # Only reject event keys directly under top-level `on:` (two-space indent).
        # Action inputs such as docker/build-push-action's `push: true` are not triggers.
        if re.search(rf"^  {re.escape(trigger)}", workflow, re.MULTILINE):
            errors.append(f"automatic workflow trigger is forbidden: {trigger}")
    if "environment: fr007-staging" not in workflow or "id-token: write" not in workflow:
        errors.append("protected staging environment and OIDC permission are required")
    if "acknowledge_staging_deployment" not in workflow:
        errors.append("DEPLOY_STAGING acknowledgement is required")
    if "azure/login@v2" not in workflow or "auth-type: SERVICE_PRINCIPAL" not in workflow:
        errors.append("Azure OIDC login contract is missing")
    if "az deployment group what-if" not in workflow or "az deployment group create" not in workflow:
        errors.append("VALIDATE/WHAT_IF/DEPLOY_STAGING Azure commands are incomplete")
    if "az network" in workflow.lower() or "dns" in workflow.lower() or "cutover" in workflow.lower():
        errors.append("DNS/network cutover operations are forbidden")
    order = [
        workflow.find("deployApplicationRoles=false"),
        workflow.find("containerapp job start"),
        workflow.find("job execution list"),
        workflow.find("Succeeded) exit 0"),
        workflow.find("deployApplicationRoles=true"),
    ]
    if any(position < 0 for position in order) or order != sorted(order):
        errors.append("successful migration execution must be proven before application rollout")
    return errors


def _workflow(root: Path) -> str:
    path = root / ".github" / "workflows" / "fr007-azure-staging-deploy.yml"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--image", help="optional immutable image to validate")
    args = parser.parse_args(argv)
    errors = validate_package(args.root)
    if args.image:
        errors.extend(validate_image(args.image))
    if errors:
        print("Cloud deployment contract BLOCKED: " + "; ".join(errors))
        return 2
    print("Cloud deployment contract PASS: four roles, protected workflow, immutable-image policy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
