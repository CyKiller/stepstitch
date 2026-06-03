# StepStitch — Compliance Evidence

> Generated from the live `ScrubPolicy` by `scripts/generate_compliance_evidence.py`. Do not edit by hand — the drift guard in `service/tests/test_compliance.py` keeps this file equal to the code.

**Active policy:** `financial-services-enterprise`  
**Free-text handling:** `scrub` (max 280 chars)  
**Forbidden key on payload →** dropped + reported

## What StepStitch never captures

- Screenshots / video
- Input values (what a user typed)
- Page text / DOM content
- Raw URLs (templated to routes)
- Request / response bodies
- Raw frontend logs / console messages / stack traces
- Network headers / cookies
- SSNs, account/card numbers, emails, phone numbers (redacted from free text)

## What StepStitch captures (structural only)

- Route templates (e.g. /accounts/:id)
- Stable selectors (data-testid preferred)
- API status codes
- Endpoint templates and source-path templates
- Exception types
- SDK/build/release metadata
- Masked labels

## Server-side enforcement (defense-in-depth)

Every ingestion is scrubbed server-side before storage, independent of the SDK (`service/stepstitch_service/scrubber.py`). The browser SDK also redacts, but the server never trusts the client.

### Metadata allowlist (everything else dropped)

- Top-level: `consent_version`, `environment`, `locale`, `release`, `sdk_build`, `sdk_version`, `sentry_environment`, `sentry_release`, `user_agent`, `viewport`
- Footstep: `column`, `endpoint`, `error_type`, `interacted`, `line`, `method`, `source_path`, `status`

### Forbidden keys (dropped as a leak signal)

- `body`
- `console`
- `console_log`
- `console_messages`
- `cookie`
- `cookies`
- `dom`
- `dom_text`
- `headers`
- `html`
- `log`
- `logs`
- `message`
- `messages`
- `network_headers`
- `query`
- `query_string`
- `raw_url`
- `request_bodies`
- `request_body`
- `response_bodies`
- `response_body`
- `screenshot`
- `screenshots`
- `stack`
- `stacktrace`
- `url`

## Operational controls

- Consent required before capture; GPC and DNT respected (capture stays off).
- Admin-only operator reads; **every** read writes an audit event.
- Right-to-delete removes trace bodies; the deletion audit record is retained.
- Split retention: bodies purged on a short clock; audit records on a separate 5-year clock (SEC Reg S-P 2024).
- Org-wide kill switch refuses ingestion (HTTP 503) with no row written; a broken flag fails safe (capture OFF).
- Per-trace scrub report stored at `trace_metadata._scrub` and returned on ingestion.

## Deployment profiles

| Profile | free_text | forbidden-key handling |
|---|---|---|
| `financial-services-enterprise` | scrub | drop |
| `healthcare-strict` | disabled | reject (422) |
| `internal-enterprise` | scrub | drop |
| `open-source-default` | scrub | drop |

## Verification

- `pytest service/tests` — scrubber, replayability, profiles, integrations, Copilot surface, retention, compiler, router.
- `ruff check service` — lint.
- `sbom.cdx.json` — supply-chain bill of materials.

