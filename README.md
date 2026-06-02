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
