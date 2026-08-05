"""Fragility Radar — predict which steps will break, and shrink a trace to its failing path.

Two pure, deterministic views built on the same structural signals the replayability scorer
already produces (no extra capture; structural fields only):

  * **Fragility map** — per interactive step, how brittle is its selector (and is its route
    templated), ranked worst-first, with a concrete recommendation. This turns the
    reproducibility signal into *prediction*: which steps are most likely to break as the app
    evolves.
  * **Minimal repro** — reduce the trace to the steps on the failing route, dropping navigation
    to unrelated routes. A smaller, faster repro without guessing execution dependencies.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .replayability import selector_stability

_INTERACTIVE = {"click", "input"}
_TERMINAL = {"click", "api_error", "exception"}

# Higher = more likely to break when the UI changes.
_RISK = {"none": 1.0, "structural": 0.7, "id": 0.3, "testid": 0.1}
_REC = {
    "none": "No selector to target — add a data-testid to this control.",
    "structural": "Structural selector (nth-of-type/tag path) is brittle — add a data-testid.",
    "id": "An #id is decent; a data-testid survives refactors better.",
    "testid": "Stable selector — good.",
}


def compute_fragility_map(footsteps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-step brittleness, ranked worst-first. Pure, deterministic, structural."""
    items: List[Dict[str, Any]] = []
    for i, step in enumerate(footsteps or []):
        if str(step.get("type", "")).lower() not in _INTERACTIVE:
            continue
        tier = selector_stability(step.get("target"))
        route = str(step.get("route", "/"))
        risk = _RISK.get(tier, 0.5)
        if ":" in route:  # templated route needs a fixture id -> a bit more fragile to replay
            risk = min(1.0, risk + 0.1)
        items.append({
            "step_index": i,
            "type": str(step.get("type", "")).lower(),
            "route": route,
            "selector": step.get("target"),
            "stability": tier,
            "risk": round(risk, 3),
            "recommendation": _REC.get(tier, "Review this selector."),
        })
    items.sort(key=lambda x: (-x["risk"], x["step_index"]))
    return {
        "fragility": items,
        "most_fragile": items[0] if items else None,
        "interactive_steps": len(items),
    }


def _failing_route(footsteps: List[Dict[str, Any]]) -> Optional[str]:
    for step in reversed(footsteps or []):
        if str(step.get("type", "")).lower() in _TERMINAL:
            return str(step.get("route", "/"))
    return None


def minimal_repro(footsteps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Reduce a trace to the steps on its failing route (drops unrelated-route navigation).

    Deterministic and safe: it never invents dependencies — it keeps the failing-route
    interactions and drops detours. Returns the reduced footsteps + reduction stats.
    """
    original = list(footsteps or [])
    n = len(original)
    if n == 0:
        return {"original_steps": 0, "reduced_steps": 0, "reduction_ratio": 0.0, "footsteps": []}
    route = _failing_route(original)
    if route is None:  # nothing to assert on -> cannot reduce meaningfully
        return {"original_steps": n, "reduced_steps": n, "reduction_ratio": 1.0,
                "footsteps": original}
    reduced = [s for s in original if str(s.get("route", "/")) == route]
    if not reduced:
        reduced = original
    return {
        "original_steps": n,
        "reduced_steps": len(reduced),
        "reduction_ratio": round(len(reduced) / n, 4),
        "footsteps": reduced,
    }


__all__ = ["compute_fragility_map", "minimal_repro"]
