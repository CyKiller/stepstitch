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
| `financial-services-strict` | disabled | reject (422) |
| `healthcare-strict` | disabled | reject (422) |
| `internal-enterprise` | scrub | drop |
| `open-source-default` | scrub | drop |

## Regulatory crosswalk

The controls above mapped to the frameworks a regulated reviewer applies (columns selected for the `financial-services-enterprise` profile).

| Control | SEC Reg S-P (2024) | NIST AI RMF |
|---|---|---|
| Server-side scrub / NPI data-minimization (`scrubber.py`) | Safeguards Rule — protect customer NPI | MAP/MEASURE — data governance |
| Split retention + 5-yr audit clock (`retention.py`) | Recordkeeping — incident records retained 5 yrs | GOVERN — documentation & records |
| Admin-only reads, audit on every read (`router.py`) | Access controls; incident-response program | GOVERN/MANAGE — accountability |
| Org-wide kill switch, fail-safe (`router.py`) | Incident-response containment | MANAGE — incident response |
| Deterministic compiler + replayability + eval gate (`compiler.py`, `test_repro_eval.py`) | — | MEASURE — validity & reliability |
| Draft-only, human-in-the-loop (`integrations/`, `copilot/action-policy.md`) | — | GOVERN — human-AI configuration |

## Model-risk principles (informational)

The April-2026 interagency model risk management guidance (OCC Bulletin 2026-13, superseding SR 11-7) states that generative AI and agentic AI are "not within the scope of this guidance", that it sets no enforceable or prescriptive requirements, and that deterministic rule-based software is excluded from its definition of a model. StepStitch's pipeline is deterministic rule-based software, and the coding agents it governs are agentic AI — so StepStitch does not claim any control here satisfies that guidance.

Stated only as engineering fact: the release gates below are named, runnable controls an institution's own model-risk program may map to its internal principles (auditability, ongoing monitoring, human oversight):

| Gate | Check | Engineering-control role |
|---|---|---|
| End-to-end golden path | `test_golden_path.py` | System validation |
| Server-side scrub boundary | `test_scrubber.py` | Data-control validation |
| Profile drift guard | `test_profiles.py` | Configuration control |
| Executable repro proof | `scripts/prove-repro-executes.mjs` | Output validity |
| Reproduction quality eval | `test_repro_eval.py` | Ongoing output-quality monitoring |
| Open-core import boundary | `.importlinter` / `test_open_core_boundary.py` | Change control / segregation of duties |
| Compliance evidence drift guard | `test_compliance.py` | Documentation currency |

StepStitch is a deterministic, **draft-only provider**: it produces evidence and drafts for human decision-makers and never takes autonomous action, keeping AI outputs in a "support, not replace" posture for fiduciary use.

## Verification

- `pytest service/tests` — scrubber, replayability, profiles, integrations, Copilot surface, retention, compiler, router.
- `ruff check service` — lint.
- `sbom.cdx.json` — supply-chain bill of materials.

