"""Did the fix work? The half of the loop the agent does not get to answer.

An agent proposes a change; StepStitch reruns the **frozen** reproduction and reports what
it observed. Four answers, and each means something different to the person reading it:

- ``fixed`` — the failure was measured before the change and is gone after it.
- ``still_failing`` — the same failure, in the same way.
- ``different_failure`` — it fails after the change, but not how it failed before. The
  patch moved the problem rather than solving it, and calling that "still failing" would
  hide the most useful thing anyone could tell the developer.
- ``unable_to_verify`` — no verdict. A missing red run, a refused script, a broken
  toolchain. Never a guess.

``unable_to_verify`` is deliberately the fallback for anything ambiguous: this module
exists so that "proven fixed" means proven.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .runner import (
    INCONCLUSIVE,
    NEEDS_SETUP,
    NOT_REPRODUCED,
    REPRODUCED,
    ReproductionResult,
)

FIXED = "fixed"
STILL_FAILING = "still_failing"
DIFFERENT_FAILURE = "different_failure"
UNABLE_TO_VERIFY = "unable_to_verify"

# Lines Playwright prints when an assertion fails. The first match is the most specific
# statement of what went wrong, which is what makes two failures comparable.
_SIGNATURE_PATTERNS = (
    # `expect(...).toBe(false)` with a message: the message is the assertion's own words.
    re.compile(r"^\s*(?:Error|✘|×|\d+\))?\s*(?:expect|Expected).*$", re.M),
    re.compile(r"^\s*Error:\s*(.+)$", re.M),
    re.compile(r"^\s*(\w*Error):\s*(.+)$", re.M),
)


def failure_signature(transcript: str) -> str:
    """A short, comparable description of HOW a run failed.

    Deliberately coarse: it only has to tell "the same failure" from "a different one",
    and an over-precise signature (line numbers, timings, ids) would call every rerun a
    different failure.
    """
    if not transcript:
        return ""
    for pattern in _SIGNATURE_PATTERNS:
        match = pattern.search(transcript)
        if match:
            line = match.group(0).strip()
            # Drop volatile detail so two runs of the same failure agree.
            line = re.sub(r"\b\d+(\.\d+)?(ms|s)\b", "", line)
            line = re.sub(r"\b[0-9a-f]{8,}\b", "", line)
            line = re.sub(r":\d+:\d+", "", line)
            line = re.sub(r"\s+", " ", line).strip()
            return line[:200]
    return ""


@dataclass
class FixVerdict:
    """What StepStitch observed across the red and green runs."""

    verdict: str
    detail: str
    script_sha256: str = ""
    red_verdict: str = ""
    green_verdict: str = ""
    red_signature: str = ""
    green_signature: str = ""
    flaky: bool = False
    # False for sessions frozen before the envelope was stored with the freeze. The script
    # hash is still enforced for those — the referee holds — but "same experiment" is
    # reduced to "same bytes", and a `measured` grade obtained that way is weaker than one
    # with the envelope pinned. Saying so beats silently equating them.
    envelope_enforced: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "detail": self.detail,
            "script_sha256": self.script_sha256,
            "red_verdict": self.red_verdict,
            "green_verdict": self.green_verdict,
            "red_signature": self.red_signature,
            "green_signature": self.green_signature,
            "flaky": self.flaky,
            "envelope_enforced": self.envelope_enforced,
        }


def derive_fix_verdict(
    *,
    red_verdict: Optional[str],
    red_signature: str,
    after: ReproductionResult,
    envelope_enforced: bool = False,
) -> FixVerdict:
    """Compare the recorded red run against the run made after the change.

    ``red_verdict`` and ``red_signature`` come from the frozen record — measured before the
    agent touched anything. ``after`` is what just happened.
    """
    green_signature = ""
    for attempt in after.runs:
        if not attempt.passed and attempt.transcript:
            green_signature = failure_signature(attempt.transcript)
            if green_signature:
                break

    base = FixVerdict(
        verdict=UNABLE_TO_VERIFY, detail="", script_sha256=after.script_sha256,
        red_verdict=red_verdict or "", green_verdict=after.verdict,
        red_signature=red_signature, green_signature=green_signature,
        flaky=after.flaky, envelope_enforced=envelope_enforced,
    )

    if red_verdict != REPRODUCED:
        base.detail = (
            "there is no measured red run for this session, so a passing test proves "
            "nothing about the change. Reproduce the failure first — a fix can only be "
            "proven against a failure that was observed."
        )
        return base

    if after.verdict == NOT_REPRODUCED:
        base.verdict = FIXED
        base.detail = (
            "the failure was measured before the change and the same frozen test passes "
            "after it."
        )
        return base

    if after.verdict == REPRODUCED:
        if green_signature and red_signature and green_signature != red_signature:
            base.verdict = DIFFERENT_FAILURE
            base.detail = (
                "it still fails, but not the way it failed before — the change moved the "
                f"problem. Before: {red_signature}. Now: {green_signature}."
            )
            return base
        base.verdict = STILL_FAILING
        base.detail = "the same failure is still there, in the same way."
        return base

    if after.verdict == NEEDS_SETUP:
        # A broken toolchain, named as such — the docstring above reserves
        # unable_to_verify for exactly this, and "no reliable answer" would send the
        # developer hunting through their application for a problem on their machine.
        base.detail = (
            "this machine cannot run the reproduction, so nothing was learned about "
            f"the change: {after.detail}"
            if after.detail else
            "this machine cannot run the reproduction, so nothing was learned about "
            "the change."
        )
        return base

    if after.verdict == INCONCLUSIVE:
        base.detail = (
            f"no reliable answer after the change: {after.detail}"
            if after.detail else "no reliable answer after the change."
        )
        return base

    base.detail = after.detail or "the reproduction did not produce a usable result."
    return base
