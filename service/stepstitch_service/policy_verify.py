"""Tenant fixture validator — ``stepstitch policy verify <fixtures.json>``.

An operator adopting the strict financial profile needs to prove, before go-live,
that their configuration actually refuses the payload shapes they are worried
about: synthetic names, addresses, account numbers, emails, semantic route slugs,
semantic selectors. This module runs a fixture file against a named profile plus
the operator's overrides and reports, per fixture, whether the payload was
**rejected** (a 422 at the live router), had a field **dropped**, had a value
**redacted**, or was **accepted** untouched — and whether any ``must_not_persist``
literal survived into what would have been stored.

Stdlib-only (imports only :mod:`scrubber`, :mod:`profiles`, :mod:`replayability`)
so the CLI keeps working in a minimal environment. Router parity is enforced by
``service/tests/test_policy_verify.py``: every shipped fixture is also POSTed at a
real router and the classifications must agree, so this offline mirror can never
quietly drift from the live 422 behavior.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .profiles import available_profiles, get_profile, policy_from_profile
from .replayability import SUPPORTED_STEP_TYPES
from .scrubber import (
    ScrubPolicy,
    ScrubRejection,
    apply_scrub_overrides,
    scrub_trace_payload,
)

FIXTURE_FILE_VERSION = 1

# Mirrors of the router's pydantic schemas (extra="forbid"). The parity test keeps
# these honest against the real IngestTracePayload / FootstepSchema.
KNOWN_TOP_KEYS = frozenset(
    {"app_id", "project_id", "explanation", "footsteps", "consent_version", "metadata"}
)
KNOWN_FOOTSTEP_KEYS = frozenset(
    {"timestamp", "type", "route", "target", "label", "metadata"}
)
REQUIRED_FOOTSTEP_KEYS = frozenset({"timestamp", "type", "route"})

OUTCOMES = ("rejected", "dropped", "redacted", "accepted")


@dataclass
class Classification:
    outcome: str  # one of OUTCOMES
    detail: List[str] = field(default_factory=list)
    scrubbed: Optional[Dict[str, Any]] = None  # what would have been stored (None if rejected)


def _schema_violations(payload: Dict[str, Any]) -> List[str]:
    """The offline mirror of the router's extra="forbid" pydantic boundary."""
    problems: List[str] = []
    for key in payload:
        if key not in KNOWN_TOP_KEYS:
            problems.append(f"unknown top-level key {key!r}")
    if "footsteps" not in payload or not isinstance(payload.get("footsteps"), list):
        problems.append("footsteps missing or not a list")
        return problems
    for i, step in enumerate(payload["footsteps"]):
        if not isinstance(step, dict):
            problems.append(f"footsteps[{i}] is not an object")
            continue
        for key in step:
            if key not in KNOWN_FOOTSTEP_KEYS:
                problems.append(f"unknown key {key!r} on footsteps[{i}]")
        for key in REQUIRED_FOOTSTEP_KEYS:
            if key not in step:
                problems.append(f"footsteps[{i}] missing required {key!r}")
        step_type = step.get("type")
        if step_type is not None and step_type not in SUPPORTED_STEP_TYPES:
            problems.append(
                f"footsteps[{i}].type {step_type!r} not in {list(SUPPORTED_STEP_TYPES)}"
            )
    return problems


def _resolve(scrubbed: Dict[str, Any], path: str) -> Any:
    """Look a scrub-report field path up in the scrubbed output.

    Paths look like ``explanation``, ``metadata.cookies``, ``footsteps[2].label``,
    ``footsteps[2].metadata.stack``. Missing anywhere along the way → None.
    """
    node: Any = scrubbed
    for part in re.split(r"\.", path):
        m = re.match(r"^([a-z_]+)\[(\d+)\]$", part)
        if m:
            node = (node or {}).get(m.group(1)) if isinstance(node, dict) else None
            idx = int(m.group(2))
            node = node[idx] if isinstance(node, list) and idx < len(node) else None
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            return None
    return node


def classify_payload(payload: Dict[str, Any], policy: ScrubPolicy) -> Classification:
    """What would the live router do with this payload under this policy?

    ``rejected`` = a 422 (schema violation or ScrubRejection): nothing stored.
    ``dropped``  = at least one field removed before storage.
    ``redacted`` = at least one value rewritten before storage.
    ``accepted`` = stored exactly as sent.
    The hierarchy (rejected > dropped > redacted) names the strongest action taken.
    """
    schema_problems = _schema_violations(payload)
    if schema_problems:
        return Classification(outcome="rejected", detail=schema_problems)
    try:
        scrubbed, report = scrub_trace_payload(json.loads(json.dumps(payload)), policy)
    except ScrubRejection as exc:
        return Classification(
            outcome="rejected",
            detail=[f"scrub policy rejected: {f}" for f in exc.fields],
        )
    dropped: List[str] = []
    redacted: List[str] = []
    for path in report["scrubbed_fields"]:
        value = _resolve(scrubbed, path)
        (dropped if value is None else redacted).append(path)
    if dropped:
        return Classification(
            outcome="dropped",
            detail=[f"dropped: {p}" for p in dropped] + [f"redacted: {p}" for p in redacted],
            scrubbed=scrubbed,
        )
    if redacted:
        return Classification(
            outcome="redacted",
            detail=[f"redacted: {p}" for p in redacted],
            scrubbed=scrubbed,
        )
    return Classification(outcome="accepted", scrubbed=scrubbed)


@dataclass
class FixtureResult:
    name: str
    expected: str
    outcome: str
    leaked: List[str]
    detail: List[str]

    @property
    def passed(self) -> bool:
        return self.outcome == self.expected and not self.leaked

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "expected": self.expected,
            "outcome": self.outcome,
            "passed": self.passed,
            "leaked": self.leaked,
            "detail": self.detail,
        }


@dataclass
class FixtureRunResult:
    profile: str
    results: List[FixtureResult]

    @property
    def ok(self) -> bool:
        return all(r.passed for r in self.results)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.profile,
            "ok": self.ok,
            "results": [r.as_dict() for r in self.results],
        }


def _scan_for_leaks(scrubbed: Optional[Dict[str, Any]], literals: List[str]) -> List[str]:
    """Any must_not_persist literal that survives into the would-be-stored JSON is a
    hard FAIL regardless of the expected outcome — persistence is the whole question."""
    if scrubbed is None:  # rejected: nothing would be stored
        return []
    blob = json.dumps(scrubbed)
    return [lit for lit in literals if lit in blob]


def build_policy(profile_name: str, overrides: Dict[str, Any]) -> ScrubPolicy:
    if profile_name not in available_profiles():
        raise ValueError(
            f"unknown profile {profile_name!r}; available: {available_profiles()}"
        )
    base = policy_from_profile(get_profile(profile_name))
    return apply_scrub_overrides(base, overrides or {})


def verify_fixtures(
    doc: Dict[str, Any], profile_override: Optional[str] = None
) -> FixtureRunResult:
    version = doc.get("version")
    if version != FIXTURE_FILE_VERSION:
        raise ValueError(
            f"fixture file version {version!r} not supported (expected {FIXTURE_FILE_VERSION})"
        )
    profile_name = profile_override or doc.get("profile")
    if not isinstance(profile_name, str) or not profile_name:
        raise ValueError("fixture file needs a 'profile' (or pass --profile)")
    overrides = doc.get("overrides") or {}
    if not isinstance(overrides, dict):
        raise ValueError("'overrides' must be an object")
    fixtures = doc.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError("'fixtures' must be a non-empty list")

    policy = build_policy(profile_name, overrides)
    results: List[FixtureResult] = []
    for i, fx in enumerate(fixtures):
        if not isinstance(fx, dict):
            raise ValueError(f"fixtures[{i}] is not an object")
        name = str(fx.get("name") or f"fixture-{i}")
        expected = fx.get("expect")
        if expected not in OUTCOMES:
            raise ValueError(f"{name}: 'expect' must be one of {list(OUTCOMES)}")
        payload = fx.get("payload")
        if not isinstance(payload, dict):
            raise ValueError(f"{name}: 'payload' must be an object")
        literals_raw = fx.get("must_not_persist") or []
        literals = [str(item) for item in literals_raw]
        cls = classify_payload(payload, policy)
        results.append(
            FixtureResult(
                name=name,
                expected=str(expected),
                outcome=cls.outcome,
                leaked=_scan_for_leaks(cls.scrubbed, literals),
                detail=cls.detail,
            )
        )
    return FixtureRunResult(profile=profile_name, results=results)


def render_report(run: FixtureRunResult) -> str:
    lines = [f"policy verify — profile {run.profile}", ""]
    for r in run.results:
        status = "PASS" if r.passed else "FAIL"
        line = f"  {status}  {r.name} — expected {r.expected}, got {r.outcome}"
        if r.leaked:
            line += f", LEAKED: {r.leaked}"
        lines.append(line)
        if not r.passed:
            for d in r.detail:
                lines.append(f"          {d}")
    passed = sum(1 for r in run.results if r.passed)
    lines.append("")
    lines.append(
        f"{passed}/{len(run.results)} fixtures passed"
        + ("" if run.ok else " — the policy does NOT hold; fix config before go-live")
    )
    return "\n".join(lines)


__all__: Tuple[str, ...] = (
    "classify_payload",
    "verify_fixtures",
    "build_policy",
    "render_report",
    "Classification",
    "FixtureResult",
    "FixtureRunResult",
    "KNOWN_TOP_KEYS",
    "KNOWN_FOOTSTEP_KEYS",
    "FIXTURE_FILE_VERSION",
)
