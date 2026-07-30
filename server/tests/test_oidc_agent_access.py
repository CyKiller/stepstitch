"""Agent tokens under OIDC: a capability gap, not a bypass.

STATUS.md notes agent-scope enforcement exists only in shared-admin-token mode. This file
pins down what that means when a deployment runs OIDC (no shared admin token): the agent
middleware and the ``/admin/agents`` routes are absent, and a stored, unrevoked ``ssa_``
token — even one whose scope would allow the path in shared-token mode — is refused
everywhere. No request gains access it would not otherwise have, so the correct
classification is "agents unsupported under OIDC" (a capability gap), not a privilege
bypass. If a future change ever lets an ``ssa_`` token through under OIDC, these tests
fail and the classification must be revisited.
"""
import hashlib
import json
import time

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from server.host import build_app
from server.oidc import OidcVerifier, build_oidc_auth

ISS = "https://login.example.com/tenant/v2.0"
AUD = "api://stepstitch"
_PFX = "/api/stepstitch/v1"

# A syntactically valid agent token whose hash is present and unrevoked in the DB —
# the strongest starting position an agent credential can have.
AGENT_TOKEN = "ssa_test-token-registered-before-oidc-migration"


class _DB:
    """In-memory fake holding one trace and one registered, unrevoked agent."""

    def __init__(self):
        self.traces = {}
        self.agent = {
            "id": "agent-1", "name": "repro-bot",
            "token_hash": hashlib.sha256(AGENT_TOKEN.encode("utf-8")).hexdigest(),
            "scope": "read", "revoked": False,
        }

    async def execute(self, query, params=()):
        if " ".join(query.split()).upper().startswith("INSERT INTO STEPSTITCH_TRACES"):
            self.traces[params[0]] = {"footsteps": params[5], "explanation": params[4],
                                      "user_id": params[3], "project_id": params[2]}

    async def fetchone(self, query, params=()):
        q = " ".join(query.split())
        if "FROM stepstitch_agents" in q:
            a = self.agent
            if a["token_hash"] == params[0]:
                return (a["id"], a["name"], a["scope"], a["revoked"])
            return None
        row = self.traces.get(params[0])
        if not row:
            return None
        if q.startswith("SELECT footsteps, project_id"):
            return (row["footsteps"], row["project_id"])
        if q.startswith("SELECT footsteps FROM"):
            return (row["footsteps"],)
        return (row["footsteps"], row["explanation"], row["user_id"], row["project_id"], None)

    async def fetchall(self, query, params=()):
        return []


def _keypair(kid="k1"):
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(priv.public_key()))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return priv, {"keys": [jwk]}


def _operator_token(priv):
    now = int(time.time())
    return jwt.encode(
        {"iss": ISS, "aud": AUD, "sub": "op1", "email": "op@example.com",
         "roles": ["stepstitch-operator"], "iat": now, "exp": now + 3600},
        priv, algorithm="RS256", headers={"kid": "k1"})


_PAYLOAD = {
    "app_id": "demo",
    "footsteps": [{"timestamp": "t", "type": "api_error", "route": "/accounts/:id",
                   "label": "[masked]", "metadata": {"status": 500}}],
    "metadata": {"sdk_version": "0.4.0"},
}


def _oidc_client():
    """An OIDC-mode app: no shared admin token, so no agent middleware, no agent routes."""
    priv, jwks = _keypair()
    verifier = OidcVerifier(issuer=ISS, audience=AUD, jwks=jwks)
    get_user_id, require_admin = build_oidc_auth(
        verifier, admin_roles=["stepstitch-operator"], ingest_token="ing")
    db = _DB()
    app: FastAPI = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall)
    return TestClient(app), priv


def _agent(tok=AGENT_TOKEN):
    return {"Authorization": f"Bearer {tok}"}


def test_agent_token_gets_no_read_access_under_oidc():
    client, priv = _oidc_client()
    tid = client.post(f"{_PFX}/session", json=_PAYLOAD,
                      headers={"Authorization": "Bearer ing"}).json()["trace_id"]
    # Sanity: the trace is readable by a real operator...
    ok = client.get(f"{_PFX}/session/{tid}/summary",
                    headers={"Authorization": "Bearer " + _operator_token(priv)})
    assert ok.status_code == 200
    # ...but the registered agent token — scope 'read', unrevoked — is a plain 401:
    # it is not a JWT, and no middleware exists to translate it.
    r = client.get(f"{_PFX}/session/{tid}/summary", headers=_agent())
    assert r.status_code == 401


def test_agent_token_cannot_ingest_under_oidc():
    client, _ = _oidc_client()
    r = client.post(f"{_PFX}/session", json=_PAYLOAD, headers=_agent())
    assert r.status_code == 401


def test_agent_management_routes_do_not_exist_under_oidc():
    client, priv = _oidc_client()
    operator = {"Authorization": "Bearer " + _operator_token(priv)}
    # Even a legitimate operator cannot register agents: the routes are only built in
    # shared-admin-token mode, so agents are unsupported — not silently unscoped.
    assert client.post("/admin/agents", json={"name": "x", "scope": "read"},
                       headers=operator).status_code == 404
    assert client.get("/admin/agents", headers=operator).status_code == 404
