"""Replayability scoring — "can engineering actually reproduce this?"

A privacy-safe trace is only useful if it is *reproducible*. This module scores a
trace 0..1 (with a letter grade and human-readable warnings) purely from the
structural footsteps already on the wire — no extra capture, no NPI. Like the
scrubber and compiler it is pure (no I/O, no state) so the scoring boundaries are
directly unit-testable.

Signals:
  * **Selector stability** — a ``[data-testid=...]`` selector is replay-stable;
    an ``#id`` is decent; a bare ``nth-of-type`` / tag path is brittle; a click or
    input with no selector at all is the worst.
  * **Terminal action** — a trace that ends in a click, ``api_error`` or
    ``exception`` gives engineering something to assert on; a navigation-only trace
    does not.
  * **Templated routes** — ``/accounts/:id`` is correct for privacy but needs a
    concrete fixture id to replay, so it is flagged (not penalised heavily).
  * **Volume** — an empty trace cannot be replayed; an extremely long one is flaky.

Contract: see contracts/stepstitch.md (Replayability).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = ["score_trace", "selector_stability", "GRADE_THRESHOLDS"]

# Letter grade thresholds (inclusive lower bounds), best first.
GRADE_THRESHOLDS = (("A", 0.85), ("B", 0.70), ("C", 0.55), ("D", 0.40))

_INTERACTIVE = {"click", "input"}
_TERMINAL = {"click", "api_error", "exception"}


def selector_stability(target: Optional[str]) -> str:
    """Classify a selector's replay stability: testid | id | structural | none."""
    if not target or not isinstance(target, str):
        return "none"
    t = target.strip()
    if "data-testid" in t:
        return "testid"
    # A pure id selector (``#foo``) with no descendant combinator is stable-ish.
    if t.startswith("#") and " " not in t and ">" not in t:
        return "id"
    return "structural"


def _grade(score: float) -> str:
    for letter, threshold in GRADE_THRESHOLDS:
        if score >= threshold:
            return letter
    return "F"


def score_trace(footsteps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return ``{score, grade, warnings, signals}`` for a trace.

    ``score`` is clamped to [0, 1]; ``warnings`` is a list of
    ``{code, detail, step_index?}``. Deterministic for a given input.
    """
    warnings: List[Dict[str, Any]] = []

    if not footsteps:
        return {
            "score": 0.0,
            "grade": "F",
            "warnings": [{"code": "empty_trace", "detail": "No footsteps captured."}],
            "signals": {"steps": 0, "interactive": 0, "stable_selectors": 0},
        }

    score = 1.0
    interactive = 0
    stable_selectors = 0

    for i, step in enumerate(footsteps):
        step_type = str(step.get("type", "")).lower()
        route = str(step.get("route", "/"))

        if step_type in _INTERACTIVE:
            interactive += 1
            tier = selector_stability(step.get("target"))
            if tier == "testid":
                stable_selectors += 1
            elif tier == "id":
                stable_selectors += 1
                score -= 0.05
            elif tier == "structural":
                score -= 0.12
                warnings.append({
                    "code": "unstable_selector",
                    "detail": "Structural selector (nth-of-type/tag path) is brittle; "
                              "prefer a data-testid.",
                    "step_index": i,
                })
            else:  # none
                score -= 0.20
                warnings.append({
                    "code": "missing_selector",
                    "detail": f"{step_type} step has no selector — cannot target it.",
                    "step_index": i,
                })

        if ":" in route:
            score -= 0.04
            warnings.append({
                "code": "templated_route_needs_fixture",
                "detail": f"Route '{route}' is templated; supply a concrete fixture id.",
                "step_index": i,
            })

    # Terminal-action signal: something to assert on.
    has_terminal = any(str(s.get("type", "")).lower() in _TERMINAL for s in footsteps)
    if not has_terminal:
        score -= 0.25
        warnings.append({
            "code": "no_terminal_action",
            "detail": "Navigation-only trace — no click, api_error, or exception to "
                      "assert against.",
        })

    # Volume signals.
    if len(footsteps) > 50:
        score -= 0.10
        warnings.append({
            "code": "long_trace",
            "detail": f"{len(footsteps)} steps — long traces replay flakily; trim to "
                      "the failing path.",
        })

    score = max(0.0, min(1.0, round(score, 4)))
    return {
        "score": score,
        "grade": _grade(score),
        "warnings": warnings,
        "signals": {
            "steps": len(footsteps),
            "interactive": interactive,
            "stable_selectors": stable_selectors,
        },
    }
