# FR-007 private durable artifact storage

Artifact generation keeps the existing authenticated API routes and response
headers. `postgres_payload` remains the local/test compatibility backend.
Cloud deployments must explicitly choose a backend with
`OPPORTUNITYOS_ARTIFACT_STORAGE_BACKEND`:

* `postgres_payload`: bytes remain in PostgreSQL and are readable by existing
  local/test flows; this does not satisfy final cloud A-11 object placement.
* `supabase_storage`: bytes are uploaded server-side to the configured private
  bucket. PostgreSQL stores the canonical cache identity, object key, content
  type, SHA-256, size, and generation version. The browser receives bytes only
  through the authenticated OpportunityOS API; no signed/public object URL is
  returned.

Required server-only configuration for the Supabase backend:

`SUPABASE_STORAGE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and
`OPPORTUNITYOS_ARTIFACT_BUCKET`. The service-role key is never a `NEXT_PUBLIC_*`
value and is never included in evidence or error text. Bucket provisioning is
outside this repository lane.

The deterministic object key is `artifacts/<sha256(cache_key)>` and contains
no Founder text. Exact cache hits do not regenerate or upload. Stale truth-pack
rows and global-cap victims delete external objects before metadata deletion.
Upload or checksum failures fail closed; metadata persistence failures attempt
compensating object deletion.

Migration `0008_artifact_storage` preserves existing rows as
`postgres_payload` rows. Database backup/restore carries metadata and any
legacy payload bytes. External bodies are verified separately with
`scripts/artifact_integrity.py`; a database metadata row alone is not body
retrieval proof.

This implementation is repository-complete but does not claim A-11 production
closure. A real private bucket and restart/retrieval execution are still
required.
