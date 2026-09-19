# Private Truth Pack runtime contract

Cloud API and worker roles load the Founder Truth Pack through the existing
`truth.pack.load_founder_pack` seam. In cloud mode the URI must be a credential
free HTTPS object URL and `OPPORTUNITYOS_TRUTH_PACK_HASH` must match either the
raw or canonical SHA-256 digest. Credentials are supplied only in headers:

- generic private HTTPS or legacy Supabase access may use `Authorization: Bearer $OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN`;
- Supabase Storage always receives `apikey: $OPPORTUNITYOS_TRUTH_PACK_API_KEY`;
- when `OPPORTUNITYOS_TRUTH_PACK_API_KEY` is a modern `sb_secret_` key, no Authorization bearer header is sent or required. This follows Supabase's current secret-key model and avoids attempting to parse a non-JWT secret key as a JWT.

Query strings, fragments, URL userinfo, HTTP, local paths, data URIs, and
Supabase `/object/public/` routes fail closed. URI and hash are safe
configuration; auth token and API key are server secrets. Scheduler and
migrate roles receive neither secret.

Azure uses secure parameters and Container Apps secret references for the URI,
optional legacy auth token, and API key. For new staging configuration prefer one
modern Supabase `sb_secret_` API key rather than duplicating the legacy
`service_role` JWT into two environment variables. The deployment validator
checks that API and worker references exist and that the migration job has no
Truth Pack environment.

Static readiness reports `PRIVATE_REMOTE_READY` only for a private HTTPS
configuration. `PUBLIC_OR_UNAUTHENTICATED_REMOTE_BLOCKED` and missing
credentials remain blocking states. No hosted object was fetched in this lane;
real private remote retrieval after restart is required for production closure.
