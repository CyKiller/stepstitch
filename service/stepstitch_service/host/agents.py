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

``verify`` sits OUTSIDE that ladder, deliberately. It is the CI credential: it may fetch a
reproduction and post the measured red/green outcome, and nothing else. It is not a superset
of ``drafts`` (CI has no business drafting tickets), and ``drafts`` is not a superset of it
(a ticket-drafting agent must never be able to write a verdict — verdicts are evidence). So
rules carry an explicit set of scopes rather than a minimum tier.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

SCOPES: Tuple[str, ...] = ("none", "summaries", "repros", "drafts", "verify")
# The linear evidence-access ladder. 'verify' is not on it (see the module docstring).
_LADDER: Tuple[str, ...] = ("none", "summaries", "repros", "drafts")
_TIER_RANK = {s: i for i, s in enumerate(_LADDER)}


def _from_tier(min_tier: str, *extra: str) -> frozenset:
    """Every ladder scope at or above ``min_tier``, plus any off-ladder scopes named."""
    floor = _TIER_RANK[min_tier]
    return frozenset(
        [s for s in _LADDER if _TIER_RANK[s] >= floor and s != "none"] + list(extra)
    )


_PFX = r"/api/stepstitch/v1"
# (method, path-regex, the exact set of scopes that unlocks it). Anything not listed is denied.
_RULES: Tuple[Tuple[str, str, frozenset], ...] = (
    ("GET", rf"^{_PFX}/sessions$", _from_tier("summaries")),
    ("GET", rf"^{_PFX}/corpus$", _from_tier("summaries")),
    ("GET", rf"^{_PFX}/session/[^/]+/summary$", _from_tier("summaries")),
    ("GET", rf"^{_PFX}/session/[^/]+/replayability$", _from_tier("summaries")),
    ("GET", rf"^{_PFX}/session/[^/]+/privacy-posture$", _from_tier("summaries")),
    ("GET", rf"^{_PFX}/session/[^/]+/diagnostic-summary$", _from_tier("summaries")),
    ("GET", rf"^{_PFX}/correlation/[^/]+/summary$", _from_tier("summaries")),
    # Structural reads that carry no reproduction code: a fix reference matched by shape,
    # and the signed evidence bundle. Both are already-sanitized composites of summary-tier
    # facts, so they sit with the summaries.
    ("GET", rf"^{_PFX}/session/[^/]+/similar-fixes$", _from_tier("summaries")),
    ("GET", rf"^{_PFX}/session/[^/]+/attestation$", _from_tier("summaries")),
    # The FixProof statement is the same class of artifact as the attestation: digests,
    # statuses, and identities — never reproduction code or raw values. 'verify' joins
    # because CI is exactly the caller that exports the proof it just earned; download
    # is the same document with a filename, so the same rule covers it.
    ("GET", rf"^{_PFX}/session/[^/]+/fixproof(/download)?$",
     _from_tier("summaries", "verify")),
    # CI needs the reproduction it is about to run, so 'verify' joins the repro readers.
    ("GET", rf"^{_PFX}/session/[^/]+/playwright$", _from_tier("repros", "verify")),
    # These describe or reduce the reproduction itself — fragility scores its selectors,
    # minimal-repro returns a shorter version of the test — so they are repro-tier, not
    # summary-tier. CI is not on them: it runs the frozen script it was given, and has no
    # business fetching a different, shorter one.
    ("GET", rf"^{_PFX}/session/[^/]+/fragility$", _from_tier("repros")),
    ("GET", rf"^{_PFX}/session/[^/]+/minimal-repro$", _from_tier("repros")),
    # The Safe Agent Packet composes summary + score + posture + the compiled reproduction
    # into one call. It is exactly repro-tier because it CONTAINS the reproduction —
    # granting it below that tier would let a summaries-only agent read repro code through
    # the side door. This is the tool a coding agent actually uses; before it had a rule,
    # `scope_allows` default-denied it and the only credential that worked was the admin
    # token, which defeated the entire point of scoped agents.
    ("GET", rf"^{_PFX}/session/[^/]+/agent-packet$", _from_tier("repros")),
    ("POST", rf"^{_PFX}/session/[^/]+/export-preview$", _from_tier("drafts")),
    ("POST", rf"^{_PFX}/session/[^/]+/financial-services-export-preview$", _from_tier("drafts")),
    # Writing a verdict is exclusive to 'verify' — no read tier can record evidence.
    ("POST", rf"^{_PFX}/session/[^/]+/verify$", frozenset({"verify"})),
)


def scope_allows(scope: str, method: str, path: str) -> bool:
    """True if an agent at ``scope`` may call ``method path``. Default-deny."""
    if scope not in SCOPES or scope == "none":
        return False
    method = method.upper()
    for m, pattern, allowed in _RULES:
        if m == method and re.match(pattern, path):
            return scope in allowed
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
