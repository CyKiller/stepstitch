"""Deterministic compiler tests — no network, no credentials, stable output."""
from stepstitch_service.compiler import generate_playwright_test

TRACE = [
    {"type": "navigation", "route": "/dashboard", "label": "[masked]"},
    {"type": "click", "route": "/dashboard", "target": "#pay-btn", "label": "[masked]"},
    {"type": "click", "route": "/dashboard", "target": '[data-testid="submit"]', "label": "Submit"},
    {"type": "input", "route": "/dashboard", "target": "#memo", "label": "[masked]"},
    {"type": "navigation", "route": "/accounts/:id", "label": "[masked]"},
    {"type": "api_error", "route": "/accounts/:id", "metadata": {"status": 500, "endpoint": "/api/pay"}},
    {"type": "exception", "route": "/accounts/:id", "metadata": {"name": "TypeError"}},
]


def test_emits_valid_playwright_scaffold():
    code = generate_playwright_test("t_1", TRACE, base_url="https://app.example.test")
    assert code.startswith("import { test, expect } from '@playwright/test';")
    assert "test('StepStitch reproduction'" in code
    assert code.rstrip().endswith("});")


def test_no_embedded_credentials():
    code = generate_playwright_test("t_1", TRACE)
    lowered = code.lower()
    assert "password" not in lowered
    assert "fill('stepstitch-test-value')" in code  # redacted inputs become placeholders
    assert "TODO: authenticate" in code


def test_uses_supplied_base_url_and_templates_ids():
    code = generate_playwright_test("t_1", TRACE, base_url="https://app.example.test/")
    assert "await page.goto('https://app.example.test/dashboard');" in code
    assert "await page.goto('https://app.example.test/accounts/:id');" in code
    assert "TODO: substitute id(s)" in code  # templated route flagged


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
    assert "r.url().includes('/api/pay')" in code
    assert ".toBeLessThan(500);" in code
    # No vacuous wait that would let a broken page pass.
    assert "waitForTimeout" not in code


def test_exception_becomes_a_pageerror_assertion():
    code = generate_playwright_test("t_1", TRACE)
    assert "const pageErrors: string[] = [];" in code
    assert "page.on('pageerror'" in code
    assert "pageErrors.some((m) => m.includes('TypeError'))" in code
    assert ".toBe(false);" in code
