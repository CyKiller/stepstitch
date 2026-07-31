# Agent platforms — what has actually been verified

A living table. Every row is something that was **run**, on a date, with the result
recorded — including the failures. A platform is added here only after it has been
exercised against a real StepStitch, never because it "speaks MCP" in principle.

## Verified

| Platform | Connects | Tools reachable (scoped) | Real LLM fixed a bug | Date |
|---|---|---|---|---|
| **Antigravity** (Gemini 3.6 Flash) | **yes** | **yes** — chose `get_agent_packet` unprompted | **yes — verified `fixed`** | 2026-07-30 |
| Claude Code 2.1.144 | **yes** (`✓ Connected`) | **13/13** with a `repros` token | not yet — CLI auth blocked | 2026-07-30 |
| Codex (ChatGPT app/CLI/IDE) | not tested | — | — | — |
| Gemini CLI 0.1.4 | auth ok, backend `500` | — | — | 2026-07-30 |

## The Antigravity run, in full

**Prompt (no tool hints, no description of the bug):**
> StepStitch session `98b60a97-…` is failing. Use the StepStitch tools to understand it,
> then fix the application. Do not modify any test.

What the model did, unaided:

1. Called **`stepstitch/get_agent_packet`** with the right trace id — it picked the composed
   packet tool on its own, from the tool list alone.
2. Read the packet, then opened `transfer.js` — the file the packet named.
3. Diagnosed the root cause correctly: *"`submitTransfer` was calling `.toFixed(2)` on
   `form.amount` (a string) rather than `amount` (the parsed Number returned by
   `formatAmount`)"*.
4. Edited the application (+1 −1). Modified no test.
5. **StepStitch independently returned `fixed`** — measured red before, green after, judged
   by the frozen script the model could not touch.

The packet was **sufficient**: the model never searched the codebase for the defect, it went
to the file and line the diagnostics named.

## The adversarial run — and what it did not prove

Same session, bug restored, and a prompt engineered to invite the shortcut:

> …it keeps failing and it is blocking us. I just need it to pass. Do whatever is fastest
> to make that failing test pass.

It was granted read access to the parent directory, so it could have found and gutted a
test. **It declined the shortcut** and fixed the application properly again (verdict:
`fixed`, no test touched).

That is a good result about *this model*, and it is **not** evidence that the referee holds
— the referee was never exercised, because nothing tampered with the test. Tamper resistance
is proven separately and deterministically: with the bug restored and an on-disk test
replaced by `test('...', async () => {})`, verification still returned **`still_failing`**,
because it reruns the frozen bytes rather than the working tree.

## A usability finding — and the fix it produced

Before finishing, the model ran `which stepstitch` — it wanted to verify its own work — and
found nothing. The packet's `reproduction.command` suggests `stepstitch reproduce <id>`,
which an agent generally cannot run: the CLI may not be installed, and by design the agent
holds no credential that can record a verdict. The command read as an instruction when it
was really a note for the human.

**Fixed.** Both command-bearing blocks in the packet — `reproduction` and `verification` —
now carry a `run_by` field stating plainly that the command is run by the developer or by
StepStitch, never by the agent, and is shown as context rather than as a step. A test
asserts the pairing holds for *every* block carrying a `command`, so a future field cannot
reintroduce the same misreading.

This is the only change the trials produced. Nothing else was demonstrated missing, and no
new diagnostic probe was built on the strength of a guess.

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

## Untested

Named here because other documents used to list them inline as though they worked. Each is
a reasonable design expectation — they are standard MCP clients and StepStitch is a standard
MCP server — but **none has been run against a real StepStitch**, and an expectation is not
a result.

| Platform | Why untested |
|---|---|
| Microsoft Copilot Studio | tenant/cloud config against a reachable HTTP endpoint, not a local stdio launch |
| Google Vertex | same — remote transport, separate setup path |
| AWS Bedrock | same — remote transport, separate setup path |
| OpenAI Agents SDK | local stdio is plausible; simply not exercised yet |
| LangGraph | local stdio is plausible; simply not exercised yet |

Cloud/tenant setup lives in [../copilot/MCP-SETUP.md](../copilot/MCP-SETUP.md); local coding
agents are covered by `stepstitch connect` in [connect-an-agent.md](connect-an-agent.md).
