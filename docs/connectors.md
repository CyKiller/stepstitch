# Building a StepStitch connector

StepStitch is fully open (Apache-2.0) and the adapter framework is its **public extension
seam**. Anyone can add a connector (Jira, Zendesk, Linear, PagerDuty, …) without forking.

A connector turns the sanitized `TraceSummary` into a **flat draft** for a system of record.
It never sees raw footsteps, the explanation, the user id, page text, or bodies.

## 1. Write the adapter

Subclass `DraftAdapter` and return a flat draft validated by `assert_flat`:

```python
from stepstitch_service.integrations.base import DraftAdapter, TraceSummary, assert_flat
from stepstitch_service.integrations.validation import cap  # optional length helpers

class MyAdapter(DraftAdapter):
    name = "my-system"

    def build_draft(self, summary: TraceSummary) -> dict:
        subject, _ = cap(summary.headline, 255)
        draft = {
            "subject": subject,
            "route": summary.route,
            "replayability": summary.replayability_score,
            "external_id": f"stepstitch:{summary.trace_id}",
        }
        return assert_flat(draft)   # scalars only; no forbidden keys
```

Rules enforced by the framework:
- **Flat scalars only** — no nested objects/lists (`assert_flat` raises otherwise).
- **No forbidden keys** — `footsteps`, `explanation_raw`, `user_id`, bodies, selectors,
  `raw_url` are rejected.
- **Deterministic** — same summary in, same draft out.

See the worked references: `integrations/contrib/jira.py` and `integrations/contrib/zendesk.py`.

## 2. Prove it with the conformance kit

```python
from stepstitch_service.integrations.conformance import assert_adapter_conformant

def test_my_adapter():
    assert_adapter_conformant(MyAdapter())
```

The kit checks flatness, no forbidden keys, no NPI markers, and determinism — the same
guarantees the built-in adapters pass.

## 3. Register it (so hosts discover it automatically)

Publish your adapter as a package and declare an entry point:

```toml
# pyproject.toml of your connector package
[project.entry-points."stepstitch.adapters"]
my-system = "my_pkg:MyAdapter"
```

A host that calls `all_draft_adapters()` (built-ins + discovered) will pick it up. Or a host
can inject adapters explicitly:

```python
from stepstitch_service import create_stepstitch_router
from my_pkg import MyAdapter
router = create_stepstitch_router(..., draft_adapters=[MyAdapter()])
```

## 4. (Optional) direct-write

If you also want StepStitch to *send* the draft (not just preview it), implement a
`RecordWriter` in the same spirit — see `stepstitch_service/delivery/` and
`docs/integrations/servicenow.md`. Direct-write is off by default and human-approval-gated;
it is never exposed on the agent/MCP surface.
