# Releasing

Cutting a release is cheap; an unusable published version is not. Every version on npm and
PyPI is permanent and public, so the goal here is **one careful release**, not a fast one
followed by a hotfix.

## The rule

**Finalize everything on `main` and verify it there. Then tag once.**

Do not tag to find out whether something works. If a published release turns out broken,
batch the fix with whatever else is pending rather than immediately cutting another —
a version list that reads `0.9.0, 0.9.1` an hour apart tells a stranger the release
process is not careful, which is exactly the opposite of what this project claims.

## Steps

1. **Land everything.** All PRs merged, `main` green, `git log <last-tag>..main` contains
   everything you intend to ship.
2. **Merge the release-please PR** (`--admin` is required; branch protection blocks the
   bot). This writes the version into every tracked file and creates the tag.
3. **Dispatch `release.yml`.** The tag alone does *not* fire it in this repo — dispatch by
   hand. On the tag: `gh workflow run release.yml --ref vX.Y.Z`. If the release workflow
   itself was just fixed, dispatch on `main` and name the version instead:
   `gh workflow run release.yml --ref main -f version=X.Y.Z` — a tag dispatch runs the
   workflow *as of that tag*, which is wrong when the fix is to the workflow.
4. **Verify as a stranger, from the registries:**

   ```bash
   scripts/verify-published-release.sh X.Y.Z
   ```

   The release pipeline runs the same checks in its `installable` job. Run the script too
   when you want an independent answer.
5. **Only then** say the release is good.

## Why step 4 is not optional

Green CI has said a release was fine when it was not, twice, in one afternoon:

- `stepstitch` — the launcher every doc tells people to run — **was never published to
  npm.** `release.yml` only published the tracker.
- Once published, the launcher installed the engine **without the `[local]` extra**, so
  `npx stepstitch start` printed an apology instead of starting.

Both passed every gate, because the first-run gate exercises a *local* `npm pack` of the
shim and overrides the service spec with `./service[local]`. The working tree is not the
registry. Nothing that reads the working tree can answer the question a release makes.

## What tracks the version

`release-please-config.json` lists the files whose versions are rewritten. Four of them
matter and drift silently when missed:

- `service/pyproject.toml` — the engine
- `packages/cli-shim/package.json` — **both** its `version` and its pinned
  `stepstitch.serviceVersion`, so the launcher and the engine always move together
- `service/server.json` — both the top-level `version` and `packages[0].version`
  (the plain-path updater only touched the first; both are jsonpath entries now)
- `src/tracker.ts`, `web/src/lib/version.ts`, `docs/STATUS.md`
