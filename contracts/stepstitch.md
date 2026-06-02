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
  "metadata": { "status": 500 }              // structural, NPI-free only (optional)
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
    "sdk_version": "0.2.0", "sdk_build": "<git-short-sha>",
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

### Operator & maintenance surface (admin only, audited)

| Method + path | Purpose | Audit action |
|---|---|---|
| `GET /sessions` | list traces | `stepstitch.list` |
| `GET /session/{id}` | read one trace | `stepstitch.read` |
| `GET /session/{id}/playwright` | compile repro | `stepstitch.compile` |
| `DELETE /session/by-user/{id}` | right-to-delete bodies | `stepstitch.delete_by_user` |
| `POST /maintenance/purge-expired` | split-retention body purge | `stepstitch.retention_purge` |

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
