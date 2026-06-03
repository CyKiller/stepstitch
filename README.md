# @stepstitch/tracker

Privacy-by-default user-footsteps SDK. Records a structural trace of a user session and
lets a backend compile it into a deterministic Playwright reproduction script. **Zero
runtime dependencies.** Built for regulated, self-hosting deployments.

## Privacy posture

Adopts the strongest industry model (Sentry Session Replay's "private by default"):

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
- **Deployment profiles** — `financial-services-enterprise` (default), `healthcare-strict`
  (free text dropped, forbidden keys reject 422), `internal-enterprise`,
  `open-source-default`. A profile may only *tighten* the NPI boundary.
- **Draft-only integrations** — flat, sanitized ServiceNow incident / Salesforce case
  drafts built from a structure-derived `TraceSummary` (never raw footsteps, the
  explanation, or the user id). Direct system-of-record writes stay behind host governance.
- **Copilot-safe surface** — read-only/draft endpoints + an OpenAPI tool pack
  (`copilot/`) for a Microsoft Copilot Studio agent. Exposes no delete, retention,
  kill-switch, raw-read, or direct write. **StepStitch is the core; supporting systems
  (ServiceNow, Salesforce) are reached through the agent's _native_ Copilot connectors**,
  fed by StepStitch's sanitized flat draft — StepStitch holds no CRM credentials and
  builds no outbound CRM send layer. See `copilot/SETUP.md`.
- **Compliance evidence** — `COMPLIANCE-EVIDENCE.md` is generated from the live scrub
  policy (`npm run evidence`); a drift guard keeps it equal to the code.

Each is proven in `service/tests/` (76 tests). See `contracts/stepstitch.md` for the
frozen contracts and `COMPLIANCE-EVIDENCE.md` for the reviewer packet.

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
if (!res.ok) tracker.recordApiError(res.status, res.url)

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
