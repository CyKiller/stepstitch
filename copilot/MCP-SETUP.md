# StepStitch MCP server — universal agentic connector setup

This is the **"for all" path**: StepStitch exposes its Copilot-safe operations as a Model
Context Protocol (MCP) server, so an MCP client consumes the *same* audited,
read-only/draft surface with no bespoke adapter. The server is
`service/stepstitch_service/mcp_server.py`; run it with `stepstitch mcp`. See
[docs/PRODUCT-PLAN.md](../docs/PRODUCT-PLAN.md) (P1/P2).

**Which clients have actually been run against a real StepStitch — and which have not — is
recorded in [docs/agent-platforms.md](../docs/agent-platforms.md)**, with dates and
failures. Nothing is listed as working here on the strength of speaking MCP in principle.
For local coding agents the supported path is `stepstitch connect <agent>`
([docs/connect-an-agent.md](../docs/connect-an-agent.md)); this document covers the
remote/tenant clients, which `connect` deliberately does not handle.

> StepStitch is a capability **provider**, not an agent orchestrator. The MCP server only
> perceives, scores, compiles a repro, and **drafts** — it never files, deletes, purges,
> toggles capture, or returns raw trace bodies. The autonomy lives in the *client's* agent
> network; the trust boundary (server-side scrubber), admin auth, and `stepstitch.*`
> read-audit all stay in the StepStitch service behind the connector.

## The thirteen tools (identical to the OpenAPI pack)

| MCP tool | Service route | Returns |
|---|---|---|
| `list_recent_traces` | `GET /sessions` | trace list, no bodies |
| `get_trace_summary` | `GET /session/{id}/summary` | sanitized, structure-derived summary |
| `get_replayability_score` | `GET /session/{id}/replayability` | score · grade · warnings |
| `get_privacy_posture` | `GET /session/{id}/privacy-posture` | scrub report + never-captured list |
| `get_diagnostic_summary` | `GET /session/{id}/diagnostic-summary` | sanitized diagnostics + next step |
| `generate_playwright_repro` | `GET /session/{id}/playwright` | runnable Playwright code (text) |
| `match_verified_fixes` | `GET /session/{id}/similar-fixes` | structural matches to prior verified fixes (no raw values) |
| `get_attestation` | `GET /session/{id}/attestation` | signed, independently-verifiable evidence bundle (no raw values) |
| `get_fragility_map` | `GET /session/{id}/fragility` | per-step fragility ranking, worst-first (no raw values) |
| `generate_minimal_repro` | `GET /session/{id}/minimal-repro` | smallest failing path compiled to Playwright (no raw values) |
| `get_agent_packet` (**Safe Agent Packet**) | `GET /session/{id}/agent-packet` | the six rows above, composed into one call |
| `create_export_preview` | `POST /session/{id}/export-preview` | ServiceNow/Salesforce/Genesys **drafts** |
| `create_fs_export_preview` | `POST /session/{id}/financial-services-export-preview` | named FS support **draft** pack |

### The Safe Agent Packet

`get_agent_packet` is the one name behind the "safe packet to help fix it" pitch: instead of an
agent making five separate round-trips (summary, replayability, privacy posture, diagnostic,
repro), one call returns all five, still read-only and structure-derived — no new capability, just fewer
round-trips. Reach for the individual tools when you only need one field; reach for the packet
when you're handing a bug to an agent for the first time.

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
stepstitch mcp                                        # serves over stdio
```

It builds an authenticated `call_route` against your deployed service and serves the tools.
The token above is an **operator/admin** credential, appropriate for an operator console
where each read writes an audit event server-side.

> **Do not give this credential to a coding agent.** An admin token can record a verdict on
> a fix, which is the one thing an agent must never be able to do about its own work. Local
> agents get a scoped token from `stepstitch connect <agent>` instead, written to a
> 0600 file and referenced by path — see
> [docs/connect-an-agent.md](../docs/connect-an-agent.md).

### Transports
- **stdio** (shipped, via `stepstitch mcp`): for local/embedded MCP clients.
- **Streamable-HTTP / SSE** (for remote/cloud clients incl. **Copilot Studio**): run the
  same `COPILOT_SAFE_OPERATIONS` registry behind an HTTP MCP transport. The tool registry
  and `dispatch_tool` are transport-agnostic; only the serving shell differs. Until the
  HTTP shell is deployed, Copilot Studio can use the **OpenAPI custom connector**
  ([SETUP.md](SETUP.md)) — same thirteen operations, same governance.

## Per-client registration

**Microsoft Copilot Studio** — Tools → Add a tool → **Model Context Protocol** → point at
the StepStitch MCP server endpoint (remote HTTP transport) with the bearer credential.
Then apply [action-policy.md](action-policy.md) and the DLP/approval governance in
[SETUP.md](SETUP.md) §3. *(Or use the OpenAPI custom connector path today — see SETUP.md.)*

**Claude Code, Codex, Gemini CLI, Antigravity** — do not hand-edit config for these. Run
`stepstitch connect <agent>`, which registers through the agent's own `mcp add` and issues a
scoped token rather than an admin one
([docs/connect-an-agent.md](../docs/connect-an-agent.md)).

**OpenAI Agents SDK / LangGraph / Vertex / Bedrock** — *untested.* In principle each
registers the StepStitch MCP server as a tool source and treats the thirteen tools as
standard MCP tools, with no StepStitch-specific code. None of them has been run against a
real StepStitch, so this is a design expectation and not a verified result — it is recorded
as untested in [docs/agent-platforms.md](../docs/agent-platforms.md), and that table is the
one to trust.

## Public registry listing (prepared, not yet submitted)

A fully-built MCP server that no one can find is a wasted asset. `service/server.json` is a
ready-to-submit manifest for the **official MCP Registry**
(`registry.modelcontextprotocol.io`) — the canonical place a third-party server registers
itself. Researched and confirmed (2026-07): **Smithery, Glama, mcp.so, and PulseMCP are
registry *aggregators*** — they scrape the official registry's public REST API on their own
schedule rather than taking separate manual submissions, so publishing once to the official
registry is the one action that reaches all of them.

**This submission is intentionally left for the maintainer to run** — it requires a live
GitHub OAuth device-flow login (`mcp-publisher login github`), which only the account owner
can authorize.

Steps (owner-run, from `service/`):

```bash
# 1. Install the CLI (macOS/Linux; see MCP docs for Windows/Homebrew)
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" \
  | tar xz mcp-publisher && sudo mv mcp-publisher /usr/local/bin/

# 2. Authenticate as CyKiller (opens a GitHub device-flow prompt)
mcp-publisher login github

# 3. Publish the prepared manifest (service/server.json)
cd service && mcp-publisher publish
```

Prerequisites already satisfied by this repo:
- `stepstitch-service` is live on PyPI (`registryType: "pypi"` in `server.json`).
- Ownership verification is in place: `service/README.md` carries the required
  `<!-- mcp-name: io.github.CyKiller/stepstitch -->` marker (becomes the PyPI
  description via `readme = "README.md"` in `service/pyproject.toml`), and it **must
  match `server.json`'s `name` field exactly** — the registry rejects a mismatch.
- `service/server.json`'s `version` must be bumped alongside every PyPI release
  (`stepstitch-service`'s version in `pyproject.toml`) — the registry checks the PyPI
  version at that identifier actually exists.

After publishing, verify with:
```bash
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.CyKiller/stepstitch"
```

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
