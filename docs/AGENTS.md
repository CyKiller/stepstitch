# Consuming StepStitch from any agent network

StepStitch is a capability **provider**, not an agent orchestrator. It perceives, scores,
compiles a Playwright repro, and drafts — but never plans, acts autonomously, or writes to a
system of record from the agent surface. Any agent network consumes the **same eight
read-only / draft operations** (`COPILOT_SAFE_OPERATIONS`), projected three ways from one
source of truth:

| Consumer | Surface | How |
|---|---|---|
| Claude Code, Copilot Studio, LangGraph, Bedrock, Vertex | **MCP** | `build_tool_definitions()` / `serve_stdio()` — run `python -m stepstitch_service.mcp_cli` (see `copilot/MCP-SETUP.md`) |
| Hermes, OpenAI tools API, Gemini function calling | **Function specs** | `build_function_tool_specs()` — OpenAI/JSON-Schema `{"type":"function", ...}` |
| Power Platform / native connectors | **OpenAPI** | `copilot/openapi-v2.json` |

All three are drift-guarded against each other (`service/tests/test_mcp_surface.py`), so a new
operation appears everywhere at once and a destructive one can appear nowhere.

## Function-calling models (e.g. Hermes)

```python
from stepstitch_service import build_function_tool_specs
tools = build_function_tool_specs()   # pass straight to the model's tools= parameter
```

The model emits a tool call (`get_trace_summary`, `generate_playwright_repro`, …); your
harness routes it to the deployed StepStitch service (carrying the admin token — auth stays
in your stack, not the model). The MCP `dispatch_tool(name, args, call_route)` helper shows
the exact request shape per tool if you want to reuse it.

## The repro → fix → verify loop (where the loop lives)

StepStitch closes the **repro → verify** half deterministically; the **fix/merge** half lives
in the consumer's stack. A safe, human-gated loop:

1. **Perceive** — a user reports a bug; StepStitch stores a scrubbed trace.
2. **Score** — the agent reads `get_replayability_score` to decide if it's reproducible.
3. **Repro** — the agent fetches `generate_playwright_repro` (deterministic, text only).
4. **Verify** — the agent runs that Playwright test **in the customer's CI/sandbox** (never
   against production). A green→red repro becomes a regression test.
5. **Fix (human-gated)** — the agent opens a **pull request** in the customer's repo with the
   new regression test and a proposed fix. The PR is the human gate: a reviewer merges, not
   the agent. StepStitch supplies the artifact; it never merges and never holds the repo's
   write credentials in core.

### Why a PR is the right actuator

A pull request is a *draft that requires human approval by construction* — consistent with
StepStitch's draft-only stance. The agent proposing a PR does not violate the no-autonomous-
write rule, because nothing lands without a reviewer. Ticket creation in ServiceNow/Salesforce
follows the same principle: governed, human-approved, never an autonomous agent tool (see
`copilot/action-policy.md` and `docs/integrations/`).

## What the agent must never do

- Run the generated Playwright against production.
- Treat a draft/preview as a created record (always say "draft").
- Reach for a destructive or direct-write operation — they are not on the agent surface, by
  design (`assert_no_destructive_operation()`).
- Use the Repair Loop (`/github/issue`, `/github/pr`) — it is a governed, admin-only,
  human-merged capability, deliberately off the agent surface (see docs/integrations/github.md).
