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
  "app_id": "demo-app",
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
- **Unknown keys 422 at the door (every profile):** the ingestion schema is
  `extra="forbid"` at both the top level and per footstep. A key outside the wire
  contract (`screenshot`, `value`, `html`, …) is refused with a 422 naming the field —
  never silently discarded before the scrubber could count it. Proven in
  `service/tests/test_strict_policy.py`.

A policy may additionally enable the **strict-schema knobs** (used by the
`financial-services-strict` profile): `selector_policy: "approved_testids"` accepts a
footstep `target` only when it is an operator-approved static `data-testid` or a purely
structural path (tags + `:nth-of-type` — no author strings); `route_policy:
"operator_templates"` accepts a footstep `route` only when it matches an
operator-declared template; `enforce_masked_labels` re-masks any label to `[masked]`,
making the SDK's unmask attribute inert for the tenant. Violations are rejected fields
(422 under `reject_on_forbidden`), and a surviving payload's scrub report carries
`"schema_status": "strict_schema_passed"` — an explicit statement of which checks ran,
never an unprovable "no NPI" claim. The operator allowlists live in the scrub-overrides
document (`approved_testids`, `route_templates`) and can only scope the deny-by-default
checks — they can never disable them.

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
Copilot Studio agent — the same **thirteen** operations the MCP server exposes
(`COPILOT_SAFE_OPERATIONS`, the single source of truth for the OpenAPI pack, the MCP
tools, and the live routes): `ListRecentTraces`, `GetTraceSummary`,
`GetReplayabilityScore`, `GetPrivacyPosture`, `GetDiagnosticSummary`,
`GeneratePlaywrightRepro`, `MatchVerifiedFixes`, `GetAttestation`, `GetFragilityMap`,
`GenerateMinimalRepro`, `GetAgentPacket`, `CreateExportPreview`,
`CreateFinancialServicesExportPreview`. It deliberately omits delete, retention/purge,
kill-switch, the raw `GET /session/{id}` (carries `explanation`), the operator-only
verify/verifications/corpus reads, the Repair Loop (`/github/issue`, `/github/pr`), and the
optional governed direct-write (`/deliver`) — see the surface table below.
`copilot/action-policy.md` and `copilot/system-prompt.md` bound agent behavior. Guarded by
`test_copilot_surface.py::test_openapi_exposes_no_destructive_operation` and
`::test_openapi_paths_are_real_routes` (every advertised path must map to a live route),
and by `test_mcp_surface.py` (the three surfaces cannot drift apart).

### The Safe Agent Packet

`GetAgentPacket` (`GET /session/{id}/agent-packet`) is the public name for "a safe packet to
help fix it": one call composing `GetTraceSummary` + `GetReplayabilityScore` +
`GetPrivacyPosture` + `GetDiagnosticSummary` + `GeneratePlaywrightRepro` into a single response.
It adds no new data or capability over those five individually-agent-safe reads — it only
removes the round-trips, so an agent handling a bug report for the first time makes one call
instead of five. The individual operations remain available for callers that only need one
field.

### Operator & maintenance surface (admin only, audited)

Every operator route requires the admin role and emits an audit event. The **Agent
surface** column says whether the route is also exposed to agents through the
MCP/OpenAPI connector:

- **✅ agent-safe** — one of the thirteen `COPILOT_SAFE_OPERATIONS`; read-only or draft-only,
  NPI-free, exposed via the MCP server and `openapi-v2.json`.
- **admin-only** — operator-only; never an agent/MCP tool (carries `explanation`, raw
  bodies, or governance/verification reads).
- **admin-only · human-gated** — a governed write loop; off unless the host injects it,
  dry-run by default, requires a named approver, and never an agent tool.

| Method + path | Purpose | Agent surface | Audit action |
|---|---|---|---|
| `GET /sessions` | list traces (no bodies) | ✅ agent-safe | `stepstitch.list` |
| `GET /session/{id}/summary` | sanitized, structure-derived summary | ✅ agent-safe | `stepstitch.summary` |
| `GET /session/{id}/replayability` | reproducibility score only | ✅ agent-safe | `stepstitch.replayability` |
| `GET /session/{id}/privacy-posture` | per-trace scrub report + never-captured list | ✅ agent-safe | `stepstitch.privacy_posture` |
| `GET /session/{id}/diagnostic-summary` | sanitized frontend/API diagnostic summary | ✅ agent-safe | `stepstitch.diagnostic_summary` |
| `GET /session/{id}/playwright` | compile repro (text only) | ✅ agent-safe | `stepstitch.compile` |
| `GET /session/{id}/similar-fixes` | structural match to the verified-fix corpus (no NPI) | ✅ agent-safe | `stepstitch.similar_fixes` |
| `GET /session/{id}/attestation` | signed, independently-verifiable evidence bundle (no NPI) | ✅ agent-safe | `stepstitch.attestation` |
| `GET /session/{id}/fragility` | per-step fragility ranking, worst-first (no NPI) | ✅ agent-safe | `stepstitch.fragility` |
| `GET /session/{id}/minimal-repro` | smallest failing path compiled to Playwright (no NPI) | ✅ agent-safe | `stepstitch.minimal_repro` |
| `GET /session/{id}/agent-packet` | Safe Agent Packet: summary + replayability + privacy posture + diagnostic + repro, composed | ✅ agent-safe | `stepstitch.agent_packet` |
| `POST /session/{id}/export-preview` | build ServiceNow + Salesforce + Genesys drafts (sends nothing) | ✅ agent-safe (draft) | `stepstitch.export_preview` |
| `POST /session/{id}/financial-services-export-preview` | named financial-services support draft pack (sends nothing) | ✅ agent-safe (draft) | `stepstitch.financial_services_export_preview` |
| `GET /session/{id}` | read one raw trace (carries `explanation`; includes `replayability`) | admin-only | `stepstitch.read` |
| `GET /correlation/{id}/summary` | reverse-lookup sanitized summary from `stepstitch:<trace_id>` | admin-only | `stepstitch.by_correlation` |
| `GET /audit` | governance read of the durable audit trail | admin-only | `stepstitch.audit_read` |
| `GET /session/{id}/verifications` | verification history for a trace | admin-only | `stepstitch.verifications` |
| `GET /corpus` | regression corpus (reproduced failures by verdict) | admin-only | `stepstitch.corpus` |
| `POST /session/{id}/verify` | CI reports the repro outcome; StepStitch derives + stores the verdict | admin-only | `stepstitch.verify` |
| `POST /session/{id}/github/issue` | Repair Loop: open/label a GitHub issue from the summary (off unless a bridge is injected) | admin-only · human-gated | `stepstitch.github_issue` |
| `POST /session/{id}/github/pr` | Repair Loop: open a regression-test PR (dry-run default; never merges) | admin-only · human-gated | `stepstitch.github_pr` |
| `POST /session/{id}/deliver` | optional governed direct-write of the sanitized draft (off unless writers injected; dry-run default; named approver + idempotency key) | admin-only · human-gated | `stepstitch.deliver` |
| `DELETE /session/by-user/{id}` | right-to-delete bodies | admin-only · destructive | `stepstitch.delete_by_user` |
| `POST /maintenance/purge-expired` | split-retention body purge | admin-only · destructive | `stepstitch.retention_purge` |

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
  (a host app can mirror its job-cleanup loop). Minimizes NPI exposure.
- **Access/audit records:** retained 5 years (SEC Reg S-P 2024), stored separately so
  erasing a body never destroys the record of who touched it.
- **Right-to-delete:** delete-by-user removes bodies; the deletion audit record is kept.

## Local runner security (normative — precedes any runner implementation)

Any component that executes a compiled reproduction on a developer machine (the Phase 2
"Reproduce locally" runner and everything built on it) MUST satisfy all of the following.
These requirements are written before the runner exists so the implementation is held to
them, not the reverse. Each MUST maps to a test in the release that ships the runner.

**Execution limits**
- A strict wall-clock timeout per run; on expiry the browser process tree is killed.
- A maximum run count per invocation (`--runs N` is capped); no unbounded retry loops.
- A cancel control: an in-flight reproduction can be aborted from the surface that
  started it, and abort is recorded in the run transcript.

**Isolation**
- The child process environment is built from an explicit allowlist — never inherited
  wholesale. Anything not allowlisted (cloud credentials, `*_TOKEN`, `*_KEY`, …) is absent.
- A fixed working directory chosen by the runner; the reproduction cannot select paths.
- The runner constructs no shell command from user-provided or capsule-provided text:
  fixed argv arrays only, with capsule data passed as files or arguments, never
  interpolated into a shell string.
- The reproduction may only reach explicitly configured application addresses
  (`STEPSTITCH_APP_BASE_URL` and operator-listed extras); other destinations are refused.

**Evidence hygiene**
- Run transcripts pass through the same secret-redaction rules as ingest before storage.
- Screenshots, when enabled, are taken only of StepStitch's own local reproduction run —
  never a customer session — and are stored locally next to the run record, not uploaded.
  The run targets the operator-configured application, so what appears on screen is only
  as customer-free as that application's data; the customer-data status is not verified.

**Reproduction freezing (the referee property)**
- Before a capsule is handed to any fixing agent, the compiled reproduction script is
  frozen: its `sha256` is recorded with the session.
- Verification MUST rerun the byte-identical frozen script. A hash mismatch is a refusal
  (`Unable to verify`), not a warning: the agent may change application code, but it can
  never weaken, replace, or regenerate the test that judges its fix.
- The pre-fix and post-fix runs use the same frozen script, same runner limits, and the
  verdict is derived by StepStitch from observed exit status — never asserted by the agent.

## Compatibility note

This supersedes the original draft's `{ url, value }` footstep shape. The `value` field
is removed by design (it carried input text); `url` is replaced by `route` (templated).
