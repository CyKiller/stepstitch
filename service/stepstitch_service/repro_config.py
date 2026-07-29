"""Project-level reproduction configuration — pure, no I/O, no secrets.

A captured trace is structural by design: routes are templates (``/accounts/:id``), input
values were never recorded, and the app's real base URL is not the SDK's business. That
leaves four holes the compiler cannot fill on its own, and this module is where a project
fills them once:

  base_url            where the reproduction should point
  auth                which Playwright fixture logs in, and which env vars it reads
  route_params        concrete values for ``:id``-style segments
  input_values        synthetic values to type into fields
  api_overrides       a precise response matcher when the derived one is too loose
  verify_workflow_url the CI workflow that runs the repro red and green

**This config never holds a credential.** ``auth.env_vars`` records env var *names*; the
values live in the CI secret store. ``from_dict`` refuses anything that looks like a secret
(a secret-shaped key, a bearer/JWT-shaped value) rather than storing it — see
``_reject_secretish``. That refusal is the point of the module, not a nicety: config is read
back by the dashboard and compiled into test files, so a stored secret would leak twice.

``readiness()`` answers "which parts of this trace's reproduction are ready to run, and which
still need configuration" — the compiler emits it as a header checklist and the dashboard
shows it in the setup steps.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

__all__ = [
    "ReproConfig",
    "ReproConfigError",
    "AuthConfig",
    "infer_input_kind",
    "synthetic_value",
    "endpoint_match_regex",
    "readiness",
    "DEFAULT_VALUES",
]


class ReproConfigError(ValueError):
    """Invalid reproduction config. The message is shown to the operator verbatim."""


# --- secret refusal ----------------------------------------------------------------------
# A key whose NAME claims to hold a credential, in any position in the document.
_SECRET_KEY = re.compile(r"(token|password|passwd|secret|api[_-]?key|credential|auth_?key)", re.I)
# A value SHAPED like a credential, even under an innocent key.
_SECRET_VALUE_SHAPES: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("a StepStitch token", re.compile(r"^ss[ai]_[A-Za-z0-9_\-]{8,}$")),
    ("a JWT", re.compile(r"^ey[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{4,}\.")),
    ("an Authorization header", re.compile(r"^\s*bearer\s+\S+", re.I)),
    ("a GitHub token", re.compile(r"^gh[pousr]_[A-Za-z0-9]{16,}$")),
    ("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

_NEVER_STORE = (
    "StepStitch never stores credentials in project config. "
    "Put the env var NAME in auth.env_vars and keep the value in your CI secret store."
)


def _reject_secretish(path: str, key: Optional[str], value: Any) -> None:
    """Raise if a key names a credential or a value is shaped like one."""
    if key is not None and _SECRET_KEY.search(key):
        raise ReproConfigError(f"{path}: '{key}' looks like a credential. {_NEVER_STORE}")
    if isinstance(value, str):
        for label, pattern in _SECRET_VALUE_SHAPES:
            if pattern.search(value):
                raise ReproConfigError(f"{path}: the value looks like {label}. {_NEVER_STORE}")


def _str_map(raw: Any, path: str) -> Dict[str, str]:
    """Coerce a {str: str} mapping, rejecting secrets and unhelpful types."""
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ReproConfigError(
            f"{path} must be an object of string values — got {type(raw).__name__}; "
            'example: {"id": "1001"}'
        )
    out: Dict[str, str] = {}
    for key, value in raw.items():
        name = str(key)
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise ReproConfigError(
                f"{path}.{name} must be a string — got {type(value).__name__}; "
                'example: {"id": "1001"}'
            )
        text = str(value)
        _reject_secretish(path, name, text)
        out[name] = text
    return out


def _http_url(raw: Any, path: str) -> Optional[str]:
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        raise ReproConfigError(f"{path} must be a string URL — got {type(raw).__name__}")
    if not re.match(r"^https?://", raw):
        raise ReproConfigError(
            f"{path} must start with http:// or https:// — got '{raw[:60]}'; "
            "example: https://staging.example.test"
        )
    _reject_secretish(path, None, raw)
    return raw.rstrip("/")


@dataclass(frozen=True)
class AuthConfig:
    """A reference to the project's Playwright auth fixture. Names only, never values."""

    fixture: Optional[str] = None
    env_vars: Tuple[str, ...] = ()

    @staticmethod
    def from_dict(raw: Any) -> Optional["AuthConfig"]:
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            raise ReproConfigError(
                "auth must be an object; "
                'example: {"fixture": "tests/auth.setup.ts", "env_vars": ["E2E_USER_EMAIL"]}'
            )
        fixture = raw.get("fixture")
        if fixture is not None and not isinstance(fixture, str):
            raise ReproConfigError("auth.fixture must be a string path, e.g. tests/auth.setup.ts")
        if isinstance(fixture, str):
            _reject_secretish("auth.fixture", None, fixture)
        env_raw = raw.get("env_vars") or []
        if not isinstance(env_raw, (list, tuple)):
            raise ReproConfigError(
                'auth.env_vars must be a list of env var NAMES; example: ["E2E_USER_EMAIL"]'
            )
        names: List[str] = []
        for item in env_raw:
            if not isinstance(item, str):
                raise ReproConfigError("auth.env_vars entries must be strings (env var names)")
            # A NAME is fine even when it contains 'PASSWORD' — that is the point. A VALUE
            # is not: anything that isn't shaped like an identifier is rejected here.
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item):
                raise ReproConfigError(
                    f"auth.env_vars: '{item[:40]}' is not an env var name. {_NEVER_STORE}"
                )
            names.append(item)
        if fixture is None and not names:
            return None
        return AuthConfig(fixture=fixture, env_vars=tuple(names))


@dataclass(frozen=True)
class ReproConfig:
    """Validated project reproduction settings. Absent fields fall back to compiler defaults."""

    base_url: Optional[str] = None
    auth: Optional[AuthConfig] = None
    route_params: Dict[str, str] = field(default_factory=dict)
    input_by_selector: Dict[str, str] = field(default_factory=dict)
    input_by_kind: Dict[str, str] = field(default_factory=dict)
    api_overrides: Dict[str, str] = field(default_factory=dict)
    verify_workflow_url: Optional[str] = None

    @staticmethod
    def from_dict(raw: Any) -> "ReproConfig":
        """Validate an operator-supplied document. Raises ``ReproConfigError`` with a message
        written to be shown directly to the person who typed it."""
        if raw is None:
            return ReproConfig()
        if not isinstance(raw, Mapping):
            raise ReproConfigError(
                f"reproduction config must be a JSON object — got {type(raw).__name__}"
            )

        known = {
            "base_url", "auth", "route_params", "input_values",
            "api_overrides", "verify_workflow_url",
        }
        unknown = sorted(set(map(str, raw.keys())) - known)
        if unknown:
            raise ReproConfigError(
                f"unknown setting(s): {', '.join(unknown)}. "
                f"Supported: {', '.join(sorted(known))}"
            )

        inputs = raw.get("input_values") or {}
        if not isinstance(inputs, Mapping):
            raise ReproConfigError(
                'input_values must be an object with "by_selector" and/or "by_type"'
            )
        unknown_inputs = sorted(set(map(str, inputs.keys())) - {"by_selector", "by_type"})
        if unknown_inputs:
            raise ReproConfigError(
                f"input_values: unknown key(s) {', '.join(unknown_inputs)}. "
                "Supported: by_selector, by_type"
            )

        overrides_raw = raw.get("api_overrides") or {}
        if not isinstance(overrides_raw, Mapping):
            raise ReproConfigError(
                'api_overrides must be an object keyed by endpoint template; example: '
                '{"/api/accounts/:id/transfers": {"match_regex": "/api/accounts/[^/]+/transfers$"}}'
            )
        overrides: Dict[str, str] = {}
        for endpoint, spec in overrides_raw.items():
            name = str(endpoint)
            if not isinstance(spec, Mapping) or "match_regex" not in spec:
                raise ReproConfigError(
                    f"api_overrides['{name}'] must be an object with a match_regex key"
                )
            pattern = spec.get("match_regex")
            if not isinstance(pattern, str) or not pattern:
                raise ReproConfigError(
                    f"api_overrides['{name}'].match_regex must be a non-empty string"
                )
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ReproConfigError(
                    f"api_overrides['{name}'].match_regex is not a valid regex: {exc}"
                ) from exc
            overrides[name] = pattern

        return ReproConfig(
            base_url=_http_url(raw.get("base_url"), "base_url"),
            auth=AuthConfig.from_dict(raw.get("auth")),
            route_params=_str_map(raw.get("route_params"), "route_params"),
            input_by_selector=_str_map(inputs.get("by_selector"), "input_values.by_selector"),
            input_by_kind=_str_map(inputs.get("by_type"), "input_values.by_type"),
            api_overrides=overrides,
            verify_workflow_url=_http_url(raw.get("verify_workflow_url"), "verify_workflow_url"),
        )

    def as_dict(self) -> Dict[str, Any]:
        """Round-trippable document (the shape ``from_dict`` accepts)."""
        doc: Dict[str, Any] = {}
        if self.base_url:
            doc["base_url"] = self.base_url
        if self.auth is not None:
            auth: Dict[str, Any] = {}
            if self.auth.fixture:
                auth["fixture"] = self.auth.fixture
            if self.auth.env_vars:
                auth["env_vars"] = list(self.auth.env_vars)
            doc["auth"] = auth
        if self.route_params:
            doc["route_params"] = dict(self.route_params)
        inputs: Dict[str, Any] = {}
        if self.input_by_selector:
            inputs["by_selector"] = dict(self.input_by_selector)
        if self.input_by_kind:
            inputs["by_type"] = dict(self.input_by_kind)
        if inputs:
            doc["input_values"] = inputs
        if self.api_overrides:
            doc["api_overrides"] = {
                k: {"match_regex": v} for k, v in sorted(self.api_overrides.items())
            }
        if self.verify_workflow_url:
            doc["verify_workflow_url"] = self.verify_workflow_url
        return doc

    def is_empty(self) -> bool:
        return not self.as_dict()


# --- synthetic input values ---------------------------------------------------------------
# The SDK never records an input's value OR its type — only the structural selector. So the
# kind is inferred from the selector text alone, deterministically. Every default below is
# obviously synthetic: a reader of the generated test must never wonder if it is real data.
DEFAULT_VALUES: Dict[str, str] = {
    "email": "qa@example.test",
    "tel": "555-0100",
    "number": "1",
    "date": "2024-01-15",
    "url": "https://example.test",
    "search": "stepstitch-test-value",
    "text": "stepstitch-test-value",
}

_KIND_HINTS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    # Ordered: the first match wins, so the most specific hints come first.
    ("password", re.compile(r"passw|pwd|passcode", re.I)),
    ("email", re.compile(r"e-?mail", re.I)),
    ("tel", re.compile(r"\btel\b|phone|mobile", re.I)),
    ("date", re.compile(r"\bdate\b|dob|birth", re.I)),
    ("url", re.compile(r"\burl\b|website|\blink\b", re.I)),
    ("number", re.compile(r"amount|qty|quantity|\bnum\b|number|price|total|count", re.I)),
    ("search", re.compile(r"search|query", re.I)),
)


def infer_input_kind(selector: str) -> str:
    """Best-effort field kind from a structural selector. Deterministic; defaults to 'text'.

    ``[data-testid=transfer-amount]`` -> ``number``; ``#login-password`` -> ``password``.
    """
    text = selector or ""
    for kind, pattern in _KIND_HINTS:
        if pattern.search(text):
            return kind
    return "text"


def synthetic_value(selector: str, config: Optional[ReproConfig]) -> Tuple[Optional[str], str]:
    """Return ``(value, kind)`` to fill ``selector`` with. ``value`` is None when the operator
    must supply it — a password field, where guessing a literal would be both wrong and unsafe.

    Precedence: exact selector override > kind override > built-in synthetic default.
    """
    kind = infer_input_kind(selector)
    if config is not None:
        exact = config.input_by_selector.get(selector)
        if exact is not None:
            return exact, kind
        by_kind = config.input_by_kind.get(kind)
        if by_kind is not None:
            return by_kind, kind
    if kind == "password":
        return None, kind
    return DEFAULT_VALUES.get(kind, DEFAULT_VALUES["text"]), kind


# --- endpoint matching --------------------------------------------------------------------
def endpoint_match_regex(endpoint: str, config: Optional[ReproConfig] = None) -> Optional[str]:
    """A JS-compatible regex source matching a templated endpoint's concrete runtime URL.

    ``/api/accounts/:id/transfers`` -> ``/api/accounts/[^/]+/transfers$``. Anchored at the end
    so a busy page's other traffic under the same prefix cannot bind the wait — the failure
    mode of the older "prefix before the first ``:``" match. An operator override wins.
    """
    if config is not None:
        override = config.api_overrides.get(endpoint)
        if override:
            return override
    if not endpoint:
        return None
    # Strip any leaked origin; match on the path only.
    path = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/]+", "", endpoint)
    if not path.startswith("/"):
        path = "/" + path
    parts: List[str] = []
    for segment in path.split("/"):
        if not segment:
            continue
        parts.append("[^/]+" if segment.startswith(":") else re.escape(segment))
    if not parts:
        return None
    return "/" + "/".join(parts) + "$"


# --- readiness ----------------------------------------------------------------------------
_PARAM = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")


def route_params_in(footsteps: List[Dict[str, Any]]) -> List[str]:
    """Every distinct ``:param`` name a navigation in this trace needs, in first-seen order."""
    seen: List[str] = []
    for step in footsteps or []:
        if str(step.get("type", "")).lower() != "navigation":
            continue
        for name in _PARAM.findall(str(step.get("route", ""))):
            if name not in seen:
                seen.append(name)
    return seen


def readiness(
    config: Optional[ReproConfig],
    footsteps: List[Dict[str, Any]],
    *,
    fallback_base_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Which parts of this trace's reproduction can run as-is, and which need configuration.

    Each item is ``{id, ready, title, detail}``. ``detail`` names the exact setting to change,
    so the compiler header and the dashboard checklist can both show an actionable next step.
    """
    cfg = config or ReproConfig()
    items: List[Dict[str, Any]] = []

    base = cfg.base_url or fallback_base_url
    items.append({
        "id": "base_url",
        "ready": bool(base),
        "title": "Application base URL",
        "detail": (
            f"points at {base}" if base
            else "not set — the reproduction will target http://localhost:3000. "
                 'Set base_url (e.g. "https://staging.example.test").'
        ),
    })

    needed = route_params_in(footsteps)
    missing = [p for p in needed if p not in cfg.route_params]
    if needed:
        items.append({
            "id": "route_params",
            "ready": not missing,
            "title": "Templated route values",
            "detail": (
                "every templated segment has a test value"
                if not missing
                else "no value for " + ", ".join(f"':{p}'" for p in missing)
                     + ' — set route_params, e.g. {"' + missing[0] + '": "1001"}'
            ),
        })

    input_steps = [
        s for s in footsteps or []
        if str(s.get("type", "")).lower() == "input" and s.get("target")
    ]
    if input_steps:
        unresolved = [
            str(s["target"]) for s in input_steps
            if synthetic_value(str(s["target"]), cfg)[0] is None
        ]
        items.append({
            "id": "input_values",
            "ready": not unresolved,
            "title": "Synthetic form values",
            "detail": (
                f"{len(input_steps)} field(s) filled with synthetic test values"
                if not unresolved
                else "needs a test value for " + ", ".join(unresolved[:3])
                     + " — set input_values.by_selector (never a real credential)"
            ),
        })

    auth_ready = cfg.auth is not None and bool(cfg.auth.fixture)
    items.append({
        "id": "auth",
        "ready": auth_ready,
        "title": "Authentication fixture",
        "detail": (
            f"uses {cfg.auth.fixture}"  # type: ignore[union-attr]
            + (f" (env: {', '.join(cfg.auth.env_vars)})" if cfg.auth and cfg.auth.env_vars else "")
            if auth_ready
            else "not configured — the reproduction runs unauthenticated. "
                 'Set auth.fixture (e.g. "tests/auth.setup.ts") if the flow needs a session.'
        ),
    })

    return items
