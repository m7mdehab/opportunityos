# FR-007 Azure staging deployment package

This package targets an **existing** Azure Container Apps managed
environment. It creates only the four OpportunityOS workload resources:

| Role | Azure resource | Ingress | Scale | Entrypoint |
| --- | --- | --- | --- | --- |
| api | Container App | external, port 8000 | 1–2 | `python scripts/container_entrypoint.py api` |
| worker | Container App | none | 1–2 | `python scripts/container_entrypoint.py worker` |
| scheduler | Container App | none | exactly 1 | `python scripts/container_entrypoint.py scheduler` |
| migrate | Container Apps Job | none, manual | one-shot | `python scripts/container_entrypoint.py migrate` |

The package does not create a subscription, resource group, managed
environment, registry, database, storage account, network, DNS zone, or
monitoring service. The managed environment resource ID, name prefix, and
immutable image are explicit deployment inputs. The image must be a digest
reference such as `registry.example/opportunityos@sha256:<64 hex>`.

## Static validation

```bash
python scripts/validate_cloud_deployment.py \
  --image registry.example/opportunityos@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

This requires no Azure credentials. If the Azure CLI is installed, syntax can
also be checked with:

```bash
az bicep build --file infra/azure/main.bicep --stdout > /tmp/fr007-main.json
```

## Manual staging sequence

1. Select the existing Azure subscription, resource group, and managed
   environment.
2. Set the immutable image and staging secret names in the protected
   `fr007-staging` environment.
3. Run the workflow in `VALIDATE` mode.
4. Run `WHAT_IF` against the explicit resource group and environment.
5. Run `DEPLOY_STAGING` with `acknowledge_staging_deployment=true`. The
   workflow deploys the migration job, starts it once, then deploys API,
   worker, and scheduler.
6. Wait for Azure resource health, then run readiness and authenticated API
   checks. Worker and scheduler are checked through Azure health/logs and have
   no public ingress.
7. Keep source/local authority until FR-007 migration, parity, and later
   cutover gates authorize a change.

The workflow uses Azure OIDC (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
`AZURE_SUBSCRIPTION_ID`) and application secret names only. Secret values are
materialized only under the ephemeral runner temp directory for Azure CLI
parameter ingestion, are never printed or uploaded, and are deleted in an
always-run cleanup step. No production cutover occurs.

Expected current evidence is `azure_execution: NOT_EXECUTED` when Azure
credentials and an existing environment are unavailable. This package does
not claim A-1, A-14, production deployment, or migration completion.
