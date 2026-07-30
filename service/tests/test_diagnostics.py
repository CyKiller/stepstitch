"""Diagnostics: provenance that cannot be configured away, and an envelope that refuses.

The interesting assertions here are all about what this module will NOT do — claim customer
provenance, grow without bound, or let a verification run under a different experiment than
the one that was frozen.
"""
import json
import zipfile

import pytest
from stepstitch_service.diagnostics import (
    MAX_CONSOLE_ERRORS,
    MAX_FIELD_CHARS,
    SCHEMA_VERSION,
    SOURCE_SYNTHETIC,
    Diagnostics,
    EnvelopeMismatch,
    ExecutionEnvelope,
    check_envelope,
    parse_trace,
    provenance,
    scrub_diagnostics,
)


def _envelope(**over):
    base = dict(
        config="export default {}", browser="chromium 141.0.7390.37",
        base_url="http://127.0.0.1:4321", timeout_ms=120000, retries=0,
        diagnostics_profile="four-signal", runner_version="0.9.1",
        env_names=["PATH", "HOME"],
    )
    base.update(over)
    return ExecutionEnvelope(**base)


# --- provenance -------------------------------------------------------------------------

def test_every_record_says_where_it_came_from():
    """A reader must be able to tell reproduction evidence from production evidence
    without knowing which endpoint produced it."""
    stamp = provenance()
    assert stamp["source"] == SOURCE_SYNTHETIC
    assert stamp["contains_customer_session_data"] is False
    assert stamp["schema_version"] == SCHEMA_VERSION


def test_a_diagnostics_record_carries_the_stamp():
    out = Diagnostics(console_errors=["boom"]).as_dict()
    assert out["source"] == SOURCE_SYNTHETIC
    assert out["contains_customer_session_data"] is False


def test_provenance_survives_scrubbing():
    """Scrubbing rewrites strings; it must not be able to strip or alter the claim about
    where the data came from."""
    record = Diagnostics(console_errors=["token=abc123"]).as_dict()
    cleaned = scrub_diagnostics(record, lambda s: s.replace("abc123", "[redacted]"))
    assert cleaned["source"] == SOURCE_SYNTHETIC
    assert cleaned["contains_customer_session_data"] is False
    assert "abc123" not in str(cleaned)


def test_scrubbing_reaches_nested_strings():
    record = Diagnostics(
        failed_requests=[{"path": "/api/x", "note": "secret=hunter2"}],
        failure_snapshot={"html": "<b>secret=hunter2</b>"},
    ).as_dict()
    cleaned = scrub_diagnostics(record, lambda s: s.replace("hunter2", "[redacted]"))
    assert "hunter2" not in str(cleaned)


# --- bounds -----------------------------------------------------------------------------

def test_a_record_cannot_grow_without_bound():
    """The size argument the product makes dies if one noisy page can produce a megabyte
    of diagnostics."""
    out = Diagnostics(
        console_errors=[f"error {i}" for i in range(500)],
        failed_requests=[{"path": f"/api/{i}"} for i in range(500)],
    ).as_dict()
    assert len(out["console_errors"]) == MAX_CONSOLE_ERRORS
    assert len(out["failed_requests"]) <= 20


def test_a_single_huge_field_is_clipped():
    out = Diagnostics(console_errors=["x" * (MAX_FIELD_CHARS * 3)]).as_dict()
    assert len(out["console_errors"][0]) <= MAX_FIELD_CHARS + 20
    assert out["console_errors"][0].endswith("[truncated]")


# --- the execution envelope -------------------------------------------------------------

def test_env_vars_are_pinned_by_name_never_by_value():
    """How a run was configured is worth freezing. What was in the variables is exactly
    what must never be recorded."""
    payload = _envelope().as_dict()
    assert payload["env_names"] == ["HOME", "PATH"]
    assert "env_values" not in payload and "env" not in payload


def test_the_same_envelope_hashes_the_same():
    assert _envelope().sha256() == _envelope().sha256()
    # Order of env names must not matter — it is a set in spirit.
    assert _envelope(env_names=["HOME", "PATH"]).sha256() == _envelope(
        env_names=["PATH", "HOME"]).sha256()


@pytest.mark.parametrize("field,value", [
    ("browser", "chromium 999.0.0.0"),
    ("base_url", "http://127.0.0.1:9999"),
    ("timeout_ms", 5000),
    ("retries", 2),
    ("diagnostics_profile", "off"),
    ("runner_version", "0.9.2"),
    ("config", "export default { different: true }"),
])
def test_any_change_to_how_it_runs_moves_the_hash(field, value):
    assert _envelope(**{field: value}).sha256() != _envelope().sha256()


def test_a_matching_envelope_is_allowed_through():
    env = _envelope()
    check_envelope(env.sha256(), env)          # must not raise


def test_a_different_experiment_is_refused_not_reported():
    """A fix 'proven' under a different browser or base URL was not proven against the
    same experiment. Refusing beats explaining afterwards."""
    with pytest.raises(EnvelopeMismatch, match="different experiment"):
        check_envelope(_envelope().sha256(), _envelope(browser="firefox 1"))


def test_no_recorded_envelope_means_nothing_to_enforce():
    # Sessions frozen before envelopes existed must still be verifiable.
    check_envelope(None, _envelope())


# --- parsing a real Playwright trace ------------------------------------------------------
# Event shapes below were read off a trace.zip this runner actually produced, not from
# documentation — the SDK-2.0 break taught us what assuming a third-party shape costs.

def _trace(tmp_path, *, test_trace=None, trace=None, network=None):
    path = tmp_path / "trace.zip"
    with zipfile.ZipFile(path, "w") as archive:
        if test_trace is not None:
            archive.writestr("test.trace", "\n".join(json.dumps(e) for e in test_trace))
        if trace is not None:
            archive.writestr("0-trace.trace", "\n".join(json.dumps(e) for e in trace))
        if network is not None:
            archive.writestr("0-trace.network",
                             "\n".join(json.dumps(e) for e in network))
    return path


def test_the_failure_stack_carries_the_message_and_where_it_broke(tmp_path):
    path = _trace(tmp_path, test_trace=[{
        "type": "error",
        "message": "Error: must not reproduce\n\n\x1b[2mexpect(\x1b[22mreceived).toBe(false)",
        "stack": [{"file": "/w/tests/repro.spec.ts", "line": 8, "column": 81}],
    }])
    stack = parse_trace(path).failure_stack
    assert "must not reproduce" in stack[0]
    assert "\x1b[" not in stack[0], "ANSI colour codes are noise to an agent"
    assert stack[1] == "/w/tests/repro.spec.ts:8:81"


def test_only_console_errors_are_kept(tmp_path):
    """An app's info/debug chatter is not evidence, and collecting it would bloat every
    packet for no diagnostic gain."""
    path = _trace(tmp_path, trace=[
        {"type": "console", "messageType": "log", "text": "rendered ok"},
        {"type": "console", "messageType": "info", "text": "analytics ready"},
        {"type": "console", "messageType": "error", "text": "pay failed"},
    ])
    assert parse_trace(path).console_errors == ["pay failed"]


def test_only_failing_requests_are_kept_and_paths_are_templated(tmp_path):
    """A 200 is not evidence of a failure, and a raw URL can carry an account number in a
    path segment or a token in a query string."""
    path = _trace(tmp_path, network=[
        {"type": "resource-snapshot", "snapshot": {
            "request": {"method": "GET", "url": "http://app/index.html"},
            "response": {"status": 200}, "time": 20.9}},
        {"type": "resource-snapshot", "snapshot": {
            "request": {"method": "POST",
                        "url": "http://app/api/accounts/8675309/pay?session=abc123"},
            "response": {"status": 500}, "time": 2.798}},
    ])
    requests = parse_trace(path).failed_requests
    assert len(requests) == 1
    assert requests[0] == {"method": "POST", "path": "/api/accounts/:id/pay",
                           "status": 500, "duration_ms": 2.8}
    assert "8675309" not in str(requests) and "abc123" not in str(requests)


def test_the_snapshot_reports_the_last_real_interaction(tmp_path):
    """Traces end with internal bookkeeping. "The failure happened during waitForTimeout"
    tells a developer nothing; the last action with a selector is what the flow did."""
    path = _trace(tmp_path, trace=[
        {"type": "before", "method": "goto", "params": {"selector": "", "url": "/x"}},
        {"type": "before", "method": "click",
         "params": {"selector": "[data-testid=submit]"}},
        {"type": "before", "method": "waitForTimeout", "params": {}},
    ])
    snapshot = parse_trace(path).failure_snapshot
    assert snapshot["action"] == "click"
    assert snapshot["target"] == "[data-testid=submit]"


def test_a_trace_missing_sections_does_not_explode(tmp_path):
    """Playwright writes what it has. A partial trace is a normal outcome of a timeout,
    and losing all diagnostics because one section is absent would be worse than useless."""
    diags = parse_trace(_trace(tmp_path))
    assert diags.failure_stack == [] and diags.console_errors == []


def test_a_corrupt_line_is_skipped_not_fatal(tmp_path):
    path = tmp_path / "trace.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("0-trace.trace",
                         '{"type":"console","messageType":"error","text":"real"}\n'
                         "{not json at all\n")
    assert parse_trace(path).console_errors == ["real"]


# --- the planted-secret gate --------------------------------------------------------------

def test_real_credential_shapes_do_not_survive_the_real_redactor(tmp_path):
    """Uses the runner's actual redactor, not a stand-in.

    The reproduction is synthetic, so nothing here is a customer's — but a developer's own
    app will happily print a live key into its console against a staging backend, and the
    packet goes to a third-party agent. Provenance explains where data came from; it does
    not excuse shipping a key.
    """
    from stepstitch_service.runner import scrub_transcript

    path = _trace(tmp_path, trace=[
        {"type": "console", "messageType": "error",
         "text": "auth failed Bearer tok_fake_for_testing_only_0123456789"},
        {"type": "console", "messageType": "error",
         "text": "db url postgres://admin:hunter2@10.0.0.5/prod"},
        {"type": "console", "messageType": "error",
         "text": "api_key=AKIAIOSFODNN7EXAMPLE"},
        {"type": "console", "messageType": "error",
         "text": "agent token ssa_ZmFrZXRva2VuZm9ydGVzdGluZw"},
    ])
    record = scrub_diagnostics(parse_trace(path).as_dict(), scrub_transcript)
    blob = json.dumps(record)
    for secret in ("tok_fake_for_testing_only_0123456789", "hunter2",
                   "AKIAIOSFODNN7EXAMPLE", "ssa_ZmFrZXRva2VuZm9ydGVzdGluZw"):
        assert secret not in blob, f"{secret} survived scrubbing"
    assert record["contains_customer_session_data"] is False


def test_an_id_in_a_path_never_reaches_an_agent(tmp_path):
    """Templating is not cosmetic: /api/accounts/8675309/pay names a real account."""
    path = _trace(tmp_path, network=[
        {"type": "resource-snapshot", "snapshot": {
            "request": {"method": "POST", "url": "http://app/api/accounts/8675309/pay"},
            "response": {"status": 500}, "time": 4.1}},
    ])
    assert "8675309" not in json.dumps(parse_trace(path).as_dict())
