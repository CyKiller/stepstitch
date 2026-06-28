"""Agent connections + per-agent scope for the StepStitch ingest host.

StepStitch is consumed by AI agents over MCP. Today a single shared admin token gives any
agent the full read/draft surface. This module adds **named, scoped tokens**: each connected
agent registers, receives its own bearer token (stored only as a SHA-256 hash), and is
limited to a scope tier. Enforcement lives in the host (see ``build_app``): the service
router and its auth stay untouched — an allowed agent request is translated to admin access
for that one request; a disallowed one is refused with 403.

Scope tiers (increasing), mirroring the Copilot-safe MCP surface
(``mcp_server.COPILOT_SAFE_OPERATIONS``). Agents NEVER reach raw traces, deliver/GitHub
writes, the audit log, or any destructive op — those are not in the rules below, so the
default-deny applies.

  none      → no evidence access (registered but disabled)
  summaries → list/corpus + summary/replayability/privacy-posture/diagnostic-summary
  repros    → summaries + the Playwright reproduction
  drafts    → repros + the sanitized export-preview drafts
"""
from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

SCOPES: Tuple[str, ...] = ("none", "summaries", "repros", "drafts")
_TIER_RANK = {s: i for i, s in enumerate(SCOPES)}  # none=0 < summaries < repros < drafts

_PFX = r"/api/stepstitch/v1"
# (method, path-regex, minimum scope tier that unlocks it). Anything not listed is denied.
_RULES: Tuple[Tuple[str, str, str], ...] = (
    ("GET", rf"^{_PFX}/sessions$", "summaries"),
    ("GET", rf"^{_PFX}/corpus$", "summaries"),
    ("GET", rf"^{_PFX}/session/[^/]+/summary$", "summaries"),
    ("GET", rf"^{_PFX}/session/[^/]+/replayability$", "summaries"),
    ("GET", rf"^{_PFX}/session/[^/]+/privacy-posture$", "summaries"),
    ("GET", rf"^{_PFX}/session/[^/]+/diagnostic-summary$", "summaries"),
    ("GET", rf"^{_PFX}/correlation/[^/]+/summary$", "summaries"),
    ("GET", rf"^{_PFX}/session/[^/]+/playwright$", "repros"),
    ("POST", rf"^{_PFX}/session/[^/]+/export-preview$", "drafts"),
    ("POST", rf"^{_PFX}/session/[^/]+/financial-services-export-preview$", "drafts"),
)


def scope_allows(scope: str, method: str, path: str) -> bool:
    """True if an agent at ``scope`` may call ``method path``. Default-deny."""
    rank = _TIER_RANK.get(scope, 0)
    if rank == 0:  # 'none' or unknown → nothing
        return False
    method = method.upper()
    for m, pattern, min_tier in _RULES:
        if m == method and re.match(pattern, path):
            return rank >= _TIER_RANK[min_tier]
    return False


def new_token() -> str:
    """A fresh agent bearer token. Shown to the operator exactly once; only its hash is stored."""
    return "ssa_" + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


ExecuteFn = Callable[..., Awaitable[Any]]
FetchOneFn = Callable[..., Awaitable[Any]]
FetchAllFn = Callable[..., Awaitable[Any]]


async def register_agent(
    execute: ExecuteFn, *, name: str, scope: str, actor: str,
    now: Optional[datetime] = None,
) -> Tuple[str, str]:
    """Register an agent and return ``(agent_id, token)``. The token is returned ONCE."""
    if scope not in SCOPES:
        raise ValueError(f"invalid scope {scope!r}; must be one of {SCOPES}")
    if not name or not name.strip():
        raise ValueError("agent name is required")
    agent_id = str(uuid.uuid4())
    token = new_token()
    await execute(
        "INSERT INTO stepstitch_agents "
        "(id, name, token_hash, scope, revoked, created_at, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (agent_id, name.strip(), hash_token(token), scope, False,
         now or datetime.now(timezone.utc), actor),
    )
    return agent_id, token


async def list_agents(fetchall: FetchAllFn) -> List[Dict[str, Any]]:
    """All registered agents (never the token or its hash)."""
    rows = await fetchall(
        "SELECT id, name, scope, revoked, created_at, created_by "
        "FROM stepstitch_agents ORDER BY created_at DESC",
        (),
    )
    return [
        {
            "id": r[0], "name": r[1], "scope": r[2], "revoked": bool(r[3]),
            "created_at": r[4].isoformat() if hasattr(r[4], "isoformat") else r[4],
            "created_by": r[5],
        }
        for r in rows
    ]


async def revoke_agent(execute: ExecuteFn, agent_id: str) -> None:
    await execute(
        "UPDATE stepstitch_agents SET revoked = ? WHERE id = ?", (True, agent_id)
    )


async def resolve_agent(fetchone: FetchOneFn, token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Look up a live (non-revoked) agent by bearer token, or None."""
    if not token:
        return None
    row = await fetchone(
        "SELECT id, name, scope, revoked FROM stepstitch_agents WHERE token_hash = ?",
        (hash_token(token),),
    )
    if not row or bool(row[3]):
        return None
    return {"id": row[0], "name": row[1], "scope": row[2]}
