# Show HN launch post

> Channel: Hacker News (Show HN). Tone: dev-first, substance-only, no marketing
> adjectives. The repo and the demo are the proof — there are no usage metrics,
> so don't imply any. Keep the title under 80 chars.

---

## Title

**Show HN: StepStitch – turn a user-reported bug into a Playwright test, no session replay**

## Post body

StepStitch is issue-to-repro infrastructure — not session replay. When a user
reports a bug, it turns that single report into a scrubbed event timeline, a
replayability score, and a copyable Playwright reproduction — without ever
capturing screens, keystrokes, input values, page text, or raw URLs.

The thing I kept hitting: most "user reported a bug" tools hand you a video to
watch. I didn't want another recording. I wanted the bug as a regression test —
one that fails on the bug and passes once it's fixed, so it stays fixed. So the
output here is a test, not a replay.

New in 0.6 (and the reason I'm posting now): three things I haven't seen elsewhere,
each an open-source API + an MCP tool — (1) **Fix Memory**: every confirmed red→green fix
becomes a structural fingerprint, so a new bug surfaces "you've fixed this shape before"
without an agent ever seeing raw data; (2) **Evidence Attestation**: a signed, canonical
evidence bundle you can verify independently with `cosign verify-blob` (I hold no key — you
sign with yours); (3) **Fragility Radar**: predicts which steps will break + emits a minimal
repro. Install paths are all live now: `npm i @stepstitch/tracker`,
`pip install stepstitch-service`, `docker pull ghcr.io/cykiller/stepstitch-api`.

How it works:

- A tiny tracker (`@stepstitch/tracker`, zero runtime deps) records *structural*
  steps — which control, which route, in what order — never the contents.
- Every ingest hits a server-side scrubber before storage. SSNs, card/account
  numbers, email, phone, long IDs and raw URLs are redacted from free text;
  routes are re-templated; request/response bodies, headers, cookies, console,
  DOM and screenshots are dropped outright (not optional).
- A deterministic compiler turns the trace into a Playwright test. Same trace →
  same test, every time. It's text only; it never runs against production.
- A 0–1 replayability score (and an A–F grade) tells you up front whether the
  report is actually reproducible before anyone spends time on it.

Why it's built this way: it's aimed at teams that *can't* use session replay —
financial services, healthcare — because they can't have screens and PII sitting
in a vendor's database. The privacy boundary is the product, not a setting.

It's open-core and Apache-2.0. You can self-host the whole thing today. There's
also an MCP server that exposes the read-only/draft tools, so coding agents
(Copilot, Claude, etc.) can pull a scrubbed repro as context instead of guessing.

- Repo: https://github.com/CyKiller/stepstitch
- npm: https://www.npmjs.com/package/@stepstitch/tracker

Honest about the stage: it runs in production in two of my own projects (one
treats it as a required boot-time subsystem; the other docks it into an agent
swarm as a capability provider), but those repos are private, so I can't link
them — happy to answer architecture questions here instead. No customer metrics
to wave around yet; I'd rather show the code and the generated test.

Would especially like feedback on the scrub boundary and the determinism of the
compiler — those are the two things that have to be airtight for this to be
trustworthy.

---

## First-comment seed (post yourself, ~1 min after)

A bit more on the threat model people usually ask about: the SDK only ever sees
structure, but I don't trust the SDK as the privacy boundary — the *server-side*
scrubber is. Even a misconfigured or malicious client can't get a value past it,
because the forbidden keys (bodies, headers, cookies, console, DOM, screenshots)
are dropped at ingest regardless of what the client sends. Retention is a
configurable window with a hard purge, and there's an org-wide kill switch
(`STEPSTITCH_CAPTURE_DISABLED=1`) that halts ingestion with no redeploy. Glad to
go deeper on any of it.

---

## Posting checklist
- [ ] Post Tue–Thu, ~8–10am ET (HN morning).
- [ ] Title stays "Show HN:" prefixed, under 80 chars, no hype words.
- [ ] Be present in the thread for the first 3–4 hours to answer fast.
- [ ] Lead every reply with substance; never link the private repos.
- [ ] Have the red→green demo (`/demo`) ready to paste if asked "can I see it?".
