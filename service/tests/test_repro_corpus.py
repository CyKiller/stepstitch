"""Reproduction Success gates — the corpus is the product's definition of "works".

Phase 2 of the product plan. The corpus (examples/repro/reproduction-corpus.json)
holds one synthetic trace per failure family with the outcome the product MUST
produce; this file turns those expectations into gates:

  - >= 90% of eligible entries reach `ready`
  - every ineligible entry carries ONE named reason the operator actually sees
  - generated tests are byte-deterministic (pinned sha, compile-twice equality)
  - `confirmed_fixed` is unreachable except from measured red -> measured green
  - a toolchain failure (browser missing, broken module) can never read as a
    reproduced bug

The intended-red rate (>= 85% in real Chromium) is enforced by
scripts/prove-repro-corpus.mjs in the e2e-proof CI job, not here — a unit file
asserting browser behavior would be pretending.
"""
import copy
import json
from pathlib import Path

import pytest

from stepstitch_service import repro_eval
from stepstitch_service.fixcheck import derive_fix_verdict
from stepstitch_service.runner import (
    INCONCLUSIVE,
    REPRODUCED,
    RunAttempt,
    classify_run,
    derive_verdict,
)
from stepstitch_service.verification.verdict import derive_verdict as corpus_verdict

_CORPUS = Path(__file__).resolve().parents[2] / "examples" / "repro" / "reproduction-corpus.json"


def _load():
    return json.loads(_CORPUS.read_text())


def _result():
    return repro_eval.evaluate_corpus(_load())


# --- The corpus itself -----------------------------------------------------------


def test_corpus_covers_every_planned_category():
    cats = {e["category"] for e in _load()["entries"]}
    missing = set(repro_eval.CATEGORIES) - cats
    assert not missing, f"corpus is missing categories: {sorted(missing)}"


def test_every_entry_meets_its_expectation():
    result = _result()
    problems = [f"{e.name}: {p}" for e in result.entries for p in e.problems]
    assert not problems, "\n".join(problems)


def test_ready_rate_gate():
    result = _result()
    assert result.eligible_count > 0
    assert result.ready_rate >= repro_eval.READY_RATE_GATE, (
        f"only {result.ready_rate:.0%} of eligible corpus traces reach ready "
        f"(gate: {repro_eval.READY_RATE_GATE:.0%})"
    )


def test_every_refusal_names_its_reason():
    """An ineligible entry must carry one reason, and that reason must be a signal
    the operator actually sees (a warning code or a blocking readiness item)."""
    result = _result()
    for e in result.entries:
        if e.eligible:
            continue
        assert e.reason, f"{e.name}: ineligible but no reason named"
        assert e.reason_observed, (
            f"{e.name}: names reason '{e.reason}' but nothing the product emits says so"
        )


def test_generated_tests_are_byte_deterministic():
    result = _result()
    for e in result.entries:
        if e.script_sha256 is None:
            continue  # transcript-only entries generate nothing
        assert e.deterministic, f"{e.name}: two compiles differed in the same process"
        assert e.expected_sha, (
            f"{e.name}: no pinned sha — run scripts/refresh_repro_corpus.py and commit"
        )
        assert e.script_sha256 == e.expected_sha, (
            f"{e.name}: generated test bytes moved (pinned {e.expected_sha[:12]}, "
            f"got {e.script_sha256[:12]}). If the compiler change is deliberate, "
            "refresh with scripts/refresh_repro_corpus.py."
        )


# --- The gates must be able to fail (anti-vacuity) -------------------------------


def test_a_wrong_state_expectation_is_caught():
    doc = _load()
    entry = next(e for e in doc["entries"] if e["name"] == "strong-api-500")
    entry["expect"]["state"] = "draft"
    result = repro_eval.evaluate_corpus(doc)
    bad = next(e for e in result.entries if e.name == "strong-api-500")
    assert bad.problems, "evaluator accepted a state expectation the product contradicts"


def test_a_wrong_warning_expectation_is_caught():
    doc = _load()
    entry = next(e for e in doc["entries"] if e["name"] == "empty-trace")
    entry["expect"]["warnings"] = []
    result = repro_eval.evaluate_corpus(doc)
    bad = next(e for e in result.entries if e.name == "empty-trace")
    assert bad.problems


def test_an_unnamed_refusal_is_caught():
    doc = _load()
    entry = next(e for e in doc["entries"] if e["name"] == "navigation-only-no-terminal")
    entry["reason"] = "made_up_reason"
    result = repro_eval.evaluate_corpus(doc)
    bad = next(e for e in result.entries if e.name == "navigation-only-no-terminal")
    assert not bad.reason_observed


def test_a_tampered_sha_is_caught():
    doc = _load()
    entry = next(e for e in doc["entries"] if e["name"] == "strong-api-500")
    entry["expect"]["script_sha256"] = "0" * 64
    result = repro_eval.evaluate_corpus(doc)
    bad = next(e for e in result.entries if e.name == "strong-api-500")
    assert bad.script_sha256 != bad.expected_sha


# --- Zero false confirmed_fixed (exhaustive over the input space) ----------------


def test_confirmed_fixed_requires_measured_red_then_green():
    truth = {
        (True, True): "not_reproduced",
        (True, False): "not_reproduced",
        (True, None): "not_reproduced",
        (False, True): "confirmed_fixed",
        (False, False): "not_fixed",
        (False, None): "reproduced_unfixed",
    }
    for (pre, post), expected in truth.items():
        assert corpus_verdict(pre, post) == expected
    # The only path to confirmed_fixed is measured-red -> measured-green.
    positives = [k for k, v in truth.items() if v == "confirmed_fixed"]
    assert positives == [(False, True)]


def _attempt(*, passed, errored=False, timed_out=False, transcript=""):
    return RunAttempt(
        index=0, exit_code=0 if passed else 1, passed=passed,
        timed_out=timed_out, duration_seconds=0.1,
        transcript=transcript, errored=errored,
    )


def test_fix_verdict_never_fixed_without_a_measured_red():
    from stepstitch_service.runner import ReproductionResult

    green = ReproductionResult(
        verdict="not_reproduced", session_id="s", script_sha256="a" * 64,
        runs=[_attempt(passed=True)],
    )
    for red in (None, INCONCLUSIVE, "needs_setup", "not_reproduced"):
        v = derive_fix_verdict(red_verdict=red, red_signature="", after=green)
        assert v.verdict != "fixed", f"fixed granted with red_verdict={red!r}"
    ok = derive_fix_verdict(red_verdict=REPRODUCED, red_signature="sig", after=green)
    assert ok.verdict == "fixed"


# --- Setup failure is never an application failure -------------------------------


@pytest.mark.parametrize("category", ["setup-failure", "browser-failure"])
def test_toolchain_transcripts_classify_as_errors_not_bugs(category):
    entries = [e for e in _load()["entries"] if e["category"] == category]
    assert entries, f"corpus lost its {category} entries"
    for entry in entries:
        passed, errored, detail = classify_run(1, entry["transcript"])
        assert not passed
        assert errored, f"{entry['name']}: a never-ran transcript read as a test result"
        assert detail
        verdict, flaky = derive_verdict(
            [_attempt(passed=False, errored=True, transcript=entry["transcript"])]
        )
        assert verdict == INCONCLUSIVE
        assert verdict != REPRODUCED


def test_a_genuine_failure_still_reads_reproduced():
    """Anti-vacuity for the gate above: the classifier must not call everything a
    toolchain error."""
    transcript = (
        "  1) repro.spec.ts:3:1 > repro\n"
        "    Error: expect(received).toBe(expected)\n"
        "  1 failed"
    )
    passed, errored, _ = classify_run(1, transcript)
    assert not passed and not errored
    verdict, _ = derive_verdict([_attempt(passed=False, transcript=transcript)])
    assert verdict == REPRODUCED


# --- Report ----------------------------------------------------------------------


def test_report_renders_and_names_the_gates():
    report = repro_eval.render_report(_result())
    assert "ready rate" in report
    assert "eligible" in report
    for e in _result().entries:
        assert e.name in report


def test_corpus_matches_deep_copy_of_itself():
    """evaluate_corpus must not mutate its input — the mjs harness reuses the doc."""
    doc = _load()
    snapshot = copy.deepcopy(doc)
    repro_eval.evaluate_corpus(doc)
    assert doc == snapshot
