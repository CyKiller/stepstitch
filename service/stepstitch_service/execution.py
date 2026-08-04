"""Execution state — has this reproduction actually been *run*, and can it be?

The product had four state machines (verification verdict, board stage, runner
verdict, fix verdict) and none of them answered the question a new operator
actually asks: *is this thing runnable, and did anyone run it?* A compiled draft
that cannot execute (no base URL, no route fixture) looked exactly like one that
had been measured red and fixed.

This module is the missing projection, derived from data that already exists —
it stores nothing and changes no existing state machine:

    draft            the reproduction compiles, but setup is missing: running it
                     now would produce a verdict about the configuration, not the bug
    ready            setup is complete; nothing has been run yet
    reproduced       a red run was measured (frozen with red_verdict=reproduced,
                     or a verification whose pre-fix half genuinely failed)
    confirmed_fixed  measured red THEN measured green

Deliberately not a superset of the verdict vocabulary: ``not_reproduced`` and
``fix_failed`` are outcomes the board already shows. This axis answers "how far
has execution actually got", so its worst state is "we never ran it".

Pure (no I/O, no state) so every combination is directly unit-testable.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

STATE_DRAFT = "draft"
STATE_READY = "ready"
STATE_REPRODUCED = "reproduced"
STATE_CONFIRMED_FIXED = "confirmed_fixed"

# Ordered worst → best; a trace is described by the furthest state it reached.
EXECUTION_STATES = (STATE_DRAFT, STATE_READY, STATE_REPRODUCED, STATE_CONFIRMED_FIXED)

STATE_MEANING: Dict[str, str] = {
    STATE_DRAFT: "A reproduction was generated, but something it needs is missing — "
                 "running it now would test the configuration, not the bug.",
    STATE_READY: "Everything the reproduction needs is configured. Nothing has run yet, "
                 "so the failure is still unproven.",
    STATE_REPRODUCED: "StepStitch ran the reproduction and measured the failure. The bug "
                      "is real and the test is a valid referee.",
    STATE_CONFIRMED_FIXED: "Measured red, then measured green running the same frozen "
                           "bytes. The fix is proven, not asserted.",
}


def blocking_items(readiness_items: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """The unready items that make a run meaningless (never the advisory ones)."""
    return [
        item for item in (readiness_items or [])
        if item.get("blocking") and not item.get("ready")
    ]


def derive_execution_state(
    readiness_items: Optional[List[Dict[str, Any]]] = None,
    *,
    frozen: Optional[Dict[str, Any]] = None,
    verifications: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """How far execution actually got for one trace.

    ``frozen`` is the ``stepstitch_frozen_repros`` row (``red_verdict`` is the field
    that matters — freezing REFUSES to record a red that was never observed).
    ``verifications`` are ``stepstitch_verifications`` rows (``pre_passed`` /
    ``post_passed`` / ``verdict``).

    Measured execution outranks readiness: a trace that was reproduced *is*
    reproduced even if the config was edited afterwards. Anything else would let a
    later config change silently un-prove a measurement that happened.
    """
    rows = verifications or []
    if any(r.get("verdict") == STATE_CONFIRMED_FIXED for r in rows):
        return STATE_CONFIRMED_FIXED

    red_measured = (frozen or {}).get("red_verdict") == "reproduced"
    # pre_passed False means the pre-fix run genuinely FAILED — the red half is real.
    # A missing pre_passed is not evidence of anything.
    red_reported = any(r.get("pre_passed") is False for r in rows)
    if red_measured or red_reported:
        return STATE_REPRODUCED

    return STATE_DRAFT if blocking_items(readiness_items) else STATE_READY


def execution_summary(
    readiness_items: Optional[List[Dict[str, Any]]] = None,
    *,
    frozen: Optional[Dict[str, Any]] = None,
    verifications: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """The state plus the evidence for it — what the console shows an operator.

    ``red_ran`` / ``green_ran`` are the honest answers to "did anyone actually run
    this?", kept separate from the verdict so a caller can never mistake a reported
    verdict for a run StepStitch observed.
    """
    rows = verifications or []
    state = derive_execution_state(readiness_items, frozen=frozen, verifications=rows)
    blockers = blocking_items(readiness_items)
    grades = [r.get("evidence_grade") for r in rows if r.get("evidence_grade")]
    return {
        "execution_state": state,
        "meaning": STATE_MEANING[state],
        "blockers": [
            {"id": b.get("id"), "title": b.get("title"), "detail": b.get("detail")}
            for b in blockers
        ],
        "red_ran": (frozen or {}).get("red_verdict") == "reproduced"
        or any(r.get("pre_passed") is False for r in rows),
        "green_ran": any(r.get("post_passed") is True for r in rows),
        "frozen": bool(frozen),
        "frozen_red_verdict": (frozen or {}).get("red_verdict"),
        # 'measured' means StepStitch ran it; 'asserted' means a caller reported it.
        # Surfacing the strongest grade present keeps the distinction visible.
        "evidence_grade": ("measured" if "measured" in grades
                           else ("signed" if "signed" in grades
                                 else ("asserted" if grades else None))),
    }


__all__ = [
    "EXECUTION_STATES",
    "STATE_DRAFT",
    "STATE_READY",
    "STATE_REPRODUCED",
    "STATE_CONFIRMED_FIXED",
    "STATE_MEANING",
    "blocking_items",
    "derive_execution_state",
    "execution_summary",
]
