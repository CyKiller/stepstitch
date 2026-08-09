"""Host-side Ed25519 signing for FixProof and attestation documents.

The layering rule this file keeps: the service CORE never holds a key. The seed comes
from the deployer's environment (``STEPSTITCH_SIGNING_KEY``), is loaded here in the
host layer, and is closed over by the ``sign_blob`` callable the router receives — the
same seam the cosign signer (server/signing.py) uses, so a deployer can pick either.

The signature value is the structured object the offline verifier can actually check
(``{"algorithm": "ed25519", "key_id": ..., "signature": <hex>}``) — an opaque string
deliberately no longer satisfies ``require_signature``, because presence is not
authenticity (the trust-audit lesson).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional

_SEED_HEX = re.compile(r"^[0-9a-f]{64}$")


def load_signing_seed(value: Optional[str]) -> Optional[bytes]:
    """A 32-byte Ed25519 seed from an env value: 64 hex chars, or a path to a file
    holding them (what ``stepstitch proof keygen`` writes). Anything else is None —
    the caller falls back to cosign or to unsigned, never to a half-parsed key."""
    text = (value or "").strip()
    if not text:
        return None
    if _SEED_HEX.fullmatch(text.lower()):
        return bytes.fromhex(text.lower())
    path = Path(text)
    try:
        if path.is_file():
            content = path.read_text(encoding="utf-8").strip().lower()
            if _SEED_HEX.fullmatch(content):
                return bytes.fromhex(content)
    except OSError:
        return None
    return None


def make_ed25519_signer(seed: bytes,
                        key_id: str) -> Callable[[bytes], Dict[str, Any]]:
    """``sign(blob) -> signature object`` bound to the deployer's key."""
    from .. import _ed25519

    if len(seed) != _ed25519.SEED_BYTES:
        raise ValueError("an ed25519 signing seed is exactly 32 bytes")

    def sign(blob: bytes) -> Dict[str, Any]:
        return {
            "algorithm": "ed25519",
            "key_id": key_id,
            "signature": _ed25519.sign(seed, blob).hex(),
        }

    return sign
