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

from . import _ed25519
from .attestation import canonical_bytes
from .evidence import TamperError, grade_at_least

SCHEMA = "stepstitch.fixproof/v2"
STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://stepstitch.dev/attestation/fixproof/v2"

MEASURED_BY_HOST = "measured-by-host"
ASSERTED_BY_CALLER = "asserted-by-caller"

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_PUBLIC_KEY = re.compile(r"^ed25519:[0-9a-f]{64}$")

# Every key a proof policy may carry. An unknown key is refused as unusable input — a
# typo'd requirement that silently verified nothing would be worse than no policy.
POLICY_KEYS = frozenset({
    "require_grade", "require_pre_red", "require_post_green", "require_signature",
    "trusted_keys", "require_bindings", "allowed_verifier_kinds",
    "allowed_verifier_identities", "require_privacy", "expected_head_sha",
})

# The load-bearing bindings a merge gate refuses to go without (`require_bindings`).
# The trust-audit lesson behind the list: a proof is only "no trust in the PR author"
# if every field that anchors it to reality is actually there — a missing envelope or
# policy digest is a proof about less than it appears to claim.
MANDATORY_BINDINGS = (
    "subject.gitCommit",
    "base_commit",
    "failure.fingerprint",
    "failure.red_signature",
    "frozen_test.sha256",
    "execution_envelope.sha256",
    "privacy.policy_sha256",
    "privacy.structural_result",
)


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


def sign_statement(statement: Dict[str, Any], *, seed: Any,
                   key_id: str) -> Dict[str, Any]:
    """A detached Ed25519 signature object over the canonical statement bytes.

    Deliberately minimal — algorithm, key id, signature hex. The public key is NOT
    embedded: a verifier that read the key out of the document it is verifying would
    be trusting the author again, which is the exact failure this signature exists to
    close. Trust comes from the policy's ``trusted_keys``, nowhere else.
    """
    if isinstance(seed, str):
        seed = bytes.fromhex(seed.strip())
    return {
        "algorithm": "ed25519",
        "key_id": key_id,
        "signature": _ed25519.sign(seed, canonical_bytes(statement)).hex(),
    }


def _trusted_keys_or_refuse(policy: Dict[str, Any]) -> Dict[str, bytes]:
    """Decode ``trusted_keys`` or refuse the policy as unusable.

    Unusable — not failing: a gate whose trust anchors are absent, placeholders, or
    malformed did not reject the proof, it never ran. The distinction is the CLI's
    exit-code contract (2, not 1), and it is what makes "forgot to configure the gate"
    a loud error instead of a green check.
    """
    keys = policy.get("trusted_keys")
    if policy.get("require_signature") and not keys:
        raise ValueError(
            "require_signature is true but trusted_keys is empty — a signature nobody "
            "is trusted to make cannot be verified. Run `stepstitch proof keygen` on "
            "the verifying host and put its public key in trusted_keys."
        )
    decoded: Dict[str, bytes] = {}
    for key_id, value in (keys or {}).items():
        text = str(value).strip().lower()
        if not _PUBLIC_KEY.fullmatch(text):
            raise ValueError(
                f"trusted_keys[{key_id!r}] is not a usable ed25519 public key "
                f"(expected 'ed25519:<64 hex>', got {value!r}). Replace the "
                "placeholder with your host's real public key — "
                "`stepstitch proof keygen` prints it."
            )
        decoded[key_id] = bytes.fromhex(text.removeprefix("ed25519:"))
    return decoded


def _check_signature(signature: Any, trusted: Dict[str, bytes],
                     message: bytes) -> tuple:
    """(passed, detail) for the cryptographic signature requirement.

    The v2 lesson, permanently: presence is not authenticity. Anything that cannot be
    verified against a policy-trusted key — no signature, an opaque string, a wrong
    algorithm, an untrusted key id, forged bytes — fails with a detail that says which."""
    if not signature:
        return False, "no signature on the document"
    if not isinstance(signature, dict):
        return False, ("opaque signature string cannot be cryptographically verified "
                       "offline — sign with an ed25519 key (`stepstitch proof keygen`)")
    if signature.get("algorithm") != "ed25519":
        return False, f"unsupported signature algorithm {signature.get('algorithm')!r}"
    key_id = signature.get("key_id")
    if key_id not in trusted:
        return False, (f"signed by key_id={key_id!r}, which this policy does not "
                       "trust — a valid signature by the wrong signer proves nothing")
    try:
        raw = bytes.fromhex(str(signature.get("signature") or ""))
    except ValueError:
        return False, "signature bytes are not hex"
    if not _ed25519.verify(trusted[key_id], message, raw):
        return False, (f"signature does not verify against trusted key {key_id!r} — "
                       "forged, or made over different statement bytes")
    return True, (f"ed25519 signature by trusted key {key_id!r} verifies over the "
                  "canonical statement bytes")


def _binding_values(statement: Dict[str, Any]) -> Dict[str, Any]:
    predicate = statement.get("predicate") or {}
    subject = (statement.get("subject") or [{}])[0]
    failure = predicate.get("failure") or {}
    frozen = predicate.get("frozen_test") or {}
    envelope = predicate.get("execution_envelope") or {}
    privacy = predicate.get("privacy") or {}
    return {
        "subject.gitCommit": (subject.get("digest") or {}).get("gitCommit"),
        "base_commit": (predicate.get("base_commit") or {}).get("gitCommit"),
        "failure.fingerprint": failure.get("fingerprint"),
        "failure.red_signature": failure.get("red_signature"),
        "frozen_test.sha256": frozen.get("sha256"),
        "execution_envelope.sha256": envelope.get("sha256"),
        "privacy.policy_sha256": privacy.get("policy_sha256"),
        "privacy.structural_result": privacy.get("structural_result"),
    }


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
    # Trust anchors are validated BEFORE any evidence question: a policy with absent or
    # placeholder keys, or a typo'd binding name, is unusable input — refusing it here
    # (ValueError, CLI exit 2) is what keeps "misconfigured gate" from reading as green.
    trusted = _trusted_keys_or_refuse(policy)
    required_bindings = policy.get("require_bindings")
    if isinstance(required_bindings, (list, tuple)):
        bogus = sorted(set(required_bindings) - set(MANDATORY_BINDINGS))
        if bogus:
            raise ValueError(
                f"require_bindings names unknown binding(s): {', '.join(bogus)} — "
                f"known bindings: {', '.join(MANDATORY_BINDINGS)}"
            )

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
        passed, detail = _check_signature(document.get("signature"), trusted,
                                          canonical_bytes(statement))
        outcome.add("require_signature", passed, detail)

    if required_bindings:
        names = list(MANDATORY_BINDINGS) if required_bindings is True \
            else list(required_bindings)
        values = _binding_values(statement)
        missing = [n for n in names if not values.get(n)]
        outcome.add("require_bindings", not missing,
                    f"missing binding(s): {', '.join(missing)}" if missing
                    else f"all {len(names)} required bindings present")

    allowed = policy.get("allowed_verifier_kinds")
    if allowed is not None:
        kind = verifier.get("kind")
        outcome.add("allowed_verifier_kinds", kind in allowed,
                    f"verifier kind={kind!r}, allowed={list(allowed)!r}")

    allowed_identities = policy.get("allowed_verifier_identities")
    if allowed_identities is not None:
        identity = verifier.get("identity")
        outcome.add("allowed_verifier_identities", identity in allowed_identities,
                    f"verifier identity={identity!r}, "
                    f"authorized={list(allowed_identities)!r}")

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
