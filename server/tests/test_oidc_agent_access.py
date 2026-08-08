"""Agent tokens under OIDC: same scopes, same refusals as shared-token mode.

Historically agents were unsupported under OIDC (a capability gap this file used
to pin): the middleware's mechanism was header substitution to the shared admin
token, which cannot exist in OIDC mode. The enforcement is now auth-mode-agnostic
— the middleware resolves ``ssa_`` tokens, checks ``scope_allows``, and stamps
``request.state.agent``; the admin dependency accepts the stamp in both modes.

What must hold, and is pinned here:
  - a registered, unrevoked agent gets exactly its scope's reads — no more
  - a request outside the scope is refused 403 BY SCOPE, never translated
  - an unregistered or revoked ``ssa_`` token stays a plain 401
  - the verify scope still cannot be issued through any read tier
  - operators manage agents via /admin/agents in OIDC mode too
"""
import hashlib
import json
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
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
    """In-memory fake holding one trace and one registered agent."""

    def __init__(self, scope="summaries", revoked=False):
        self.traces = {}
        self.agent = {
            "id": "agent-1", "name": "repro-bot",
            "token_hash": hashlib.sha256(AGENT_TOKEN.encode("utf-8")).hexdigest(),
            "scope": scope, "revoked": revoked,
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


def _oidc_client(scope="summaries", revoked=False):
    """An OIDC-mode app: no shared admin token anywhere."""
    priv, jwks = _keypair()
    verifier = OidcVerifier(issuer=ISS, audience=AUD, jwks=jwks)
    get_user_id, require_admin = build_oidc_auth(
        verifier, admin_roles=["stepstitch-operator"], ingest_token="ing")
    db = _DB(scope=scope, revoked=revoked)
    app: FastAPI = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall)
    return TestClient(app), priv


def _agent(tok=AGENT_TOKEN):
    return {"Authorization": f"Bearer {tok}"}


def _ingest_trace(client):
    return client.post(f"{_PFX}/session", json=_PAYLOAD,
                       headers={"Authorization": "Bearer ing"}).json()["trace_id"]


def test_a_scoped_agent_reads_exactly_its_tier_under_oidc():
    client, priv = _oidc_client(scope="summaries")
    tid = _ingest_trace(client)
    # The operator path is untouched...
    ok = client.get(f"{_PFX}/session/{tid}/summary",
                    headers={"Authorization": "Bearer " + _operator_token(priv)})
    assert ok.status_code == 200
    # ...and the registered summaries-scope agent now reads the summary too.
    r = client.get(f"{_PFX}/session/{tid}/summary", headers=_agent())
    assert r.status_code == 200
    # But a repros-tier read is beyond its scope: refused BY SCOPE, not by auth mode.
    deeper = client.get(f"{_PFX}/session/{tid}/playwright", headers=_agent())
    assert deeper.status_code == 403
    assert "scope" in deeper.json()["detail"]


def test_agent_token_still_cannot_ingest_under_oidc():
    client, _ = _oidc_client()
    r = client.post(f"{_PFX}/session", json=_PAYLOAD, headers=_agent())
    # Refused by scope (no read tier may write) — a 403 naming the scope, exactly as
    # shared-token mode refuses it. Never a silent translation to ingest.
    assert r.status_code == 403
    assert "scope" in r.json()["detail"]


def test_an_unregistered_or_revoked_token_stays_a_plain_401():
    client, _ = _oidc_client()
    tid = _ingest_trace(client)
    r = client.get(f"{_PFX}/session/{tid}/summary",
                   headers=_agent("ssa_never-registered-token"))
    assert r.status_code == 401

    revoked_client, _ = _oidc_client(revoked=True)
    tid = _ingest_trace(revoked_client)
    r = revoked_client.get(f"{_PFX}/session/{tid}/summary", headers=_agent())
    assert r.status_code == 401


def test_admin_routes_are_never_agent_accessible():
    """The middleware only stamps service-prefix requests: an agent token on an
    /admin route is not a JWT, so it dies in the OIDC verifier as before."""
    client, _ = _oidc_client(scope="verify")
    assert client.get("/admin/status", headers=_agent()).status_code == 401
    assert client.get("/admin/agents", headers=_agent()).status_code == 401


def test_operators_manage_agents_under_oidc():
    client, priv = _oidc_client()
    operator = {"Authorization": "Bearer " + _operator_token(priv)}
    created = client.post("/admin/agents", json={"name": "ci", "scope": "verify"},
                          headers=operator)
    assert created.status_code == 200
    assert created.json()["token"].startswith("ssa_")
    assert client.get("/admin/agents", headers=operator).status_code == 200
