"""One normalized handoff: everything an agent needs, and an honest account of its origin.

Before this, the packet said things like ``never_included: stack traces, raw console logs``.
That was true when the only evidence came from the reported session. It stopped being true
the moment StepStitch began collecting deep diagnostics from the **synthetic reproduction** —
and a privacy claim that quietly went stale is worse than one that was never made, because
people rely on it.

So the posture is split by origin rather than softened:

- ``from_production`` — what is taken from the person who hit the bug. Unchanged, minimal,
  and still free of screenshots, page text, input values and bodies.
- ``from_reproduction`` — what is collected from a synthetic run on the developer's own
  machine. Rich, including stack traces and console errors, and containing no customer data
  because no customer was ever in it.

Both lists are true. Neither is a hedge. An agent reading the packet can tell which half it
is looking at without knowing how StepStitch works internally.

The packet also carries the two digests (**script** and **execution envelope**) and the
exact command StepStitch will use to judge a fix. An agent that can see how it will be
marked can aim at the real target rather than guess.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# What is never taken from the reported session. This is the promise to the person who hit
# the bug, and it is unchanged by anything on the reproduction side.
NEVER_FROM_PRODUCTION: List[str] = [
    "screenshots", "video", "input values", "raw URLs", "page text",
    "request/response bodies", "console messages", "network headers",
]

# What the DIAGNOSTIC SUMMARY never carries out of the reported session. A separate list
# from NEVER_FROM_PRODUCTION because it answers a different question: that one is about
# capture, this one is about what a summary discloses.
#
# The wording matters. This list used to read as an absolute — "stack traces are never
# included" — and deep diagnostics made that false, because a stack from the SYNTHETIC
# reproduction is exactly what an agent now receives. Nothing was removed from the promise;
# it is simply scoped to the thing it was always about: the reported session.
NEVER_FROM_REPORTED_SESSION: List[str] = [
    "raw console logs", "raw error messages", "stack traces",
    "request/response bodies", "headers", "cookies",
    "input values", "screenshots", "full URLs",
]

# What a synthetic run may yield. Stated positively: an agent should know what it is
# allowed to expect, and a reader should be able to see that the two lists do not conflict.
COLLECTED_FROM_REPRODUCTION: List[str] = [
    "source-located failure stack", "console errors (errors only)",
    "failed requests (method, templated path, status, duration)",
    "the last interaction before the failure",
    "browser build and StepStitch version",
]


def privacy_posture(policy_name: str, scrub: Optional[Dict[str, Any]],
                    has_diagnostics: bool) -> Dict[str, Any]:
    # ``has_diagnostics`` is a claim about data that exists. Listing what we *could*
    # collect when we collected nothing would describe a run that never happened.
    """The origin-split posture. Legacy keys stay so existing readers do not break."""
    return {
        # Legacy shape — the individual /privacy-posture endpoint returns these, and the
        # packet must keep matching it or the drift guard is meaningless.
        "policy": policy_name,
        "scrub": scrub,
        "never_captured": list(NEVER_FROM_PRODUCTION),
        # The honest split.
        "from_production": {
            "policy": policy_name,
            "scrub": scrub,
            "never_captured": list(NEVER_FROM_PRODUCTION),
            "detail": "taken from the person who reported the bug; scrubbed server-side "
                      "before storage",
        },
        "from_reproduction": {
            "source": "synthetic_reproduction",
            "contains_customer_session_data": False,
            "collected": list(COLLECTED_FROM_REPRODUCTION) if has_diagnostics else [],
            "detail": (
                "collected from a synthetic run on this machine. No customer was in it, "
                "which is why deeper technical detail is available here than from "
                "production."
                if has_diagnostics else
                "no reproduction has been run for this session yet, so there are no "
                "reproduction diagnostics."
            ),
        },
    }


# A frame that points inside the generated reproduction rather than the application. Those
# are noise as a fix suggestion: the test is the thing doing the asserting, not the thing
# that is broken.
_GENERATED = re.compile(r"(repro\.spec\.ts|/\.stepstitch/|node_modules)")


def likely_files(diagnostics: Optional[Dict[str, Any]], limit: int = 5) -> List[Dict[str, str]]:
    """Files worth looking at first, derived from the failure stack.

    Explicitly labelled as suggestions everywhere they surface. A stack frame is evidence
    of where execution was, not of where the mistake is — the two are often different, and
    an agent told "the bug is here" will happily edit the wrong file with confidence.
    """
    out: List[Dict[str, str]] = []
    seen = set()
    if not isinstance(diagnostics, dict):
        # A legacy or malformed record must not cost a caller the whole packet. The
        # diagnostics are the extra; the reproduction and the summary are the product.
        return out
    for frame in diagnostics.get("failure_stack", []) or []:
        match = re.search(r"((?:/|\w:\\)[^\s:]+\.(?:ts|tsx|js|jsx|py|rb|go|java|cs))", frame)
        if not match:
            continue
        path = match.group(1)
        if _GENERATED.search(path) or path in seen:
            continue
        seen.add(path)
        out.append({"path": path, "why": "appears in the failure stack"})
        if len(out) >= limit:
            break
    return out


def verification_command(trace_id: str, host: str = "http://127.0.0.1:8321") -> str:
    """Exactly how the fix will be judged.

    Shown to the agent on purpose. There is no advantage in hiding the marking scheme when
    the scheme cannot be gamed: the script is frozen, the envelope is frozen, and the agent
    has no credential that can write a verdict.
    """
    return (f"curl -X POST {host.rstrip('/')}/admin/session/{trace_id}/verify-fix "
            "-H 'Authorization: Bearer $STEPSTITCH_ADMIN_TOKEN'")


def build_packet(
    *,
    trace_id: str,
    summary: Dict[str, Any],
    replayability: Dict[str, Any],
    policy_name: str,
    scrub: Optional[Dict[str, Any]],
    recommended_next_step: str,
    playwright_code: str,
    diagnostics: Optional[Dict[str, Any]] = None,
    frozen: Optional[Dict[str, Any]] = None,
    repository: Optional[Dict[str, Any]] = None,
    host: str = "http://127.0.0.1:8321",
) -> Dict[str, Any]:
    """Compose the handoff. Pure: every input is passed in, nothing is fetched here."""
    frozen = frozen or {}
    packet: Dict[str, Any] = {
        # --- what the user experienced -------------------------------------------------
        "summary": summary,
        "replayability": replayability,
        "diagnostic": {
            "recommended_next_step": recommended_next_step,
            # Same list the /diagnostic-summary endpoint returns — one constant, so the two
            # cannot drift into disagreeing about a privacy claim.
            "never_included": list(NEVER_FROM_REPORTED_SESSION),
            "never_included_scope": (
                "from the reported session. Evidence from the synthetic reproduction is "
                "listed separately under privacy_posture.from_reproduction."
            ),
        },
        # --- how to reproduce it ------------------------------------------------------
        "playwright_code": playwright_code,
        "reproduction": {
            "command": f"stepstitch reproduce {trace_id}",
            "script_sha256": frozen.get("script_sha256"),
            "execution_envelope_sha256": frozen.get("execution_envelope_sha256"),
            "frozen": bool(frozen.get("script_sha256")),
            "detail": (
                "This test is frozen. Verification reruns these exact bytes under the "
                "same execution envelope, so changing the test does not change the "
                "verdict — fix the application."
                if frozen.get("script_sha256") else
                "Not frozen yet. Freezing records the script and the browser/timeout "
                "envelope so the same experiment judges before and after."
            ),
        },
        # --- what the reproduction revealed --------------------------------------------
        "diagnostics": diagnostics,
        # --- where to look, and how it will be judged ----------------------------------
        "likely_files": likely_files(diagnostics),
        "likely_files_note": (
            "Suggestions only, derived from the failure stack. A stack frame shows where "
            "execution was, not necessarily where the mistake is."
        ),
        "verification": {
            "command": verification_command(trace_id, host),
            "verdicts": ["fixed", "still_failing", "different_failure", "unable_to_verify"],
            "detail": "StepStitch reruns the frozen reproduction and decides. This agent "
                      "cannot record a verdict on its own fix.",
        },
        # --- provenance ----------------------------------------------------------------
        "privacy_posture": privacy_posture(policy_name, scrub, bool(diagnostics)),
    }
    if repository:
        packet["repository"] = repository
    return packet
