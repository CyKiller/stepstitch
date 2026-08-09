"""Pure-stdlib Ed25519 (RFC 8032) — the cryptography under FixProof signatures.

Why hand-carried instead of a dependency: ``stepstitch proof verify`` promises to run
offline in an environment that has nothing but Python (the same promise attestation.py
and fixproof.py keep), and the stdlib has no Ed25519. This module is the RFC 8032
reference construction — arbitrary-precision integer arithmetic on edwards25519 in
extended homogeneous coordinates — kept small enough to audit in one sitting and pinned
to the RFC's own test vectors in ``tests/test_ed25519.py``.

Scope, stated honestly: this is NOT constant-time. That is acceptable here and only
here because the verify path handles exclusively public data (a public key, a published
statement, a detached signature), and the sign path runs inside the tenant's own host
against the tenant's own key — the classic remote-timing attacker of TLS lore has no
interface to this code. Do not lift it into a context where an attacker can time
signing of chosen messages.
"""
from __future__ import annotations

import hashlib

_P = 2**255 - 19                                  # the field prime
_L = 2**252 + 27742317777372353535851937790883648493  # the group order

_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)

SEED_BYTES = 32
SIGNATURE_BYTES = 64
PUBLIC_KEY_BYTES = 32

# Extended homogeneous coordinates (X, Y, Z, T) with x = X/Z, y = Y/Z, T = XY/Z.
_IDENTITY = (0, 1, 1, 0)


def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def _recover_x(y: int, sign: int) -> int:
    """Solve x² = (y² − 1)/(dy² + 1); raise if y is not on the curve."""
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
_BASE = ( _recover_x(_BASE_Y, 0), _BASE_Y, 1, _recover_x(_BASE_Y, 0) * _BASE_Y % _P)


def _clamp(seed_hash: bytes) -> int:
    a = int.from_bytes(seed_hash[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a


def public_key(seed: bytes) -> bytes:
    """The 32-byte public key for a 32-byte seed (RFC 8032 §5.1.5)."""
    if len(seed) != SEED_BYTES:
        raise ValueError("an ed25519 seed is exactly 32 bytes")
    return _compress(_scalar_mult(_BASE, _clamp(_sha512(seed))))


def sign(seed: bytes, message: bytes) -> bytes:
    """Deterministic 64-byte signature over ``message`` (RFC 8032 §5.1.6)."""
    if len(seed) != SEED_BYTES:
        raise ValueError("an ed25519 seed is exactly 32 bytes")
    h = _sha512(seed)
    a = _clamp(h)
    prefix = h[32:]
    public = _compress(_scalar_mult(_BASE, a))
    r = int.from_bytes(_sha512(prefix + message), "little") % _L
    r_point = _compress(_scalar_mult(_BASE, r))
    k = int.from_bytes(_sha512(r_point + public + message), "little") % _L
    s = (r + k * a) % _L
    return r_point + int.to_bytes(s, 32, "little")


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    """True only for a valid signature by ``public`` over exactly ``message``.

    Returns False (never raises) on malformed inputs: a verifier's caller wants one
    question answered, and an exception path that skips the answer is how "invalid"
    accidentally becomes "unchecked".
    """
    if len(public) != PUBLIC_KEY_BYTES or len(signature) != SIGNATURE_BYTES:
        return False
    try:
        a_point = _decompress(public)
        r_point = _decompress(signature[:32])
    except ValueError:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:  # RFC 8032 §5.1.7: reject non-canonical s (signature malleability)
        return False
    k = int.from_bytes(_sha512(signature[:32] + public + message), "little") % _L
    return _equal(_scalar_mult(_BASE, s), _add(r_point, _scalar_mult(a_point, k)))
