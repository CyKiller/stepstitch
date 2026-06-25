# StepStitch red-to-green demo

A self-contained proof of the full moat — **with no ServiceNow, Salesforce, GitHub,
Copilot, or Railway credentials, and no database**. Everything in
[`evidence-bundle.json`](./evidence-bundle.json) is produced by the *real* StepStitch
service modules (the same scrubber, scorer, compiler, draft adapters, and verdict logic the
live service runs). Nothing is mocked or hand-written; drafts and the PR are dry-run
previews and nothing is ever sent.

## Run it

```bash
npm run demo     # PYTHONPATH=service python3 scripts/demo_red_to_green.py
```

This (re)generates `demo/evidence-bundle.json` and `web/src/lib/demo-bundle.json` (the copy
the marketing site's `/demo` page renders). The output is deterministic — re-running
produces an identical file, which the drift guard in
`service/tests/test_demo_bundle.py` enforces.

Prerequisite: the service package's runtime deps must be importable
(`pip install -e ./service` or use the repo `.venv`) — the same precondition as
`npm run release-gate:evidence`. No credentials are required.

Verify the privacy gate in one command:

```bash
npm run smoke    # regenerates the bundle, then asserts no forbidden field/value survives
```

## The eight-step story

The bundle's `steps` object maps one-to-one to the visible story:

| # | Step | Where in the bundle | What it proves |
|---|------|---------------------|----------------|
| 1 | User reports a bug | `steps.1_bug_report` | A normal support report. `raw_unsafe_input` holds **synthetic placeholders only** (e.g. `000-00-0000`, `user@example.test`) so we can show them being removed — never real NPI. |
| 2 | Structural capture | `steps.2_structural_capture` | Only route templates, stable selectors, and status codes are kept. No screens, input values, page text, or raw URLs. |
| 3 | Privacy scrub | `steps.3_privacy_scrub` | The server scrubber dropped the forbidden fields (`cookies`, `request_body`, `url`, `headers`, `raw_url`) and redacted the PII-shaped text. `scrubbed_fields` is the per-trace compliance proof. |
| 4 | Replayability score | `steps.4_replayability` | A deterministic 0–1 score + grade tells engineering whether the bug is reproducible, with warnings for anything that needs a fixture. |
| 5 | Playwright repro | `steps.5_playwright_repro` | A deterministic Playwright test that fails while the bug exists and passes once it is fixed. No credentials embedded. |
| 6 | Draft ticket/PR | `steps.6_drafts` | Flat ServiceNow/Salesforce/Genesys drafts plus a GitHub issue and a dry-run PR — **created, never sent**. Each draft is validated flat (`assert_flat`) and carries no identity field. |
| 7 | CI verification | `steps.7_ci_verification` | StepStitch never runs code; the customer's CI runs the repro. The verdict `confirmed_fixed` derives **only** from `pre_passed=false` (red) + `post_passed=true` (green). |
| 8 | Regression corpus | `steps.8_regression_corpus` | The confirmed fix is recorded as durable regression evidence. |

`never_captured` and `trace_summary` at the top level mirror the live
`GET /privacy-posture` and `GET /summary` responses.

## Run the same flow live (optional)

The demo above needs nothing external. To exercise the *running service* end-to-end
instead, point a local Postgres at it and drive the real HTTP endpoints:

```bash
# 1. Start the host with a local Postgres (see docs/DEPLOY.md for the full setup).
export DATABASE_URL=postgres://localhost/stepstitch
export STEPSTITCH_INGEST_TOKEN=dev-ingest STEPSTITCH_ADMIN_TOKEN=dev-admin
uvicorn server.app:app --port 8000

# 2. Seed a trace.
STEPSTITCH_BASE_URL=http://localhost:8000 STEPSTITCH_INGEST_TOKEN=dev-ingest \
  node scripts/seed-demo-trace.mjs

# 3. Read the sanitized evidence (admin token), generate the repro, and POST a
#    pre-failed then post-passed verification to /session/{id}/verify — the corpus
#    will then show confirmed_fixed. Open /dashboard to watch it.
```

No system-of-record credentials are needed for any read, draft preview, or dry-run.
