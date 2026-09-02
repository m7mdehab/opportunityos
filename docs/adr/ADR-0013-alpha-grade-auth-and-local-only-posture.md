# ADR-0013 — Alpha-Grade Auth and Local-Only Posture

- **Status:** Accepted
- **Date:** 2026-09-02
- **Phase:** BRIEF-FR-004
- **Supersedes:** none
- **Superseded by:** none

## Context

BRIEF-FR-004 (Founder Alpha: Local Thin Slice) puts a browser in front of the
founder's own machine for the first time. `api/app.py::create_app(settings)`
serves exactly one founder, over one local PostgreSQL instance, with no
hosting, no reverse proxy, and no public network exposure — the brief's
explicit non-goals list "hosting/HTTPS/Caddy/Docker" as FR-005 work, not
FR-004 work.

ADR-0012 already records that persistence through Phase 5 is single-workspace
by construction: 9 of 11 tables carry no tenant key, and the 2 that do are
unenforced by any query path. An authentication design for this brief must
not contradict that decision by implying a multi-tenant system exists behind
the login screen. There is one founder, one password, and one session at a
time.

The service reads its identity and secrets from environment variables —
`OPPORTUNITYOS_DB_URL`, `OPPORTUNITYOS_FOUNDER_PASSWORD`,
`OPPORTUNITYOS_SESSION_SECRET` — set locally by the founder via
`private/alpha.env` (from `docs/templates/alpha.env.template`) and refuses to
start if any is missing. This ADR binds the auth and transport decisions that
`api/app.py` and its auth routes (`D6`) must implement, and records honestly
what this posture does and does not protect against, so that a future reader
cannot mistake "runs on localhost with a password" for a hosted security
boundary.

## Decision

1. **Single-founder password auth, no user table.** `POST /api/auth/login`
   accepts one password, compared against `OPPORTUNITYOS_FOUNDER_PASSWORD` in
   constant time, and on success issues a signed, HttpOnly session cookie
   (`SameSite=Lax`) using `OPPORTUNITYOS_SESSION_SECRET`. `POST
   /api/auth/logout` clears it; `GET /api/auth/me` reports session state.
   Every other route fails closed (401) without a valid session. There is no
   registration, no password reset, and no roles. This is deliberate:
   ADR-0012 records that this system has no enforced tenancy, and adding a
   user table here would imply a multi-tenancy this system does not have.
   Authentication in this phase is a gate on one person's own data, not an
   identity system, and must not be read as evidence of multi-tenant
   readiness.
2. **Localhost only.** The service is not hosted and is not reachable over a
   network in this phase. The session cookie sets `Secure` only when the
   service is not running on localhost; on localhost it is deliberately
   omitted so the alpha works over plain HTTP loopback. This whole posture is
   **not safe on a network.** The mitigation is not a network-layer control —
   it is that the service is never placed on one. Running this build behind
   any reverse proxy, tunnel, or port-forward before FR-005 lands is out of
   scope and unauthorized by this ADR.
3. **The password is a gate, not a security boundary.** It is compared
   against a value read from an environment file on the founder's own disk,
   not a hash at rest, because there is no user table to hash it into.
   Anyone with filesystem access to `private/alpha.env` has the password in
   full. That is stated plainly rather than implied away: the founder's own
   machine is the trust boundary this design relies on. The password's job is
   to stop an unattended browser tab or a shared machine from exposing the
   dashboard, not to withstand an attacker who already has local access.
4. **Rate-limiting is in-memory and best-effort.** Login attempts are
   rate-limited (5/min) in the running process's memory. It stops casual
   automated guessing while the process is up; it is not durable and confers
   no guarantee across restarts or across process instances.
5. **What FR-005 (hosted staging) must add before this posture is exposed to
   a network.** FR-005 inherits the following obligations from this ADR and
   may not treat them as optional:
   - **TLS termination** in front of the service; plaintext HTTP must not
     carry the session cookie or the password off the founder's own machine.
   - **`Secure` and `__Host-` cookie posture**, replacing the localhost-only
     cookie flags this ADR sets, once the origin is a real HTTPS host.
   - **Password hashing at rest**, and the migration that implies, if and
     when a user table is introduced — the environment-variable password
     compared in this ADR is authorized for single-founder localhost use
     only and must not be carried into a hosted, multi-identity design
     unchanged.
   - **Explicit CSRF defence.** `SameSite=Lax` alone is not sufficient once
     the origin is public and reachable by other sites.
   - **Session expiry and revocation**, including a way to invalidate a
     specific session, not just to rotate the shared secret.
   - **Rate-limiting that survives a process restart** — the in-memory 5/min
     limit this ADR authorizes is explicitly not durable and must not be
     assumed sufficient once the service is reachable over a network.
   - **An audit trail for login attempts**, which this alpha does not keep.

## Consequences

- **Positive:** the founder can run the First Founder Acceptance Script in a
  real browser against real local data without building or reviewing a
  hosted-grade identity system first; the smallest correct thing for a
  single-user, single-machine, localhost-only deployment is what gets built.
- **Positive:** the boundary between "acceptable now" and "required before
  hosting" is recorded explicitly, so FR-005 has a checklist rather than a
  rediscovery.
- **Negative:** a lost or rotated `OPPORTUNITYOS_SESSION_SECRET` invalidates
  all existing sessions; there is no per-session key, so this is an
  all-or-nothing invalidation.
- **Negative:** the in-memory login rate limit resets on every process
  restart, so a restart briefly restores a fresh guessing budget to any
  caller who can reach the loopback interface.
- **Negative:** there is no logout-everywhere and no server-side session
  registry — clearing the cookie is the only issued way to end a session, and
  a copied cookie remains valid until the shared session secret is rotated.
- **Security:** this design is authorized for localhost-only, single-founder
  use. It must not be read as a template for a hosted deployment; FR-005 is
  required to close each gap enumerated in Decision item 5, not to build
  further on top of this posture unchanged.
- **Privacy:** the founder's password lives only in `private/alpha.env` on
  the founder's own machine and in the process environment; this ADR does not
  authorize storing it, logging it, or transmitting it anywhere else.
- **Cost / operational:** none beyond the deferred hosting-grade auth work
  already implied by FR-005's non-goal boundary in BRIEF-FR-004.

## Alternatives considered

- **Add a user table and hashed password now, ahead of any hosting need.**
  Rejected: there is exactly one founder and no roles to model; a user table
  would imply a multi-tenancy ADR-0012 explicitly records this system does
  not have, and would add migration surface with no present benefit.
- **Skip authentication entirely on the reasoning that the service only
  binds loopback.** Rejected: an unattended browser tab or a shared machine
  can still reach a loopback service; a password gate is cheap insurance
  against that specific, realistic failure mode even though it is not a
  network security boundary.
- **Build the full FR-005 hosted-grade posture (TLS, hashed passwords,
  CSRF tokens, durable rate limiting) inside FR-004.** Rejected as out of
  scope: BRIEF-FR-004 names hosting/HTTPS as an explicit non-goal deferred to
  FR-005, and building it now would substitute unreviewed hosting-security
  work for the brief's actual deliverable, the local thin slice.

## Required tests and rollback

- **Verification:** `api/test_api.py` (Case W family) asserts every route
  fails closed (401) without a valid session, that login/logout succeed with
  the correct password and fail otherwise, and that `uvicorn api.app:app`
  refuses to start with any of `OPPORTUNITYOS_DB_URL`,
  `OPPORTUNITYOS_FOUNDER_PASSWORD`, or `OPPORTUNITYOS_SESSION_SECRET`
  missing. `python scripts/check_repository.py` verifies this ADR carries a
  valid `Status` field.
- **Rollback:** this ADR records a decision about the FR-004 auth and
  transport posture; it makes no code change itself and has nothing to
  revert. A future brief that changes this posture (most likely FR-005) must
  supersede this ADR rather than editing it in place.
