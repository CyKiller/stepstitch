# @stepstitch/tracker

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

Each is proven in `service/tests/` (99 service tests; 21 SDK tests). See
`contracts/stepstitch.md` for the frozen contracts and `COMPLIANCE-EVIDENCE.md` for the
reviewer packet.

## Universal agentic connector (MCP)

StepStitch is a capability **provider**, not an agent orchestrator — it perceives, scores,
compiles a Playwright repro, and **drafts**, but never plans or acts autonomously. Its
universal connector is an **MCP server** (`service/stepstitch_service/mcp_server.py`, run
via `mcp_cli.py`): the same eight read-only/draft operations, consumable by **any** MCP
client — Microsoft Copilot Studio, OpenAI, Google Vertex, LangGraph, AWS Bedrock, Claude.
One server, every agent network; the autonomy stays in the customer's stack. A
no-destructive guard runs at import, and the tool set is drift-guarded against the OpenAPI
pack and the live routes (`service/tests/test_mcp_surface.py`). See `copilot/MCP-SETUP.md`
and `docs/DEPLOY.md`.

## Open core

Apache-2.0 core (SDK + privacy/repro engine + MCP connector) with a commercially-licensed
adapter pack (the ServiceNow / Salesforce / Genesys exporters) injected at the boundary.
The core never imports the commercial adapters — enforced by
`service/tests/test_open_core_boundary.py` and an `.importlinter` contract. See
`COMMERCIAL.md`, `docs/PRODUCT-PLAN.md`, and `docs/DEPLOY.md`.

## Usage

```ts
import { StepStitchTracker } from "@stepstitch/tracker"

const tracker = new StepStitchTracker({
  appId: "marvox",
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
