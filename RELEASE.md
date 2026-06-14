# StepStitch — Release & Supply-Chain Runbook

This is the §5b vendor-sign-off procedure. A regulated tenant runs a vendor security
review before any third-party JS touches a customer-facing app; this runbook produces
the artifacts that review signs against: a **reproducible build**, an **SBOM**, an
**SRI hash**, and a **signed, provenance-bearing release**.

## Automated release (preferred)

Releases are automated end-to-end:

1. **Commit** with [Conventional Commits](https://www.conventionalcommits.org/)
   (`feat:`, `fix:`, …). On push to `main`, **release-please** opens/updates a release PR
   that bumps the three version locations in lockstep — `package.json`, `src/tracker.ts`,
   `service/pyproject.toml` (each carries an `x-release-please-version` annotation) — and
   updates `CHANGELOG.md`.
2. **Merge the release PR.** release-please creates the GitHub Release + `vX.Y.Z` tag.
3. The tag triggers **`.github/workflows/release.yml`**, which runs all gates, then:
   - `npm publish --provenance` (`@stepstitch/tracker`),
   - `python -m build` + PyPI publish (`stepstitch-service`),
   - multi-arch Docker build + push to GHCR (`stepstitch-api`, `stepstitch-mcp`),
   - attaches `sbom.cdx.json` + the SRI hash to the release.

**Required repository secrets** (publish steps skip cleanly if absent):
`NPM_TOKEN`, `PYPI_API_TOKEN`. GHCR uses the built-in `GITHUB_TOKEN`. Optional:
`RAILWAY_TOKEN` for staging/preview deploys.

The manual runbook below remains valid as a fallback / for the regulated vendor sign-off.

## Invariants (must hold every release)

- **Zero runtime dependencies.** `package.json` `dependencies` is `{}`. `npm run sbom`
  hard-fails if anything appears there. This keeps the SBOM a single component and the
  CVE surface to our own code.
- **Strict-CSP clean.** The SDK runs with no `unsafe-eval` and no `unsafe-inline`; it is
  nonce/SRI-friendly. It must pass a stricter CSP than the host app's own.
- **Deterministic output.** `npm run build` is `tsc` only — same input, same `dist/`.

## Release steps

```bash
# 1. Bump versions in lockstep:
#    - package.json            "version"
#    - src/tracker.ts          SDK_VERSION
#    - service/pyproject.toml  version
#    Update contracts/stepstitch.md "Version" + this file's examples if needed.

# 2. Stamp provenance, build, and emit the SBOM:
npm ci
npm run release            # = stamp-build (git short SHA → BUILD_HASH) + tsc + SBOM

# 3. Verify gates are green:
npm run type-check
npm test                   # unit + redaction-proof (the compliance-proving suite)
npm run test:e2e-proof     # compiles a trace and runs the output in Chromium (§7)
(cd service && PYTHONPATH=. pytest tests -q)

# 4. Compute the Subresource Integrity hash for the published ESM bundle:
cat dist/index.js | openssl dgst -sha384 -binary | openssl base64 -A
#    Publish as:  integrity="sha384-<output>"
#    The tenant pins this exact hash in their <script> / import map.

# 5. Tag and sign the release artifact:
git tag -s v<x.y.z> -m "StepStitch v<x.y.z>"
#    Optionally attach a cosign signature + the SBOM to the GitHub release:
#      cosign sign-blob --yes dist/index.js > dist/index.js.sig
#    npm publishes carry provenance attestation:
#      npm publish --provenance --access restricted
```

## Artifacts handed to the tenant security review

| Artifact | File | Purpose |
|---|---|---|
| SBOM (CycloneDX 1.5) | `sbom.cdx.json` | Bill of materials — proves zero deps |
| SRI hash | from step 4 | Pin an exact, verified bundle |
| Signed tag / blob sig | `v<x.y.z>` / `*.sig` | Tamper-evident provenance |
| Build hash in traces | `metadata.sdk_build` | Tie a stored trace to an exact build |
| Redaction-proof suite | `tests/redaction-proof.test.ts` | Proves NPI never egresses (client) |
| Server-side scrub suite | `service/tests/test_scrubber.py` | Proves NPI never persists (server) |
| Compliance evidence | `COMPLIANCE-EVIDENCE.md` | Capture/never-capture matrix from live policy (`npm run evidence`) |
| Incident-response boundary | `INCIDENT-RESPONSE.md` | Kill switch + service-provider boundary |

## Marvox (reference integration) re-vendor

Marvox pins the **compiled** SDK and the service `.py` under `lib/vendor/` and
`services/vendor/`. After cutting a release, regenerate those per the `VENDOR.md` in
each location and bump the recorded version.
