"""Demo shared-bearer auth for the StepStitch ingest host.

This is the *host's* auth, injected into ``create_stepstitch_router`` — StepStitch core
holds no auth itself. This implementation is deliberately simple (two shared bearer
tokens) so a demo deploys today; swap ``build_auth`` for a real JWT/OIDC verifier for
production without touching StepStitch.

- ``require_admin`` gates operator reads (every read is audited server-side).
- ``get_user_id`` gates writes (trace ingestion); the admin token may also write.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

from fastapi import Header, HTTPException


def _bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization[len("bearer "):].strip() or None


def build_auth(
    admin_token: str, ingest_token: str
) -> Tuple[Callable[..., Any], Callable[..., Any]]:
    """Return ``(get_user_id, require_admin)`` FastAPI dependencies.

    Raises at build time if a token is empty — a deployment must set both, otherwise the
    surface would be unauthenticated.
    """
    if not admin_token or not ingest_token:
        raise ValueError(
            "STEPSTITCH_ADMIN_TOKEN and STEPSTITCH_INGEST_TOKEN must both be set"
        )

    write_tokens = {ingest_token, admin_token}

    def require_admin(authorization: Optional[str] = Header(default=None)) -> Dict[str, str]:
        if _bearer(authorization) != admin_token:
            raise HTTPException(status_code=401, detail="admin bearer token required")
        return {"user_id": "admin"}

    def get_user_id(authorization: Optional[str] = Header(default=None)) -> str:
        if _bearer(authorization) not in write_tokens:
            raise HTTPException(status_code=401, detail="ingest bearer token required")
        return "ingest-client"

    return get_user_id, require_admin
