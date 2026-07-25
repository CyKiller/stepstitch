"""Failure Shapes — cluster traces by their structural fingerprint.

A **shape** is every trace that failed the same way: same route template, diagnostic type,
failing status, exception type, endpoint, and terminal selector. Forty users hitting one broken
transfer form is one shape, one decision, one fix — not forty rows.

Grouping on structure is something only StepStitch can do. Error trackers group by stack trace
and replay tools group by session; the fingerprint from :mod:`.fix_memory` is derived purely from
already-scrubbed structural fields, so it is NPI-free by construction and — because it is stored
independently of the trace body — a shape and its fix **survive retention purge**. The evidence
expires; the institutional memory does not.

Design: pure, deterministic, dependency-free. Every function here takes plain data and returns
plain data; the router performs all I/O. That keeps the interesting logic directly testable.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Optional

from .fix_memory import DEFAULT_WEIGHTS
from .fix_memory import match as fix_match
from .humanize import plain_summary, stage_label
from .verification.verdict import (
    VERDICT_CONFIRMED_FIXED,
    VERDICT_NOT_FIXED,
    VERDICT_NOT_REPRODUCED,
    VERDICT_REPRODUCED_UNFIXED,
)

# The fields a fingerprint is made of, in a fixed order. Derived from fix_memory's weight table
# so the two can never drift apart.
FP_KEYS = tuple(DEFAULT_WEIGHTS.keys())

# ---- Pipeline stages -------------------------------------------------------------------
# Every stage is DERIVED from the verdict state machine in verification/verdict.py. Nothing is
# stored twice, and a shape's stage is always recomputable from its verifications.
STAGE_UNTRIAGED = "untriaged"            # no verification run has been reported yet
STAGE_KNOWN = "known_shape"              # untriaged, but matches a fix already confirmed
STAGE_REPRO_INVALID = "repro_invalid"    # not_reproduced — the repro passed pre-fix; it is wrong
STAGE_REPRODUCED = "reproduced"          # reproduced_unfixed — red confirmed, awaiting a fix
STAGE_FIX_FAILED = "fix_failed"          # not_fixed — a fix was attempted and it is still red
STAGE_FIXED = "fixed"                    # confirmed_fixed — red->green

# Board order, left to right. The two "needs attention" columns sit where the eye lands first
# after the inbox.
STAGE_ORDER = (
    STAGE_UNTRIAGED,
    STAGE_KNOWN,
    STAGE_REPRO_INVALID,
    STAGE_REPRODUCED,
    STAGE_FIX_FAILED,
    STAGE_FIXED,
)

# Most-advanced-verdict-wins. A shape that has ever been confirmed fixed reads as fixed even if an
# earlier run failed, because the corpus entry is the durable fact.
_VERDICT_STAGE = {
    VERDICT_CONFIRMED_FIXED: STAGE_FIXED,
    VERDICT_NOT_FIXED: STAGE_FIX_FAILED,
    VERDICT_REPRODUCED_UNFIXED: STAGE_REPRODUCED,
    VERDICT_NOT_REPRODUCED: STAGE_REPRO_INVALID,
}
_STAGE_RANK = {
    STAGE_FIXED: 5,
    STAGE_FIX_FAILED: 4,
    STAGE_REPRODUCED: 3,
    STAGE_REPRO_INVALID: 2,
    STAGE_KNOWN: 1,
    STAGE_UNTRIAGED: 0,
}


def canonical_fingerprint(fp: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalise a fingerprint to exactly ``FP_KEYS``, so equal shapes hash identically."""
    fp = fp or {}
    return {k: fp.get(k) for k in FP_KEYS}


def shape_id(fp: Optional[Dict[str, Any]]) -> str:
    """Stable id for a fingerprint.

    SHA-256 over the canonical JSON rather than :func:`hash`, which is salted per process and
    would hand out different ids on every restart.
    """
    canonical = json.dumps(canonical_fingerprint(fp), sort_keys=True, separators=(",", ":"))
    return "shp_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def derive_stage(verdicts: Iterable[str], *, has_prior_fix: bool = False) -> str:
    """Map a shape's verification verdicts to its board column.

    ``has_prior_fix`` only promotes a shape out of *untriaged*: once its own CI has reported
    something, that reality outranks the resemblance to an older fix.
    """
    stage = STAGE_KNOWN if has_prior_fix else STAGE_UNTRIAGED
    for verdict in verdicts:
        candidate = _VERDICT_STAGE.get(verdict)
        if candidate and _STAGE_RANK[candidate] > _STAGE_RANK[stage]:
            stage = candidate
    return stage


def cluster(
    traces: List[Dict[str, Any]],
    *,
    corpus: Optional[List[Dict[str, Any]]] = None,
    weights: Optional[Dict[str, float]] = None,
    min_similarity: float = 0.4,
) -> List[Dict[str, Any]]:
    """Group traces into shapes, newest-active first.

    ``traces`` are ``{trace_id, fingerprint, created_at, verdicts?}`` — ``verdicts`` being the
    verdict strings already recorded against that trace. ``corpus`` is the confirmed-fix corpus
    in :func:`fix_memory.match` form; when supplied, each shape reports the prior fixes it
    resembles.

    Traces with no usable fingerprint (every field null) are skipped rather than collapsed into
    one meaningless bucket.
    """
    buckets: Dict[str, Dict[str, Any]] = {}

    for trace in traces:
        fp = canonical_fingerprint(trace.get("fingerprint"))
        if all(v is None for v in fp.values()):
            continue
        sid = shape_id(fp)
        bucket = buckets.get(sid)
        if bucket is None:
            bucket = buckets[sid] = {
                "shape_id": sid,
                "fingerprint": fp,
                "trace_ids": [],
                "verdicts": [],
                "first_seen": None,
                "last_seen": None,
            }
        bucket["trace_ids"].append(trace.get("trace_id"))
        bucket["verdicts"].extend(trace.get("verdicts") or [])
        created = trace.get("created_at")
        if created is not None:
            if bucket["first_seen"] is None or created < bucket["first_seen"]:
                bucket["first_seen"] = created
            if bucket["last_seen"] is None or created > bucket["last_seen"]:
                bucket["last_seen"] = created

    shapes: List[Dict[str, Any]] = []
    for bucket in buckets.values():
        members = set(bucket["trace_ids"])
        prior_fixes: List[Dict[str, Any]] = []
        if corpus:
            # A shape's own confirmed fix is not "seen before" — exclude every member trace so a
            # fixed shape does not cite itself as precedent.
            candidates = [c for c in corpus if c.get("trace_id") not in members]
            prior_fixes = fix_match(
                bucket["fingerprint"], candidates,
                weights=weights, min_similarity=min_similarity,
            )
        stage = derive_stage(bucket["verdicts"], has_prior_fix=bool(prior_fixes))
        shapes.append({
            "shape_id": bucket["shape_id"],
            "fingerprint": bucket["fingerprint"],
            # Plain-language rendering travels WITH the shape rather than being reconstructed by
            # each consumer, so the console, the MCP surface and anything later all say the same
            # sentence about the same failure.
            "plain_summary": plain_summary(bucket["fingerprint"]),
            "stage_label": stage_label(stage),
            "occurrences": len(bucket["trace_ids"]),
            "trace_ids": bucket["trace_ids"],
            "representative_trace_id": bucket["trace_ids"][0],
            "first_seen": bucket["first_seen"],
            "last_seen": bucket["last_seen"],
            "stage": stage,
            "verdicts": sorted(set(bucket["verdicts"])),
            "prior_fixes": prior_fixes,
        })

    # Most recently active first; ties broken by shape_id so the board never reshuffles between
    # identical requests.
    shapes.sort(key=lambda s: (_sort_key(s["last_seen"]), s["shape_id"]), reverse=True)
    return shapes


def _sort_key(value: Any) -> str:
    """created_at may arrive as a datetime or an ISO string depending on the driver."""
    if value is None:
        return ""
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def board(shapes: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Bucket shapes into the board's columns, every stage present (possibly empty)."""
    columns: Dict[str, List[Dict[str, Any]]] = {stage: [] for stage in STAGE_ORDER}
    for shape in shapes:
        columns[shape["stage"]].append(shape)
    return columns


__all__ = [
    "FP_KEYS", "STAGE_ORDER", "STAGE_UNTRIAGED", "STAGE_KNOWN", "STAGE_REPRO_INVALID",
    "STAGE_REPRODUCED", "STAGE_FIX_FAILED", "STAGE_FIXED",
    "canonical_fingerprint", "shape_id", "derive_stage", "cluster", "board",
]
