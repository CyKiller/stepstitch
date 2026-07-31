# StepStitch

[![npm](https://img.shields.io/npm/v/@stepstitch/tracker?color=cb3837&logo=npm)](https://www.npmjs.com/package/@stepstitch/tracker)
[![CI](https://github.com/CyKiller/stepstitch/actions/workflows/ci.yml/badge.svg)](https://github.com/CyKiller/stepstitch/actions/workflows/ci.yml)
[![CodeQL](https://github.com/CyKiller/stepstitch/actions/workflows/codeql.yml/badge.svg)](https://github.com/CyKiller/stepstitch/actions/workflows/codeql.yml)
[![Release](https://img.shields.io/github/v/release/CyKiller/stepstitch?sort=semver&color=10b981)](https://github.com/CyKiller/stepstitch/releases)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Website](https://img.shields.io/badge/website-stepstitch.vercel.app-10b981)](https://stepstitch.vercel.app)

**Issue-to-repro infrastructure — not session replay.** When a user reports a problem,
StepStitch turns that single report into a scrubbed event timeline, structural frontend
diagnostics, a replayability score, and a copyable **Playwright reproduction** — without
capturing screens, input values, page text, or raw URLs. **Zero runtime dependencies.**
Built for regulated and quality-focused teams that self-host.

The wedge is deliberate. Session-replay/observability tools (Sentry, LogRocket,
FullStory, Datadog) already sell "watch every session." Most engineering teams don't
need another recording to watch — they need a user-reported bug that can become a
**regression test**. StepStitch leads with privacy-safe *debugging evidence and
reproducibility*, not analytics.

| | Session-replay / observability | **StepStitch** |
|---|---|---|
| Records the user's screen / session | Yes | **No, never** |
| Captures input values, page text, PII | By default (can be configured to reduce) | **No — structural evidence only** |
| What you get out | A session to watch | **A runnable Playwright regression test** |
| Self-hosted, data stays in your boundary | Varies / mostly SaaS | **Yes — Apache-2.0, self-hostable** |
| SDK runtime dependencies | Several | **Zero** |
| Posture for regulated / PII-sensitive teams | Privacy is an opt-in configuration | **Privacy is the default and the boundary is the code** |

> See it: the [red-to-green demo](https://stepstitch.vercel.app/demo) — a real bug
> becomes a failing Playwright test that turns green once the fix lands.

## Privacy posture

Borrows the strongest privacy model in the category (Sentry Session Replay's "private by
default") — but StepStitch captures *structure for reproduction*, never a watchable
recording:

- Masks **all** text by default; opt-in unmask via `data-stepstitch-unmask`.
- Never captures input values; hard-skips password / credit-card / `[data-sensitive]`.
- Blocks media; reduces URLs to route templates (`/accounts/:id`).
- Capture is OFF until `grantConsent()`, and honors GPC / Do-Not-Track.
- `disable()` kill switch for incident response.

The redaction guarantees are proven in `tests/redaction-proof.test.ts` — the artifact
to hand a security review.

## Enterprise evidence layer (server-side)

The browser SDK redacts in the page, but the backend **never trusts the client**. The
`stepstitch_service` package (see `service/`) turns a reported session into privacy-safe
support-to-engineering evidence:

- **Server-side scrubber** — every ingestion is scrubbed before storage, independent of
  the SDK. SSNs, card/account numbers, phone, email, dates, long IDs and raw URLs are
  redacted from free text; routes are re-templated; metadata is strict-allowlisted; and
  forbidden keys (request/response bodies, console, headers, cookies, screenshots, dom)
  are dropped. A hand-rolled hostile POST cannot persist NPI. The per-trace scrub report
  is returned on ingest and stored at `trace_metadata._scrub` as compliance proof.
- **Replayability score** — every trace carries a deterministic 0–1 score + grade +
  warnings, so support knows whether engineering can actually reproduce it. The compiled
  Playwright repro leads with that header.
- **Sanitized frontend diagnostics** — API failures and frontend exceptions can carry
  useful structure (status, method, endpoint template, exception type, source path, line,
  build/release metadata) while raw logs, raw messages, stacks, headers, cookies, bodies,
  screenshots, page text, input values, and full URLs remain out of the trace.
- **Deployment profiles** — `financial-services-enterprise` (default), `healthcare-strict`
  (free text dropped, forbidden keys reject 422), `internal-enterprise`,
  `open-source-default`. A profile may only *tighten* the NPI boundary.
- **Financial-services support pack** — flat, sanitized ServiceNow incident, Salesforce
  case, and Genesys support-context drafts built from a structure-derived `TraceSummary`
  (never raw footsteps, the explanation, or the user id). Direct system-of-record writes
  stay behind host governance.
- **Copilot-safe surface** — read-only/draft endpoints + an OpenAPI tool pack
  (`copilot/`) for a Microsoft Copilot Studio agent. Exposes no delete, retention,
  kill-switch, raw-read, or direct write. **StepStitch is the core; supporting systems
  (ServiceNow, Salesforce, Genesys workflows) are reached through the agent's _native_
  Copilot connectors or governed Power Platform flows**, fed by StepStitch's sanitized
  flat drafts — StepStitch holds no system-of-record credentials and builds no outbound
  CRM/contact-center send layer. See `copilot/SETUP.md`.
- **Compliance evidence** — `COMPLIANCE-EVIDENCE.md` is generated from the live scrub
  policy (`npm run evidence`); a drift guard keeps it equal to the code.

Each is proven by the test suite — the service, host, and SDK test gates that CI requires
green. See `contracts/stepstitch.md` for the frozen contracts and `COMPLIANCE-EVIDENCE.md`
for the reviewer packet.

## Universal agentic connector (MCP)

StepStitch is a capability **provider**, not an agent orchestrator — it perceives, scores,
compiles a Playwright repro, and **drafts**, but never plans or acts autonomously. Its
universal connector is an **MCP server** (`service/stepstitch_service/mcp_server.py`, run
via `stepstitch mcp`): the same thirteen read-only/draft operations — including the composed
**Safe Agent Packet** (`get_agent_packet`, one call instead of five) — over standard MCP, so
the autonomy stays in the customer's stack. A no-destructive guard runs at import, and the
tool set is drift-guarded against the OpenAPI pack and the live routes
(`service/tests/test_mcp_surface.py`).

Connect one in two commands — `stepstitch connect claude` (or `codex`, `gemini`) registers
StepStitch through that agent's own `mcp add` and issues a least-privilege token that can
read evidence but **cannot record a verdict on its own fix**. See
[docs/connect-an-agent.md](docs/connect-an-agent.md).

Speaking MCP is not the same as having been tried. **Which platforms were actually run, on
what date, and what failed** is a living table in
[docs/agent-platforms.md](docs/agent-platforms.md) — one row per platform, failures
included. As of 2026-07-30 one platform has been verified end-to-end, with a real model
reading the packet and fixing a real bug. Cloud/tenant clients (Copilot Studio, Vertex,
Bedrock) are a separate setup path — see `copilot/MCP-SETUP.md` and `docs/DEPLOY.md`.

## Fully open (Apache-2.0)

Everything in this repository is Apache-2.0 — the SDK, the privacy/repro engine, the MCP
connector, **and** the concrete ServiceNow / Salesforce / Genesys adapters. The adapter
**framework** (`integrations/base.py`: `TraceSummary`, `DraftAdapter`, `assert_flat`) is the
single, public extension seam: a host injects adapters via
`create_stepstitch_router(draft_adapters=...)`, and anyone can add their own (Jira, Zendesk,
…) the same way.

An **architecture boundary** is still enforced so the design stays clean — the core never
imports a *concrete* adapter, and adapters only ever see the sanitized `TraceSummary`. This
is a layering rule (not a licensing one), proven by
`service/tests/test_open_core_boundary.py` and an `.importlinter` contract. A future
commercially-licensed edition may *add* a separately-licensed adapter or compliance pack —
additive only; nothing currently Apache-2.0 would be closed. See
`COMMERCIAL.md`, `docs/PRODUCT-PLAN.md`, and `docs/DEPLOY.md`.

## Quickstart

Three ways in, smallest first. Each path lists its real prerequisites, and every command
works in the order shown — the clean-install CI gate runs these sequences on a bare
machine, and `web/tests/quickstart-parity.test.ts` keeps this section and the website's
quickstart page telling the same story.

### Add the SDK to your app (Node + npm only)

```bash
npm install @stepstitch/tracker
```

Zero dependencies, ESM and CommonJS. Capture is off until your app calls `grantConsent()`.

### Prove the loop offline (Git, Node 20+, Python 3.10+)

The demo imports the real service modules — scrubber, scorer, compiler, verdict — so the
service package must be installed first. Nothing leaves your machine, and re-running
writes an identical `demo/evidence-bundle.json`:

```bash
git clone https://github.com/CyKiller/stepstitch.git
cd stepstitch
python3 -m venv .venv
source .venv/bin/activate
pip install ./service
npm run demo
npm run smoke
```

On Windows (PowerShell), activate with `.venv\Scripts\Activate.ps1` instead.

### Run the full host (Docker)

Brings up Postgres + the ingest host with throwaway dev tokens. `-d` returns your
terminal once the containers are up (follow logs with `docker compose logs -f stepstitch`):

```bash
docker compose up --build -d
```

Then open <http://localhost:8000/dashboard> and paste `dev-admin` when the console asks for
a token. To fill the board with a realistic failure (the script needs both variables):

```bash
STEPSTITCH_BASE_URL=http://localhost:8000 STEPSTITCH_INGEST_TOKEN=dev-ingest \
  node scripts/seed-demo-trace.mjs
```

To check the whole install at any point — env, host, database, both tokens, capture policy
and reproduction settings — run the diagnostic. It reads configuration from its own
environment, so with Compose it runs inside the container (on your host shell it would
truthfully report the variables missing). It never prints a secret value, and `-T` skips
TTY allocation so the exact same line works from scripts and CI:

```bash
docker compose exec -T stepstitch stepstitch doctor
```

Prefer no Docker? The manual path (macOS/Linux; on Windows use Docker above) needs a
Postgres you provide, and **two terminals**, because uvicorn runs in the foreground and
owns the first. `STEPSTITCH_APP_BASE_URL` is where generated reproductions will point —
without it every repro targets `localhost:3000`.

**Terminal 1 — run the host** (install everything before starting anything, export the
configuration, then leave this terminal open):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install ./service
pip install -r server/requirements.txt
export DATABASE_URL=postgres://localhost/stepstitch
export STEPSTITCH_INGEST_TOKEN=dev-ingest
export STEPSTITCH_ADMIN_TOKEN=dev-admin
export STEPSTITCH_APP_BASE_URL=https://staging.your-app.example
uvicorn server.app:app --port 8000
```

**Terminal 2 — check it with doctor** (a fresh shell has neither the venv nor your
exports, and doctor reads configuration only from its own environment):

```bash
source .venv/bin/activate
export DATABASE_URL=postgres://localhost/stepstitch
export STEPSTITCH_INGEST_TOKEN=dev-ingest
export STEPSTITCH_ADMIN_TOKEN=dev-admin
export STEPSTITCH_APP_BASE_URL=https://staging.your-app.example
stepstitch doctor
```

### The two tokens

StepStitch has two long-lived bearers, and they are not interchangeable:

| Token | Who holds it | What it can do |
|---|---|---|
| `STEPSTITCH_INGEST_TOKEN` | your **server** (never the browser) | POST traces to `/session` |
| `STEPSTITCH_ADMIN_TOKEN` | the operator, in the console | read evidence, drafts, config |

Two narrower credentials exist so nobody has to hand out the admin token: **scoped agent
tokens** for AI assistants (`summaries` / `repros` / `drafts`) and a **`verify` token** for
CI, which may fetch a reproduction and post a verdict and nothing else. Issue both from the
console's Agents tab. Enterprise deployments can replace the admin token entirely with OIDC
SSO — see [docs/DEPLOY.md](docs/DEPLOY.md).

### Keep the ingest token server-side

The SDK posts to a path in **your** app, which forwards to StepStitch with the ingest token
attached. The token never reaches browser JavaScript:

```js
// POST /api/stepstitch/ingest  — your server, same origin as your app
export async function POST(request) {
  return fetch(`${process.env.STEPSTITCH_HOST}/api/stepstitch/v1/session`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${process.env.STEPSTITCH_INGEST_TOKEN}`, // server-side only
    },
    body: await request.text(),
  })
}
```

`examples/tiny-transfer` is a complete runnable version of this, including the red→green loop.

### Point reproductions at your app

A captured trace is structural: it knows the route template, not your hostname, and never
recorded what was typed. Tell StepStitch the rest once, or every generated test will target
`http://localhost:3000` and cannot run in CI:

```bash
STEPSTITCH_APP_BASE_URL=https://staging.your-app.example   # the app under test
```

Per-project settings (auth fixture, values for `:id` segments, synthetic form values) live at
`PUT /admin/config/repro`. Generated tests carry a READY / NEEDS-CONFIG checklist naming
exactly what is still missing. Configuration stores env var **names**, never credentials.

## Usage

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

// from your own frontend error boundary (no raw messages or stacks):
tracker.recordFrontendException("ChunkLoadError", "/static/app-abc123.js", 41, 2)

// from a "Report Bug" control:
const { traceId } = await tracker.submitTrace("Pay button did nothing", projectId)

// SPA route hook:
tracker.recordNavigation()

// teardown / kill switch:
tracker.destroy()
tracker.disable()
```

## Develop

```bash
npm install
npm run type-check
npm test          # includes the redaction-proof gate
npm run build
```

See `contracts/stepstitch.md` for the frozen wire contract and `INCIDENT-RESPONSE.md`
for the self-host incident-response notes.

## Documentation

- **Getting started** — [`docs/getting-started.md`](docs/getting-started.md) (install → ingest host → first repro)
- **0.6 features** — [`docs/fix-memory.md`](docs/fix-memory.md) (match a bug against the verified-fix corpus),
  [`docs/evidence-attestation.md`](docs/evidence-attestation.md) (signed, independently-verifiable evidence),
  [`docs/fragility-radar.md`](docs/fragility-radar.md) (predict what breaks + minimal repro)
- **Contributing & governance** — `CONTRIBUTING.md`, `GOVERNANCE.md`, `SECURITY.md`
- **Build a connector** — `docs/connectors.md` (the public `DraftAdapter` SDK + conformance kit)
- **Agent networks** — `docs/AGENTS.md` (MCP, function specs for Hermes/OpenAI, the repro→PR loop)
- **System-of-record integrations** — `docs/integrations/servicenow.md`,
  `docs/integrations/salesforce.md` (incl. the optional governed direct-write)
- **Deploy & release** — `docs/DEPLOY.md`, `RELEASE.md` (automated via release-please + publish-on-tag)
- **Pilot** — `docs/targets/financial-services-pilot.md`; status ledger `docs/STATUS.md`; plan `docs/PRODUCT-PLAN.md`
- **Product site & buyer pages** — [stepstitch.vercel.app](https://stepstitch.vercel.app): the
  [red-to-green demo](https://stepstitch.vercel.app/demo) (generated by `demo/README.md` → `npm run demo`),
  [quickstart](https://stepstitch.vercel.app/quickstart),
  [financial-services pilot](https://stepstitch.vercel.app/financial-services-pilot),
  [privacy vs. replay](https://stepstitch.vercel.app/privacy-vs-replay), and
  [agents & MCP](https://stepstitch.vercel.app/agents)
