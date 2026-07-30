"""Fix Memory — match a new bug against the verified-fix corpus by STRUCTURE.

Every confirmed red->green fix is reduced to a privacy-safe **structural fingerprint** (route
template, diagnostic type, failing HTTP status, exception type, endpoint, terminal selector). A
new trace's fingerprint is matched against the stored fingerprints to surface *"you've fixed this
shape before"* — institutional memory an agent can consume without ever seeing raw data.

Design: pure, deterministic, **dependency-free**, and explainable (every match reports the fields
that agreed). Fingerprints carry no NPI — routes are templated and selectors are structural; the
server-side scrubber already guaranteed that at ingest. Match weights are configurable so a
deployer can tune what "similar" means.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Fields that make up a fingerprint, with the default weight each contributes to similarity.
# A deployer can override via STEPSTITCH_FIX_MEMORY_WEIGHTS (parsed by the host, passed to match).
DEFAULT_WEIGHTS: Dict[str, float] = {
    "route": 0.35,
    "diagnostic_type": 0.15,
    "failing_status": 0.15,
    "exception_type": 0.15,
    "diagnostic_endpoint": 0.10,
    "terminal_selector": 0.10,
}

_FP_KEYS = tuple(DEFAULT_WEIGHTS.keys())
_INTERACTIVE = {"click", "input", "api_error"}


def _terminal_selector(footsteps: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """The structural selector of the last interactive step (already scrubbed at ingest)."""
    for step in reversed(footsteps or []):
        if isinstance(step, dict) and step.get("type") in _INTERACTIVE:
            target = step.get("target")
            if isinstance(target, str) and target:
                return target
    return None


def fingerprint(
    summary: Dict[str, Any],
    footsteps: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Reduce a trace summary (+ optional footsteps) to a structural fingerprint.

    ``summary`` is ``TraceSummary.as_dict()`` (or any dict with those keys). The fingerprint
    is JSON-serializable and NPI-free, so it is safe to persist and expose to agents.
    """
    return {
        "route": summary.get("route"),
        "diagnostic_type": summary.get("diagnostic_type"),
        "failing_status": summary.get("failing_status"),
        "exception_type": summary.get("exception_type"),
        "diagnostic_endpoint": summary.get("diagnostic_endpoint"),
        "terminal_selector": (
            summary.get("terminal_selector")
            if footsteps is None
            else _terminal_selector(footsteps)
        ),
    }


def _similarity(
    a: Dict[str, Any], b: Dict[str, Any], weights: Dict[str, float]
) -> "tuple[float, List[str]]":
    """How much of the QUERY fingerprint ``a`` the candidate ``b`` reproduces.

    The denominator is the weight of fields PRESENT in the query, so a candidate that matches
    every field the query has scores 1.0. Fields absent from the query don't penalize.
    """
    total = 0.0
    score = 0.0
    reasons: List[str] = []
    for key in _FP_KEYS:
        av = a.get(key)
        if av is None:
            continue  # field not in the query → not part of the comparison
        total += weights.get(key, 0.0)
        if b.get(key) is not None and b.get(key) == av:
            score += weights.get(key, 0.0)
            reasons.append(f"same {key}")
    if total == 0.0:
        return 0.0, []
    return score / total, reasons


def match(
    new_fp: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    *,
    weights: Optional[Dict[str, float]] = None,
    top_k: int = 5,
    min_similarity: float = 0.4,
    exclude_trace_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Rank corpus fixes by structural similarity to ``new_fp``.

    ``candidates`` are ``{trace_id, fix_ref, run_url, fingerprint, evidence_grade}`` (the
    stored corpus; the caller is expected to have filtered it to measured evidence). Returns
    the top matches at/above ``min_similarity``, each with a 0-1 ``similarity`` and the ``reasons``
    that drove it. Deterministic for a given input (ties broken by trace_id for stability).
    """
    w = weights or DEFAULT_WEIGHTS
    out: List[Dict[str, Any]] = []
    for c in candidates:
        tid = c.get("trace_id")
        if exclude_trace_id is not None and tid == exclude_trace_id:
            continue
        cand_fp = c.get("fingerprint") or {}
        sim, reasons = _similarity(new_fp, cand_fp, w)
        if sim >= min_similarity:
            out.append({
                "trace_id": tid,
                "fix_ref": c.get("fix_ref"),
                "run_url": c.get("run_url"),
                # How the earlier fix was established. A reader deciding whether to copy
                # it deserves to know whether anyone actually watched it work.
                "evidence_grade": c.get("evidence_grade"),
                "similarity": round(sim, 4),
                "reasons": reasons,
            })
    out.sort(key=lambda r: (-r["similarity"], str(r["trace_id"])))
    return out[:top_k]


__all__ = ["DEFAULT_WEIGHTS", "fingerprint", "match"]
