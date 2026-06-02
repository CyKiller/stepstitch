# StepStitch — Incident Response Notes (for the hosting tenant)

StepStitch is deployed **self-hosted**: the SDK runs in the tenant's own front-ends and
posts only to the tenant's own ingestion endpoint. Trace data never reaches the
StepStitch vendor. This document is written to drop into a regulated tenant's incident
response program (e.g. an SEC Regulation S-P §248.30(b) program).

## Data boundary

- **In scope (tenant-controlled):** the SDK bundle, the ingestion service, the
  `stepstitch_traces` store, and the access-audit log — all inside the tenant tenant.
- **Out of scope (vendor):** nothing. Because the tenant self-hosts, the StepStitch
  vendor is **not** a "service provider" receiving customer information, so the Reg S-P
  72-hour service-provider notification clause does not attach to the vendor for trace
  data. (If the vendor is ever given production data, that clause applies and the vendor
  owes notice ≤72 hours.)

## What a trace can and cannot contain

By design (see `contracts/stepstitch.md`), a trace holds structural selectors, route
templates, and masked labels. It does **not** hold input values, account/SSN/balance
text, media, or raw URLs. A compromise of the trace store therefore exposes minimal
NPI — but the tenant should still treat it as containing user-correlated metadata
(`user_id`, `user_agent`, IP at the edge) and assess accordingly.

## Runbook — first actions

1. **Kill capture (org-wide):** flip the tenant kill-switch config flag (the host's
   `capture_enabled` callable; in Marvox, set `STEPSTITCH_CAPTURE_DISABLED=1`). The
   ingestion endpoint then refuses every `POST /session` with 503 — no redeploy needed.
   Optionally also call `tracker.disable()` in the shipped bundle to stop a single
   browser instance. New traces stop immediately.
2. **Preserve the access-audit log** (5-year retention store) — it is the forensic
   record of who read which trace.
3. **Scope the exposure** using the access-audit log + trace metadata.
4. **Notify** per the tenant's program: customer notice as soon as practicable and
   ≤30 days where customer information was reasonably likely accessed.
5. **Recover:** rotate ingestion credentials, purge affected trace bodies
   (`DELETE /session/by-user/{id}` for a subject, or `POST /maintenance/purge-expired`
   for expired bodies — both audit-logged), redeploy a fresh signed SDK build (verify
   the SRI hash from `RELEASE.md` against `dist/index.js`).

## Supporting controls

- **Kill switch:** server-side `capture_enabled` flag (503s ingestion org-wide, fails
  safe) + SDK `disable()` per instance.
- **Audit trail:** every operator read of a trace writes a tamper-evident access event.
- **Split retention:** short-lived trace bodies (`purge_expired_traces` cleanup path);
  5-year audit records on a separate clock.
- **Supply chain:** SDK ships with an SRI hash, signed artifact, and SBOM
  (`sbom.cdx.json`) so the tenant pins an exact verified build; `SDK_VERSION` + the
  stamped `BUILD_HASH` are embedded in trace metadata (`sdk_build`) for forensics. See
  `RELEASE.md` for the full procedure.
