"""Diagnostics: provenance that cannot be configured away, and an envelope that refuses.

The interesting assertions here are all about what this module will NOT do — claim customer
provenance, grow without bound, or let a verification run under a different experiment than
the one that was frozen.
"""
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
