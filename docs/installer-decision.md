# Installer decision: what runs behind `npx stepstitch start`

**Status: SELECTED — A (npm shim → uv), confirmed by the 3-OS matrix (run 30537861366, 2026-07-30).**
The public promise is fixed (`npx stepstitch start`); this document decides and records
the mechanism behind it. The measurement lives in
[.github/workflows/installer-experiment.yml](../.github/workflows/installer-experiment.yml)
(runs on every PR touching the shim, and on demand via `workflow_dispatch`).

## Candidates

| | Mechanism | Ships as |
|---|---|---|
| **A** | npm shim finds-or-bootstraps `uv`, then `uvx --from stepstitch-service==<pinned> stepstitch <cmd>` | `stepstitch` on npm ([packages/cli-shim](../packages/cli-shim)) |
| **B** | Signed per-OS single-file binary (PyInstaller), npm shim downloads it | binaries + shim |
| **C** | Python-native: documented `uvx --from stepstitch-service stepstitch start` | docs only |

## Criteria

1. **Clean-machine success** on Windows / macOS / Linux with only Node present
   (the npm audience's guaranteed baseline).
2. **Cold-start time** to first engine output.
3. **Security-team friction**: AV flags, unsigned-binary warnings, what gets downloaded
   from where, and whether the developer consents to it visibly.
4. **Maintenance cost for one person**: build matrix, signing/notarization, release
   surface.
5. **Failure modes**: network points-of-failure and the quality of the error when one
   fails.

## Measurements

Matrix run 30537861366 (clean GitHub runners, cold-start to first engine output;
step wall-clock from the jobs API):

| Approach | ubuntu | macos | windows |
|---|---:|---:|---:|
| A: npm shim + uv (incl. bootstrap when needed) | 3s | 4s | 20s |
| B: PyInstaller binary (build + run, unsigned) | 32s | 24s | 57s |
| C: direct uvx (baseline the shim wraps) | 1s | 1s | 5s |

All three legs green on all three OSes. A's overhead vs C is the uv find/bootstrap; B's
number is build time a *user* would not pay, but B still loses on criterion 3 (unsigned)
and 4 (three build targets + signing for one maintainer). Local macOS dev machine (warm
uv cache): shim → engine output in ~3.3s.

**Finding (2026-07-30):** PyPI `stepstitch-service==0.8.0` predates the
`[project.scripts]` console entry (landed post-tag in `1392a33`), so the shim's pinned
version must be the **first release published after that commit**; until then CI tests
via `STEPSTITCH_SERVICE_SPEC=./service`. Publishing the next service release is therefore
a Phase 1 prerequisite.

## Rationale for provisional A

- **B is the best end-state but the worst first move for a solo maintainer**: three build
  targets plus macOS notarization and Windows signing before any product value ships —
  and an *unsigned* B is strictly worse on criterion 3 than A (uv's installer is signed,
  widely allowlisted, and inspectable).
- **C is honest and near-free but fails the audience**: the target developer is
  npm-native; `uvx` on a landing page is a conversion cliff. C survives as the documented
  fallback (it is literally what A runs).
- **A's real risk is the bootstrap moment** (downloading a package manager). Mitigation
  shipped in the shim: it never auto-installs — it finds `uv` on PATH or in uv's default
  locations, and otherwise prints the exact commands, installing itself only with
  explicit `--install-uv` / `STEPSTITCH_AUTO_INSTALL=1` consent. Corporate machines that
  forbid the download get a copyable, policy-reviewable one-liner instead of a silent
  failure.

## What flips the decision

- A red matrix leg that can't be fixed in the shim (e.g. AV quarantining uv on Windows
  runners) → escalate B (accept the signing toil) with C as the interim.
- uv availability regressing (license/distribution change) → B.

Revisit at Phase 1 exit: if alpha users report bootstrap friction the matrix didn't
catch, B's signing cost gets re-priced against real adoption data.
