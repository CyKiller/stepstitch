# StepStitch threat model

Scope: the StepStitch SDK (`src/`), the service engine (`service/stepstitch_service/`), the
MCP/agent surface, the optional governed direct-write, and the reference ingest host
(`server/`). This is a living document; pair it with `RELEASE.md` (supply chain),
`INCIDENT-RESPONSE.md` (operations), and `COMPLIANCE-EVIDENCE.md` (generated capture matrix).

## Assets (in priority order)

1. **NPI / customer data** — the thing StepStitch must *never* capture, store, log, or
   return: input values, page text, screenshots, raw URLs, request/response bodies, headers,
   cookies, stack traces, and the free-text explanation.
2. **Stored trace evidence** — scrubbed footsteps + structural metadata.
3. **Admin operator credentials** — the bearer/JWT that gates reads and direct-write.
4. **System-of-record credentials** (Mode B only) — ServiceNow/Salesforce auth, held by the
   host, never by StepStitch core.
5. **Audit trail** — recordkeeping integrity (Reg S-P).

## Trust boundaries

- **B1 — Browser ↔ ingest API.** The SDK redacts in the page, but the server **never trusts
  the client**: every payload passes the server-side scrubber before storage
  (`scrubber.py`, enforced in `router.py:save_session_trace`). A hostile hand-rolled POST
  cannot persist NPI (`service/tests/test_scrubber.py`).
- **B2 — Caller ↔ operator surface.** Reads/deletes/purge require the host's `require_admin`;
  writes require `get_user_id`. StepStitch core ships no auth — the host injects it
  (`server/auth.py` is a demo; swap for OIDC/JWT in production). Every operator read is
  audited.
- **B3 — Agent/MCP surface.** Only the 12 read-only/draft operations are exposed; a hard
  import-time guard (`assert_no_destructive_operation`) plus drift tests
  (`test_mcp_surface.py`) keep destructive/direct-write operations off it forever.
- **B4 — Direct-write ↔ system of record (Mode B).** Off by default; admin-only `/deliver`
  with a named human approver + idempotency key; dry-run by default; sends only the
  `assert_flat` draft. Credentials live in a host closure (`delivery/clients.py`).
- **B5 — Host-injected dependencies.** Auth, DB, and audit are injected; their correctness
  is the host's responsibility (see Assumptions).

## Key threats & mitigations (STRIDE)

| Threat | Vector | Mitigation | Evidence |
|---|---|---|---|
| **Information disclosure** | Client sends NPI in footsteps/explanation/metadata | Server-side scrubber + strict metadata allowlist; forbidden keys dropped/422 | `scrubber.py`, `test_scrubber.py`, `redaction-proof.test.ts` |
| Information disclosure | Draft/direct-write leaks identity to a SoR | Drafts built only from `TraceSummary`; `assert_flat` rejects nested/forbidden keys; conformance kit | `integrations/base.py`, `test_integrations.py`, `conformance.py` |
| Information disclosure | Agent tool reads the raw trace (carries explanation) | Raw single-trace read (`GET /session/{id}`) is flagged destructive and excluded from the agent surface | `mcp_server.is_destructive`, `test_mcp_surface.py` |
| Information disclosure | Trace ids become metrics label cardinality / leak in logs | Metrics use the route **template**; access log carries route template + status only | `server/metrics.py`, `server/host.py` |
| **Elevation of privilege** | Ingest token used to read operator surface | Separate `require_admin` vs `get_user_id`; reads reject the ingest token | `server/auth.py`, `test_host.py` |
| Elevation / **Tampering** | Unauthorized record creation in a SoR | `/deliver` admin-only + human `approved_by`; not an agent tool; dry-run default | `router.py`, `test_delivery.py` |
| **Spoofing** | Forged bearer | Host auth verifies the token; production should use signed JWT/OIDC | `server/auth.py` (swap point) |
| **Repudiation** | Operator denies an action | Every read/action audited; durable `stepstitch_audit` store on a long clock | `router._audit`, `server/audit.py` |
| **Denial of service** | Capture flood / incident | Org-wide kill switch (`capture_enabled` → 503, fail-safe on error) | `router.py`, `test_router_smoke.py` |
| DoS | Duplicate writes on retry storms | Idempotency key + durable store dedupe | `delivery/base.py`, `test_delivery_clients.py` |
| **Tampering** (supply chain) | Compromised SDK bundle | Zero runtime deps, SBOM, SRI, signed provenance release | `RELEASE.md`, `sbom.cdx.json`, CodeQL/audit CI |

## Assumptions / host responsibilities (residual risk)

- The host provides **real** auth (`server/auth.py` ships a demo shared-bearer — replace with
  OIDC/JWT for production) and serves StepStitch over TLS.
- `/metrics` and `/dashboard` are operator/internal surfaces; the host should network-restrict
  `/metrics` and require the admin token for any data the dashboard loads (it does — the
  dashboard embeds no data and calls the authenticated API).
- The host enforces transport security, rate limiting, and WAF at the edge.
- Mode B credentials and the durable idempotency store are the host's to secure.
- Right-to-delete and retention purge are exercised by the host on schedule
  (`retention.py`, `/maintenance/purge-expired`).

## Out of scope

Physical security, the customer's own ServiceNow/Salesforce tenant hardening, and the
correctness of host-side OIDC/WAF/TLS configuration.
