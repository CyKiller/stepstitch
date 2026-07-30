"""How much is this evidence actually worth? Three grades, none of them claimable.

Every verification record answers "did the fix work". This module answers the harder
question underneath it: **how do we know?**

- ``asserted`` — somebody told us. A CI job posted ``pre_passed``/``post_passed`` and
  StepStitch stored what it was given. Useful, and completely dependent on trusting the
  caller. For most of this product's life this was the *only* grade, and it was presented
  in the same words as a measurement — which is the dishonesty this file exists to end.
- ``measured`` — StepStitch ran the frozen reproduction itself, saw it fail, saw it pass
  after the change, and both runs are on record. No caller was trusted.
- ``signed`` — measured, and the canonical bundle carries a signature made with the
  tenant's own key. Now a third party who trusts neither the caller nor StepStitch can
  check it.

The ladder is strict: a grade is derived from **how the outcome was obtained**, never
accepted as an input. There is deliberately no code path that lets a caller hand us a
grade — see ``test_evidence.py``, which asserts that a payload claiming ``signed`` is
still recorded as ``asserted``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# The ISSUER's canonicalisation, reused deliberately. A verifier with its own copy of
# "how we serialise" is a verifier that will one day disagree with the issuer over a
# separator and call a good bundle forged — the first version of this module did exactly
# that, differing only by the "sha256:" prefix.
from .attestation import bundle_sha256 as _issuer_hash
from .attestation import canonical_bytes as _issuer_bytes

ASSERTED = "asserted"
MEASURED = "measured"
SIGNED = "signed"

# Ordered weakest to strongest. Used for "at least this good" comparisons.
GRADE_ORDER = (ASSERTED, MEASURED, SIGNED)

GRADE_MEANING = {
    ASSERTED: "a caller reported this outcome; StepStitch did not observe it",
    MEASURED: "StepStitch ran the frozen reproduction itself, before and after the change",
    SIGNED: "measured, and signed with the tenant's key so a third party can verify it",
}


class TamperError(Exception):
    """The bundle does not match its own hash. Not a warning — a refusal."""


def grade_at_least(grade: Optional[str], minimum: str) -> bool:
    """Is ``grade`` at least as strong as ``minimum``? Unknown grades are the weakest."""
    try:
        have = GRADE_ORDER.index(grade or "")
    except ValueError:
        return False
    return have >= GRADE_ORDER.index(minimum)


def derive_grade(*, measured_by_stepstitch: bool, signature: Optional[str] = None) -> str:
    """The only way a grade is ever produced.

    Note the argument names: this function asks *what happened*, not *what was claimed*.
    A signature alone does not earn ``signed`` — signing an assertion would just be a
    signed rumour.
    """
    if not measured_by_stepstitch:
        return ASSERTED
    return SIGNED if signature else MEASURED


def canonical_bytes(bundle: Dict[str, Any]) -> bytes:
    """The exact bytes a hash and a signature cover.

    Sorted keys and no incidental whitespace, so anyone can recompute this from the JSON
    they were handed without a StepStitch tool — that is what makes the attestation
    independently checkable rather than something you take our word for.
    """
    return _issuer_bytes(bundle)


def bundle_hash(bundle: Dict[str, Any]) -> str:
    """The issued form, including its ``sha256:`` prefix."""
    return _issuer_hash(bundle)


def _read_grade(document: Dict[str, Any]) -> str:
    verification = document.get("verification")
    if isinstance(verification, dict) and verification.get("evidence_grade"):
        return str(verification["evidence_grade"])
    return str(document.get("evidence_grade") or ASSERTED)


def verify_bundle(document: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute the hash over the payload and REFUSE a mismatch.

    ``document`` is the whole attestation as handed out: the payload plus the recorded
    ``bundle_sha256``. Anything that changed the payload — a flipped verdict, a removed
    redaction, an upgraded grade — moves the hash and is rejected here. Key order and
    whitespace do not, because canonicalisation removes them; that is a property worth
    having, since JSON round-trips through many hands.

    Raises ``TamperError`` rather than returning a flag: a caller that forgets to check a
    boolean gets a silent pass, and this is exactly the check nobody may forget.
    """
    stated = document.get("bundle_sha256")
    if not stated:
        raise TamperError(
            "this attestation carries no bundle_sha256, so nothing about it can be "
            "checked. Treat it as unverified evidence.")
    payload = {k: v for k, v in document.items()
               if k not in ("bundle_sha256", "signature")}
    actual = bundle_hash(payload)
    # Accept a bare hex digest as well as the issued "sha256:…" form: the value travels
    # through other people's tooling, and rejecting a correct hash over its prefix would
    # teach readers to ignore this check.
    if actual != stated and actual.removeprefix("sha256:") != str(stated).removeprefix(
            "sha256:"):
        raise TamperError(
            f"this attestation does not match its own hash (states {stated[:16]}…, "
            f"content hashes to {actual[:16]}…). It has been altered since it was issued "
            "— do not rely on it.")
    return {
        "verified": True,
        "bundle_sha256": actual,
        # The grade lives inside the verification block of a real attestation; a bare
        # payload may carry it at the top level.
        "evidence_grade": _read_grade(document),
        "signed": bool(document.get("signature")),
        "detail": GRADE_MEANING.get(_read_grade(document), "unknown evidence grade"),
    }
