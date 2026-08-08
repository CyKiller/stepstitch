# Getting started

The fastest path from `npm install` to a compiled Playwright reproduction. Everything
here is self-hosted and Apache-2.0 — no account, no SaaS, no credentials.

> Prefer to watch first? The [red-to-green demo](https://stepstitch.vercel.app/demo) runs
> the whole loop end-to-end in the browser.

## The guided path

With a local host running (`npx stepstitch start`), one command scaffolds the wiring
below into your app — the same-origin ingest proxy, a safe tracker wrapper, and the
report control — detects your framework, configures a synthetic reproduction, and sends
one sample report so you can see a trace in the console immediately:

```bash
npx stepstitch init
```

It never overwrites a file you have edited, never writes a credential into a file, and
`npx stepstitch init --uninstall` removes exactly what it created. The manual steps
below remain the reference for what the generated files do.

## 1. Install the SDK

```bash
npm install @stepstitch/tracker
```

The browser SDK has **zero runtime dependencies**. Capture is OFF until you call
`grantConsent()`, and it honors GPC / Do-Not-Track.

## 2. Wire it into your app

<!-- doc-example:wire-up-ts -->
```ts
import { StepStitchTracker } from "@stepstitch/tracker"

const tracker = new StepStitchTracker({
  appId: "your-app",
  ingestEndpoint: "/api/stepstitch/v1/session", // same-tenant only
})

// after your consent manager confirms opt-in:
tracker.grantConsent("v1")

// from your own API client (the SDK does NOT patch fetch):
if (!res.ok) tracker.recordApiError(res.status, res.url, "POST")

// from a "Report a bug" control:
const { traceId } = await tracker.submitTrace("Pay button did nothing", projectId)
```

The SDK never captures input values, page text, screens, or raw URLs — only the
structural footsteps needed to reproduce the bug. See `tests/redaction-proof.test.ts` for
the guarantees.

## 3. Run the ingest host

The browser posts to your own host, which mounts the StepStitch service router. The
backend **never trusts the client**: every trace is scrubbed again on the server before it
is stored. See [`docs/DEPLOY.md`](DEPLOY.md) for a complete host, including the OIDC, RBAC,
and deployment-profile configuration.

```bash
# from a checkout of this repo
pip install -e service
PYTHONPATH=service uvicorn your_host:app   # mounts /api/stepstitch/v1/*
```

## 4. Get the replayability score and the compiled repro

Once a trace is ingested, an operator (or an agent over MCP) can read its score and pull a
deterministic Playwright test:

```bash
# is this bug reproducible?
GET /api/stepstitch/v1/session/{trace_id}/replayability   # 0–1 score + A–F grade

# the compiled reproduction (text only, never run against production)
GET /api/stepstitch/v1/session/{trace_id}/playwright
```

The compiled test runs **red** while the bug is present and turns **green** once the fix
lands — that pre-fail to post-pass transition is what gets recorded as `confirmed_fixed`
in the regression corpus.

## 5. Try it with no backend at all

The credential-free demo runs the full pipeline (scrub → score → compile → draft → verify)
against the real service modules, with no database or network. It imports those modules,
so Python 3.10+ and the service package are prerequisites:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install ./service
npm run demo   # writes demo/evidence-bundle.json — deterministic, re-runs identical
```

## Where to go next

- **Self-host quickstart (hosted page)** — [stepstitch.vercel.app/quickstart](https://stepstitch.vercel.app/quickstart)
- **Deploy & configuration** — [`docs/DEPLOY.md`](DEPLOY.md)
- **Build a connector** — [`docs/connectors.md`](connectors.md) (the `DraftAdapter` SDK + conformance kit)
- **Agent networks & MCP** — [`docs/AGENTS.md`](AGENTS.md)
- **Frozen wire contract** — [`contracts/stepstitch.md`](../contracts/stepstitch.md)
- **Compliance evidence** — [`COMPLIANCE-EVIDENCE.md`](../COMPLIANCE-EVIDENCE.md)
