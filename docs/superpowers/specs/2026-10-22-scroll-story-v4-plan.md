# "Follow one request" v4 — phased plan (live surface, high-key)

Status: proposal, 2026-10-22. Supersedes the v3 design and the greybox previs on branch
`feat/story-previs` (dark, a continuous 3D camera flight, hard to follow; rejected).

Brief: self-authored under explicit creative delegation ("what is the best plan … scan our
features and workflow to bring this to life"). Method: the Scrollcraft skill
(nateherkai/scroll-craft, MIT), steps 0–5, with its verification harness.

## Decisions

- **Grammar: Live surface.** The page behaves like the product: a light-theme rendering of the
  real StepStitch console, built from its real UI vocabulary and the committed demo data, with
  scroll driving its state. Why the other seven lost: filmic one-shot and continuous world are the
  dark camera flight we rejected; typographic poster and gallery cannot show a workflow; chaptered
  editorial and rhythmic cutlist tell the story instead of showing it; split stage is the
  runner-up and is borrowed for phone composition (surface above, status text below).
- **World: High-key.** The site's light tokens (bg `#fafafa`, surface `#ffffff`, ink `#18181b`,
  one accent `#047857`), soft offset shadows, no dark canvas. Red only on the failing run, green
  only on proof. Geist Sans and Mono.
- **No three.js in v1.** "Zoom into the architecture" is done with CSS transforms on the
  surface: a slight perspective tilt that flattens, and focus zooms into the panel that is
  changing. About 0 KB extra instead of ~250 KB, and nothing renders dark or muddy. The
  three / React Three Fiber dependencies added for the previs are removed.
- **One object to follow:** the customer's report. It is the same row, card or packet in every
  beat, so the eye never has to search.
- **Two depths come from the product itself.** The real console has a plain-language toggle
  (Evidence → "What happened", Repro → "The test", Verify → "Proof it's fixed", Agent view →
  "What an AI sees", Attestation → "Signed record"). The story uses that switch, so plain and
  technical are the product's own words.
- **Signature move: the share dial.** The visitor sets what an AI assistant may receive
  (none, summaries, repros, drafts) and the "What an AI sees" panel updates with the literal
  packet, while the "never from the customer" list stays locked. No other site does this.
- **Peak: proof.** The test fails before the fix and passes after; the signed record verifies
  ("8/8 checks passed", the real `stepstitch proof verify` output). Largest scroll span.
- **Close: an actual input.** A command line holding `npx stepstitch start --connect claude`
  with copy, plus "Plan a pilot" as the secondary action.

## The journey (six beats, all real)

| # | Beat | What the visitor sees (real source) | Receipt on screen |
|---|---|---|---|
| 1 | Recognition | A payment fails in TinyTransfer (examples/tiny-transfer): consent box, Send, HTTP 500, "Report a problem" with the customer's own words | The app's own error state |
| 2 | Turn | What actually left the browser: TinyTransfer's printed outbound payload, account, amount and email absent, route templated | Scrub report: fields removed (real count from the run) |
| 3 | Substance | The console board: the report lands in Untriaged, gets grade A (0.96), joins its shape when the same failure repeats, "You have fixed this before" when Fix Memory matches | Real stage names and counts from demo data |
| 4 | Range (signature) | "What an AI sees": the share dial, the literal agent packet per scope, the locked never-list; the Agents page issues a scoped key | Packet JSON for the chosen scope |
| 5 | Peak | "Proof it's fixed": run before the fix fails, run after passes; one failed attempt shown honestly as "still failing" first; verdict confirmed fixed | `proof verify`: 8/8 checks passed |
| 6 | Commitment | The command line, ready to run; drafts and PR shown as drafts a person merges | `npx stepstitch start --connect claude` |

Feeling curve: recognition (mild unease) → relief (nothing private left) → control (it's sorted
and graded) → trust (you set the AI's limits) → certainty (proven, the peak) → readiness (one
command). No two adjacent beats share a feeling.

## Honesty fixes the scan found (must land before the story)

- "Forty reports" is not in any dataset (the demo has 6 traces). Use the real repeat: the
  second transfer failure joining the first shape.
- Priority is derived for Linear, Salesforce, Zendesk and Slack only; ServiceNow stays at 3 and
  Jira has none. Caption: "Drafts carry the priority each tool supports."
- The demo artifacts disagree: `fixproof.json` describes a `TypeError` with fake commits while
  the evidence bundle says HTTP 500 for the same trace id. Regenerate so one failure runs through
  bundle, proof and console data.
- Tickets and PRs are drafts; StepStitch never merges. Diagnostics from replay are
  `not_verified` for customer data and say so.
- The CI verdicts and the fix-check verdicts are different vocabularies; each beat names the
  right one.

## Phases

**Phase 0 — Brief and score (½ day).** Write `BRIEF.md` (Scrollcraft step 0, self-authored under
delegation), the journey above, feeling curve, peak, signature move, grammar rationale and the
device score (pin, count, reveal, pointer, focus-zoom; at least four families, none repeated
back to back). Gate: you approve one page.

**Phase 1 — Make the evidence coherent (1–2 days).** One synthetic failure (the TinyTransfer 500)
regenerated through `scripts/demo_red_to_green.py`, `stepstitch proof export`, and the console
demo dataset, so every receipt matches. Fix the priority and "forty" wording. Capture real
outputs (`proof verify` 8/8, `policy verify` 19/19, scrub report). CI green, STATUS.md updated.
Gate: CI green.

**Phase 2 — Style frames (1–2 days).** Static, real-HTML frames of each beat at its key state, in
the light theme, at 1440×900 and 390×844, on a hidden `/story/frames` route. No motion yet. Gate:
you approve the look.

**Phase 3 — Build the surface (4–5 days).** Scroll choreography with pins and CSS focus-zooms,
the share dial, the honest proof loop, the command-line close, both depths through the
plain-language switch, separate phone composition, reduced-motion as complete still states,
analytics events. Remove the previs's three.js code and dependencies.

**Phase 4 — Verify and one feedback round (2 days).** Scrollcraft `shoot.mjs` contact sheets
(desktop, 390px, reduced motion): no dead scroll, contrast on the composited page, cues reach
full opacity. Keyboard and screen-reader pass, Lighthouse against main, the feel check. Then a
Vercel preview link and one round of your section-by-section feedback, applied and re-shot.

**Phase 5 — Launch and measure (1 day, then 2 weeks).** Replace "In plain words" on the homepage
above the live demo; Vercel Web Analytics on; a five-person hallway test (three non-technical);
tune the weakest beat once.

Total: about two weeks of work across five approval gates.

## Out of scope / separate

- The Railway auto-deploy fix and a 0.12.1 release (independent; both need your OK).
- Generated photography (not needed: the live-surface grammar shows the product itself).
- A 3D object: reconsidered only after launch data, and only if it makes a beat clearer.
