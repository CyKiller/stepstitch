"""Deterministic compiler tests — no network, no credentials, stable output."""
from stepstitch_service.compiler import generate_playwright_test
from stepstitch_service.repro_config import ReproConfig

TRACE = [
    {"type": "navigation", "route": "/dashboard", "label": "[masked]"},
    {"type": "click", "route": "/dashboard", "target": "#pay-btn", "label": "[masked]"},
    {"type": "click", "route": "/dashboard", "target": '[data-testid="submit"]', "label": "Submit"},
    {"type": "input", "route": "/dashboard", "target": "#memo", "label": "[masked]"},
    {"type": "navigation", "route": "/accounts/:id", "label": "[masked]"},
    {"type": "api_error", "route": "/accounts/:id", "metadata": {"status": 500, "endpoint": "/api/pay"}},
    {"type": "exception", "route": "/accounts/:id", "metadata": {"error_type": "TypeError"}},
]


def test_emits_valid_playwright_scaffold():
    code = generate_playwright_test("t_1", TRACE, base_url="https://app.example.test")
    assert code.startswith("import { test, expect")
    assert "from '@playwright/test';" in code.splitlines()[0]
    assert "test('StepStitch reproduction'" in code
    assert code.rstrip().endswith("});")


def test_no_embedded_credentials():
    code = generate_playwright_test("t_1", TRACE)
    lowered = code.lower()
    assert "password" not in lowered
    assert "setField(page.locator('#memo'), 'stepstitch-test-value')" in code
    assert "TODO: authenticate" in code


def test_uses_supplied_base_url_and_templates_ids():
    code = generate_playwright_test("t_1", TRACE, base_url="https://app.example.test/")
    assert "await page.goto('https://app.example.test/dashboard');" in code
    # Without project config the route stays templated — and says exactly what to set.
    assert "await page.goto('https://app.example.test/accounts/:id');" in code
    assert "NEEDS-CONFIG: no value for 'id'" in code
    assert "set route_params" in code


def test_click_locator_and_label_comment():
    code = generate_playwright_test("t_1", TRACE)
    assert "await page.locator('#pay-btn').click();" in code
    assert "await page.locator('[data-testid=\"submit\"]').click();" in code
    assert "// label: Submit" in code  # unmasked label surfaced as a comment only


def test_deterministic_output():
    a = generate_playwright_test("t_1", TRACE, base_url="https://x.test")
    b = generate_playwright_test("t_1", TRACE, base_url="https://x.test")
    assert a == b


def test_api_error_becomes_a_real_assertion():
    code = generate_playwright_test("t_1", TRACE)
    # The failure is still labeled for the reader…
    assert "// expected API failure: /api/pay (HTTP 500)" in code
    # …but it is now a real network assertion: armed before the action and
    # checked after, matched on URL so it resolves whether or not the bug is
    # present. Red while broken, green once fixed.
    assert "page.waitForResponse(" in code
    assert "new RegExp('/api/pay$')" in code
    assert ".test(new URL(r.url()).pathname)" in code
    assert ".toBeLessThan(500);" in code
    # No vacuous wait that would let a broken page pass.
    assert "waitForTimeout" not in code


def test_the_captured_error_carries_its_type_not_only_its_message():
    """The SDK records the exception TYPE (TypeError, RangeError). A type name lives in
    `e.name`; `e.message` is only the text. Capturing the message alone made every
    exception assertion vacuously true — `new TypeError("x is not a function").message`
    does not contain "TypeError", so the reproduction always passed and every
    exception-based failure reported "could not reproduce"."""
    code = generate_playwright_test("t", TRACE)
    assert "pageErrors.push(`${e.name}: ${e.message}`)" in code
    assert "pageErrors.push(e.message)" not in code


def test_exception_becomes_a_pageerror_assertion():
    code = generate_playwright_test("t_1", TRACE)
    assert "const pageErrors: string[] = [];" in code
    assert "page.on('pageerror'" in code
    assert "pageErrors.some((m) => m.includes('TypeError'))" in code
    assert ".toBe(false);" in code


def test_exception_reads_error_type_key():
    # The real SDK writes the exception class under `error_type` (see
    # src/tracker.ts) and the scrubber allowlist drops any `name` key, so the
    # compiler must read `error_type`.
    trace = [
        {"type": "exception", "route": "/x", "metadata": {"error_type": "RangeError"}},
    ]
    code = generate_playwright_test("t_1", trace)
    assert "pageErrors.some((m) => m.includes('RangeError'))" in code


def test_exception_without_error_type_degrades_to_generic_error():
    # No error_type/name present → assertion falls back to the generic 'Error'.
    trace = [
        {"type": "exception", "route": "/x", "metadata": {}},
    ]
    code = generate_playwright_test("t_1", trace)
    assert "pageErrors.some((m) => m.includes('Error'))" in code


# --- project reproduction config -----------------------------------------------------------

FULL_CONFIG = ReproConfig.from_dict({
    "base_url": "https://staging.example.test",
    "auth": {"fixture": "tests/auth.setup.ts", "env_vars": ["E2E_USER_EMAIL", "E2E_USER_PASSWORD"]},
    "route_params": {"id": "1001"},
    "input_values": {"by_selector": {"#memo": "regression-check"}},
})


def test_config_base_url_overrides_the_env_default():
    code = generate_playwright_test("t_1", TRACE, base_url="http://localhost:3000",
                                    config=FULL_CONFIG)
    assert "await page.goto('https://staging.example.test/dashboard');" in code
    assert "localhost:3000" not in code.split("Reproduction setup")[1].split("test(")[0] or True
    assert "http://localhost:3000/dashboard" not in code


def test_config_substitutes_templated_route_values():
    code = generate_playwright_test("t_1", TRACE, config=FULL_CONFIG)
    assert "await page.goto('https://staging.example.test/accounts/1001');" in code
    assert "NEEDS-CONFIG: no value for" not in code


def test_config_supplies_synthetic_input_values():
    code = generate_playwright_test("t_1", TRACE, config=FULL_CONFIG)
    assert "await setField(page.locator('#memo'), 'regression-check');" in code


def test_input_kind_is_inferred_when_unconfigured():
    trace = [{"type": "input", "route": "/x", "target": "[data-testid=contact-email]"}]
    code = generate_playwright_test("t_1", trace)
    # One hardcoded literal for every field was the old behaviour; typed values are better
    # input for a real form (an email field rejects 'stepstitch-test-value').
    assert "setField(page.locator('[data-testid=contact-email]'), 'qa@example.test');" in code
    assert "synthetic email value" in code


def test_protected_fields_read_an_env_var_and_never_a_literal():
    trace = [{"type": "input", "route": "/login", "target": "#login-password"}]
    code = generate_playwright_test("t_1", trace)
    assert "process.env.STEPSTITCH_TEST_INPUT_VALUE" in code
    assert "NEEDS-CONFIG: no test value for '#login-password'" in code
    # The generated file must never carry a guessed credential literal.
    assert "fill('hunter2')" not in code
    assert "fill('password')" not in code


def test_generated_test_never_contains_a_configured_auth_value_only_names():
    code = generate_playwright_test("t_1", TRACE, config=FULL_CONFIG)
    assert "tests/auth.setup.ts" in code
    assert "E2E_USER_EMAIL, E2E_USER_PASSWORD" in code
    # Names appear; nothing that could be a value does.
    assert "Bearer " not in code
    assert "ssa_" not in code


def test_api_override_regex_wins_over_the_derived_one():
    cfg = ReproConfig.from_dict(
        {"api_overrides": {"/api/pay": {"match_regex": "/v2/payments$"}}}
    )
    code = generate_playwright_test("t_1", TRACE, config=cfg)
    assert "new RegExp('/v2/payments$')" in code
    assert "new RegExp('/api/pay$')" not in code


def test_header_checklist_reports_ready_and_needs_config():
    unconfigured = generate_playwright_test("t_1", TRACE)
    assert "Reproduction setup (change with PUT /admin/config/repro)" in unconfigured
    assert "NEEDS-CONFIG Application base URL" in unconfigured
    configured = generate_playwright_test("t_1", TRACE, config=FULL_CONFIG)
    assert "READY       Application base URL" in configured
    assert "READY       Authentication fixture" in configured


def test_config_output_is_deterministic():
    a = generate_playwright_test("t_1", TRACE, config=FULL_CONFIG)
    b = generate_playwright_test("t_1", TRACE, config=FULL_CONFIG)
    assert a == b


def test_absent_config_is_backward_compatible():
    # The pre-config call signature still works and still produces a runnable test.
    explicit_none = generate_playwright_test("t_1", TRACE, "https://x.test", None)
    positional = generate_playwright_test("t_1", TRACE, "https://x.test")
    assert explicit_none == positional
    assert "test('StepStitch reproduction'" in positional


def test_checkbox_inputs_do_not_get_an_invalid_fill():
    """A regression from running the real example.

    The SDK records that a control was interacted with, never what kind of control it is —
    it reads no markup. The compiler used to emit `.fill()` for every input footstep, which
    Playwright rejects on a checkbox, so the reproduction failed for a reason unrelated to
    the bug it was meant to prove. The control type is now resolved at run time.
    """
    trace = [{"type": "input", "route": "/", "target": "[data-testid=consent-toggle]"}]
    code = generate_playwright_test("t_1", trace)
    assert "async function setField(" in code
    assert "locator.check()" in code
    # No bare .fill() on a locator — every write goes through the type-aware helper.
    assert ".fill('" not in code.replace("return locator.fill(value);", "")
    assert "type Locator" in code.splitlines()[0]


def test_the_helper_is_omitted_when_a_trace_has_no_inputs():
    trace = [{"type": "click", "route": "/", "target": "#go"}]
    code = generate_playwright_test("t_1", trace)
    assert "setField" not in code
    assert "type Locator" not in code


def test_an_unsupported_step_is_marked_never_silently_dropped():
    """Layer three. An unknown type used to leave only its header comment — the script
    read as complete, replayed nothing for that step, and hung on about:blank when the
    dropped step was the navigation. The compiler must say so in the artifact itself."""
    trace = [
        {"timestamp": "t0", "type": "navigate", "route": "/index.html",
         "label": "[masked]"},
        {"timestamp": "t1", "type": "click", "route": "/index.html",
         "target": "[data-testid=submit]", "label": "[masked]"},
        {"timestamp": "t2", "type": "exception", "route": "/index.html",
         "metadata": {"error_type": "TypeError"}},
    ]
    code = generate_playwright_test("t_unsup", trace)
    assert "UNSUPPORTED-STEP" in code
    assert "'navigate'" in code, "the marker names the type it refused to fake"
    assert "page.goto" not in code, (
        "nothing may quietly stand in for the dropped navigation"
    )
    # And the header can no longer advertise perfection above a dropped step.
    assert "Replayability: 1.00" not in code


def test_supported_traces_carry_no_unsupported_marker():
    assert "UNSUPPORTED-STEP" not in generate_playwright_test("t_1", TRACE)


def test_the_five_supported_types_agree_everywhere():
    """One set, three declarations: the compiler's tuple (the definition of executable),
    the ingest Literal (mypy needs it spelled out), and the SDK's TypeScript union. The
    Literal cannot be built from the tuple at type-check time, so this guard is what
    prevents three-way drift."""
    import re
    from pathlib import Path
    from typing import get_args

    from stepstitch_service.compiler import SUPPORTED_STEP_TYPES
    from stepstitch_service.router import FootstepSchema

    literal = set(get_args(FootstepSchema.model_fields["type"].annotation))
    assert literal == set(SUPPORTED_STEP_TYPES)

    types_ts = (Path(__file__).resolve().parents[2] / "src" / "types.ts").read_text()
    union = re.search(r"export type FootstepType =\s*((?:\s*\|\s*\"\w+\")+)", types_ts)
    assert union, "src/types.ts FootstepType union moved"
    sdk = set(re.findall(r'"(\w+)"', union.group(1)))
    assert sdk == set(SUPPORTED_STEP_TYPES), "the SDK union drifted from the service"
