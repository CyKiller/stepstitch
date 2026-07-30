# Agent platforms — what has actually been verified

A living table. Every row is something that was **run**, on a date, with the result
recorded — including the failures. A platform is added here only after it has been
exercised against a real StepStitch, never because it "speaks MCP" in principle.

## Verified

| Platform | Connects | Tools reachable (scoped) | Real LLM fixed a bug | Date |
|---|---|---|---|---|
| Claude Code 2.1.144 | **yes** (`✓ Connected`) | **13/13** with a `repros` token | **not yet** — CLI auth blocked | 2026-07-30 |
| Codex (ChatGPT app/CLI/IDE) | not tested | — | — | — |
| Gemini CLI 0.1.4 | not tested | — | — | — |
| Antigravity | not tested | — | — | — |

## What "not yet" means for Claude Code

The connection is real and was verified live: `claude mcp list` reports `✓ Connected`, and a
`repros`-scoped token reaches all thirteen tools while being refused a verdict write (403)
and a delete (403).

What has **not** been demonstrated is a real language model reading the packet and fixing
the bug. The standalone `claude` CLI on the test machine held a credential last written
six weeks earlier and rejected every request with `401 OAuth access token has been revoked`
— note that the desktop app and the CLI use **separate** credential stores, so being signed
into one does not authenticate the other. Gemini CLI 0.1.4 authenticated successfully but
its Code Assist backend returned a persistent `500 INTERNAL` on even a one-word prompt.

Neither is a StepStitch defect, and neither is a reason to claim the trial passed.

## What was demonstrated without an LLM

Two things, both measured on 2026-07-30 against a seeded `TypeError` in a scratch app:

**The packet contains enough to locate the defect.** Consulting *only* what came back over
MCP — no repository search, no file listing — the packet named the failing call
(`form.amount.toFixed is not a function`), the file (`transfer.js`) and the line (`11:31`).
Applying the indicated fix and asking StepStitch to verify returned **`fixed`**, judged by
the frozen script.

This is a weaker claim than "an agent fixed it" and is labelled as such. It shows the
*information* is present; it does not show a model will use it well.

**The referee cannot be talked out of it.** With the bug restored and a weakened test
written to disk (`test('...', async () => {})`, assertion deleted), verification returned
**`still_failing`** — still judged by the frozen bytes, because verification reruns the
recorded script rather than whatever is in the working tree.

## Not covered

Microsoft Copilot Studio, Google Vertex and AWS Bedrock are tenant/cloud configurations
against a reachable endpoint, not a local stdio launch. They are a separate setup path and
have not been tested; see [connect-an-agent.md](connect-an-agent.md).
