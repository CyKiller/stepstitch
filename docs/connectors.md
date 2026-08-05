# Building a StepStitch connector

StepStitch is fully open (Apache-2.0) and the adapter framework is its **public extension
seam**. Anyone can add a connector (PagerDuty, Discord, …) without forking.

## Bundled by default

`default_draft_adapters()` (`stepstitch_service.integrations.bundle`) ships eight adapters
today, in canonical order:

| Adapter | System | Shape |
|---|---|---|
| `ServiceNowAdapter` | ServiceNow | Incident draft |
| `SalesforceAdapter` | Salesforce | Case draft |
| `GenesysAdapter` | Genesys | Support-context draft |
| `JiraAdapter` | Jira | Issue draft |
| `ZendeskAdapter` | Zendesk | Ticket draft |
| `GitHubIssuesAdapter` (`name = "github_issues"`) | GitHub Issues | Issue draft |
| `LinearAdapter` | Linear | Issue draft |
| `SlackAdapter` | Slack | Message draft (not a ticket — a channel notification) |

`GitHubIssuesAdapter`'s adapter name is `github_issues`, not `github` — that key is already
used by the human-gated Repair Loop's dry-run issue/PR preview
(`github_bridge/`, `contracts/stepstitch.md`'s `/github/issue` + `/github/pr`), which is a
different, more privileged flow (it can open a real issue/PR against *this* repo, admin-only,
never on the agent surface). This adapter is the general-purpose "draft a ticket in the
visitor's own GitHub repo" connector — same draft-only posture as every other adapter here.

The first three are enterprise system-of-record adapters; the rest close the developer-first
gap (GitHub Issues, Linear, Jira, Zendesk, Slack) so a team that isn't running ServiceNow or
Salesforce still has a first-class integration target. All eight are draft-only and share the
same governance posture: nothing here ever gains direct-write/auto-file capability — see
[Optional direct-write](#4-optional-direct-write) below.

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

See the worked references — also the real, bundled-by-default adapters, not just examples:
`integrations/contrib/jira.py`, `integrations/contrib/zendesk.py`, `integrations/github.py`,
`integrations/linear.py`, `integrations/slack.py`.

## 2. Prove it with the conformance kit

```python
from stepstitch_service.integrations.conformance import assert_adapter_conformant

def test_my_adapter():
    assert_adapter_conformant(MyAdapter())
```

The kit checks flatness, no forbidden keys, no planted markers, and determinism — the same
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
