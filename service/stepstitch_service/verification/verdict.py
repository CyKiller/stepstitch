"""Pure verification verdict logic.

StepStitch never runs code; the customer's CI runs the deterministic repro and reports
pass/fail. The verdict is derived from the pre-fix run (the repro should FAIL — the bug is
present) and the post-fix run (it should PASS — the bug is gone). Only red->green is a
confirmed fix.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

VERDICT_NOT_REPRODUCED = "not_reproduced"          # pre-fix run passed -> repro is invalid
VERDICT_REPRODUCED_UNFIXED = "reproduced_unfixed"  # pre failed, no post yet
VERDICT_NOT_FIXED = "not_fixed"                     # pre failed, post still failed
VERDICT_CONFIRMED_FIXED = "confirmed_fixed"         # pre failed -> post passed (red->green)


def derive_verdict(pre_passed: bool, post_passed: Optional[bool]) -> str:
    """Map a (pre-fix, post-fix) repro outcome to a verdict."""
    if pre_passed:
        return VERDICT_NOT_REPRODUCED
    if post_passed is None:
        return VERDICT_REPRODUCED_UNFIXED
    return VERDICT_CONFIRMED_FIXED if post_passed else VERDICT_NOT_FIXED


@dataclass(frozen=True)
class VerificationResult:
    trace_id: str
    pre_passed: bool
    post_passed: Optional[bool]
    verdict: str
    fix_ref: Optional[str] = None
    run_url: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "pre_passed": self.pre_passed,
            "post_passed": self.post_passed,
            "verdict": self.verdict,
            "fix_ref": self.fix_ref,
            "run_url": self.run_url,
        }
