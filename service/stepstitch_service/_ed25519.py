"""Ed25519 for FixProof signatures: hardened library for the crypto, plus the one
check the library will not do.

The second trust audit's direction, followed: signing and signature verification are
delegated to the ``cryptography`` library (OpenSSL underneath) — StepStitch does not
maintain its own signature math. What remains here is deliberately NOT signature math:
``is_usable_public_key`` validates a TRUST ANCHOR — canonical encoding, actually on the
curve, and of prime order. RFC 8032-compliant verifiers (OpenSSL included) accept
small-order public keys, and against one of those — the identity point above all — a
single forged signature verifies EVERY message, because the key contributes nothing to
``sB == R + kA``. A policy's trusted key must therefore be checked here, separately,
before any signature is consulted; ``verify`` also refuses such keys outright as
defense in depth. The arithmetic below (curve arithmetic in extended homogeneous
coordinates) exists solely for that subgroup check and is pinned, alongside the
delegated paths, to RFC 8032's own test vectors in ``tests/test_ed25519.py``.
"""
from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

_P = 2**255 - 19                                  # the field prime
_L = 2**252 + 27742317777372353535851937790883648493  # the prime group order

_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)

SEED_BYTES = 32
SIGNATURE_BYTES = 64
PUBLIC_KEY_BYTES = 32

# Extended homogeneous coordinates (X, Y, Z, T) with x = X/Z, y = Y/Z, T = XY/Z.
_IDENTITY = (0, 1, 1, 0)


def _recover_x(y: int, sign: int) -> int:
    """Solve x² = (y² − 1)/(dy² + 1); raise if y is not on the curve or non-canonical."""
    if y >= _P:
        raise ValueError("point coordinate out of range")
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        raise ValueError("not a point on edwards25519")
    if x == 0 and sign == 1:
        raise ValueError("invalid sign bit for x = 0")
    if x & 1 != sign:
        x = _P - x
    return x


def _add(p: tuple, q: tuple) -> tuple:
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = 2 * t1 * t2 * _D % _P
    d = 2 * z1 * z2 % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _scalar_mult(p: tuple, e: int) -> tuple:
    q = _IDENTITY
    while e > 0:
        if e & 1:
            q = _add(q, p)
        p = _add(p, p)
        e >>= 1
    return q


def _compress(p: tuple) -> bytes:
    x, y, z, _ = p
    zinv = pow(z, _P - 2, _P)
    x, y = x * zinv % _P, y * zinv % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(data: bytes) -> tuple:
    if len(data) != 32:
        raise ValueError("a point is 32 bytes")
    y = int.from_bytes(data, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return (x, y, 1, x * y % _P)


def _equal(p: tuple, q: tuple) -> bool:
    x1, y1, z1, _ = p
    x2, y2, z2, _ = q
    return (x1 * z2 - x2 * z1) % _P == 0 and (y1 * z2 - y2 * z1) % _P == 0


_BASE_Y = 4 * pow(5, _P - 2, _P) % _P
_BASE = (_recover_x(_BASE_Y, 0), _BASE_Y, 1,
         _recover_x(_BASE_Y, 0) * _BASE_Y % _P)


def is_usable_public_key(public: bytes) -> bool:
    """True only for a canonical, on-curve, PRIME-ORDER public key.

    This is the trust-anchor gate the signature library does not provide: the identity
    point and the other seven small-order points are valid curve points that verify
    forged signatures for every message, and a mixed-order point smuggles a small-order
    component past a naive check. ``[L]A == identity`` with ``A != identity`` accepts
    exactly the points whose order is L — every honestly generated key, nothing else.
    """
    if len(public) != PUBLIC_KEY_BYTES:
        return False
    try:
        point = _decompress(public)
    except ValueError:
        return False
    if _equal(point, _IDENTITY):
        return False
    return _equal(_scalar_mult(point, _L), _IDENTITY)


def public_key(seed: bytes) -> bytes:
    """The 32-byte public key for a 32-byte seed."""
    if len(seed) != SEED_BYTES:
        raise ValueError("an ed25519 seed is exactly 32 bytes")
    return Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()


def sign(seed: bytes, message: bytes) -> bytes:
    """Deterministic 64-byte signature over ``message`` (delegated to the library)."""
    if len(seed) != SEED_BYTES:
        raise ValueError("an ed25519 seed is exactly 32 bytes")
    return Ed25519PrivateKey.from_private_bytes(seed).sign(message)


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    """True only for a valid signature by a PRIME-ORDER ``public`` over ``message``.

    Returns False (never raises) on malformed inputs: a verifier's caller wants one
    question answered, and an exception path that skips the answer is how "invalid"
    accidentally becomes "unchecked". Small-order keys are refused here too, not only
    at policy load — a forgery must have no path in even if a caller skips validation.
    """
    if len(public) != PUBLIC_KEY_BYTES or len(signature) != SIGNATURE_BYTES:
        return False
    if not is_usable_public_key(public):
        return False
    try:
        Ed25519PublicKey.from_public_bytes(public).verify(signature, message)
    except (InvalidSignature, ValueError):
        return False
    return True
