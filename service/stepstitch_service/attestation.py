"""Evidence Attestation — a signed, portable, independently-verifiable evidence bundle.

For any trace, compose the facts that already exist — the scrub report (what was redacted),
the replayability score (is the repro reliable), the verification verdict (did the fix go
red->green), and the SDK build that captured it — into a **canonical** bundle, hash it, and
(optionally) sign it with the **tenant's own key**. Anyone can then verify it independently:
re-compute the hash (no tooling needed) and, if signed, ``cosign verify-blob`` with the tenant's
public key — without trusting StepStitch or even reaching us.

Design: pure + deterministic. The same trace always produces the same canonical bytes and hash,
so the signature is stable and tamper-evident. The bundle is structural/NPI-free by construction
(it only composes already-sanitized reads). Signing is **not** done here — a host injects a signer
bound to the tenant's key — so the service never holds a key.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

SCHEMA = "stepstitch.attestation/v1"


def build_attestation(
    trace_id: str,
    *,
    summary: Dict[str, Any],
    replayability: Dict[str, Any],
    scrub: Optional[Dict[str, Any]],
    never_captured: List[str],
    sdk_build: Optional[str],
    latest_verification: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compose the canonical evidence bundle from already-sanitized reads. Pure + NPI-free."""
    return {
        "schema": SCHEMA,
        "trace_id": trace_id,
        "sdk_build": sdk_build,
        "summary": {
            "route": summary.get("route"),
            "headline": summary.get("headline"),
            "diagnostic_type": summary.get("diagnostic_type"),
            "failing_status": summary.get("failing_status"),
            "exception_type": summary.get("exception_type"),
            "diagnostic_endpoint": summary.get("diagnostic_endpoint"),
            "step_count": summary.get("step_count"),
        },
        "replayability": {
            "score": replayability.get("score"),
            "grade": replayability.get("grade"),
        },
        "privacy": {
            "policy": (scrub or {}).get("policy"),
            "scrub_status": (scrub or {}).get("scrub_status"),
            "scrubbed_fields": (scrub or {}).get("scrubbed_fields") or [],
            "never_captured": list(never_captured or []),
        },
        "verification": (
            {
                "verdict": latest_verification.get("verdict"),
                "fix_ref": latest_verification.get("fix_ref"),
                "run_url": latest_verification.get("run_url"),
            }
            if latest_verification
            else None
        ),
    }


def canonical_bytes(bundle: Dict[str, Any]) -> bytes:
    """Deterministic serialization (sorted keys, no whitespace) so the hash/signature is stable."""
    return json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode("utf-8")


def bundle_sha256(bundle: Dict[str, Any]) -> str:
    """The integrity hash anyone can recompute from the bundle, with no tooling."""
    return "sha256:" + hashlib.sha256(canonical_bytes(bundle)).hexdigest()


def verify_recipe(trace_id: str) -> str:
    """The independent-verification recipe (no StepStitch account needed)."""
    return (
        "Recompute: sha256 of the canonical bundle (sorted keys, no whitespace) must equal "
        "bundle_sha256. If a signature is present, verify with the tenant's public key: "
        "`cosign verify-blob --key tenant.pub --signature attestation.sig bundle.json`."
    )


__all__ = [
    "SCHEMA",
    "build_attestation",
    "canonical_bytes",
    "bundle_sha256",
    "verify_recipe",
]
