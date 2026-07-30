"""Startup environment validation for the ingest host.

Lives in its own module because ``server/app.py`` builds the application at import time
(``app = create_app_from_env()``), so it cannot be imported without a full environment —
including by a test of this very function.
"""
from __future__ import annotations

from typing import Dict


def require_env(env: Dict[str, str]) -> None:
    """Raise ``SystemExit`` naming every misconfiguration, or return quietly.

    A raw ``KeyError: 'DATABASE_URL'`` from a container that exits immediately is a bad first
    impression and a slow one: you fix one variable, redeploy, and discover the next. Collect
    them all, name the fix, and point at the tool that checks the rest.

    Two modes (``STEPSTITCH_MODE``, default ``production``):

    - ``production`` — the checks below, unchanged: Postgres DSN + tokens are mandatory.
    - ``local`` — StepStitch Local (single developer, ``stepstitch start``): storage is a
      ``sqlite:///`` path (or unset, for the default local file) and tokens may be absent
      because the local entrypoint generates them. A Postgres DSN in local mode is refused
      rather than half-honored: the operator clearly wanted the production path.
    """
    problems = []
    mode = (env.get("STEPSTITCH_MODE") or "production").strip().lower()

    if mode == "local":
        dsn = env.get("DATABASE_URL")
        if dsn and not dsn.startswith("sqlite:///"):
            scheme = dsn.split("://", 1)[0][:20] if "://" in dsn else "(no scheme)"
            raise SystemExit(
                "StepStitch host cannot start:\n"
                f"  - STEPSTITCH_MODE=local uses a sqlite:/// DATABASE_URL (found "
                f"'{scheme}://'). Unset DATABASE_URL for the default local file, or unset "
                "STEPSTITCH_MODE to run the production Postgres path.\n"
            )
        return

    dsn = env.get("DATABASE_URL")
    if not dsn:
        problems.append("DATABASE_URL is not set — the Postgres DSN "
                        "(e.g. postgres://user:pass@host:5432/stepstitch)")
    elif not dsn.startswith(("postgres://", "postgresql://")):
        # Report the scheme only; the rest of a DSN carries a password.
        scheme = dsn.split("://", 1)[0][:20] if "://" in dsn else "(no scheme)"
        problems.append(f"DATABASE_URL is not a Postgres DSN (found '{scheme}://') — "
                        "it must start with postgres:// or postgresql://")

    if not env.get("STEPSTITCH_INGEST_TOKEN"):
        problems.append("STEPSTITCH_INGEST_TOKEN is not set — the bearer the SDK uses to "
                        "POST traces (e.g. openssl rand -hex 24)")

    if not env.get("STEPSTITCH_OIDC_ISSUER") and not env.get("STEPSTITCH_ADMIN_TOKEN"):
        problems.append("STEPSTITCH_ADMIN_TOKEN is not set — the operator bearer. "
                        "(Or enable SSO by setting STEPSTITCH_OIDC_ISSUER instead.)")

    if problems:
        raise SystemExit(
            "StepStitch host cannot start:\n"
            + "".join(f"  - {p}\n" for p in problems)
            + "\nSee docs/DEPLOY.md, or run `stepstitch doctor` once the host is up."
        )
