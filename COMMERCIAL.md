# StepStitch licensing — open core + commercial pack

StepStitch is **open core**. The licensing boundary is enforced in code, not just stated
here (see [`service/tests/test_open_core_boundary.py`](service/tests/test_open_core_boundary.py)
and the `.importlinter` contract in [`service/pyproject.toml`](service/pyproject.toml)).

## Open core — Apache-2.0 ([LICENSE](LICENSE))

The privacy/repro engine and the universal connector — everything a team needs to capture,
sanitize, score, reproduce, and expose evidence to any agent network:

- **SDK** — `src/` (`@stepstitch/tracker`): privacy-by-default capture + redaction.
- **Service core** — `service/stepstitch_service/`: `scrubber`, `compiler`,
  `replayability`, `router`, `retention`, `profiles`, `compliance`, and the adapter
  **framework** `integrations/base.py`.
- **Universal MCP connector** — `mcp_server.py`, `mcp_cli.py` (the product's headline
  surface; see [`docs/PRODUCT-PLAN.md`](docs/PRODUCT-PLAN.md)).

The open core is fully functional on its own: it serves every read-only/draft operation,
and the MCP connector works against it. With no commercial pack installed, export-preview
endpoints simply return an empty draft set.

## Commercial pack — separately licensed (not Apache-2.0)

- **System-of-record adapters** — `service/stepstitch_service/integrations/bundle.py` and
  the concrete `servicenow.py` / `salesforce.py` / `genesys.py` modules. A host injects
  them via `create_stepstitch_router(draft_adapters=default_draft_adapters())`.
- **Compliance pack** (PRODUCT-PLAN P4) — the regulatory crosswalk (SEC Reg S-P + the
  April-2026 interagency MRM guidance; HIPAA for the healthcare profile) and the evidence
  packaging built on `compliance.py`.

These ship from a separate distribution. The enforced import boundary guarantees the open
core never depends on them, so they can be extracted without touching core code.

> The concrete adapter modules currently live in this repository for development
> convenience; they are **commercially licensed, not Apache-2.0**, and are excluded from
> the open-core import graph. Contact the maintainers for commercial terms.
