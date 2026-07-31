# Contributing to StepStitch

Thanks for your interest in StepStitch — privacy-safe issue→repro infrastructure. The
project is Apache-2.0 and welcomes contributions: bug fixes, new connectors, docs, and
tests.

## The one rule that governs everything: never leak NPI

StepStitch's entire value is that it **cannot** leak non-public personal information. Any
change must preserve this:

- Drafts and writes are built **only** from the sanitized `TraceSummary`
  (`service/stepstitch_service/integrations/base.py`) — never raw footsteps, the free-text
  explanation, the user id, page text, request/response bodies, headers, cookies, or full
  URLs.
- The server-side scrubber (`scrubber.py`) is the trust boundary; the backend never trusts
  the client.
- The MCP / Copilot agent surface stays **read-only / draft-only**
  (`assert_no_destructive_operation()` in `mcp_server.py`). Destructive or direct-write
  capabilities are never exposed as autonomous agent tools.

If your change touches capture, scrubbing, drafts, or the agent surface, expect extra
scrutiny and add a proof test.

## Development setup

```bash
# SDK (TypeScript)
npm install
npm run type-check
npm test                # includes the redaction-proof gate
npm run test:e2e-proof  # compiles a trace and runs the Playwright repro in Chromium

# Service (Python, >=3.10 declared)
python -m venv .venv && source .venv/bin/activate
pip install -e "service[test,mcp,lint]"
python -m pytest service/tests -q

# Ingest host (FastAPI). Copy the env template, point it at a Postgres, then:
cp server/.env.example server/.env   # fill in DATABASE_URL + tokens
pip install -r server/requirements.txt
# migrations run automatically on startup; or apply manually:
cd server && alembic upgrade head && cd ..
uvicorn server.app:app --reload
```

### Checks before you push

This repository ships no git hooks — hooks are per-clone local tooling, and one that
arrives with a checkout runs someone else's code on your machine on every push. Nothing
here configures `core.hooksPath`, and `npm install` does not touch your git configuration.

If you want the same checks locally that CI runs on your PR, run them directly:

```bash
npm run type-check                            # root
cd web && npm run lint && npx tsc --noEmit    # web/ (there is no type-check script)
```

Wire those into your own global hooks if you like — that is your configuration to make.

Commit under whatever name and email you normally use. This repository does not check
authorship or commit trailers.

## Definition of Done (house rule)

Every capability must be backed by **code AND a named, green test**. PRs without a test for
new behavior will be asked to add one. Keep `docs/STATUS.md` and `README.md` claims truthful
— if you change a count or a guarantee, update the docs in the same PR.

## Adding a connector / adapter

The adapter framework (`integrations/base.py`) is the only public extension seam:

1. Subclass `DraftAdapter` and build a **flat** draft via `assert_flat` (scalars only, no
   forbidden keys).
2. Derive every field from `TraceSummary` — nothing else.
3. Add tests proving flatness and no-NPI (a conformance kit is provided for this).
4. Adapters may import **only** `integrations.base` — never core internals. This layering is
   enforced by `service/tests/test_open_core_boundary.py` and `.importlinter`.

## Pull request checklist

- [ ] Tests added/updated and green (`npm test`, `npm run test:e2e-proof`, `pytest service/`)
- [ ] `npm run type-check` clean
- [ ] No new runtime dependency in the SDK (zero-dep invariant; SBOM gate enforces this)
- [ ] Privacy invariant preserved; `tests/redaction-proof.test.ts` + `test_compliance.py` green
- [ ] Docs updated if behavior or claims changed
- [ ] Conventional Commit title (e.g. `feat:`, `fix:`, `docs:`) so release-please can version

## Reporting security issues

Do **not** open a public issue for vulnerabilities. See [SECURITY.md](SECURITY.md).

## License

By contributing you agree your contributions are licensed under the project's
[Apache-2.0 License](LICENSE).
