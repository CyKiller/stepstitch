# Fragility Radar

**Predict which steps will break — and shrink a trace to its failing path.**

Most troubleshooting is reactive: a bug happens, you reproduce it. Fragility Radar uses
StepStitch's deterministic replayability signal — a metric no recording tool has — to shift left:
*which steps in this flow are most likely to break as the app evolves?* And it produces a smaller,
faster repro by dropping the steps that don't matter.

## Fragility map

`GET /session/{id}/fragility` ranks each interactive step by how brittle it is, worst-first:

- **Selector stability** — `data-testid` (robust) → `#id` (decent) → structural `nth-of-type`/tag
  path (brittle) → no selector at all (worst).
- **Templated routes** — a `/accounts/:id` route needs a fixture to replay, adding fragility.

Each step gets a `risk` score and a concrete recommendation (e.g. "add a data-testid"). It is pure,
deterministic, and structure-derived — selectors are structural.

```json
{ "fragility": [
    { "step_index": 1, "stability": "structural", "risk": 0.7,
      "recommendation": "Structural selector is brittle — add a data-testid." }
  ], "most_fragile": { "step_index": 1, "...": "..." }, "interactive_steps": 2 }
```

## Minimal repro

`GET /session/{id}/minimal-repro` reduces a trace to the steps on its **failing route** — dropping
navigation detours to unrelated pages — and compiles the result to a runnable Playwright test. It
never invents execution dependencies; it keeps the failing-route interactions and drops the noise.

```json
{ "original_steps": 5, "reduced_steps": 3, "reduction_ratio": 0.6, "playwright_code": "import { test … }" }
```

## Use it

- **MCP tools:** `get_fragility_map`, `generate_minimal_repro`.
- **Dashboard:** *Fragility* and *Minimal repro* actions on the trace detail.

Source: `service/stepstitch_service/fragility.py` (built on `replayability.py`'s per-step signals
and the deterministic `compiler.py`).
