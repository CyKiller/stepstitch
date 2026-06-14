<!-- Thanks for contributing to StepStitch! Use a Conventional Commit title (feat:/fix:/docs:/…). -->

## What & why

<!-- What does this change do, and why? Link any issue. -->

## Privacy invariant (required)

- [ ] This change does **not** capture/store/log/return NPI (input values, page text,
      screenshots, raw URLs, bodies, headers, cookies, stack traces, or the free-text
      explanation).
- [ ] Drafts/writes derive only from `TraceSummary`; the MCP/Copilot surface stays
      read-only/draft-only.

## Definition of Done

- [ ] New behavior is backed by a named, green test
- [ ] `npm run type-check` clean
- [ ] `npm test` + `npm run test:e2e-proof` green
- [ ] `pytest service/tests -q` green
- [ ] No new SDK runtime dependency (zero-dep invariant)
- [ ] Docs (`README.md` / `docs/STATUS.md`) updated if claims or behavior changed

## Notes for the reviewer

<!-- Anything that needs extra attention, especially around scrubbing or the agent surface. -->
