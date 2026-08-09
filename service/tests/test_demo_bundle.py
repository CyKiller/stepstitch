"""Proof tests for the credential-free red-to-green demo bundle.

These guard the demo (`scripts/demo_red_to_green.py`) the same way `test_compliance.py`
guards the compliance packet: the committed bundle must stay in sync with the generator, must
carry the full moat, and must never leak a forbidden field or value into any sanitized region.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from stepstitch_service.integrations.base import FORBIDDEN_DRAFT_KEYS, assert_flat
from stepstitch_service.scrubber import _DEFAULT_FORBIDDEN_KEYS
from stepstitch_service.verification.verdict import (
    VERDICT_CONFIRMED_FIXED,
    derive_verdict,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_PATH = REPO_ROOT / "demo" / "evidence-bundle.json"
WEB_COPY_PATH = REPO_ROOT / "web" / "src" / "lib" / "demo-bundle.json"
GENERATOR = REPO_ROOT / "scripts" / "demo_red_to_green.py"

# Synthetic placeholder values seeded into the *raw* input purely to demonstrate scrubbing.
# None of them may survive into any sanitized region of the bundle.
PLACEHOLDER_VALUES = (
    "PLACEHOLDER", "session=", "Bearer ", "bank.example.test/accounts",
    "user@example.test", "000-00-0000",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bundle() -> dict:
    assert BUNDLE_PATH.exists(), "run `npm run demo` to generate demo/evidence-bundle.json"
    return _load(BUNDLE_PATH)


def _build_fresh_bundle() -> dict:
    """Import the generator module and rebuild the bundle in-memory (no file writes)."""
    spec = importlib.util.spec_from_file_location("demo_red_to_green", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.build_bundle()


def test_bundle_is_in_sync_with_generator(bundle):
    # The committed bundle must equal a fresh generation — no manual drift.
    assert bundle == _build_fresh_bundle(), "demo/evidence-bundle.json is stale — run `npm run demo`"


def test_web_copy_matches_canonical_bundle(bundle):
    # The site builds against web/src/lib/demo-bundle.json; it must be byte-identical.
    assert WEB_COPY_PATH.exists(), "run `npm run demo` to generate the web copy"
    assert _load(WEB_COPY_PATH) == bundle


def test_bundle_is_labeled_demo_and_dry_run(bundle):
    assert bundle["demo"] is True
    assert "dry-run" in bundle["delivery"]


def test_all_eight_steps_present(bundle):
    steps = bundle["steps"]
    for key in (
        "1_bug_report", "2_structural_capture", "3_privacy_scrub", "4_replayability",
        "5_playwright_repro", "6_drafts", "7_ci_verification", "8_regression_corpus",
    ):
        assert key in steps, f"missing story step: {key}"


def test_privacy_scrub_reports_status_and_fields(bundle):
    scrub = bundle["steps"]["3_privacy_scrub"]
    assert scrub["scrub_status"] == "scrubbed"
    assert scrub["scrubbed_fields"], "scrub must report the fields it dropped/redacted"
    # The forbidden keys we seeded were dropped and recorded.
    for field in ("metadata.headers", "metadata.raw_url", "footsteps[5].metadata.cookies",
                  "footsteps[5].metadata.request_body", "footsteps[5].metadata.url"):
        assert field in scrub["scrubbed_fields"], f"expected scrubbed field {field}"


def test_kept_footstep_metadata_has_no_forbidden_keys(bundle):
    for step in bundle["steps"]["2_structural_capture"]["footsteps"]:
        for key in (step.get("metadata") or {}):
            assert key not in _DEFAULT_FORBIDDEN_KEYS, f"forbidden key kept: {key}"


def test_no_placeholder_value_leaks_into_sanitized_regions(bundle):
    # Strip the one place placeholders are intentionally shown (the labeled before-state).
    sanitized = json.loads(json.dumps(bundle))
    sanitized["steps"]["1_bug_report"].pop("raw_unsafe_input", None)
    blob = json.dumps(sanitized)
    for token in PLACEHOLDER_VALUES:
        assert token not in blob, f"placeholder value leaked into sanitized bundle: {token}"


def test_raw_unsafe_input_is_clearly_labeled(bundle):
    raw = bundle["steps"]["1_bug_report"]["raw_unsafe_input"]
    assert "placeholder" in raw["note"].lower() or "synthetic" in raw["note"].lower()


def test_playwright_repro_generated(bundle):
    code = bundle["steps"]["5_playwright_repro"]["playwright_code"]
    assert "import { test, expect } from '@playwright/test';" in code
    assert "StepStitch reproduction" in code


def test_drafts_are_flat_and_carry_no_forbidden_key(bundle):
    drafts = bundle["steps"]["6_drafts"]
    for name in (
        "servicenow", "salesforce", "genesys", "jira", "zendesk",
        "github_issues", "linear", "slack",
    ):
        draft = drafts[name]
        assert_flat(draft)  # raises on a nested or identity-leaking field
        for key in draft:
            assert key not in FORBIDDEN_DRAFT_KEYS


def test_confirmed_fixed_derives_only_from_red_then_green(bundle):
    verify = bundle["steps"]["7_ci_verification"]
    assert verify["pre_passed"] is False
    assert verify["post_passed"] is True
    assert verify["verdict"] == VERDICT_CONFIRMED_FIXED
    # Re-derive from the recorded inputs — the verdict is not hand-set.
    assert derive_verdict(verify["pre_passed"], verify["post_passed"]) == VERDICT_CONFIRMED_FIXED
    # And the corpus entry carries that same verdict.
    corpus = bundle["steps"]["8_regression_corpus"]
    assert corpus["verdict"] == VERDICT_CONFIRMED_FIXED
    assert corpus["entries"][0]["verdict"] == VERDICT_CONFIRMED_FIXED


def test_a_non_red_green_pair_is_not_confirmed_fixed():
    # Negative control: only red->green is a confirmed fix.
    assert derive_verdict(True, True) != VERDICT_CONFIRMED_FIXED
    assert derive_verdict(False, False) != VERDICT_CONFIRMED_FIXED
    assert derive_verdict(False, None) != VERDICT_CONFIRMED_FIXED


# --- the committed example FixProof ------------------------------------------------------

PROOF_PATH = REPO_ROOT / "demo" / "fixproof.json"
PROOF_WEB_COPY = REPO_ROOT / "web" / "public" / "fixproof.json"
POLICY_WEB_COPY = REPO_ROOT / "web" / "public" / "proof-policy.json"
POLICY_SOURCE = REPO_ROOT / "examples" / "proof" / "proof-policy.json"


@pytest.fixture()
def fixproof():
    return json.loads(PROOF_PATH.read_text(encoding="utf-8"))


def test_the_committed_proof_verifies_offline_with_the_demo_policy(fixproof):
    """The exact experience the /verify page promises a visitor: two downloaded files
    and the CLI, nothing else — and the verification now includes a REAL ed25519
    signature check against the demo key the policy names."""
    from stepstitch_service.fixproof import verify_fixproof

    policy = json.loads(POLICY_WEB_COPY.read_text(encoding="utf-8"))
    result = verify_fixproof(fixproof, policy)
    assert result.ok, [c for c in result.checks if not c["passed"]]
    signature = next(c for c in result.checks if c["check"] == "require_signature")
    assert "ed25519" in signature["detail"]


def test_a_tampered_demo_proof_is_refused_by_the_demo_policy(fixproof):
    """The visitor's second command — change any byte, verification refuses."""
    from stepstitch_service.evidence import TamperError
    from stepstitch_service.fixproof import verify_fixproof

    policy = json.loads(POLICY_WEB_COPY.read_text(encoding="utf-8"))
    tampered = json.loads(json.dumps(fixproof))
    tampered["statement"]["predicate"]["results"]["pre_passed"] = True
    with pytest.raises(TamperError):
        verify_fixproof(tampered, policy)


def test_the_proof_copies_match_and_the_policies_deliberately_differ(fixproof):
    """The web policy is generated (it must actually verify, so it trusts the
    public-by-design demo key); the customer template deliberately refuses to run until
    a real key replaces its placeholder. Same requirements, different trust anchors —
    and the customer template must never be the weaker of the two."""
    assert fixproof == json.loads(PROOF_WEB_COPY.read_text(encoding="utf-8"))
    web = json.loads(POLICY_WEB_COPY.read_text(encoding="utf-8"))
    template = json.loads(POLICY_SOURCE.read_text(encoding="utf-8"))
    for key in ("require_grade", "require_pre_red", "require_post_green",
                "require_signature", "allowed_verifier_kinds"):
        assert web[key] == template[key], f"{key} drifted between demo and template"
    # The template requires EVERY binding; the demo omits only the envelope digest
    # (the committed measurement is byte-stable; a real envelope digest would move
    # with CI's browser version).
    assert template["require_bindings"] is True
    assert set(web["require_bindings"]) == {
        "subject.gitCommit", "base_commit", "failure.fingerprint",
        "failure.red_signature", "frozen_test.sha256", "privacy.policy_sha256",
        "privacy.structural_result",
    }
    # And the demo policy pins the demo commit, so the committed proof cannot be
    # replayed as evidence about any real code.
    assert web["expected_head_sha"] == "beefc0de" * 5


def test_the_demo_policy_matches_its_generator(fixproof):
    """web/public/proof-policy.json is a build artifact of demo_red_to_green.py; the
    committed copy must equal what the generator produces today."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "demo_red_to_green",
        Path(REPO_ROOT) / "scripts" / "demo_red_to_green.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    committed = json.loads(POLICY_WEB_COPY.read_text(encoding="utf-8"))
    assert committed == module.build_demo_proof_policy()


def test_the_proof_agrees_with_the_bundle_it_was_built_from(bundle, fixproof):
    """One demo, one story: the proof's measured booleans, verdict, and frozen-test digest
    must be the bundle's own — drift between the two committed artifacts is a failure."""
    import hashlib

    p = fixproof["statement"]["predicate"]
    ci = bundle["steps"]["7_ci_verification"]
    assert p["results"]["pre_passed"] == ci["measurement"]["pre_passed"]
    assert p["results"]["post_passed"] == ci["measurement"]["post_passed"]
    assert p["results"]["verdict"] == ci["verdict"]
    assert p["trace_id"] == bundle["trace_id"]
    code = bundle["steps"]["5_playwright_repro"]["playwright_code"]
    assert p["frozen_test"]["sha256"] == (
        "sha256:" + hashlib.sha256(code.encode("utf-8")).hexdigest())


def test_the_demo_commits_are_synthetic_and_labeled(fixproof):
    """A real commit id in a committed proof would drift or lie; the demo names fixture
    commits and says so where a reader will look."""
    s = fixproof["statement"]
    assert s["subject"][0]["digest"]["gitCommit"] == "beefc0de" * 5
    assert s["predicate"]["base_commit"] == {"gitCommit": "baddc0de" * 5}
    assert "synthetic" in s["predicate"]["results"]["fix_ref"]
