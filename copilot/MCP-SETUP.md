# StepStitch MCP server — universal agentic connector setup

This is the **"for all" path**: StepStitch exposes its Copilot-safe operations as a Model
Context Protocol (MCP) server, so any MCP client — Microsoft Copilot Studio, OpenAI,
Google Vertex/Gemini, LangGraph, AWS Bedrock, Claude — consumes the *same* audited,
read-only/draft surface with no bespoke adapter. The server is
`service/stepstitch_service/mcp_server.py`; run it with `mcp_cli.py`. See
[docs/PRODUCT-PLAN.md](../docs/PRODUCT-PLAN.md) (P1/P2).

> StepStitch is a capability **provider**, not an agent orchestrator. The MCP server only
> perceives, scores, compiles a repro, and **drafts** — it never files, deletes, purges,
> toggles capture, or returns raw trace bodies. The autonomy lives in the *client's* agent
> network; the trust boundary (server-side scrubber), admin auth, and `stepstitch.*`
> read-audit all stay in the StepStitch service behind the connector.

## The nine tools (identical to the OpenAPI pack)

| MCP tool | Service route | Returns |
|---|---|---|
| `list_recent_traces` | `GET /sessions` | trace list, no bodies |
| `get_trace_summary` | `GET /session/{id}/summary` | sanitized, structure-derived summary |
| `get_replayability_score` | `GET /session/{id}/replayability` | score · grade · warnings |
| `get_privacy_posture` | `GET /session/{id}/privacy-posture` | scrub report + never-captured list |
| `get_diagnostic_summary` | `GET /session/{id}/diagnostic-summary` | sanitized diagnostics + next step |
| `generate_playwright_repro` | `GET /session/{id}/playwright` | runnable Playwright code (text) |
| `match_verified_fixes` | `GET /session/{id}/similar-fixes` | structural matches to prior verified fixes (no NPI) |
| `create_export_preview` | `POST /session/{id}/export-preview` | ServiceNow/Salesforce/Genesys **drafts** |
| `create_fs_export_preview` | `POST /session/{id}/financial-services-export-preview` | named FS support **draft** pack |

These come from one source of truth — `COPILOT_SAFE_OPERATIONS` — shared with
`openapi-v2.json` and the live routes, drift-guarded by
`service/tests/test_mcp_surface.py`. Tools that must **never** appear (delete, purge,
kill-switch, retention, raw `GET /session/{id}`) are blocked at import by
`assert_no_destructive_operation()`.

## Run the server

```bash
pip install 'stepstitch-service[mcp]'
export STEPSTITCH_BASE_URL="https://stepstitch.internal/api/stepstitch/v1"
export STEPSTITCH_TOKEN="<operator-bearer-token>"   # admin; every read is audited
python -m stepstitch_service.mcp_cli                  # serves over stdio
```

`mcp_cli` builds an authenticated `call_route` against your deployed service and serves
the tools. The token is an **operator/admin** credential — the same SSO the StepStitch
admin API already uses — because these are operator tools and each read writes an audit
event server-side.

### Transports
- **stdio** (shipped, via `mcp_cli`): for local/embedded MCP clients — Claude, the OpenAI
  Agents SDK, a LangGraph process, Cursor, etc.
- **Streamable-HTTP / SSE** (for remote/cloud clients incl. **Copilot Studio**): run the
  same `COPILOT_SAFE_OPERATIONS` registry behind an HTTP MCP transport. The tool registry
  and `dispatch_tool` are transport-agnostic; only the serving shell differs. Until the
  HTTP shell is deployed, Copilot Studio can use the **OpenAPI custom connector**
  ([SETUP.md](SETUP.md)) — same eight operations, same governance.

## Per-client registration

**Microsoft Copilot Studio** — Tools → Add a tool → **Model Context Protocol** → point at
the StepStitch MCP server endpoint (remote HTTP transport) with the bearer credential.
Then apply [action-policy.md](action-policy.md) and the DLP/approval governance in
[SETUP.md](SETUP.md) §3. *(Or use the OpenAPI custom connector path today — see SETUP.md.)*

**Claude / Claude Code** — add to the MCP server list, command
`python -m stepstitch_service.mcp_cli` with `STEPSTITCH_BASE_URL` / `STEPSTITCH_TOKEN` in env.

**OpenAI Agents SDK / LangGraph / Vertex / Bedrock** — register the StepStitch MCP server
as a tool source; each treats the eight tools as standard MCP tools. No StepStitch-specific
code required.

## Governance carried over (unchanged from the connector path)
- Read-only / draft-only; record creation happens **only** via the client's native
  connectors/flows after human approval, mapped per [connector-field-map.md](connector-field-map.md).
- Reuse [system-prompt.md](system-prompt.md) as the agent's instructions and
  [action-policy.md](action-policy.md) as its guardrail — both are transport-independent.
- Keep StepStitch and the system-of-record connectors in one DLP group so a draft can feed
  a create but a summary cannot be exfiltrated to an unmanaged connector.

## See also
- The agent capability story for buyers: the site's **/agents** page (what agents can and
  cannot do) and **/quickstart** (10-minute wire-up).
- The end-to-end evidence an agent reads/drafts: **/demo** and [`../demo/README.md`](../demo/README.md).
