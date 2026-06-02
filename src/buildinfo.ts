/**
 * Build provenance (§5b supply-chain hardening).
 *
 * `BUILD_HASH` is `"dev"` in source and stamped to the git short SHA at release time by
 * `scripts/stamp-build.mjs` (run via `npm run release`). It is surfaced in every
 * submitted trace's metadata so a tenant's incident-response team can tie a stored
 * trace back to an exact, reproducible build. Carries no runtime dependency.
 */
export const BUILD_HASH = "2d450fc"
