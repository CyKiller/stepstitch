"""StepStitch Verified-Fix engine — certify red->green and accumulate a regression corpus."""
from .verdict import (
    ALL_VERDICTS,
    VERDICT_CONFIRMED_FIXED,
    VERDICT_NOT_FIXED,
    VERDICT_NOT_REPRODUCED,
    VERDICT_REPRODUCED_UNFIXED,
    VerificationResult,
    derive_verdict,
)

__all__ = [
    "ALL_VERDICTS",
    "derive_verdict",
    "VerificationResult",
    "VERDICT_CONFIRMED_FIXED",
    "VERDICT_NOT_FIXED",
    "VERDICT_NOT_REPRODUCED",
    "VERDICT_REPRODUCED_UNFIXED",
]
