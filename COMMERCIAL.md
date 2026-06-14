# StepStitch licensing — fully open today, commercial editions later

**As of now, everything in this repository is Apache-2.0** ([LICENSE](LICENSE)) — the SDK,
the privacy/repro engine, the universal MCP connector, **and** the concrete ServiceNow /
Salesforce / Genesys adapters. There is no closed component. StepStitch is built by its sole
maintainer, Aaron Johnson (CyKiller), and is open for use and contribution today.

## What is open (all of it)

- **SDK** — `src/` (`@stepstitch/tracker`): privacy-by-default capture + redaction.
- **Service core** — `service/stepstitch_service/`: `scrubber`, `compiler`, `replayability`,
  `router`, `retention`, `profiles`, `compliance`, and the adapter **framework**
  `integrations/base.py`.
- **Universal MCP connector** — `mcp_server.py`, `mcp_cli.py`.
- **System-of-record adapters** — `integrations/bundle.py` + the concrete `servicenow.py`,
  `salesforce.py`, `genesys.py` draft builders.
- **Optional governed direct-write** — `service/stepstitch_service/delivery/` (when present):
  off by default, human-approval-gated.

## The boundary that remains (architecture, not licensing)

An import boundary is still enforced — but it is now a **layering rule**, not a license one:
the core never imports a *concrete* adapter, and adapters only ever see the sanitized
`TraceSummary`. This keeps the privacy guarantee intact and the adapter set swappable. It is
proven by [`service/tests/test_open_core_boundary.py`](service/tests/test_open_core_boundary.py)
and the `.importlinter` contract in [`service/pyproject.toml`](service/pyproject.toml).

## Future commercial editions

A commercially-licensed edition **may** be introduced later (for example: additional
supported enterprise adapters, a hosted/managed offering, or a compliance pack with
formal regulatory attestations). If that happens it will be additive and clearly delineated;
nothing currently Apache-2.0 will be retroactively closed. Until then, treat the whole repo
as Apache-2.0. For partnership or commercial-support inquiries, contact the maintainer.
