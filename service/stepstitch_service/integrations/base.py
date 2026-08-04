"""Adapter base: the sanitized TraceSummary and the flat-draft contract.

A :class:`TraceSummary` is the *only* thing adapters are allowed to see. It is a flat,
already-scrubbed projection of a trace — never the raw footsteps, the full explanation,
or the user id. Building drafts from the summary (not the trace) is what guarantees no
system of record receives NPI.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..replayability import score_trace

__all__ = [
    "TraceSummary",
    "DraftAdapter",
    "build_trace_summary",
    "assert_flat",
    "export_preview",
]

# Scalar types permitted in a flat draft (Salesforce/ServiceNow connectors reject
# nested complex objects — see contracts/stepstitch.md).
_FLAT_SCALARS = (str, int, float, bool, type(None))

# Keys an adapter draft must NEVER carry (raw trace internals / identity).
FORBIDDEN_DRAFT_KEYS = frozenset(
    {"footsteps", "explanation_raw", "user_id", "request_body", "response_body",
     "target", "selectors", "raw_url"}
)

_TERMINAL = {"api_error", "exception"}


@dataclass(frozen=True)
class TraceSummary:
    """Flat, sanitized projection of a trace. Safe to hand to any adapter."""

    trace_id: str
    route: str
    headline: str
    replayability_score: float
    replayability_grade: str
    privacy_status: str
    step_count: int
    failing_status: Optional[int] = None
    exception_type: Optional[str] = None
    diagnostic_type: Optional[str] = None
    diagnostic_endpoint: Optional[str] = None
    project_id: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "route": self.route,
            "headline": self.headline,
            "replayability_score": self.replayability_score,
            "replayability_grade": self.replayability_grade,
            "privacy_status": self.privacy_status,
            "step_count": self.step_count,
            "failing_status": self.failing_status,
            "exception_type": self.exception_type,
            "diagnostic_type": self.diagnostic_type,
            "diagnostic_endpoint": self.diagnostic_endpoint,
            "project_id": self.project_id,
        }


def _primary_route(footsteps: List[Dict[str, Any]]) -> str:
    """Route of the last failing step, else the last step, else '/'."""
    last_route = "/"
    failing_route = None
    for step in footsteps:
        route = str(step.get("route", "/"))
        last_route = route
        if str(step.get("type", "")).lower() in _TERMINAL:
            failing_route = route
    return failing_route or last_route


def build_trace_summary(
    trace_id: str,
    footsteps: List[Dict[str, Any]],
    *,
    project_id: Optional[str] = None,
) -> TraceSummary:
    """Project an already-scrubbed trace into a sanitized summary.

    Derived purely from structural footsteps — never the free-text explanation, so the
    summary cannot reintroduce NPI even if upstream scrubbing were imperfect.
    """
    replay = score_trace(footsteps)
    route = _primary_route(footsteps)

    failing_status: Optional[int] = None
    exception_type: Optional[str] = None
    diagnostic_type: Optional[str] = None
    diagnostic_endpoint: Optional[str] = None
    for step in footsteps:
        meta = step.get("metadata") or {}
        stype = str(step.get("type", "")).lower()
        if stype == "api_error" and "status" in meta:
            try:
                failing_status = int(meta["status"])
            except (TypeError, ValueError):
                failing_status = None
            endpoint = meta.get("endpoint")
            if isinstance(endpoint, str):
                diagnostic_endpoint = endpoint[:120]
            diagnostic_type = "api_error"
        elif stype == "exception":
            # error_type is an allowlisted, structural footstep-metadata key.
            et = meta.get("error_type") or meta.get("name")
            if isinstance(et, str):
                exception_type = et[:60]
            diagnostic_type = "exception"

    if failing_status is not None:
        headline = f"User-reported issue: HTTP {failing_status} on {route}"
    elif exception_type is not None:
        headline = f"User-reported issue: client {exception_type} on {route}"
    else:
        headline = f"User-reported issue with reproducible steps on {route}"

    return TraceSummary(
        trace_id=trace_id,
        route=route,
        headline=headline,
        replayability_score=replay["score"],
        replayability_grade=replay["grade"],
        # Describes the mechanism, not an unprovable absence: every stored field passed
        # the server-side scrubber and only structural fields reach a summary. "No NPI"
        # is a claim the scrubber cannot prove (a name survives regex redaction), so the
        # status names what actually ran instead.
        privacy_status="server-scrubbed, structural fields only",
        step_count=replay["signals"]["steps"],
        failing_status=failing_status,
        exception_type=exception_type,
        diagnostic_type=diagnostic_type,
        diagnostic_endpoint=diagnostic_endpoint,
        project_id=project_id,
    )


def assert_flat(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a draft is flat (scalar values only) and carries no forbidden key.

    Raises ``ValueError`` on violation so a buggy adapter can never ship a nested or
    identity-leaking payload to a system of record.
    """
    for key, value in draft.items():
        if key in FORBIDDEN_DRAFT_KEYS:
            raise ValueError(f"draft carries forbidden key {key!r}")
        if not isinstance(value, _FLAT_SCALARS):
            raise ValueError(
                f"draft field {key!r} is not flat ({type(value).__name__}); "
                "connectors reject nested objects"
            )
    return draft


class DraftAdapter(ABC):
    """A sanitized, draft-only exporter for a system of record."""

    name: str = "adapter"

    @abstractmethod
    def build_draft(self, summary: TraceSummary) -> Dict[str, Any]:
        """Return a flat, validated draft record. Must call assert_flat."""
        raise NotImplementedError


def export_preview(
    summary: TraceSummary, adapters: List[DraftAdapter]
) -> Dict[str, Dict[str, Any]]:
    """Build a preview map ``{adapter_name: draft}`` — nothing is sent."""
    return {a.name: a.build_draft(summary) for a in adapters}
