# Benchmark: 30 failure shapes

**Run it yourself:** `python3 scripts/benchmark_problems.py` (add `--json` for raw numbers).
It runs in CI on every commit, so these figures are reproducible rather than remembered.

## What was measured

Thirty failure shapes from the taxonomy — ten API errors across different statuses, ten
client exceptions across different error types, ten flows of increasing depth (5–14 steps)
— each put through the **real scrubber and the real compiler**.

| | StepStitch | Baseline |
|---|---|---|
| Median evidence per report | **609 bytes** | 780,800 bytes |
| Ratio | **~1,281× smaller** | — |
| Median compile time | 0.00004 s | not applicable (human work) |
| Tests asserting the reported failure | **30 / 30** | — |
| Median replayability | 0.84 | — |

## What the baseline is

A screenshot-and-notes bug report: three 1280×800 PNGs (180 KB each), an 800-byte
free-text description, and a 240 KB session-replay event blob for a ~30-second session.
Every one of those figures is a constant at the top of
[`scripts/benchmark_problems.py`](../scripts/benchmark_problems.py) with a comment saying
where it comes from. **If you think a number is wrong, change it and rerun** — the
comparison is only ever as good as those constants.

This is a **size and privacy-surface** comparison against a documented reference. It is not
a race against a named competitor's product.

## What this does not show

Being precise about this matters more than the headline number:

- **It does not show a human is slower.** No humans were timed. There is no
  time-to-triage claim here, because we did not measure one.
- **It does not show these tests pass or fail against a real application.** Nothing in this
  harness runs a browser. The "asserts" column says only that the compiler emitted an
  assertion for the reported failure. Execution is proven separately and against real
  Chromium by [`prove-runner-executes.mjs`](../scripts/prove-runner-executes.mjs) (red on a
  broken app, green on a fixed one, refusal on an edited test) and by
  [`demo_agent_loop.py`](../scripts/demo_agent_loop.py) (the full agent loop).
- **It is not production traffic.** A seeded corpus of failure shapes is a stronger claim
  than a mock and a much weaker one than a field study. Treat it as the former.

## Why size is the metric worth reporting

Evidence size is not a vanity number. It is what fits in an agent's context window, what a
privacy review has to clear, and what a customer's legal team has to be comfortable
leaving your building. A 609-byte structural timeline and a 780 KB screenshot bundle are
not the same artifact with different compression — one of them cannot contain a customer's
account balance, and that is the difference the ratio is standing in for.
