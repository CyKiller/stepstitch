"""OIDC/JWT auth for the StepStitch ingest host (per-operator FI-grade identity).

The host's auth is injected into ``create_stepstitch_router``; StepStitch core stays
auth-agnostic. This is the production swap-in for the demo shared-bearer ``build_auth``:
it validates RS256 JWTs from an enterprise IdP (Entra ID is the reference, but any OIDC
issuer works via config), enforces issuer/audience/expiry, and maps the token's roles
claim onto StepStitch's admin gate. Because ``require_admin`` returns the real identity
(``email``/``sub``), every audited operator action records the actual person — not a
shared ``"admin"`` — which is what Reg S-P recordkeeping needs.

Split model (matches reality): **operators authenticate with OIDC SSO**; the **SDK/clients
ingest traces with a machine token** (browsers don't carry per-user operator JWTs). So
``require_admin`` is OIDC; ``get_user_id`` (ingest) stays a shared bearer token.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

import jwt
from fastapi import Header, HTTPException
from jwt import InvalidTokenError
from jwt.algorithms import RSAAlgorithm


def _bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization[len("bearer "):].strip() or None


def _load_keys(jwks: Mapping[str, Any]) -> Dict[str, Any]:
    """Map ``kid`` -> public key from a JWKS document (RSA keys only)."""
    keys: Dict[str, Any] = {}
    for jwk in jwks.get("keys", []):
        if jwk.get("kty") != "RSA":
            continue
        kid = jwk.get("kid")
        if kid:
            keys[kid] = RSAAlgorithm.from_jwk(json.dumps(jwk))
    return keys


class OidcVerifier:
    """Validates RS256 JWTs against a static JWKS and extracts identity + roles.

    Network-free by design (takes the JWKS document, not a URL) so it is fully unit
    testable; ``oidc_auth_from_env`` does the one-time JWKS fetch for deployment.
    """

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks: Mapping[str, Any],
        algorithms: Iterable[str] = ("RS256",),
        leeway: int = 30,
        roles_claim: str = "roles",
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._keys = _load_keys(jwks)
        self._algorithms = list(algorithms)
        self._leeway = leeway
        self._roles_claim = roles_claim

    def verify(self, token: str) -> Dict[str, Any]:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
            key = self._keys.get(kid) if kid else None
            if key is None:
                raise InvalidTokenError("unknown signing key")
            return jwt.decode(
                token,
                key,
                algorithms=self._algorithms,
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iss", "aud"]},
            )
        except InvalidTokenError as exc:
            raise HTTPException(status_code=401, detail="invalid or expired token") from exc

    def identity(self, claims: Mapping[str, Any]) -> str:
        # Prefer a human-readable, stable identifier for the audit actor.
        return str(
            claims.get("email")
            or claims.get("preferred_username")
            or claims.get("sub")
            or "unknown"
        )

    def roles(self, claims: Mapping[str, Any]) -> List[str]:
        raw = claims.get(self._roles_claim) or []
        return [raw] if isinstance(raw, str) else list(raw)


def require_roles(
    verifier: OidcVerifier, roles: Iterable[str]
) -> Callable[..., Dict[str, Any]]:
    """A FastAPI dependency that verifies the JWT and requires one of ``roles``.

    Returns the rich actor dict ``{user_id, sub, email, roles}`` so the router's
    ``_actor_id`` records the real operator on every audited action.
    """
    allowed = {r for r in roles if r}
    if not allowed:
        raise ValueError("roles must be non-empty")

    def dependency(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        token = _bearer(authorization)
        if not token:
            raise HTTPException(status_code=401, detail="bearer token required")
        claims = verifier.verify(token)
        granted = verifier.roles(claims)
        if not (allowed & set(granted)):
            raise HTTPException(status_code=403, detail="insufficient role")
        return {
            "user_id": verifier.identity(claims),
            "sub": claims.get("sub"),
            "email": claims.get("email"),
            "roles": granted,
        }

    return dependency


def build_oidc_auth(
    verifier: OidcVerifier,
    *,
    admin_roles: Iterable[str],
    ingest_token: str,
) -> Tuple[Callable[..., Any], Callable[..., Any]]:
    """Return ``(get_user_id, require_admin)`` — OIDC operators, machine-token ingest.

    ``require_admin`` gates the operator/read surface on ``admin_roles``. For least-privilege
    on destructive ops, build a narrower ``require_roles(verifier, admin_only)`` and inject it
    as the router's ``require_destructive`` (``oidc_auth_from_env`` does this).
    """
    if not ingest_token:
        raise ValueError("ingest_token must be set (machine auth for trace ingestion)")
    require_admin = require_roles(verifier, admin_roles)

    def get_user_id(authorization: Optional[str] = Header(default=None)) -> str:
        if _bearer(authorization) != ingest_token:
            raise HTTPException(status_code=401, detail="ingest bearer token required")
        return "ingest-client"

    return get_user_id, require_admin


def _fetch_json(url: str) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 (https IdP URL)
        return json.loads(resp.read().decode("utf-8"))


def _roles_env(name: str, default: str) -> List[str]:
    return [r.strip() for r in os.environ.get(name, default).split(",") if r.strip()]


def oidc_auth_from_env(
    ingest_token: str,
) -> Tuple[Callable[..., Any], Callable[..., Any], Callable[..., Any]]:
    """Build OIDC auth from environment (deployment wiring; does the one-time JWKS fetch).

    Returns ``(get_user_id, require_admin, require_destructive)`` — least-privilege RBAC:
    operators read; only admins deliver/delete/purge.

    Env: ``STEPSTITCH_OIDC_ISSUER`` (required), ``STEPSTITCH_OIDC_AUDIENCE`` (required),
    ``STEPSTITCH_OIDC_JWKS_URI`` (optional; else discovered from the issuer),
    ``STEPSTITCH_OIDC_OPERATOR_ROLES`` (read surface; default ``stepstitch-operator``),
    ``STEPSTITCH_OIDC_ADMIN_ROLES`` (destructive ops; default ``stepstitch-admin``),
    ``STEPSTITCH_OIDC_ROLES_CLAIM`` (default ``roles``).
    """
    issuer = os.environ["STEPSTITCH_OIDC_ISSUER"]
    audience = os.environ["STEPSTITCH_OIDC_AUDIENCE"]
    jwks_uri = os.environ.get("STEPSTITCH_OIDC_JWKS_URI")
    if not jwks_uri:
        disco = _fetch_json(issuer.rstrip("/") + "/.well-known/openid-configuration")
        jwks_uri = disco["jwks_uri"]
    operator_roles = _roles_env("STEPSTITCH_OIDC_OPERATOR_ROLES", "stepstitch-operator")
    admin_roles = _roles_env("STEPSTITCH_OIDC_ADMIN_ROLES", "stepstitch-admin")
    verifier = OidcVerifier(
        issuer=issuer,
        audience=audience,
        jwks=_fetch_json(jwks_uri),
        roles_claim=os.environ.get("STEPSTITCH_OIDC_ROLES_CLAIM", "roles"),
    )
    # Admins can also read, so the read gate accepts both role sets; destructive ops
    # require an admin role only.
    get_user_id, require_admin = build_oidc_auth(
        verifier, admin_roles=set(operator_roles) | set(admin_roles), ingest_token=ingest_token
    )
    require_destructive = require_roles(verifier, admin_roles)
    return get_user_id, require_admin, require_destructive
