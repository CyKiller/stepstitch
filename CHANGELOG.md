# Changelog

All notable changes to StepStitch are recorded here. Versions are repo-wide tags; the
SDK (`@stepstitch/tracker`) and the backend (`stepstitch_service`) are versioned in
lockstep per `RELEASE.md`.

## v0.4.0 — Financial-services support pack

- **Positioning sharpened: issue-to-repro infrastructure, not session replay.** README +
  npm description now lead with privacy-safe debugging evidence and reproducibility
  (scrubbed timeline → diagnostics → replayability → Playwright repro), explicitly
  distinct from the crowded session-replay/observability category.
- **Financial-services support pack.** Added sanitized ServiceNow, Salesforce, and
  Genesys draft previews for Copilot/Power Platform workflows. StepStitch still sends
  nothing and holds no system-of-record credentials.
- **Sanitized frontend diagnostics.** The SDK and backend now preserve useful API/error
  structure (status, method, endpoint template, exception type, source path, line,
  build/release metadata) while raw logs, messages, stacks, bodies, headers, cookies,
  screenshots, page text, input values, and full URLs remain forbidden.
- **Copilot tool expansion.** Added `GetDiagnosticSummary` and
  `CreateFinancialServicesExportPreview` to the read/draft-only OpenAPI pack, with docs
  and policy updates for generic regulated support operations.
- **Golden-path acceptance test** (`service/tests/test_golden_path.py`) — one hostile
  report flows through the whole product (ingest+scrub → list → read → summary →
  privacy-posture → export-preview → compile) as the executable definition of done.
- **Completion ledger** (`docs/STATUS.md`) — maps every plan item to status + proof,
  and names the exact (credential/decision) unblockers for the remaining gated work.
- **Architecture: StepStitch core, integrations via Copilot.** Documented the chosen
  topology — StepStitch exposes sanitized reads + a flat draft; a Copilot Studio agent
  reaches ServiceNow/Salesforce/Genesys workflows through Microsoft's **native
  connectors** and governed Power Platform flows (StepStitch builds no outbound send
  layer, by design). New `copilot/SETUP.md` (agent blueprint)
  and `copilot/connector-field-map.md` (draft → native-connector field maps); refined
  `system-prompt.md` / `action-policy.md` to make the native-connector create explicit.

## v0.3.0 — Enterprise evidence layer

**Intent.** v0.1–v0.2 proved the *privacy* half: structural-only capture, consent, the
deterministic Playwright compiler, audited admin reads, right-to-delete, split
retention, the org-wide kill switch, and supply-chain artifacts (SBOM, SRI, signed
tags). v0.3.0 adds the *trust + usefulness + governance* half so StepStitch reads as a
privacy-safe support-to-engineering evidence layer for regulated digital operations —
not just a bug tool.

### Added (backend, `service/stepstitch_service/`)

- **Server-side scrubber** (`scrubber.py`) — the NPI trust boundary. Runs on every
  ingestion before storage, independent of the SDK. Redacts SSNs, card/account numbers,
  phone, email, DOB-like dates, long numeric IDs and raw URLs from free text;
  re-templates routes; strict-allowlists metadata; drops forbidden keys (request/response
  bodies, console, headers, cookies, screenshots, dom). `reject_on_forbidden` turns a
  leak signal into HTTP 422. Per-trace report returned on ingest + stored at
  `trace_metadata._scrub`.
- **Replayability engine** (`replayability.py`) — deterministic 0–1 score, letter grade,
  and warnings from structural footsteps; surfaced on `GET /session/{id}`, a dedicated
  `/replayability` endpoint, and the compiled repro header.
- **Deployment profiles** (`profiles.py` + `profiles/*.json`) —
  `financial-services-enterprise` (default), `healthcare-strict`, `internal-enterprise`,
  `open-source-default`. A profile can only tighten the NPI boundary.
- **Draft-only integrations** (`integrations/`) — sanitized, flat ServiceNow incident
  and Salesforce case drafts built from a `TraceSummary`; no live API calls.
- **Copilot-safe surface** — `GET /session/{id}/summary`, `/privacy-posture`,
  `POST /session/{id}/export-preview` (all admin-only, audited) + `copilot/`
  (`openapi-v2.json`, `action-policy.md`, `system-prompt.md`).
- **Compliance evidence** (`compliance.py` + `scripts/generate_compliance_evidence.py`)
  — `COMPLIANCE-EVIDENCE.md` generated from the live scrub policy; drift-guarded.

### Notes

- **SDK runtime is functionally unchanged** — `src/` redaction/tracker logic is the same
  as v0.2.0; only `SDK_VERSION` bumped (lockstep). The SRI hash changes only because the
  stamped version string changed; the redaction-proof suite is unchanged and green.
- **Backward compatible.** `create_stepstitch_router(...)` gains an optional
  `scrub_policy` (defaults to the strict financial-services posture). Existing callers
  get server-side scrubbing automatically with no signature change.
- Tests: 76 backend (`service/tests`) + 18 SDK (`tests/`), all green; `ruff` clean.

## v0.2.0

- Org-wide kill switch (`capture_enabled`) and split-retention `purge_expired_traces`.
- SBOM, SRI, signed-tag release runbook; live Chromium repro proof.

## v0.1.0

- Privacy-by-default footsteps SDK + deterministic Playwright compiler + decoupled
  router factory.
