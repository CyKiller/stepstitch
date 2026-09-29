"""Secret, encoded-payload and extended-PII detection in ``redact_text``.

The OpenAI agent incident (2026-09) moved data out in pieces: encoded fragments packed
into shortened links. A scrubber that only knows SSNs and card numbers waves every one of
those shapes through — a JWT, an API key, a base64 blob and a ``bit.ly`` link all survived
``redact_text`` before this suite existed. Each case below is a shape that must now be
caught, and each negative case is ordinary evidence that must NOT be mangled, because a
scrubber that eats stack frames and user agents is a scrubber operators turn off.

Credential-shaped literals are assembled at runtime so no scanner mistakes this file for a
leak — none of them is, or ever was, a real credential.
"""
import pytest

from stepstitch_service.scrubber import redact_text, route_template

_JWT = "eyJhbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0" + "." + "c2lnbmF0dXJlMTIzNDU2"
_OPENAI_KEY = "sk-" + "proj-" + "Ab12Cd34Ef56Gh78Ij90Kl12"
_GITHUB_TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
_AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
_SLACK_TOKEN = "xoxb-" + "123456789012-abcdEFGHijkl"
_GOOGLE_KEY = "AIza" + "SyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q"
_AGENT_TOKEN = "ssa_" + "Zx9Yw8Vu7Ts6Rq5Po4Nm3"
_PEM = ("-----BEGIN RSA " + "PRIVATE KEY-----\nMIIBOgIBAAJBAKj34GkxFhD90vcNLYLInFEX6Ppy1tPf9Cnzj4p4"
        "\n-----END RSA " + "PRIVATE KEY-----")
_BASE64_BLOB = "U2FsdGVkX1+vupppZksvRf5pq5g5XjFRlipRkwB0K1Y96Qsv2Lm+31cmzaAILwyt"
_HEX_BLOB = "deadbeefcafebabe0123456789abcdef00112233"


@pytest.mark.parametrize(
    "text,kind,secret",
    [
        (f"Authorization: Bearer {_JWT[:30]}", "bearer", _JWT[:30]),
        (f"session {_JWT} expired", "jwt", _JWT),
        (f"key {_OPENAI_KEY} leaked", "api_key", _OPENAI_KEY),
        (f"token {_GITHUB_TOKEN}", "api_key", _GITHUB_TOKEN),
        (f"aws {_AWS_KEY} in log", "api_key", _AWS_KEY),
        (f"slack {_SLACK_TOKEN} here", "api_key", _SLACK_TOKEN),
        (f"maps {_GOOGLE_KEY} key", "api_key", _GOOGLE_KEY),
        (f"agent {_AGENT_TOKEN} used", "api_key", _AGENT_TOKEN),
        (f"pem {_PEM} end", "private_key", "MIIBOgIBAAJBAKj34GkxFhD90vcNLYLInFEX6Ppy1tPf9Cnzj4p4"),
        ("password=hunter2hunter2 was rejected", "secret_assignment", "hunter2hunter2"),
        ("api_key: 9f8e7d6c5b4a was refused", "secret_assignment", "9f8e7d6c5b4a"),
        # The exact hostile string test_fixproof.py carries: a secret-named word followed
        # by a credential-shaped value, no separator.
        ("token FAKE-QUERY-SECRET-123 acct 8842", "secret_assignment", "FAKE-QUERY-SECRET-123"),
        ("avatar data:image/png;base64,iVBORw0KGgoAAAANSUhEUg== broke", "data_uri",
         "iVBORw0KGgoAAAANSUhEUg=="),
        ("go to bit.ly/3xYzAbC now", "short_link", "bit.ly/3xYzAbC"),
        ("see t.co/Ab12Cd for more", "short_link", "t.co/Ab12Cd"),
        ("name %6A%61%6E%65%40%65%78 leaked", "percent_encoded", "%6A%61%6E%65%40%65%78"),
        (f"blob {_BASE64_BLOB} attached", "high_entropy", _BASE64_BLOB),
        (f"hash {_HEX_BLOB} seen", "high_entropy", _HEX_BLOB),
    ],
)
def test_secret_and_encoded_shapes_are_redacted(text, kind, secret):
    out, kinds = redact_text(text)
    assert kind in kinds, (kind, kinds, out)
    assert secret not in out, out
    assert f"[redacted:{kind}]" in out


@pytest.mark.parametrize(
    "text,kind,raw",
    [
        ("from 10.20.30.40 at noon", "ip", "10.20.30.40"),
        ("peer 2001:db8:85a3::8a2e:370:7334 dropped", "ip", "2001:db8:85a3::8a2e:370:7334"),
        ("IBAN GB82 WEST 1234 5698 7654 32 bounced", "iban", "GB82 WEST 1234 5698 7654 32"),
        ("IBAN DE89370400440532013000 bounced", "iban", "DE89370400440532013000"),
        ("born 1980-04-12 per form", "date", "1980-04-12"),
        ("SSN 123 45 6789 typed", "ssn", "123 45 6789"),
        ("call +44 20 7946 0958 today", "phone", "+44 20 7946 0958"),
        ("device 00:1A:2B:3C:4D:5E offline", "mac", "00:1A:2B:3C:4D:5E"),
    ],
)
def test_extended_pii_shapes_are_redacted(text, kind, raw):
    out, kinds = redact_text(text)
    assert kind in kinds, (kind, kinds, out)
    assert raw not in out, out


@pytest.mark.parametrize(
    "text",
    [
        "Submit button did nothing on the distributions page",
        "TypeError: Cannot read properties of undefined (reading 'balance')",
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        "at submitTransfer (src/components/TransferFormWizard.tsx:42:17)",
        '[data-testid="transfer-submit"] > button:nth-of-type(2)',
        "release 2026.09.1 on build v1.2.3.4",
        "the token expired before the password reset finished",
        "handleSubmitTransferButtonClickEventListener",
        "/accounts/:id/distributions",
        "ERR12ABCD1234 returned by the gateway",
        "retry at 12:00:02 failed",
    ],
)
def test_ordinary_evidence_is_not_mangled(text):
    out, kinds = redact_text(text)
    assert kinds == [], (kinds, out)
    assert out == text


def test_secrets_are_caught_before_digit_rules_chew_them():
    # A JWT's payload has digits; the old number rule never saw inside a word, so the whole
    # token survived. Now the token goes as one unit, labeled for what it is.
    out, kinds = redact_text(f"cookie {_JWT}")
    assert kinds == ["jwt"]
    assert out == "cookie [redacted:jwt]"


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Percent-encoding is decoded first (parity with the SDK's routeTemplate), so an
        # encoded slug is judged by what it actually says.
        ("/u/%6A%61%6E%65%40example.com/profile", "/u/:id/profile"),
        ("/users/jane.doe@example.com/profile", "/users/:id/profile"),
        (f"/s/{_GITHUB_TOKEN}", "/s/:id"),
        (f"/share/{_BASE64_BLOB.replace('/', '_').replace('+', '-')}", "/share/:id"),
        ("/transfer/review", "/transfer/review"),
        ("/accounts/:id/distributions", "/accounts/:id/distributions"),
    ],
)
def test_route_template_catches_sensitive_segments(raw, expected):
    assert route_template(raw) == expected
