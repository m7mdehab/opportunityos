# Hosted Founder authentication and RLS

Cloud API authentication uses a single Founder password represented by an
`OPPORTUNITYOS_FOUNDER_PASSWORD_HASH` scrypt record. The plaintext password is
accepted only by explicitly local compatibility settings. Login creates an
opaque random cookie token; PostgreSQL stores only its HMAC-SHA256 digest,
using `OPPORTUNITYOS_SESSION_SECRET`. Expired and revoked sessions fail closed.
`/api/auth/logout-all` requires the current valid Founder session and revokes
every active session, including the caller.

The global five-attempts-per-60-seconds budget and audit events are durable in
PostgreSQL. Audit rows contain event type, outcome, request ID, and safe session
reference only. Passwords, hashes, cookies, and CSRF values are never stored
or logged.

Cloud cookies use `__Host-oos_session`, `Secure`, `HttpOnly`, `Path=/`, and
`SameSite=Lax`. Unsafe browser methods require `X-OpportunityOS-CSRF: 1` and
a present `Origin` that exactly matches the credential-free HTTPS
`OPPORTUNITYOS_PUBLIC_ORIGIN`. The configured origin is canonicalized to its
scheme and authority when settings load.

Migration `0009_hosted_founder_auth` adds the durable auth tables. The RLS
registry classifies every ORM application table and enables deny policies for
the `anon` and `authenticated` roles when those Supabase roles exist. It does
not destroy pre-existing grants. Downgrade removes only the policies and RLS
enablement owned by migration 0009. The API/server owner remains authoritative. Backups
preserve audit history, restore sessions as revoked/expired, and reset the
transient rate-limit budget.

Real Supabase role checks remain a provider execution step and are not claimed
by local tests.
