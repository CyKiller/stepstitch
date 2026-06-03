"""StepStitch backend service package (host-agnostic)."""
from .compiler import generate_playwright_test
from .replayability import score_trace
from .retention import purge_expired_traces
from .router import create_stepstitch_router
from .scrubber import (
    FINANCIAL_SERVICES_ENTERPRISE,
    ScrubPolicy,
    ScrubRejection,
    scrub_trace_payload,
)

__all__ = [
    "generate_playwright_test",
    "score_trace",
    "create_stepstitch_router",
    "purge_expired_traces",
    "scrub_trace_payload",
    "ScrubPolicy",
    "ScrubRejection",
    "FINANCIAL_SERVICES_ENTERPRISE",
]
