"""FixProof v2: an in-toto-style statement binding a fix to its measured evidence.

The claim, exactly: *this specific reported failure failed before and passed after —
same frozen test, same execution envelope, under this privacy policy, measured by this
verifier.* Never "the program is correct"; a proof that overclaims teaches people to
ignore proofs.

The interoperable unit is ``statement`` — an in-toto Statement (v1) whose subject is the
fixed commit and whose predicate carries the ten bindings. The wrapper adds a
reproducible hash (``statement_sha256``) and an optional detached signature, exactly the
shape the attestation bundle already uses, so one verification recipe covers both.

Deliberately stdlib-only (like attestation.py): ``stepstitch proof verify`` must work
offline in an environment that has nothing but Python. Canonicalization is
``attestation.canonical_bytes`` — a second canonicalizer would be a second chance for
"same content, different bytes" to break verification, and the tests treat
re-serialization as explicitly not tampering.

Digest forms: rows store bare hex historically (``stepstitch_frozen_repros.sha256``,
``ExecutionEnvelope.sha256()``); the statement re-emits everything ``sha256:``-prefixed,
and the verifier tolerates a bare-hex ``statement_sha256`` the same way
``evidence.verify_bundle`` does — a correct hash without its prefix is correct.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .attestation import canonical_bytes
from .evidence import TamperError, grade_at_least

SCHEMA = "stepstitch.fixproof/v2"
STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://stepstitch.dev/attestation/fixproof/v2"

MEASURED_BY_HOST = "measured-by-host"
ASSERTED_BY_CALLER = "asserted-by-caller"

_COMMIT = re.compile(r"^[0-9a-f]{40}$")

# Every key a proof policy may carry. An unknown key is refused as unusable input — a
# typo'd requirement that silently verified nothing would be worse than no policy.
POLICY_KEYS = frozenset({
    "require_grade", "require_pre_red", "require_post_green", "require_signature",
    "allowed_verifier_kinds", "require_privacy", "expected_head_sha",
})


def _prefixed(digest: Optional[str]) -> Optional[str]:
    """Normalize a stored digest to ``sha256:<hex>`` without ever double-prefixing."""
    if digest is None:
        return None
    return digest if digest.startswith("sha256:") else f"sha256:{digest}"


def _commit_or_refuse(value: Any, *, required: bool, label: str) -> Optional[str]:
    if value is None or value == "":
        if required:
            raise ValueError(
                f"{label} is required: a proof about unidentified code proves nothing"
            )
        return None
    text = str(value).strip().lower()
    if not _COMMIT.fullmatch(text):
        raise ValueError(f"{label} must be a full 40-hex git commit id, got {value!r}")
    return text


def build_fixproof_statement(
    *,
    trace_id: str,
    subject_name: str,
    fixed_commit: str,
    base_commit: Optional[str] = None,
    fingerprint: Optional[Dict[str, Any]] = None,
    red_signature: str = "",
    red_verdict: Optional[str] = None,
    frozen_test_sha256: str,
    frozen_at: Optional[str] = None,
    frozen_by: Optional[str] = None,
    envelope_sha256: Optional[str] = None,
    envelope_schema_version: Optional[int] = None,
    pre_passed: bool,
    post_passed: Optional[bool],
    verdict: str,
    fix_ref: Optional[str] = None,
    fix_mechanism: Optional[str] = None,
    policy: str,
    policy_sha256: Optional[str] = None,
    scrub_status: Optional[str] = None,
    schema_status: Optional[str] = None,
    verifier_identity: str,
    evidence_grade: str,
    issued_at: str,
    sdk_build: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble the in-toto statement. Pure: every input is passed in, nothing is read.

    The verifier ``kind`` is DERIVED from the evidence grade, never accepted as an
    input: measured/signed evidence was observed by the host runner, asserted evidence
    was a caller's claim — letting a caller also name the kind would reopen the exact
    self-grading door the grade system closed.
    """
    fixed = _commit_or_refuse(fixed_commit, required=True, label="fixed_commit")
    base = _commit_or_refuse(base_commit, required=False, label="base_commit")
    kind = MEASURED_BY_HOST if grade_at_least(evidence_grade, "measured") \
        else ASSERTED_BY_CALLER
    if schema_status == "strict_schema_passed":
        structural_result = "structural_only"
    elif schema_status is not None:
        structural_result = "violations_dropped"
    else:
        structural_result = "redaction_only"

    predicate: Dict[str, Any] = {
        "trace_id": trace_id,
        "base_commit": {"gitCommit": base} if base else None,
        "failure": {
            "fingerprint": dict(fingerprint or {}),
            "red_signature": red_signature,
            "red_verdict": red_verdict,
        },
        "frozen_test": {
            "sha256": _prefixed(frozen_test_sha256),
            "frozen_at": frozen_at,
            "frozen_by": frozen_by,
        },
        "execution_envelope": {
            "sha256": _prefixed(envelope_sha256),
            "schema_version": envelope_schema_version,
        },
        "results": {
            "pre_passed": pre_passed,
            "post_passed": post_passed,
            "verdict": verdict,
            "fix_ref": fix_ref,
            "fix_mechanism": fix_mechanism,
        },
        "privacy": {
            "policy": policy,
            "policy_sha256": _prefixed(policy_sha256),
            "scrub_status": scrub_status,
            "schema_status": schema_status,
            "structural_result": structural_result,
        },
        "verifier": {
            "identity": verifier_identity,
            "kind": kind,
            "evidence_grade": evidence_grade,
        },
        "issued_at": issued_at,
        "sdk_build": sdk_build,
        # The honesty boundary, inside the hashed payload on purpose: stripping it is
        # tampering. This proof binds ONE failure to ONE fix under ONE environment.
        "scope": "this reported failure, under this frozen test and envelope — "
                 "not a claim of overall program correctness",
    }
    return {
        "_type": STATEMENT_TYPE,
        "subject": [{"name": subject_name, "digest": {"gitCommit": fixed}}],
        "predicateType": PREDICATE_TYPE,
        "predicate": predicate,
    }


def statement_sha256(statement: Dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(statement)).hexdigest()


def wrap(statement: Dict[str, Any], signature: Optional[str] = None) -> Dict[str, Any]:
    """The export document: statement + reproducible hash + optional detached signature."""
    return {
        "schema": SCHEMA,
        "statement": statement,
        "statement_sha256": statement_sha256(statement),
        "signature": signature,
    }


@dataclass
class FixproofVerification:
    """One named result per policy check; ``ok`` only when every check passed.

    Tamper is not a check: an altered or unhashed statement raises ``TamperError``
    before any policy question is asked — policy evaluates evidence, not forgeries.
    """

    checks: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c["passed"] for c in self.checks)

    def add(self, check: str, passed: bool, detail: str) -> None:
        self.checks.append({"check": check, "passed": bool(passed), "detail": detail})

    def as_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "checks": list(self.checks)}


def verify_fixproof(
    document: Dict[str, Any],
    policy: Dict[str, Any],
    *,
    head_sha: Optional[str] = None,
) -> FixproofVerification:
    """Offline verification: integrity first (raises ``TamperError``), then policy.

    ``head_sha`` (e.g. a PR head) overrides the policy's ``expected_head_sha`` — the
    merge gate always knows the commit better than a file written earlier does.
    """
    # Underscore-prefixed keys are commentary (JSON has no comment syntax); anything
    # else unknown is refused — a typo'd requirement that verified nothing would be
    # worse than no policy at all.
    unknown = {k for k in set(policy) - POLICY_KEYS if not k.startswith("_")}
    if unknown:
        raise ValueError(f"unknown policy key(s): {', '.join(sorted(unknown))}")

    statement = document.get("statement")
    if not isinstance(statement, dict):
        raise TamperError("document carries no statement")
    recorded = document.get("statement_sha256")
    if not recorded:
        raise TamperError(
            "document carries no statement_sha256; an unhashed proof cannot be trusted"
        )
    expected = statement_sha256(statement).removeprefix("sha256:")
    if str(recorded).removeprefix("sha256:") != expected:
        raise TamperError("statement does not match its own hash — it has been altered")

    predicate = statement.get("predicate") or {}
    results = predicate.get("results") or {}
    verifier = predicate.get("verifier") or {}
    privacy = predicate.get("privacy") or {}
    subject = (statement.get("subject") or [{}])[0]
    subject_commit = str((subject.get("digest") or {}).get("gitCommit") or "").lower()

    outcome = FixproofVerification()

    minimum = policy.get("require_grade")
    if minimum is not None:
        grade = verifier.get("evidence_grade")
        outcome.add("require_grade", grade_at_least(grade, minimum),
                    f"evidence_grade={grade!r}, floor={minimum!r}")

    if policy.get("require_pre_red"):
        outcome.add("require_pre_red", results.get("pre_passed") is False,
                    f"pre_passed={results.get('pre_passed')!r} (red requires False)")

    if policy.get("require_post_green"):
        outcome.add("require_post_green", results.get("post_passed") is True,
                    f"post_passed={results.get('post_passed')!r} (green requires True)")

    if policy.get("require_signature"):
        outcome.add("require_signature", bool(document.get("signature")),
                    "signature present" if document.get("signature")
                    else "no signature on the document")

    allowed = policy.get("allowed_verifier_kinds")
    if allowed is not None:
        kind = verifier.get("kind")
        outcome.add("allowed_verifier_kinds", kind in allowed,
                    f"verifier kind={kind!r}, allowed={list(allowed)!r}")

    required_privacy = policy.get("require_privacy") or {}
    for key, want in required_privacy.items():
        got = privacy.get(key)
        outcome.add("require_privacy", got == want,
                    f"privacy.{key}={got!r}, required {want!r}")

    expected_head = head_sha if head_sha is not None \
        else policy.get("expected_head_sha")
    if expected_head:
        outcome.add(
            "expected_head_sha",
            subject_commit == str(expected_head).strip().lower(),
            f"subject gitCommit={subject_commit!r}, expected {expected_head!r} — the "
            "proof must be about exactly the commit being merged",
        )

    return outcome
