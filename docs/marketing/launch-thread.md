# Launch thread

> Channel: X / Bluesky (primary), adaptable to a LinkedIn single-post by
> stitching the beats into paragraphs. One beat per altitude: outcome → how →
> privacy → agentic → open-core → CTA. No metrics. Canonical line stays
> "issue-to-repro infrastructure — not session replay."

---

## X / Bluesky version (8 posts)

**1/ (hook)**
A user hits a bug. Your team gets… a video to watch.

StepStitch turns that bug report into a Playwright test instead — one that fails
on the bug and passes once it's fixed. So it stays fixed.

Issue-to-repro infrastructure. Not session replay. 🧵

**2/ (outcome)**
The whole pitch in one line:

Turn a user-reported bug into a regression test.

No "watch this 4-minute recording." A failing test lands in your suite, you fix
it, the test goes green, and the bug can't quietly come back.

**3/ (how)**
How: a tiny tracker (zero runtime deps) records the *structural* steps — which
control, which route, in what order. Never the contents.

A deterministic compiler turns that trace into a Playwright test. Same trace →
same test, every time.

**4/ (privacy — the part that matters)**
Here's the part regulated teams care about:

StepStitch never captures screens, keystrokes, input values, page text, or raw
URLs. Every ingest hits a server-side scrubber before storage — bodies, headers,
cookies, console, DOM, screenshots are dropped outright.

The privacy boundary *is* the product.

**5/ (replayability score)**
It also tells you, up front, whether a report is even reproducible — a 0–1 score
and an A–F grade — before anyone burns an afternoon trying to repro it.

**6/ (agentic / MCP)**
And because the evidence is scrubbed and structured, it's safe to hand to agents.

There's an MCP server exposing read-only/draft tools, so Copilot, Claude, etc.
can pull a real scrubbed repro as context instead of guessing at "works on my
machine."

**7/ (open-core)**
It's open-core and Apache-2.0. Self-host the whole thing today.

Repo 👉 github.com/CyKiller/stepstitch
npm 👉 @stepstitch/tracker

**8/ (CTA)**
If you ship something where "a recording of the user" is a non-starter — fintech,
health, anything with PII — this was built for you.

Self-host free, or book a pilot. Either way: bugs that become tests, and stay
fixed.

---

## LinkedIn version (single post)

Most "user reported a bug" tools hand your engineers a video to watch. We didn't
want another recording — we wanted the bug as a regression test.

StepStitch is issue-to-repro infrastructure, not session replay. When a user
reports a problem, it turns that single report into a copyable Playwright test
that fails on the bug and passes once it's fixed — so it stays fixed.

The part that matters for regulated teams: it never captures screens, keystrokes,
input values, page text, or raw URLs. A server-side scrubber drops bodies,
headers, cookies, console, DOM and screenshots before anything is stored. The
privacy boundary is the product, not a setting — which is exactly why teams that
can't put session replay anywhere near their users can use this.

It's open-core (Apache-2.0), self-hostable today, and ships an MCP server so
coding agents can use a real scrubbed repro as context.

Self-host free or book a pilot 👉 github.com/CyKiller/stepstitch

---

## Notes
- Pin post 1 (X/Bluesky) for launch week.
- Attach the red→green demo clip to post 2 or 5 if available — the visual sells
  the "bug → passing test" beat better than words.
- Never reference the private Marvox/aGentSyS repos by link; "runs in production"
  framing only, architecture details on request.
