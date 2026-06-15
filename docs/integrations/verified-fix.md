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
