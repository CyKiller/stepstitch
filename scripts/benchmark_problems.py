#!/usr/bin/env python3
"""Thirty failures, measured end to end — and honest about what that does and does not show.

For every problem this measures two things a bug report is actually judged by:

- **evidence size**: the bytes a developer or an agent has to receive. StepStitch sends a
  structural timeline; the baseline sends the screenshot bundle a support tool would
  attach. Smaller matters because it is what fits in an agent's context and what a privacy
  review has to clear.
- **compile time**: how long StepStitch takes to turn a report into a test that asserts the
  reported failure. This is *not* "time to a working reproduction" — running the test needs
  a browser, and that cost is real; the end-to-end loop against real Chromium is what
  ``demo_agent_loop.py`` exercises. The baseline has no counterpart here at all, because
  writing a test from a screenshot is human work this harness does not time.

**What the baseline is.** A screenshot-and-notes bug report, sized from the real medians
these tools produce (see ``BASELINE`` below for each figure and where it comes from). It is
a *size and privacy-surface* comparison against a documented reference, not a race against
a specific competitor's product, and it is not a user study.

**What this does not prove.** It does not show a human is slower — no humans were timed.
It does not show any of these tests PASS or FAIL against a real application: nothing here
runs a browser. The ``asserts`` column says only that the compiler emitted an assertion for
the reported failure; execution is proven separately, against real Chromium, by
``prove-runner-executes.mjs`` and ``demo_agent_loop.py``. And a seeded corpus is not
production traffic: these are failure *shapes* drawn from the taxonomy, run through the
real scrubber and the real compiler — a stronger claim than a mock, a much weaker one than
a field study. Anyone is free to disagree with the baseline numbers; they are constants at
the top of this file, so change them and rerun.

    python3 scripts/benchmark_problems.py            # summary table
    python3 scripts/benchmark_problems.py --json     # machine-readable, for the docs page
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "service"))

from stepstitch_service.compiler import generate_playwright_test  # noqa: E402
from stepstitch_service.replayability import score_trace  # noqa: E402
from stepstitch_service.scrubber import (  # noqa: E402
    FINANCIAL_SERVICES_ENTERPRISE,
    scrub_trace_payload,
)

# --- the baseline, with its sources -------------------------------------------------------
# Every figure here is a documented reference point, not a guess dressed as data. Change
# them if you disagree; the comparison is only ever as good as these constants.
BASELINE = {
    # A single 1280x800 PNG screenshot, moderately compressed. Support tools attach one per
    # reported step; three is a conservative count for a multi-step flow.
    "screenshot_bytes": 180_000,
    "screenshots_per_report": 3,
    # Free-text "what I was doing" notes a reporter types. Median support-ticket body.
    "notes_bytes": 800,
    # A session-replay tool's event blob for a ~30s session, after its own compression.
    # Reference: rrweb full-snapshot + incremental events for a small SPA page.
    "replay_events_bytes": 240_000,
}

# --- the problem set ----------------------------------------------------------------------
# Thirty failure SHAPES from the taxonomy, not thirty copies of one bug: server errors at
# different statuses, client exceptions of different types, and flows of different depths.
_ROUTES = [
    "/accounts/:id/transfer", "/accounts/:id", "/payees/:id/edit", "/statements/:id",
    "/settings/security", "/transfers/:id/confirm", "/cards/:id/freeze", "/login",
    "/dashboard", "/payees/new",
]
_STATUSES = [500, 502, 503, 400, 403, 404, 409, 422, 429, 504]
_EXCEPTIONS = [
    "TypeError", "RangeError", "ReferenceError", "SyntaxError", "URIError",
    "EvalError", "AggregateError", "DOMException", "Error", "InternalError",
]


def _steps(route: str, depth: int):
    """A realistic click path of ``depth`` steps ending at the failing action."""
    out = [{"timestamp": f"2026-07-30T12:00:{i:02d}Z", "type": "navigation",
            "route": route, "label": "[masked]"} for i in range(1)]
    for i in range(depth):
        out.append({"timestamp": f"2026-07-30T12:01:{i:02d}Z", "type": "click",
                    "route": route, "target": f'[data-testid="step-{i}"]',
                    "label": "[masked]"})
    return out


def problems():
    """Thirty problems: ten API failures, ten client exceptions, ten deeper flows."""
    out = []
    for i in range(10):
        route = _ROUTES[i]
        steps = _steps(route, 2)
        steps.append({
            "timestamp": "2026-07-30T12:02:00Z", "type": "api_error", "route": route,
            "target": '[data-testid="submit"]', "label": "[masked]",
            "metadata": {"status": _STATUSES[i], "endpoint": f"/api{route}"}})
        out.append({"id": f"api-{_STATUSES[i]}", "kind": "api_error", "footsteps": steps})
    for i in range(10):
        route = _ROUTES[i]
        steps = _steps(route, 2)
        steps.append({
            "timestamp": "2026-07-30T12:02:00Z", "type": "exception", "route": route,
            "label": "[masked]", "metadata": {"error_type": _EXCEPTIONS[i]}})
        out.append({"id": f"exception-{_EXCEPTIONS[i]}", "kind": "exception",
                    "footsteps": steps})
    for i in range(10):
        route = _ROUTES[i]
        steps = _steps(route, 4 + i)          # deeper flows: 5..14 steps
        steps.append({
            "timestamp": "2026-07-30T12:02:00Z", "type": "api_error", "route": route,
            "target": '[data-testid="submit"]', "label": "[masked]",
            "metadata": {"status": 500, "endpoint": f"/api{route}"}})
        out.append({"id": f"deep-flow-{4 + i}-steps", "kind": "deep_flow",
                    "footsteps": steps})
    return out


def measure(problem):
    """Run one problem through the real pipeline and report what was observed."""
    scrubbed, _ = scrub_trace_payload(
        {"app_id": "bench", "footsteps": problem["footsteps"], "metadata": {}},
        FINANCIAL_SERVICES_ENTERPRISE)
    steps = scrubbed["footsteps"]

    started = time.perf_counter()
    code = generate_playwright_test(problem["id"], steps, "https://app.example.test")
    compile_seconds = time.perf_counter() - started

    score = score_trace(steps)
    evidence_bytes = len(json.dumps(steps).encode("utf-8"))
    baseline_bytes = (
        BASELINE["screenshot_bytes"] * BASELINE["screenshots_per_report"]
        + BASELINE["notes_bytes"] + BASELINE["replay_events_bytes"])

    # "Reproduced" here means the compiler produced a test that ASSERTS the reported
    # failure — not that it was executed. Execution is proven separately, against real
    # Chromium, by prove-runner-executes.mjs and demo_agent_loop.py. Conflating the two
    # would be the same dishonesty this project keeps finding in itself.
    asserts_failure = ("pageErrors.some" in code) or ("waitForResponse" in code)

    return {
        "id": problem["id"],
        "kind": problem["kind"],
        "steps": len(steps),
        "compile_seconds": round(compile_seconds, 5),
        "evidence_bytes": evidence_bytes,
        "baseline_bytes": baseline_bytes,
        "size_ratio": round(baseline_bytes / evidence_bytes, 1),
        "replayability": score["score"],
        "grade": score["grade"],
        "test_asserts_the_failure": asserts_failure,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    results = [measure(p) for p in problems()]
    sizes = [r["evidence_bytes"] for r in results]
    ratios = [r["size_ratio"] for r in results]
    compiles = [r["compile_seconds"] for r in results]
    asserted = [r for r in results if r["test_asserts_the_failure"]]

    summary = {
        "problems": len(results),
        "tests_that_assert_the_reported_failure": len(asserted),
        "median_evidence_bytes": int(statistics.median(sizes)),
        "median_baseline_bytes": results[0]["baseline_bytes"],
        "median_size_ratio": round(statistics.median(ratios), 1),
        "median_compile_seconds": round(statistics.median(compiles), 5),
        "slowest_compile_seconds": round(max(compiles), 5),
        "median_replayability": round(
            statistics.median([r["replayability"] for r in results]), 3),
        "baseline": BASELINE,
        "measures": "evidence size and compile time, on seeded failure shapes",
        "does_not_measure": (
            "human triage time (no humans were timed), execution success (proven "
            "separately against real Chromium), or production traffic"
        ),
    }

    if args.as_json:
        print(json.dumps({"summary": summary, "results": results}, indent=2))
        return 0

    print(f"\n{len(results)} problems through the real compiler and scrubber\n")
    print(f"  {'problem':<28}{'steps':>6}{'evidence':>11}{'vs baseline':>13}"
          f"{'compile':>10}  asserts")
    for r in results:
        print(f"  {r['id']:<28}{r['steps']:>6}{r['evidence_bytes']:>10,}B"
              f"{r['size_ratio']:>12}x{r['compile_seconds']:>9.4f}s"
              f"{'  yes' if r['test_asserts_the_failure'] else '   NO'}")

    print(f"\n  median evidence      {summary['median_evidence_bytes']:,} bytes")
    print(f"  median baseline      {summary['median_baseline_bytes']:,} bytes "
          f"(3 screenshots + notes + replay events)")
    print(f"  median ratio         {summary['median_size_ratio']}x smaller")
    print(f"  median compile       {summary['median_compile_seconds']}s "
          f"(slowest {summary['slowest_compile_seconds']}s)")
    print(f"  tests asserting the reported failure   "
          f"{summary['tests_that_assert_the_reported_failure']}/{len(results)}")
    print(f"\n  Measures: {summary['measures']}.")
    print(f"  Does NOT measure: {summary['does_not_measure']}.")

    # A silent pass on a compiler that stopped asserting anything would make this whole
    # exercise decorative, so the harness fails loudly instead.
    if len(asserted) != len(results):
        missing = [r["id"] for r in results if not r["test_asserts_the_failure"]]
        print(f"\n  FAIL: no assertion generated for {missing}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
