# StepStitch Contract (frozen)

This is the producer/consumer contract for StepStitch. Freeze it before changing any
implementation that depends on it. Producer = the SDK (`@stepstitch/tracker`); consumers
= the ingestion service, the compiler, and the operator cockpit.

## Footstep shape (the wire format)

The SDK is **privacy-by-default**. A footstep is structural; it never carries readable
text, input values, or raw URLs unless explicitly opted in.

```jsonc
{
  "timestamp": "2026-06-02T08:00:00.000Z", // ISO-8601 UTC
  "type": "navigation | click | input | api_error | exception",
  "route": "/accounts/:id",                 // route TEMPLATE, never a raw URL
  "target": "[data-testid=\"pay\"]",        // stable structural selector (optional)
  "label": "[masked]",                       // MASKED unless source is data-stepstitch-unmask
  "metadata": {
    "status": 500,
    "method": "POST",
    "endpoint": "/api/accounts/:id",
    "error_type": "TypeError"
  }                                         // structural, NPI-free only (optional)
}
```

Redaction rules (enforced in `src/redaction.ts`, proven in
`tests/redaction-proof.test.ts`):

- **Mask all text by default.** `label` is `[masked]` unless the element (or an
  ancestor) carries `data-stepstitch-unmask`.
- **Never capture input values.** `input` footsteps record only that an interaction
  occurred. `input[type=password]`, `[autocomplete*=cc-]`, and `[data-sensitive]` are
  skipped entirely.
- **No media content** (`img/svg/video/canvas/picture/audio/object/embed/map`).
- **Route templating.** Query strings and ID-like path segments (numeric, UUID, long
  hex) become `:id`. No raw URLs.
- **Frontend diagnostics are structural only.** API errors and exceptions may record
  status, method, endpoint template, exception type, source path, line, and column. Raw
  logs, raw messages, stack traces, request/response bodies, headers, cookies, DOM text,
  screenshots, input values, and full URLs are never valid producer fields.

## Ingestion API

`POST {ingestEndpoint}` — same-tenant only; the SDK has no default cloud URL.

```jsonc
// request
{
  "app_id": "marvox",
  "project_id": "proj-1 | null",
  "explanation": "user-authored bug text | null",
  "footsteps": [ /* UserFootstep[] */ ],
  "consent_version": "v1 | null",
  "metadata": {
    "sdk_version": "0.4.0", "sdk_build": "<git-short-sha>",
    "viewport": "1280x720", "user_agent": "..."
  }
}
// response
{ "status": "ok", "trace_id": "<uuid>" }
```

- **Write auth:** any authenticated user; the trace is bound to the caller's `user_id`.
- **Read auth (operator):** admin role only; every read writes an access audit event.
- **`metadata.sdk_build`** carries the SDK's stamped build hash (§5b) for incident
  forensics — it ties a stored trace to an exact, reproducible build.

### Server-side scrubber (the trust boundary)

The SDK redacts in the browser (`src/redaction.ts`), but **the server never trusts the
client**. A hand-rolled `curl`, a buggy integration, or a compromised page can POST
anything, so every ingestion runs through `scrub_trace_payload(payload, policy)`
(`service/stepstitch_service/scrubber.py`) **before** any value reaches storage. This is
defense-in-depth and is enforced independently of the SDK. Proven in
`service/tests/test_scrubber.py`.

The scrubber, under the default **`financial-services-enterprise`** policy:

- **Free text (`explanation`, unmasked labels, allowed metadata strings):** redacts
  SSNs, card/account numbers (13–19 digits), phone numbers, emails, DOB-like dates,
  long numeric identifiers, and raw URLs — replaced with `[redacted:<kind>]`. Capped to
  `max_text_len`. A policy may set `free_text: "disabled"` to drop `explanation` whole.
- **Routes:** re-templated server-side (scheme/host/query/hash stripped, ID-like
  segments → `:id`) so a leaked raw URL cannot persist. Idempotent on a clean template.
- **Metadata:** strict **allowlist** (top-level: `sdk_version`, `sdk_build`, `viewport`,
  `user_agent`, `consent_version`, `locale`, release/environment fields; footstep:
  `status`, `error_type`, `method`, `endpoint`, `source_path`, `line`, `column`,
  `interacted`). Anything else is dropped; surviving string values are still
  PII-scrubbed and endpoint/source-path values are route-templated.
- **Forbidden keys** (raw `request_body`/`response_body`, `console`, `headers`,
  `cookies`, `screenshots`, `dom`, `url`, `query_string`, …) are dropped as a leak
  signal. With `reject_on_forbidden: true` their presence makes the POST a **422**
  instead, and `stepstitch.scrub_reject` is audited.

The ingestion **response** and the stored `trace_metadata._scrub` both carry the report:

```jsonc
{ "scrub_status": "clean" | "scrubbed", "scrubbed_fields": ["explanation", "metadata.cookies"], "policy": "financial-services-enterprise" }
```

This is the compliance proof: a reviewer can see exactly what the server stripped at
ingestion, per trace. The scrubber is the canonical NPI boundary — do not store any raw
producer field that bypasses it.

#### Deployment profiles

A **profile** is a named posture that selects the `ScrubPolicy` (see
`service/stepstitch_service/profiles.py`; canonical Python definitions, with matching
`profiles/*.json` artifacts guarded against drift by `test_profiles.py`). A profile may
only *tighten* the boundary (free-text scrub→disabled, drop→reject) — it can never
weaken the allowlist/forbidden sets. Default = `financial-services-enterprise`.

| Profile | free_text | reject_on_forbidden |
|---|---|---|
| `financial-services-enterprise` (default) | scrub | drop |
| `healthcare-strict` | disabled | reject (422) |
| `internal-enterprise` | scrub (longer notes) | drop |
| `open-source-default` | scrub | drop |

A host wires it via `create_stepstitch_router(scrub_policy=load_profile("..."))`.

## Financial-services support pack (sanitized, flat, DRAFT-only)

Adapters (`service/stepstitch_service/integrations/`) export a trace to a system of
record. They consume **only** a `TraceSummary` — a flat, structure-derived projection
(trace id, route template, headline, replayability score/grade, privacy status, failing
status, exception type). They never see the raw footsteps, the free-text explanation, or
the user id, so a system of record cannot receive NPI. Proven in
`service/tests/test_integrations.py`.

Rules (frozen):

- **Draft-only.** Adapters build a payload; they do not call a vendor API in this layer.
  Direct create stays behind an explicit host-side governance flag.
- **Flat scalars only.** `assert_flat` rejects nested objects (Salesforce/ServiceNow
  connectors reject nested complex objects) and any `FORBIDDEN_DRAFT_KEYS`
  (`footsteps`, `explanation_raw`, `user_id`, `request_body`, `response_body`, `target`,
  `selectors`, `raw_url`).
- **ServiceNow** → Incident draft: `short_description`, `description` (sanitized summary
  only), `category/subcategory/impact/urgency`, `correlation_id = stepstitch:<trace_id>`,
  `work_notes` (replayability + "repro available internally").
- **Salesforce** → Case draft: `Subject`, `Origin=StepStitch`, `Status`, `Priority`,
  `StepStitchTraceId__c`, `RouteTemplate__c`, `ReplayabilityScore__c`,
  `ReplayabilityGrade__c`, `PrivacyStatus__c`, `PlaywrightReproLink__c=internal-link-only`.
- **Genesys** → support-context draft: `origin`, `trace_correlation_id`,
  `issue_headline`, `route_template`, `diagnostic_type`, `diagnostic_endpoint`,
  `failing_status`, `exception_type`, `replayability_score`, `replayability_grade`,
  `suggested_queue`, `privacy_status`, `playwright_repro=internal-link-only`.

## Copilot-safe surface

`copilot/openapi-v2.json` exposes **only** read-only/draft operations to a Microsoft
Copilot Studio agent: `ListRecentTraces`, `GetTraceSummary`, `GetReplayabilityScore`,
`GetPrivacyPosture`, `GetDiagnosticSummary`, `GeneratePlaywrightRepro`,
`CreateExportPreview`, `CreateFinancialServicesExportPreview`. It deliberately omits
delete, retention/purge, kill-switch, the raw `GET /session/{id}` (carries
`explanation`), and any direct system-of-record write. `copilot/action-policy.md` and
`copilot/system-prompt.md` bound agent behavior. Guarded by
`test_copilot_surface.py::test_openapi_exposes_no_destructive_operation` and
`::test_openapi_paths_are_real_routes` (every advertised path must map to a live route).

### Operator & maintenance surface (admin only, audited)

| Method + path | Purpose | Audit action |
|---|---|---|
| `GET /sessions` | list traces | `stepstitch.list` |
| `GET /session/{id}` | read one trace (includes `replayability`) | `stepstitch.read` |
| `GET /session/{id}/replayability` | reproducibility score only | `stepstitch.replayability` |
| `GET /session/{id}/summary` | sanitized, structure-derived summary (Copilot-safe) | `stepstitch.summary` |
| `GET /session/{id}/diagnostic-summary` | sanitized frontend/API diagnostic summary | `stepstitch.diagnostic_summary` |
| `GET /session/{id}/privacy-posture` | per-trace scrub report + never-captured list | `stepstitch.privacy_posture` |
| `POST /session/{id}/export-preview` | build ServiceNow + Salesforce + Genesys drafts (sends nothing) | `stepstitch.export_preview` |
| `POST /session/{id}/financial-services-export-preview` | named financial-services support draft pack (sends nothing) | `stepstitch.financial_services_export_preview` |
| `GET /session/{id}/playwright` | compile repro | `stepstitch.compile` |
| `DELETE /session/by-user/{id}` | right-to-delete bodies | `stepstitch.delete_by_user` |
| `POST /maintenance/purge-expired` | split-retention body purge | `stepstitch.retention_purge` |

### Replayability

`GET /session/{id}` and `GET /session/{id}/replayability` carry a deterministic
reproducibility score computed purely from the structural footsteps (no extra capture,
no NPI), proven in `service/tests/test_replayability.py`:

```jsonc
{
  "score": 0.86,          // 0..1, clamped
  "grade": "A",           // A≥0.85, B≥0.70, C≥0.55, D≥0.40, else F
  "warnings": [ { "code": "unstable_selector", "detail": "...", "step_index": 1 } ],
  "signals": { "steps": 3, "interactive": 1, "stable_selectors": 1 }
}
```

Scoring signals: selector stability (`data-testid` > `#id` > structural path > none),
presence of a terminal action (click/api_error/exception), templated-route fixture
needs, and trace volume. The compiler (`generate_playwright_test`) emits the score and
warnings as a header comment block in the generated repro.

### Org-wide kill switch

The router accepts a `capture_enabled` callable (the host wires it to a tenant-config
flag). When it returns falsy, `POST /session` is refused with **503** and no row is
written — the first action in an incident-response runbook, halting capture tenant-wide
without a redeploy. A broken/erroring flag **fails safe** (capture OFF). Reads, deletes,
and purge stay available so operators can still respond. This complements the SDK-side
`disable()`, which kills a single browser instance.

## Consent & privacy signals

- Capture is OFF until `grantConsent(consentVersion)`.
- If `navigator.globalPrivacyControl === true` or DNT is enabled, capture stays off and
  `submitTrace` returns `{ submitted: false, reason: "privacy-signal" }`.
- `disable()` is a permanent kill switch (incident-response first action).

## Retention (split clocks)

- **Trace bodies** (`footsteps`, `explanation`): short TTL via `retention_expires_at`,
  purged by the `purge_expired_traces` cleanup path — exposed as the admin
  `POST /maintenance/purge-expired` endpoint and runnable from a periodic host job
  (Marvox mirrors its job-cleanup loop). Minimizes NPI exposure.
- **Access/audit records:** retained 5 years (SEC Reg S-P 2024), stored separately so
  erasing a body never destroys the record of who touched it.
- **Right-to-delete:** delete-by-user removes bodies; the deletion audit record is kept.

## Compatibility note

This supersedes the original draft's `{ url, value }` footstep shape. The `value` field
is removed by design (it carried input text); `url` is replaced by `route` (templated).
