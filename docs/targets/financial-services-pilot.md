# Deploying StepStitch for a financial-services pilot

This is the enablement runbook for a regulated financial-services customer (via Microsoft)
design-partner pilot. StepStitch is open-source (Apache-2.0) and self-hosted; nothing here is
customer-specific in the product — it is a configuration guide for a regulated financial-services tenant.

## What StepStitch delivers in the pilot

A user-reported issue becomes: a scrubbed event timeline, a replayability score, sanitized
diagnostics, a copyable **Playwright reproduction**, and a flat **ServiceNow incident +
Salesforce case** draft — with customer data policy-scrubbed at every step (proven by
`tests/redaction-proof.test.ts` + `service/tests/test_scrubber.py`).

## Two delivery modes (pick per tenant)

StepStitch builds the same sanitized draft either way; only *who writes the record* differs.

### Mode A — Power Platform native connectors (default, recommended for Microsoft tenants)
- The agent (Copilot Studio) calls `POST /session/{id}/financial-services-export-preview`,
  gets the draft, and maps it onto Microsoft's **native ServiceNow/Salesforce connectors** as
  a human-approved step. StepStitch holds no system-of-record credentials.
- Setup: `copilot/SETUP.md`, `copilot/connector-field-map.md`, `copilot/action-policy.md`,
  and apply a Power Platform DLP policy.

### Mode B — Governed direct-write (for paths not on Power Platform)
- StepStitch writes the record itself via `POST /session/{id}/deliver` — **off by default**,
  admin-only, requires a named human `approved_by` + idempotency key, **dry-run by default**,
  audited, and never on the agent surface. See `docs/integrations/servicenow.md` and
  `docs/integrations/salesforce.md`.
- Enable with `STEPSTITCH_DIRECT_WRITE=servicenow,salesforce` and inject configured writers
  (credentials live in the host, not StepStitch core).

Both modes coexist; a pilot can start with Mode A and add Mode B without code changes.

## Pilot checklist

1. **Deploy** the ingest API (Railway `Dockerfile`, profile `financial-services-enterprise`)
   and, if using agents, the MCP connector (`service/Dockerfile.mcp`). See `docs/DEPLOY.md`.
2. **Salesforce fields**: deploy the six Case custom fields —
   `cd scripts/salesforce && sf project deploy start --manifest manifest/package.xml`
   (see `docs/integrations/salesforce.md`). Grant FLS.
3. **ServiceNow**: confirm the Incident table + `category`/`subcategory` values
   (`docs/integrations/servicenow.md`); use `correlation_id` for reconciliation.
4. **Choose mode A and/or B** per the above and configure governance (DLP / approval gate).
5. **Compliance packet**: hand the reviewer `COMPLIANCE-EVIDENCE.md` (generated from the live
   scrub policy), `RELEASE.md` (SBOM/SRI/provenance), and `INCIDENT-RESPONSE.md`.

## Case-study golden path

The end-to-end path is proven green by `service/tests/test_golden_path.py`:

```
report → scrub (server-side trust boundary) → summary + replayability score
       → sanitized diagnostics → Playwright repro
       → ServiceNow incident + Salesforce case (drafted, or directly written in Mode B)
       → run the repro in CI → regression test
```

Reverse reconciliation: a created ticket's `stepstitch:<trace_id>` resolves back to the
sanitized trace via `GET /stepstitch/v1/correlation/stepstitch:<trace_id>/summary`.

## Compliance posture for the pilot

- Capture is OFF until consent; honors GPC/DNT; org-wide kill switch for incident response.
- Server-side scrubber drops NPI independent of the SDK; profiles may only *tighten* the
  boundary.
- Crosswalk cites **SEC Reg S-P (2024)** and the **April-2026 interagency MRM guidance**
  (superseding SR 11-7). See `COMPLIANCE-EVIDENCE.md`.
