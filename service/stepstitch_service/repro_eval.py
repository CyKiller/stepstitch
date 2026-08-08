"""Reproduction Success corpus evaluator — pure, offline, stdlib-only deps.

Evaluates examples/repro/reproduction-corpus.json against the real product
surface: :func:`replayability.score_trace` for warnings, :func:`repro_config.
readiness` + :func:`execution.derive_execution_state` for the state an operator
sees, and :func:`compiler.generate_playwright_test` for the bytes that would be
frozen. No database, no server, no browser — the real-Chromium half of the gate
lives in scripts/prove-repro-corpus.mjs.

The evaluator never trusts an expectation: every entry is recomputed from the
trace, and a mismatch is reported as a problem on that entry. Gates
(:data:`READY_RATE_GATE`, refusal naming, byte-determinism) are asserted by
service/tests/test_repro_corpus.py.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .compiler import generate_playwright_test
from .execution import derive_execution_state
from .replayability import score_trace
from .repro_config import ReproConfig, readiness

__all__ = [
    "CATEGORIES",
    "READY_RATE_GATE",
    "RED_RATE_GATE",
    "CORPUS_FILE_VERSION",
    "EntryResult",
    "CorpusResult",
    "evaluate_corpus",
    "render_report",
]

CORPUS_FILE_VERSION = 1

# The plan's taxonomy. test_repro_corpus.py::test_corpus_covers_every_planned_category
# fails if the corpus loses coverage of any of these.
CATEGORIES = (
    "reproducible",
    "missing-terminal-action",
    "dynamic-route",
    "auth-required",
    "form-values",
    "api-failure",
    "unstable-selector",
    "unsupported-action",
    "setup-failure",
    "browser-failure",
    "non-reproducible",
)

READY_RATE_GATE = 0.90
RED_RATE_GATE = 0.85  # enforced in real Chromium by scripts/prove-repro-corpus.mjs


@dataclass
class EntryResult:
    """What the product actually produced for one corpus entry, and how it compares."""

    name: str
    category: str
    eligible: bool
    reason: str = ""
    reason_observed: bool = False
    state: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    blocking: List[str] = field(default_factory=list)
    script_sha256: Optional[str] = None
    expected_sha: str = ""
    deterministic: bool = True
    problems: List[str] = field(default_factory=list)


@dataclass
class CorpusResult:
    entries: List[EntryResult]
    eligible_count: int
    ready_count: int

    @property
    def ready_rate(self) -> float:
        return self.ready_count / self.eligible_count if self.eligible_count else 0.0

    @property
    def ok(self) -> bool:
        return (
            not any(e.problems for e in self.entries)
            and self.ready_rate >= READY_RATE_GATE
            and all(e.reason_observed for e in self.entries if not e.eligible)
        )


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _evaluate_entry(entry: Dict[str, Any], base_url: str) -> EntryResult:
    expect = entry.get("expect") or {}
    result = EntryResult(
        name=str(entry.get("name", "?")),
        category=str(entry.get("category", "?")),
        eligible=bool(entry.get("eligible")),
        reason=str(entry.get("reason", "")),
        expected_sha=str(expect.get("script_sha256", "")),
    )

    # Transcript-only entries (setup/browser failures) have no trace to compile;
    # their gate lives in test_repro_corpus.py via classify_run/derive_verdict.
    if "transcript" in entry:
        result.script_sha256 = None
        result.reason_observed = result.reason == "toolchain_error"
        return result

    footsteps = list(entry.get("footsteps") or [])
    cfg = ReproConfig.from_dict(entry.get("config"))

    score = score_trace(footsteps)
    result.warnings = sorted({w["code"] for w in score["warnings"]})

    items = readiness(cfg, footsteps, fallback_base_url=base_url)
    result.state = derive_execution_state(items)
    result.blocking = sorted(i["id"] for i in items if i["blocking"] and not i["ready"])

    script = generate_playwright_test(result.name, footsteps, base_url=base_url, config=cfg)
    again = generate_playwright_test(result.name, footsteps, base_url=base_url, config=cfg)
    result.deterministic = script == again
    result.script_sha256 = _sha(script)

    # A named refusal must be a signal the operator actually sees.
    if not result.eligible:
        result.reason_observed = (
            result.reason in result.warnings or result.reason in result.blocking
        )

    expected_state = expect.get("state")
    if expected_state is not None and result.state != expected_state:
        result.problems.append(
            f"expected state {expected_state!r}, product produced {result.state!r}"
        )
    expected_warnings = expect.get("warnings")
    if expected_warnings is not None and sorted(expected_warnings) != result.warnings:
        result.problems.append(
            f"expected warnings {sorted(expected_warnings)}, product emitted {result.warnings}"
        )
    if not result.deterministic:
        result.problems.append("two compiles in the same process differed")
    return result


def evaluate_corpus(doc: Dict[str, Any]) -> CorpusResult:
    """Evaluate every entry. Pure: does not mutate ``doc``."""
    if doc.get("version") != CORPUS_FILE_VERSION:
        raise ValueError(
            f"corpus version {doc.get('version')!r} != supported {CORPUS_FILE_VERSION}"
        )
    base_url = str(doc.get("base_url") or "http://app.corpus.test")
    entries = [_evaluate_entry(e, base_url) for e in doc.get("entries") or []]
    eligible = [e for e in entries if e.eligible]
    ready = [e for e in eligible if e.state == "ready"]
    return CorpusResult(entries=entries, eligible_count=len(eligible), ready_count=len(ready))


def render_report(result: CorpusResult) -> str:
    lines = [
        "Reproduction Success corpus",
        f"  eligible: {result.eligible_count}  ready: {result.ready_count}  "
        f"ready rate: {result.ready_rate:.0%} (gate {READY_RATE_GATE:.0%})",
        "",
    ]
    for e in result.entries:
        mark = "FAIL" if e.problems else "ok  "
        state = e.state if e.state is not None else "(transcript)"
        lines.append(f"  {mark} {e.name:32s} {e.category:24s} {state}")
        for p in e.problems:
            lines.append(f"       {p}")
        if not e.eligible:
            seen = "named+observed" if e.reason_observed else "NOT OBSERVED"
            lines.append(f"       refusal reason: {e.reason or '(none)'} [{seen}]")
    return "\n".join(lines)
