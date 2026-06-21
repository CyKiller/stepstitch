"""OIDC operator auth: per-operator identity, role gating, and token validation.

Generates a throwaway RSA keypair, serves it as a JWKS, and signs RS256 JWTs — no network.
Proves the headline WS-B property: two distinct operators produce two distinct audit actors.
"""
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from server.host import build_app
from server.oidc import OidcVerifier, build_oidc_auth, require_roles

ISS = "https://login.example.com/tenant/v2.0"
AUD = "api://stepstitch"
_PFX = "/api/stepstitch/v1"


def _keypair(kid="k1"):
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(priv.public_key()))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return priv, {"keys": [jwk]}


def _token(priv, *, kid="k1", iss=ISS, aud=AUD, sub="op1", email=None,
           roles=None, exp_delta=3600):
    now = int(time.time())
    payload = {"iss": iss, "aud": aud, "sub": sub, "iat": now, "exp": now + exp_delta}
    if email is not None:
        payload["email"] = email
    if roles is not None:
        payload["roles"] = roles
    return jwt.encode(payload, priv, algorithm="RS256", headers={"kid": kid})


def _auth(jwks, admin_roles=("stepstitch-operator",), ingest_token="ing"):
    verifier = OidcVerifier(issuer=ISS, audience=AUD, jwks=jwks)
    return build_oidc_auth(verifier, admin_roles=admin_roles, ingest_token=ingest_token)


# --- unit: identity + role gating + validation -------------------------------------------

def test_valid_token_yields_real_operator_identity():
    priv, jwks = _keypair()
    _, require_admin = _auth(jwks)
    actor = require_admin(authorization="Bearer " + _token(
        priv, sub="op1", email="alice@example.com", roles=["stepstitch-operator"]))
    assert actor["user_id"] == "alice@example.com"
    assert "stepstitch-operator" in actor["roles"]


def test_token_without_required_role_is_forbidden():
    priv, jwks = _keypair()
    _, require_admin = _auth(jwks)
    with pytest.raises(HTTPException) as ei:
        require_admin(authorization="Bearer " + _token(priv, roles=["someone-else"]))
    assert ei.value.status_code == 403


def test_missing_bearer_is_unauthorized():
    priv, jwks = _keypair()
    _, require_admin = _auth(jwks)
    with pytest.raises(HTTPException) as ei:
        require_admin(authorization=None)
    assert ei.value.status_code == 401


def test_bad_signature_is_rejected():
    priv, jwks = _keypair(kid="k1")
    other, _ = _keypair(kid="k1")  # signed by a key not in the JWKS
    _, require_admin = _auth(jwks)
    with pytest.raises(HTTPException) as ei:
        require_admin(authorization="Bearer " + _token(
            other, roles=["stepstitch-operator"]))
    assert ei.value.status_code == 401


def test_wrong_audience_is_rejected():
    priv, jwks = _keypair()
    _, require_admin = _auth(jwks)
    with pytest.raises(HTTPException) as ei:
        require_admin(authorization="Bearer " + _token(
            priv, aud="api://someone-else", roles=["stepstitch-operator"]))
    assert ei.value.status_code == 401


def test_expired_token_is_rejected():
    priv, jwks = _keypair()
    _, require_admin = _auth(jwks)
    with pytest.raises(HTTPException) as ei:
        require_admin(authorization="Bearer " + _token(
            priv, roles=["stepstitch-operator"], exp_delta=-30))
    assert ei.value.status_code == 401


def test_ingest_uses_machine_token_not_oidc():
    priv, jwks = _keypair()
    get_user_id, _ = _auth(jwks, ingest_token="ing")
    assert get_user_id(authorization="Bearer ing") == "ingest-client"
    with pytest.raises(HTTPException) as ei:
        get_user_id(authorization="Bearer wrong")
    assert ei.value.status_code == 401


# --- integration: two operators -> two distinct audit actors ------------------------------

class _DB:
    def __init__(self):
        self.rows = {}

    async def execute(self, query, params=()):
        if query.strip().upper().startswith("INSERT INTO STEPSTITCH_TRACES"):
            self.rows[params[0]] = {"footsteps": params[5], "explanation": params[4],
                                    "user_id": params[3], "project_id": params[2]}

    async def fetchone(self, query, params=()):
        row = self.rows.get(params[0])
        if not row:
            return None
        q = " ".join(query.split())
        if q.startswith("SELECT footsteps, project_id"):
            return (row["footsteps"], row["project_id"])
        if q.startswith("SELECT footsteps FROM"):
            return (row["footsteps"],)
        return (row["footsteps"], row["explanation"], row["user_id"], row["project_id"], None)

    async def fetchall(self, query, params=()):
        return []


_PAYLOAD = {
    "app_id": "demo",
    "footsteps": [{"timestamp": "t", "type": "api_error", "route": "/accounts/:id",
                   "label": "[masked]", "metadata": {"status": 500}}],
    "metadata": {"sdk_version": "0.4.0"},
}


def test_two_operators_recorded_as_distinct_audit_actors():
    priv, jwks = _keypair()
    get_user_id, require_admin = _auth(jwks)
    db = _DB()
    actors = []

    async def audit(action, actor, detail):
        actors.append(actor)

    app: FastAPI = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall, audit=audit)
    client = TestClient(app)

    tid = client.post(f"{_PFX}/session", json=_PAYLOAD,
                      headers={"Authorization": "Bearer ing"}).json()["trace_id"]

    for sub, email in [("op1", "alice@example.com"), ("op2", "bob@example.com")]:
        tok = _token(priv, sub=sub, email=email, roles=["stepstitch-operator"])
        r = client.get(f"{_PFX}/session/{tid}/summary",
                       headers={"Authorization": "Bearer " + tok})
        assert r.status_code == 200

    assert {"alice@example.com", "bob@example.com"} <= set(actors)


def test_rbac_operator_can_read_but_not_delete_admin_can():
    priv, jwks = _keypair()
    verifier = OidcVerifier(issuer=ISS, audience=AUD, jwks=jwks)
    # Read surface accepts operator+admin; destructive ops require admin only.
    get_user_id, require_admin = build_oidc_auth(
        verifier, admin_roles=["stepstitch-operator", "stepstitch-admin"], ingest_token="ing")
    require_destructive = require_roles(verifier, ["stepstitch-admin"])
    db = _DB()

    async def audit(action, actor, detail):
        pass

    app = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        require_destructive=require_destructive,
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall, audit=audit)
    client = TestClient(app)

    operator = "Bearer " + _token(priv, sub="op", email="op@example.com",
                                  roles=["stepstitch-operator"])
    admin = "Bearer " + _token(priv, sub="ad", email="ad@example.com",
                               roles=["stepstitch-admin"])

    tid = client.post(f"{_PFX}/session", json=_PAYLOAD,
                      headers={"Authorization": "Bearer ing"}).json()["trace_id"]

    # Operator can read the trace...
    assert client.get(f"{_PFX}/session/{tid}/summary",
                      headers={"Authorization": operator}).status_code == 200
    # ...but cannot delete (least privilege)...
    assert client.delete(f"{_PFX}/session/by-user/someone",
                         headers={"Authorization": operator}).status_code == 403
    # ...while an admin can.
    assert client.delete(f"{_PFX}/session/by-user/someone",
                         headers={"Authorization": admin}).status_code == 200
