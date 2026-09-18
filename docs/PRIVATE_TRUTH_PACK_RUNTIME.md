# Private Truth Pack runtime contract

Cloud API and worker roles load the Founder Truth Pack through the existing
`truth.pack.load_founder_pack` seam. In cloud mode the URI must be a credential
free HTTPS object URL and `OPPORTUNITYOS_TRUTH_PACK_HASH` must match either the
raw or canonical SHA-256 digest. Credentials are supplied only in headers:

- `Authorization: Bearer $OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN`
- Supabase Storage additionally receives `apikey: $OPPORTUNITYOS_TRUTH_PACK_API_KEY`.

Query strings, fragments, URL userinfo, HTTP, local paths, data URIs, and
Supabase `/object/public/` routes fail closed. URI and hash are safe
configuration; auth token and API key are server secrets. Scheduler and
migrate roles receive neither secret.

Azure uses secure parameters and Container Apps secret references for the URI,
auth token, and API key. The deployment validator checks that API and worker
references exist and that the migration job has no Truth Pack environment.

Static readiness reports `PRIVATE_REMOTE_READY` only for a private HTTPS
configuration. `PUBLIC_OR_UNAUTHENTICATED_REMOTE_BLOCKED` and missing
credentials remain blocking states. No hosted object was fetched in this lane;
real private remote retrieval after restart is required for production closure.
