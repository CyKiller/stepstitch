"""The Ed25519 primitive, pinned to RFC 8032's own test vectors (§7.1).

A hand-carried crypto implementation earns its keep only by matching the RFC byte for
byte — these vectors are the authority, not this repo. Beyond the vectors: signature
malleability (non-canonical s), truncation, wrong-key, wrong-message, and malformed
points must all verify False, never raise.
"""
from __future__ import annotations

import hashlib

import pytest

from stepstitch_service import _ed25519

# RFC 8032 §7.1 — TEST 1, TEST 2, TEST 3 (seed, public, message, signature), verbatim.
RFC_VECTORS = [
    (
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        "",
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
    ),
    (
        "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
        "72",
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
        "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
    ),
    (
        "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
        "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
        "af82",
        "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
        "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a",
    ),
]


@pytest.mark.parametrize("seed_hex,public_hex,message_hex,signature_hex", RFC_VECTORS)
def test_rfc_8032_public_key_derivation(seed_hex, public_hex, message_hex,
                                        signature_hex):
    assert _ed25519.public_key(bytes.fromhex(seed_hex)).hex() == public_hex


@pytest.mark.parametrize("seed_hex,public_hex,message_hex,signature_hex", RFC_VECTORS)
def test_rfc_8032_signing_matches_the_rfc_byte_for_byte(seed_hex, public_hex,
                                                        message_hex, signature_hex):
    signature = _ed25519.sign(bytes.fromhex(seed_hex), bytes.fromhex(message_hex))
    assert signature.hex() == signature_hex


@pytest.mark.parametrize("seed_hex,public_hex,message_hex,signature_hex", RFC_VECTORS)
def test_rfc_8032_verification_accepts_the_rfc_signatures(seed_hex, public_hex,
                                                          message_hex, signature_hex):
    assert _ed25519.verify(bytes.fromhex(public_hex), bytes.fromhex(message_hex),
                           bytes.fromhex(signature_hex))


def test_a_flipped_bit_anywhere_in_the_signature_fails():
    seed_hex, public_hex, message_hex, signature_hex = RFC_VECTORS[2]
    public, message = bytes.fromhex(public_hex), bytes.fromhex(message_hex)
    good = bytearray(bytes.fromhex(signature_hex))
    for index in (0, 31, 32, 63):  # R start/end, s start/end
        bad = bytearray(good)
        bad[index] ^= 0x01
        assert not _ed25519.verify(public, message, bytes(bad))


def test_the_wrong_message_and_the_wrong_key_both_fail():
    seed = hashlib.sha256(b"test seed one").digest()
    other = hashlib.sha256(b"test seed two").digest()
    signature = _ed25519.sign(seed, b"the signed message")
    assert _ed25519.verify(_ed25519.public_key(seed), b"the signed message", signature)
    assert not _ed25519.verify(_ed25519.public_key(seed), b"a different message",
                               signature)
    assert not _ed25519.verify(_ed25519.public_key(other), b"the signed message",
                               signature)


def test_a_non_canonical_s_is_rejected_not_normalized():
    """RFC 8032 §5.1.7: s must be < L. Accepting s+L would make every signature carry
    a sibling — malleability a replay filter upstream might trip over."""
    L = 2**252 + 27742317777372353535851937790883648493
    seed = hashlib.sha256(b"malleability").digest()
    message = b"payload"
    signature = _ed25519.sign(seed, message)
    s = int.from_bytes(signature[32:], "little")
    forged = signature[:32] + int.to_bytes(s + L, 32, "little")
    assert not _ed25519.verify(_ed25519.public_key(seed), message, forged)


def test_malformed_inputs_verify_false_never_raise():
    seed = hashlib.sha256(b"robustness").digest()
    public = _ed25519.public_key(seed)
    signature = _ed25519.sign(seed, b"m")
    assert not _ed25519.verify(public, b"m", signature[:63])          # truncated
    assert not _ed25519.verify(public[:31], b"m", signature)          # short key
    assert not _ed25519.verify(b"\xff" * 32, b"m", signature)         # off-curve key
    assert not _ed25519.verify(public, b"m", b"\xff" * 64)            # off-curve R
    assert not _ed25519.verify(b"", b"m", b"")                        # empty everything


def test_signing_is_deterministic():
    """Same seed + same message = same bytes — what lets the committed demo proof stay
    byte-stable under the drift gate."""
    seed = hashlib.sha256(b"determinism").digest()
    assert _ed25519.sign(seed, b"stable") == _ed25519.sign(seed, b"stable")


def test_seed_length_is_enforced():
    with pytest.raises(ValueError):
        _ed25519.sign(b"short", b"m")
    with pytest.raises(ValueError):
        _ed25519.public_key(b"x" * 33)
