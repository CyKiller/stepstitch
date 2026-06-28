# StepStitch Battlecard

> One-liner: **The troubleshooting evidence you're *allowed* to give an AI — customer-controlled,
> default-safe, and independently verifiable.** Works where session replay is blind (agents, APIs,
> backends).

## The 30-second pitch
A user hits a bug. Most tools hand your team a recording to *watch*. StepStitch turns that report
into a **Playwright test that stays fixed** — without ever recording the user's screen, keystrokes,
values, or PII. It's self-hosted (you hold the data), MCP-native (any agent consumes a *scrubbed*
view, scoped per agent), and 0.6 adds three things no competitor has: **Fix Memory**, **signed
Evidence Attestation**, and **Fragility Radar**.

## The control matrix (who controls what)
| | Control locus | Default safety | Deterministic repro | Verified-fix corpus | Agent-native | Signed evidence |
|---|---|---|---|---|---|---|
| Session replay (FullStory, LogRocket) | **Vendor cloud** | Record-then-redact ✗ | ✗ | ✗ | ✗ (blind to agents) | ✗ |
| LLM observability (Langfuse OSS) | Customer | Customer masking | ✗ | ✗ | tracing only | ✗ |
| Agent runtimes (OpenClaw) | Customer-run, **ungoverned** | Full perms ✗ | ✗ | ✗ | *is* the agent | ✗ |
| Error tracking (Sentry, Datadog) | Vendor/customer | n/a | ✗ | ✗ | partial (MCP) | ✗ |
| **StepStitch** | **Customer** | **Never-capture ✓** | **✓** | **✓** | **✓ governed** | **✓ tenant-key** |

## Win themes by competitor
**vs. Session replay** — *Win, decisively.* "Don't ship a recording of your users to a vendor.
We never capture it in the first place — and we see agent/API/backend traffic that has no screen to
record." Lead here.

**vs. Langfuse / LLM observability** — *Win on the combination.* They self-host + mask too — don't
lead with "self-hosted." Lead with: **no-code governance console + per-agent scoped tokens +
provable only-tighten scrub + deterministic repro + signed attestation.** They *trace*; we
*reproduce and prove.*

**vs. OpenClaw / agent runtimes** — *Not a competitor — the governed counterpoint.* They run
full-permission agents (1-in-12 marketplace skills were malicious). We're the least-privilege,
attestable evidence layer. Best played *with* them: a StepStitch MCP skill gives their agent a
scrubbed, scoped repro instead of raw access.

**vs. Sentry / Datadog** — *Match on repro, concede breadth.* They own scale + dashboards; we own
the reproducible, privacy-safe, agent-ready evidence they stop short of.

## Objection handling
- *"Isn't this just session replay with masking?"* → No. Masking is record-then-redact (the data
  still reaches the vendor). We never capture screens/values/PII — and the output is a **test**, not
  a clip.
- *"Langfuse already self-hosts with masking."* → True, and it's table-stakes now. Our edge is the
  *combination* above + deterministic repro + signed attestation, not "self-hosted" alone.
- *"How do we trust your evidence?"* → You don't have to. Evidence Attestation is **signed with
  your key** and verifiable by anyone with `cosign verify-blob` — we hold no key.
- *"Is the dashboard required?"* → No. Everything is an API + MCP tool; the dashboard is an optional,
  opinionated reference. Build your own.

## Proof points (all open-source, verifiable)
- `tests/redaction-proof.test.ts` (client) + `test_scrubber.py` (server) — NPI never egresses.
- Deterministic compiler — same trace → same test, every time.
- 12 read-only/draft MCP tools; no destructive op on the agent surface (`test_mcp_surface.py`).
- Provenance, SBOM, SRI on every release; npm + PyPI + Docker public.

## Timing
EU AI Act enforceable **Aug 2026**; DORA live now. "Least-privilege tool-call governance +
human-in-the-loop + data residency" is the named 2026 buying pattern — StepStitch already *is* that
shape.
