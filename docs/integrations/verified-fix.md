# Verified-Fix engine

StepStitch certifies that a candidate fix actually resolves a reproduced bug and remembers
it. StepStitch never runs code — your CI runs the deterministic repro and reports the
outcome; StepStitch derives the verdict and banks it in a regression corpus.

## Verdicts

`derive_verdict(pre_passed, post_passed)` — the pre-fix repro should FAIL (bug present), the
post-fix repro should PASS (bug gone):

| pre | post | verdict |
|---|---|---|
| passed | any | `not_reproduced` (invalid repro) |
| failed | (none) | `reproduced_unfixed` |
| failed | failed | `not_fixed` |
| failed | passed | `confirmed_fixed` (red->green) |

## Both halves are measured

`confirmed_fixed` requires a red run that actually happened. The shipped CI workflow
(`github_bridge/workflow.py`) is three jobs:

| Job | What it does |
|---|---|
| `red` | checks out `pre_ref` (default `HEAD^`), boots the app, runs the repro — expected to FAIL |
| `green` | checks out `fix_ref` (default the dispatched SHA), runs the same repro — expected to PASS |
| `report` | posts the two **measured** outcomes to `/verify` |

If either run does not complete (bad ref, app failed to boot), `report` records **nothing**
rather than guessing. A verdict resting on an assumed failure is not evidence — an earlier
version of this template hardcoded `pre_passed: false`, and it is the reason this section
exists.

## The CI credential

CI authenticates with a **`verify`-scoped agent token**, issued from the console's Agents tab
— not the admin token. That scope permits exactly two calls:

- `GET  /session/{id}/playwright` — fetch the reproduction to run
- `POST /session/{id}/verify` — post the measured outcome

Everything else (summaries, drafts, corpus, delivery, admin) is refused with 403. No read
tier can write a verdict, and `verify` cannot read evidence. Set it as the
`STEPSTITCH_VERIFY_TOKEN` repository secret.

Scoped agent tokens are enforced by host middleware that is active only in shared-admin-token
mode; OIDC deployments post verdicts with an OIDC admin identity instead.

## Endpoints (admin only, audited)

- `POST /stepstitch/v1/session/{id}/verify` — body
  `{ "pre_passed": bool, "post_passed": bool|null, "fix_ref": "...", "run_url": "..." }` ->
  stores the derived verdict. (Your CI calls this; the StepStitch repro workflow does it for you.)
- `GET /stepstitch/v1/session/{id}/verifications` — all verdicts for a trace.
- `GET /stepstitch/v1/corpus?verdict=confirmed_fixed&limit=50` — the regression corpus.

## Why it is the moat

Only an **executable** repro can certify a fix red->green — a session recording cannot. The
corpus compounds: every reproduced failure + its certified fix becomes permanent regression
evidence, and StepStitch is the neutral verifier regardless of which agent wrote the fix.
