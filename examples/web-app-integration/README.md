# Web app reference integration

How a host app mounts the StepStitch SDK. This is **product documentation** —
the host wiring is intentionally tiny. It is delivered here (not committed into the host app)
because the host build cannot resolve `@stepstitch/tracker` until the dependency below
is added; committing an unresolved import would break the host app's Vercel build.

## Activation (2 steps, once the package is resolvable)

### 1. Add the dependencies

**Frontend (host app `package.json`):**
```jsonc
"dependencies": {
  "@stepstitch/tracker": "github:<org>/stepstitch#semver:^0.1.0"
  // or a published registry version once available
}
```

**Backend (host app `requirements-runtime.txt`):**
```
stepstitch-service @ git+https://github.com/<org>/stepstitch.git#subdirectory=service
```
The backend glue (`backend/stepstitch_integration.py`) and optional mount in `main.py`
are already on the host app `main`; once `stepstitch_service` installs, the router mounts and
`/api/stepstitch/v1/*` goes live (otherwise it logs a warning and stays unmounted).

### 2. Mount the reporter

Copy `report-bug.tsx` into your app (e.g. `components/stepstitch/report-bug.tsx`) and
render it once near the root, wired to the host's existing consent state:

```tsx
// in app/layout.tsx (or a client shell)
<StepStitchReporter hasConsent={analyticsConsentGranted} />
```

If your app already initializes an analytics/consent gate, reuse that same consent gate so StepStitch never
captures before the user has opted in (and honors GPC/DNT automatically).

## Why it's build-safe to defer

`import { StepStitchTracker } from "@stepstitch/tracker"` is a bare specifier. Webpack
resolves it at build time (static *and* dynamic forms), so a missing package fails the
build. Keeping this file out of your app's compiled graph until the dependency exists is
the deploy-safe choice. The backend half is already safe because the import is wrapped
in a guarded optional-mount that logs and continues when the package is absent.

## Verification once activated

- `npm run type-check` and `npm run build` (route + bundle).
- End-to-end: grant consent → click/error → "Report a bug" → confirm a structural,
  NPI-free trace row → open `/admin/stepstitch` as `admin_operator` → Copy Test Code →
  run the generated Playwright locally.
