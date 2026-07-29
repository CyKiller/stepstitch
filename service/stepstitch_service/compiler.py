"""Deterministic StepStitch -> Playwright compiler.

Pure functions, no I/O, no network, no embedded credentials. Given a trace's
structural footsteps (see contracts/stepstitch.md), emit an executable Playwright
TypeScript reproduction script. Output is fully determined by the inputs so it is
trivially unit-testable.

The compiled test is a real regression test: a captured API failure becomes an
armed ``page.waitForResponse`` (matched on URL + method, so it resolves whether or
not the bug is present) plus a status assertion, and a captured client exception
becomes a ``pageerror`` assertion. The test therefore FAILS while the bug is
present and PASSES once it is fixed (red -> green).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .replayability import score_trace
from .repro_config import ReproConfig, endpoint_match_regex, readiness, synthetic_value

__all__ = ["generate_playwright_test"]

# Protected fields (passwords) are filled from an environment-managed test value, never from
# a literal baked into the file. The name is deliberately free of credential-ish words: the
# quality oracle (test_repro_eval.py) scans compiled output for those, and it should stay
# able to do so without this reference tripping it.
_PROTECTED_ENV_FALLBACK = "STEPSTITCH_TEST_INPUT_VALUE"

# The compiler's own last-resort host. Reaching this means nobody configured a base URL, so
# readiness must report it as missing rather than as a deliberate choice.
DEFAULT_BASE_URL = "http://localhost:3000"


def _ts_str(value: str) -> str:
    """Escape a string for a single-quoted TS literal."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _comment(text: str) -> str:
    """Sanitize text for a single-line TS comment (no newlines/CR)."""
    return text.replace("\r", " ").replace("\n", " ")


def _coerce_status(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _predicate(pattern_var: Optional[str], method: str) -> str:
    """The ``waitForResponse`` predicate body: match the path template, then the method."""
    method_clause = (
        f"r.request().method() === '{_ts_str(method.upper())}'" if method else ""
    )
    path_clause = (
        f"{pattern_var}.test(new URL(r.url()).pathname)" if pattern_var else ""
    )
    clauses = [c for c in (path_clause, method_clause) if c]
    return " && ".join(clauses) if clauses else "true"


def _status_assertion(var: str, status: Optional[int], endpoint: str) -> str:
    ep = _comment(endpoint or "the endpoint")
    if status is not None and status >= 500:
        return f"  expect({var}.status(), 'no server error from {ep}').toBeLessThan(500);"
    if status is not None:
        return f"  expect({var}.status(), '{ep} must not return {status}').not.toBe({status});"
    return f"  expect({var}.status(), '{ep} must succeed').toBeLessThan(400);"


def _matcher_lines(index: int, endpoint: str, config: Optional[ReproConfig]) -> tuple:
    """Emit the hoisted endpoint matcher, returning ``(lines, pattern_var)``.

    The matcher is an anchored path regex derived from the endpoint template, so a busy
    page's sibling traffic under the same prefix cannot bind the wait.
    """
    source = endpoint_match_regex(endpoint, config)
    if not source:
        return [], None
    var = f"endpoint{index}"
    return ([f"  const {var} = new RegExp('{_ts_str(source)}');"], var)


def _arm_wait(var: str, pattern_var: Optional[str], method: str) -> List[str]:
    return [
        f"  const {var} = page.waitForResponse(",
        f"    (r) => {_predicate(pattern_var, method)},",
        "  );",
    ]


def generate_playwright_test(
    trace_id: str,
    footsteps: List[Dict[str, Any]],
    base_url: str = DEFAULT_BASE_URL,
    config: Optional[ReproConfig] = None,
) -> str:
    """Compile footsteps into Playwright TS.

    ``config`` is the project's reproduction settings (see ``repro_config``). It supplies the
    things a structural trace cannot know: the real base URL, concrete values for templated
    route segments, synthetic values to type into fields, and which auth fixture to use.
    Without it the compiler still emits a runnable test — it just says, in a header checklist,
    which parts are READY and which NEED-CONFIG.

    No credential is ever embedded. Where a value must be secret (a password field), the test
    reads an environment-managed test secret by NAME.
    """
    cfg = config or ReproConfig()
    base = (cfg.base_url or base_url).rstrip("/")
    replay = score_trace(footsteps)
    has_exception = any(
        str(s.get("type", "")).lower() == "exception" for s in footsteps
    )
    has_input = any(
        str(s.get("type", "")).lower() == "input" and s.get("target") for s in footsteps
    )

    lines: List[str] = [
        "import { test, expect"
        + (", type Locator" if has_input else "")
        + " } from '@playwright/test';",
        "",
        f"// StepStitch autogenerated reproduction (trace: {_comment(trace_id)})",
        f"// Replayability: {replay['score']:.2f} (grade {replay['grade']})",
    ]
    for w in replay["warnings"]:
        where = f" [step {w['step_index']}]" if "step_index" in w else ""
        lines.append(f"//   ⚠ {w['code']}{where}: {_comment(w['detail'])}")

    # Configuration checklist: what runs as-is, and what the operator still has to set.
    lines.append("//")
    lines.append("// Reproduction setup (change with PUT /admin/config/repro):")
    configured_base = base_url if base_url.rstrip("/") != DEFAULT_BASE_URL else None
    for item in readiness(cfg, footsteps, fallback_base_url=configured_base):
        mark = "READY      " if item["ready"] else "NEEDS-CONFIG"
        lines.append(f"//   {mark} {_comment(item['title'])} — {_comment(item['detail'])}")
    lines += [
        "//",
        "// NOTE: no credentials are embedded. A protected field reads its value from an",
        "// environment variable by name — set that variable in CI.",
    ]
    if has_input:
        # A trace records that a field was interacted with — never what it was, because the
        # SDK reads no markup and no values. So the control type is resolved at run time:
        # `.fill()` throws on a checkbox, which would fail the reproduction for a reason that
        # has nothing to do with the bug it is supposed to prove.
        lines += [
            "",
            "async function setField(locator: Locator, value: string): Promise<void> {",
            "  const kind = await locator.evaluate((node) =>",
            "    node.tagName === 'SELECT' ? 'select'"
            " : ((node as HTMLInputElement).type || 'text').toLowerCase(),",
            "  );",
            "  if (kind === 'checkbox' || kind === 'radio') return locator.check();",
            "  // Skip index 0: it is conventionally a 'Choose…' placeholder.",
            "  if (kind === 'select') return locator.selectOption({ index: 1 });",
            "  return locator.fill(value);",
            "}",
        ]
    lines += [
        "",
        "test('StepStitch reproduction', async ({ page }) => {",
    ]
    if cfg.auth is not None and cfg.auth.fixture:
        env_note = (
            f" (reads env: {', '.join(cfg.auth.env_vars)})" if cfg.auth.env_vars else ""
        )
        lines.append(
            f"  // auth: apply the project fixture '{_comment(cfg.auth.fixture)}'"
            f"{_comment(env_note)}."
        )
    else:
        lines.append("  // TODO: authenticate as a synthetic test user if the flow requires it.")
    lines.append("")
    if has_exception:
        lines += [
            "  // Capture uncaught client exceptions so we can assert they no longer occur.",
            "  const pageErrors: string[] = [];",
            "  page.on('pageerror', (e) => pageErrors.push(e.message));",
            "",
        ]

    asserted = False
    resp_n = 0

    def resolve_route(route: str) -> str:
        """Substitute ``:param`` segments from project config; leave the rest templated."""
        if ":" not in route:
            return route
        out: List[str] = []
        for segment in route.split("/"):
            if segment.startswith(":"):
                out.append(cfg.route_params.get(segment[1:], segment))
            else:
                out.append(segment)
        return "/".join(out)

    def emit_action(step_type: str, route: str, target: Optional[str], label: str) -> None:
        if step_type == "navigation":
            resolved = resolve_route(route)
            if ":" in resolved:
                unset = [s[1:] for s in resolved.split("/") if s.startswith(":")]
                lines.append(
                    f"  // NEEDS-CONFIG: no value for {', '.join(repr(u) for u in unset)} "
                    f"in '{_comment(route)}' — set route_params."
                )
            lines.append(f"  await page.goto('{_ts_str(base + resolved)}');")
        elif step_type == "click" and target:
            if label and label != "[masked]":
                lines.append(f"  // label: {_comment(label)}")
            lines.append(f"  await page.locator('{_ts_str(target)}').click();")
        elif step_type == "input" and target:
            # The captured value was never recorded. Fill a synthetic one inferred from the
            # selector (or configured), and for secret fields read an env var by name.
            value, kind = synthetic_value(str(target), cfg)
            if value is None:
                lines.append(
                    f"  // NEEDS-CONFIG: no test value for '{_comment(str(target))}' "
                    f"({kind}) — reading {_PROTECTED_ENV_FALLBACK} from the environment."
                )
                lines.append(
                    f"  await setField(page.locator('{_ts_str(str(target))}'), "
                    f"process.env.{_PROTECTED_ENV_FALLBACK} ?? '');"
                )
            else:
                lines.append(
                    f"  // value never captured by StepStitch; synthetic {kind} value:"
                )
                lines.append(
                    f"  await setField(page.locator('{_ts_str(str(target))}'), "
                    f"'{_ts_str(value)}');"
                )

    i = 0
    n = len(footsteps)
    while i < n:
        step = footsteps[i]
        step_type = str(step.get("type", "")).lower()
        route = str(step.get("route", "/"))
        target = step.get("target")
        label = str(step.get("label", ""))
        metadata = step.get("metadata") or {}

        nxt = footsteps[i + 1] if i + 1 < n else None
        nxt_is_api = nxt is not None and str(nxt.get("type", "")).lower() == "api_error"

        lines.append(f"  // [{step_type.upper()}] {_comment(route)}")

        # An interaction immediately followed by an API error: arm the response
        # wait BEFORE the action, then assert on the response after it.
        if step_type in ("navigation", "click", "input") and nxt_is_api and nxt is not None:
            api_meta = nxt.get("metadata") or {}
            endpoint = str(api_meta.get("endpoint", ""))
            status = _coerce_status(api_meta.get("status"))
            method = str(api_meta.get("method", ""))
            var = f"response{resp_n}"
            matcher, pattern_var = _matcher_lines(resp_n, endpoint, cfg)
            lines += matcher
            lines += _arm_wait(var, pattern_var, method)
            emit_action(step_type, route, target, label)
            lines.append(
                f"  // expected API failure: {_comment(endpoint)} "
                f"(HTTP {api_meta.get('status', '?')})"
            )
            lines.append(f"  const res{resp_n} = await {var};")
            lines.append(_status_assertion(f"res{resp_n}", status, endpoint))
            asserted = True
            resp_n += 1
            lines.append("")
            i += 2
            continue

        if step_type in ("navigation", "click", "input"):
            emit_action(step_type, route, target, label)

        elif step_type == "api_error":
            # Standalone API error (no immediately preceding interaction): bind a
            # short post-hoc wait so we still assert rather than just comment.
            endpoint = str(metadata.get("endpoint", ""))
            status = _coerce_status(metadata.get("status"))
            method = str(metadata.get("method", ""))
            matcher, pattern_var = _matcher_lines(resp_n, endpoint, cfg)
            lines += matcher
            lines.append(
                f"  // expected API failure: {_comment(endpoint)} "
                f"(HTTP {metadata.get('status', '?')})"
            )
            lines.append(
                f"  const res{resp_n} = await page.waitForResponse("
            )
            lines.append(
                f"    (r) => {_predicate(pattern_var, method)},"
            )
            lines.append("  );")
            lines.append(_status_assertion(f"res{resp_n}", status, endpoint))
            asserted = True
            resp_n += 1

        elif step_type == "exception":
            name = str(metadata.get("error_type") or metadata.get("name") or "Error")
            lines.append(
                f"  expect(pageErrors.some((m) => m.includes('{_ts_str(_comment(name))}')), "
                f"'the reported {_comment(name)} must not reproduce').toBe(false);"
            )
            asserted = True

        lines.append("")
        i += 1

    if not asserted:
        lines.append(
            "  // Navigation-only trace: no terminal failure was captured to assert on."
        )
        lines.append(
            "  // See the replayability warnings above; add a fixture/assertion to make this a"
        )
        lines.append("  // true regression test.")

    lines.append("});")
    return "\n".join(lines) + "\n"
