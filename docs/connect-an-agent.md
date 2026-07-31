# Connect a coding agent

```bash
npx stepstitch start --connect claude    # or codex, gemini
```

That is the whole thing — one process, one terminal. It starts the host, issues a
least-privilege token, registers StepStitch through **that agent's own `mcp add` command**,
checks that the server actually starts, and keeps serving.

One command on purpose. The two-terminal version this doc used to show
(`npx stepstitch start`, then `stepstitch connect claude`) failed twice on a fresh machine:
`npx` does not leave a persistent `stepstitch` on PATH for the second terminal, and
`connect` needs the admin token, which only the `start` process holds. `--connect` runs
where the credential already lives, so nobody pastes anything.

If the host is *already* running and you exported `STEPSTITCH_ADMIN_TOKEN` yourself,
`stepstitch connect claude` still works as a standalone command.

Everything below is for the cases `connect` does not cover — a platform it does not know, a
locked-down machine, or curiosity about what it wrote.

## What the agent is allowed to do

A connected agent gets the **`repros`** scope:

| It can | It cannot |
|---|---|
| read the failure summary, replayability and privacy posture | record a verdict on any fix |
| read the Safe Agent Packet and the compiled reproduction | draft or send anything to a system of record |
| read the fragility map and the minimal reproduction | delete a trace, purge data, or change retention |

The line that matters is the second row, first column: **an agent can never write the
evidence that says its own fix worked.** Only the separate `verify` scope may do that, and
`connect` never issues it. That separation is the product, not a setting.

## What is in the config, and what is not

The config carries a **path** (`STEPSTITCH_TOKEN_FILE`), never the token. Agent config files
get opened in editors, synced by dotfile managers, and pasted into bug reports; a bearer
token in one leaks by ordinary accident rather than by attack. The token lives in
`~/.stepstitch/agents/<agent-id>.token`, owner-only (0600), and `stepstitch mcp` reads it at
launch. Nothing is passed in `argv`, where `ps` would show it to every process on the box.

To revoke: delete that file, or revoke the agent in the dashboard.

## By hand, per platform

See exactly what `connect` would run, without running it:

```bash
stepstitch connect --dry-run
```

**Claude Code** — `~/.claude.json` (user) or `.mcp.json` (project):

```json
{
  "mcpServers": {
    "stepstitch": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "stepstitch-service[mcp]==<version>", "stepstitch", "mcp"],
      "env": {
        "STEPSTITCH_BASE_URL": "http://127.0.0.1:8321/api/stepstitch/v1",
        "STEPSTITCH_TOKEN_FILE": "/Users/you/.stepstitch/agents/<agent-id>.token"
      }
    }
  }
}
```

**Codex** (ChatGPT desktop app, CLI and IDE extension share one file) —
`~/.codex/config.toml`. Note this is **TOML**, and append rather than replace: other MCP
servers very likely live in the same file.

```toml
[mcp_servers.stepstitch]
command = "uvx"
args = ["--from", "stepstitch-service[mcp]==<version>", "stepstitch", "mcp"]

[mcp_servers.stepstitch.env]
STEPSTITCH_BASE_URL = "http://127.0.0.1:8321/api/stepstitch/v1"
STEPSTITCH_TOKEN_FILE = "/Users/you/.stepstitch/agents/<agent-id>.token"
```

**Gemini CLI and Antigravity** share `~/.gemini/config/mcp_config.json`, in the same shape
as Claude Code's block above.

## Pin the version

`stepstitch mcp` exists only from the release that introduced it. An **unpinned**
`stepstitch-service[mcp]` resolves to whatever is currently on PyPI, so a config can
register cleanly and then fail to launch — which is exactly how this was found during
development. `connect` pins the version it was run with; do the same by hand.

## If it does not connect

```bash
claude mcp list        # or: codex mcp list / gemini mcp list
```

Registered is not the same as working — these commands print the server name either way, so
read the status, not the presence of the line. The usual causes:

- **an engine without `stepstitch mcp`** — pin a version that ships it
- **StepStitch is not running** — `npx stepstitch start`
- **the token file is missing or unreadable** — re-run `stepstitch connect <agent>`

## Not covered by `connect`

Microsoft Copilot Studio, Google Vertex and AWS Bedrock are tenant/cloud configurations
against a reachable endpoint, not a local stdio launch, so they are a different setup path
rather than a flag on this command. See [docs/agent-platforms.md](agent-platforms.md) for
what has actually been verified and what has not.
