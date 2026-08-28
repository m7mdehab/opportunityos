# ADR-0005 — TED Search Is a Read-Only Query

- **Status:** accepted
- **Date:** 2026-08-28
- **Phase:** BRIEF-001

## Context

TED's official public Search API retrieves published procurement notices through
`POST /v3/notices/search`. A verb-only external-action rule would incorrectly
classify that retrieval as a mutation.

## Decision

Authorize only `POST https://api.ted.europa.eu/v3/notices/search` as
`READ_ONLY_QUERY`, without authentication, solely for searches over published
TED notices. The request may contain only documented search fields. Request
metadata records the endpoint, method, allowed field names, response status, and
latency, never credentials or full payloads. All other TED POST endpoints and
all external PUT, PATCH, and DELETE requests remain prohibited.

## Consequences

The source runner enforces the exact host, method, and path before issuing the
request. Any additional exception requires a new ADR and explicit permission.
