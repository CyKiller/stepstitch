"""Compliance evidence proof — the packet is derived from code and cannot drift."""
from pathlib import Path

from stepstitch_service import build_evidence
from stepstitch_service.profiles import load_profile
from stepstitch_service.scrubber import FINANCIAL_SERVICES_ENTERPRISE

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVIDENCE = _REPO_ROOT / "COMPLIANCE-EVIDENCE.md"


def test_evidence_lists_every_forbidden_key_from_live_policy():
    doc = build_evidence()
    for key in FINANCIAL_SERVICES_ENTERPRISE.forbidden_keys:
        assert f"`{key}`" in doc, f"forbidden key {key} missing from evidence"


def test_evidence_lists_every_allowlisted_key():
    doc = build_evidence()
    for key in FINANCIAL_SERVICES_ENTERPRISE.metadata_allowlist:
        assert f"`{key}`" in doc
    for key in FINANCIAL_SERVICES_ENTERPRISE.footstep_metadata_allowlist:
        assert f"`{key}`" in doc


def test_evidence_is_deterministic():
    assert build_evidence() == build_evidence()


def test_committed_evidence_matches_live_policy():
    # Drift guard: the committed packet must equal the generated output.
    assert _EVIDENCE.is_file(), "run scripts/generate_compliance_evidence.py"
    assert _EVIDENCE.read_text() == build_evidence(), (
        "COMPLIANCE-EVIDENCE.md is stale — regenerate with "
        "scripts/generate_compliance_evidence.py"
    )


def test_evidence_states_never_captured_categories():
    doc = build_evidence()
    assert "What StepStitch never captures" in doc
    assert "Input values" in doc
    assert "Screenshots" in doc


def test_fs_crosswalk_cites_reg_sp_not_mrm():
    doc = build_evidence()  # default = financial-services-enterprise
    assert "## Regulatory crosswalk" in doc
    assert "SEC Reg S-P (2024)" in doc
    # The 2026 interagency MRM guidance excludes generative/agentic AI from its
    # scope and is non-enforceable (OCC Bulletin 2026-13) — it must never appear
    # as a crosswalk column, i.e. as a regime StepStitch's controls satisfy.
    assert "| Control | SEC Reg S-P (2024) | NIST AI RMF |" in doc
    assert "`test_repro_eval.py`" in doc
    # The FS profile must NOT advertise HIPAA as a controlling regime.
    assert "HIPAA" not in doc


def test_model_risk_section_is_informational_not_applicability():
    """The packet may describe model-risk principles but must not claim the 2026
    interagency guidance applies to StepStitch or the agents it governs."""
    doc = build_evidence()
    # The old applicability section is gone.
    assert "## Model risk management evidence" not in doc
    assert "MRM role" not in doc
    # The informational replacement states the scope exclusion in plain words.
    assert "## Model-risk principles (informational)" in doc
    assert "not within the scope" in doc
    assert "does not claim" in doc
    # Any mention of the guidance carries the exclusion, never an applicability
    # framing: the gates are engineering controls, not "validation evidence
    # under" the guidance.
    assert "gates are the validation" not in doc
    assert "Engineering-control role" in doc


def test_healthcare_profile_crosswalk_cites_hipaa_not_reg_sp():
    doc = build_evidence(load_profile("healthcare-strict"))
    assert "HIPAA" in doc
    # Healthcare column set is HIPAA + NIST, not the financial regimes.
    assert "SEC Reg S-P (2024)" not in doc
