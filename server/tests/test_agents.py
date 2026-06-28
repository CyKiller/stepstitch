"""Agent registry + scope rules (server/agents.py)."""
import asyncio

from server.agents import (
    hash_token,
    list_agents,
    new_token,
    register_agent,
    resolve_agent,
    revoke_agent,
    scope_allows,
)

_PFX = "/api/stepstitch/v1"


def run(coro):
    return asyncio.run(coro)


# ---- scope rules (pure) -------------------------------------------------------------

def test_none_scope_allows_nothing():
    assert not scope_allows("none", "GET", f"{_PFX}/session/abc/summary")
    assert not scope_allows("bogus", "GET", f"{_PFX}/session/abc/summary")


def test_tiers_are_cumulative_and_default_deny():
    summ = f"{_PFX}/session/abc/summary"
    play = f"{_PFX}/session/abc/playwright"
    draft = f"{_PFX}/session/abc/export-preview"

    assert scope_allows("summaries", "GET", summ)
    assert not scope_allows("summaries", "GET", play)
    assert not scope_allows("summaries", "POST", draft)

    assert scope_allows("repros", "GET", summ)
    assert scope_allows("repros", "GET", play)
    assert not scope_allows("repros", "POST", draft)

    assert scope_allows("drafts", "GET", play)
    assert scope_allows("drafts", "POST", draft)


def test_agents_never_reach_raw_destructive_or_audit_routes():
    # No scope, however high, unlocks raw traces, the audit log, deliver/github, or deletes.
    for scope in ("summaries", "repros", "drafts"):
        assert not scope_allows(scope, "GET", f"{_PFX}/session/abc")          # raw trace
        assert not scope_allows(scope, "GET", f"{_PFX}/audit")                # audit log
        assert not scope_allows(scope, "POST", f"{_PFX}/session/abc/deliver")
        assert not scope_allows(scope, "POST", f"{_PFX}/session/abc/github/pr")
        assert not scope_allows(scope, "DELETE", f"{_PFX}/session/by-user/u1")


def test_tokens_are_opaque_hashed_and_unique():
    a, b = new_token(), new_token()
    assert a != b and a.startswith("ssa_")
    assert hash_token(a) == hash_token(a) and hash_token(a) != hash_token(b)
    assert a not in hash_token(a)  # the hash never contains the plaintext


# ---- registry round-trip (fake DB) --------------------------------------------------

class FakeDB:
    def __init__(self):
        self.rows = {}  # id -> dict

    async def execute(self, sql, params=()):
        s = " ".join(sql.split()).upper()
        if s.startswith("INSERT INTO STEPSTITCH_AGENTS"):
            self.rows[params[0]] = {
                "id": params[0], "name": params[1], "token_hash": params[2],
                "scope": params[3], "revoked": params[4], "created_at": params[5],
                "created_by": params[6],
            }
        elif s.startswith("UPDATE STEPSTITCH_AGENTS SET REVOKED"):
            self.rows[params[1]]["revoked"] = params[0]

    async def fetchone(self, sql, params=()):
        th = params[0]
        for r in self.rows.values():
            if r["token_hash"] == th:
                return (r["id"], r["name"], r["scope"], r["revoked"])
        return None

    async def fetchall(self, sql, params=()):
        return [
            (r["id"], r["name"], r["scope"], r["revoked"], r["created_at"], r["created_by"])
            for r in self.rows.values()
        ]


def test_register_list_resolve_revoke_round_trip():
    db = FakeDB()
    agent_id, token = run(register_agent(db.execute, name="Claude repro", scope="repros",
                                         actor="admin"))

    # The token resolves to the agent's scope...
    resolved = run(resolve_agent(db.fetchone, token))
    assert resolved == {"id": agent_id, "name": "Claude repro", "scope": "repros"}

    # ...the listing never leaks the token or its hash...
    listed = run(list_agents(db.fetchall))
    assert listed[0]["name"] == "Claude repro" and listed[0]["scope"] == "repros"
    assert "token" not in listed[0] and "token_hash" not in listed[0]

    # ...and a revoked token no longer resolves.
    run(revoke_agent(db.execute, agent_id))
    assert run(resolve_agent(db.fetchone, token)) is None
