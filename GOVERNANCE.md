# StepStitch Governance

StepStitch is an open-source (Apache-2.0) project. This document describes how decisions are
made and how the project is run.

## Roles

- **Maintainer / BDFL:** Aaron Johnson ([@CyKiller](https://github.com/CyKiller)) is the
  creator and sole maintainer. As Benevolent Dictator For Now, he has final say on technical
  direction, releases, and what ships in the project, and reviews/merges contributions.
- **Contributors:** anyone who submits issues, pull requests, docs, or connectors. See
  [CONTRIBUTING.md](CONTRIBUTING.md).

As the community grows, additional maintainers may be invited based on a sustained track
record of high-quality contributions and good judgment, especially around the privacy
boundary.

## Decision making

- **Day-to-day changes** (bug fixes, docs, tests, new connectors that respect the layering
  rule): decided by maintainer review on the pull request.
- **Significant or architectural changes** (anything touching the scrubber, the privacy
  boundary, the agent/MCP surface, licensing, or public APIs): proposed as an issue or an
  ADR under `docs/adr/` and decided by the maintainer after discussion.
- **Non-negotiable invariant:** no change may weaken the scrub boundary or expose a
  destructive/direct-write capability on the autonomous agent surface. This overrides
  convenience, feature requests, and contributor preference.

## Releases

- Versioning follows [Semantic Versioning](https://semver.org/) across the three artifacts
  (npm `@stepstitch/tracker`, PyPI `stepstitch-service`, Docker images), kept in lockstep.
- Releases are automated via Conventional Commits + release-please; publishing happens on a
  signed git tag. See [RELEASE.md](RELEASE.md).
- Every release must pass all CI gates (type-check, SDK + service tests, executable repro
  proof, compliance evidence drift guard, layering boundary).

## Definition of Done

Every capability must be backed by **code AND a named green test**, and the docs
(`README.md`, `docs/STATUS.md`) must stay truthful. This is enforced socially in review and
mechanically in CI.

## Security

Vulnerabilities are handled privately per [SECURITY.md](SECURITY.md).

## License & contributions

The project is [Apache-2.0](LICENSE). Contributions are accepted under the same license. A
future commercially-licensed edition may be introduced additively; see [COMMERCIAL.md](COMMERCIAL.md).
