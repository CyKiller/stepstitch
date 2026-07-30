"""``stepstitch`` — the command line entry point. Today it has one job: ``doctor``.

Before this existed, a misconfigured install failed as a raw traceback several steps into a
quickstart: a missing ``pip install -e ./service`` surfaced as ``ModuleNotFoundError``, a
wrong token as an opaque 401 from a curl in step 6. ``doctor`` asks every question the
quickstart depends on, in order, and answers each with a fix.

**It never prints a secret.** Values are reported as a shape — set / not set, length, and a
short digest — so the output can be pasted into an issue or a support thread safely. That is
a tested property (``test_doctor.py``), not a convention.

Standard library only (``argparse`` + ``urllib``): doctor has to work in a minimal
environment, which is exactly the environment where things are broken.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

__all__ = ["main", "run_doctor", "Check", "mask"]

PASS = "pass"
WARN = "warn"
FAIL = "fail"

_MARK = {PASS: "PASS", WARN: "WARN", FAIL: "FAIL"}

DEFAULT_HOST = "http://localhost:8000"
_API = "/api/stepstitch/v1"


class Check:
    """One diagnostic result. ``fix`` is what the operator should actually do."""

    def __init__(self, name: str, status: str, detail: str, fix: str = "") -> None:
        self.name = name
        self.status = status
        self.detail = detail
        self.fix = fix

    def as_dict(self) -> Dict[str, str]:
        return {"name": self.name, "status": self.status,
                "detail": self.detail, "fix": self.fix}


def mask(value: Optional[str]) -> str:
    """Describe a secret without disclosing it.

    Length and a truncated digest are enough to tell "the token I set" from "a different
    token" across two machines, and disclose neither.
    """
    if not value:
        return "not set"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"set ({len(value)} chars, sha256:{digest}…)"


# --- transport ------------------------------------------------------------------------------
Transport = Callable[[str, str, Dict[str, str], Optional[bytes]], Tuple[int, Any]]


def _http(url: str, method: str, headers: Dict[str, str],
          body: Optional[bytes] = None, timeout: float = 5.0) -> Tuple[int, Any]:
    """Return ``(status, parsed_body_or_text)``. An HTTP error status is a result, not an
    exception — doctor reports 401 as a finding rather than a stack trace."""
    request = urllib.request.Request(url, method=method, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read().decode("utf-8", "replace")
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        status = exc.code
    except Exception as exc:  # DNS failure, connection refused, timeout…
        return 0, str(exc)
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


# --- the checks -------------------------------------------------------------------------------
def _tool_version(argv: List[str]) -> Optional[str]:
    """First line of ``argv --version``, or None if the tool is absent or unhappy.

    Fixed argv (never a shell string), short timeout, output truncated: doctor asks a
    question about the machine, it does not run the machine's code.
    """
    import subprocess

    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    line = (proc.stdout or proc.stderr or "").strip().splitlines()
    return line[0][:60] if line else None


def run_doctor(
    *,
    host: str = DEFAULT_HOST,
    env: Optional[Dict[str, str]] = None,
    transport: Optional[Transport] = None,
) -> List[Check]:
    """Run every diagnostic and return the results in the order they were checked.

    Ordering is deliberate: a later check's failure is usually meaningless if an earlier one
    failed, so the first FAIL in the list is the one to fix.
    """
    env = dict(os.environ if env is None else env)
    send: Transport = transport or (lambda u, m, h, b: _http(u, m, h, b))
    base = host.rstrip("/")
    checks: List[Check] = []

    admin = env.get("STEPSTITCH_ADMIN_TOKEN")
    ingest = env.get("STEPSTITCH_INGEST_TOKEN")
    issuer = env.get("STEPSTITCH_OIDC_ISSUER")
    database = env.get("DATABASE_URL")
    app_base = env.get("STEPSTITCH_APP_BASE_URL")
    # StepStitch Local generates its own credentials and stores everything in a SQLite
    # file, so the deployment variables below are not findings there — reporting three
    # FAILs to a developer who ran `stepstitch start` would be telling them to fix
    # something that is working.
    local = (env.get("STEPSTITCH_MODE") or "").strip().lower() == "local"

    # 1. Environment ---------------------------------------------------------------------
    if local:
        checks.append(Check(
            "mode", PASS,
            "local — SQLite store, generated credentials, loopback only", "",
        ))
        checks.append(Check(
            "local store", PASS,
            database or "sqlite:///.stepstitch/local.db (default)", "",
        ))
    else:
        checks.append(Check(
            "DATABASE_URL",
            PASS if database else FAIL,
            mask(database),
            "" if database else "Set DATABASE_URL to your Postgres DSN "
                                "(docker compose sets this for you), or run "
                                "`stepstitch start` for a local store.",
        ))
        checks.append(Check(
            "STEPSTITCH_INGEST_TOKEN",
            PASS if ingest else FAIL,
            mask(ingest),
            "" if ingest else "Set an ingest token; the SDK uses it to POST traces.",
        ))
        if issuer:
            checks.append(Check("operator auth", PASS,
                                f"OIDC SSO via {issuer}",
                                ""))
        else:
            checks.append(Check(
                "STEPSTITCH_ADMIN_TOKEN",
                PASS if admin else FAIL,
                mask(admin),
                "" if admin else "Set an admin token, or enable SSO with "
                                 "STEPSTITCH_OIDC_ISSUER.",
            ))
    checks.append(Check(
        "STEPSTITCH_APP_BASE_URL",
        PASS if app_base else WARN,
        app_base or "not set — reproductions will target http://localhost:3000",
        "" if app_base else "Set it to your app under test, or store a per-project "
                            "base_url with PUT /admin/config/repro. Without one, a "
                            "generated reproduction cannot run in CI.",
    ))

    # 1b. Can this machine RUN a reproduction? ---------------------------------------------
    # The compiler is Python but the reproduction it emits is a Playwright test executed by
    # Node. Both are WARN, never FAIL: capture, scrubbing and evidence all work without
    # them — only local execution does not.
    node = _tool_version(["node", "--version"])
    checks.append(Check(
        "node",
        PASS if node else WARN,
        node or "not found",
        "" if node else "Install Node 18+ to run a generated reproduction locally. "
                        "Capture and evidence work without it.",
    ))
    if node:
        playwright = _tool_version(["npx", "--no-install", "playwright", "--version"])
        checks.append(Check(
            "playwright",
            PASS if playwright else WARN,
            playwright or "not installed in this project",
            "" if playwright else "Install it where reproductions run: "
                                  "npm i -D @playwright/test && npx playwright install",
        ))

    # 2. Host reachable -------------------------------------------------------------------
    status, body = send(f"{base}/healthz", "GET", {}, None)
    host_up = status == 200
    checks.append(Check(
        "host reachable",
        PASS if host_up else FAIL,
        f"GET {base}/healthz -> {status or 'no response'}"
        + ("" if host_up else f" ({body})"),
        "" if host_up else f"Is the host running and listening on {base}? "
                           "Try: docker compose up --build",
    ))
    if not host_up:
        # Everything below talks to the host; reporting six more failures adds noise.
        checks.append(Check("remaining checks", WARN,
                            "skipped — the host is not reachable", ""))
        return checks

    # 3. Dashboard -------------------------------------------------------------------------
    status, body = send(f"{base}/dashboard", "GET", {}, None)
    served = status == 200 and isinstance(body, str) and "StepStitch" in body
    checks.append(Check(
        "dashboard served",
        PASS if served else FAIL,
        f"GET {base}/dashboard -> {status}",
        "" if served else "The console did not render. Check the host logs.",
    ))

    # 4. Ingest auth — deliberately an INVALID payload: a 422 proves the token was accepted
    #    without writing anything. Doctor must never leave a trace behind.
    if ingest:
        status, body = send(
            f"{base}{_API}/session", "POST",
            {"Authorization": f"Bearer {ingest}", "Content-Type": "application/json"},
            b"{}",
        )
        ok = status == 422
        checks.append(Check(
            "ingest authentication",
            PASS if ok else FAIL,
            f"POST {_API}/session (intentionally empty) -> {status}"
            + (" (accepted; nothing stored)" if ok else ""),
            "" if ok else ("The ingest token was rejected. Does STEPSTITCH_INGEST_TOKEN "
                           "match the host's?" if status in (401, 403)
                           else "Unexpected response; check the host logs."),
        ))

    # 5. Admin auth + database. /admin/status counts rows, so a 200 proves both.
    admin_headers = {"Authorization": f"Bearer {admin}"} if admin else {}
    status, body = send(f"{base}/admin/status", "GET", admin_headers, None)
    admin_ok = status == 200 and isinstance(body, dict)
    if local and not admin and not admin_ok:
        # `stepstitch start` generates the admin token and prints it once; a doctor run in
        # a second terminal legitimately does not have it. That is not a misconfiguration,
        # so it must not read as one.
        checks.append(Check(
            "admin authentication", WARN,
            "not checked — this local host generated its own admin token",
            "Open the dashboard link `stepstitch start` printed (it carries the token), "
            "or re-run with STEPSTITCH_ADMIN_TOKEN set to check the admin surface.",
        ))
    else:
        checks.append(Check(
            "admin authentication",
            PASS if admin_ok else FAIL,
            f"GET /admin/status -> {status}",
            "" if admin_ok else ("The admin token was rejected. Does STEPSTITCH_ADMIN_TOKEN "
                                 "match the host's?" if status in (401, 403)
                                 else "Unexpected response; check the host logs."),
        ))
    if admin_ok and isinstance(body, dict):
        checks.append(Check(
            "database reachable",
            PASS,
            f"{body.get('traces', 0)} trace(s), {body.get('audit_events', 0)} audit event(s)",
            "",
        ))
        # 6. Capture / scrub posture
        checks.append(Check(
            "capture configuration",
            PASS,
            f"profile '{body.get('profile')}', retention {body.get('retention_days')}d",
            "",
        ))
        # 7. Reproduction readiness
        ready = bool(body.get("base_url_configured"))
        checks.append(Check(
            "reproduction base URL",
            PASS if ready else WARN,
            "configured" if ready else "not configured (repros target localhost:3000)",
            "" if ready else "Set STEPSTITCH_APP_BASE_URL or PUT /admin/config/repro.",
        ))
        # 8. Is the CI loop closed?
        verifications = int(body.get("verifications") or 0)
        checks.append(Check(
            "CI verification endpoint",
            PASS if verifications else WARN,
            f"{verifications} verdict(s) recorded" if verifications
            else "no CI verdict has ever been recorded",
            "" if verifications else "Wire the repro workflow and issue a 'verify'-scoped "
                                     "agent token (console -> Agents). Until CI reports a "
                                     "measured red/green, Fix Memory stays empty.",
        ))

    if admin:
        status, body = send(f"{base}/admin/config/scrub", "GET", admin_headers, None)
        checks.append(Check(
            "scrub policy readable",
            PASS if status == 200 else FAIL,
            f"GET /admin/config/scrub -> {status}",
            "" if status == 200 else "The scrub policy could not be read.",
        ))
        status, body = send(f"{base}/admin/config/repro", "GET", admin_headers, None)
        if status == 200 and isinstance(body, dict):
            not_ready = [i for i in body.get("readiness", []) if not i.get("ready")]
            checks.append(Check(
                "reproduction config",
                PASS if not not_ready else WARN,
                "all settings ready" if not not_ready
                else "; ".join(f"{i['title']}: {i['detail']}" for i in not_ready),
                "" if not not_ready else "PUT /admin/config/repro to fill these in.",
            ))
        else:
            checks.append(Check("reproduction config", FAIL,
                                f"GET /admin/config/repro -> {status}",
                                "The host may predate project reproduction config."))

    return checks


def _render(checks: List[Check]) -> str:
    lines = ["StepStitch doctor", ""]
    width = max((len(c.name) for c in checks), default=0)
    for check in checks:
        lines.append(f"  {_MARK[check.status]}  {check.name.ljust(width)}  {check.detail}")
        if check.fix and check.status != PASS:
            lines.append(f"        {' ' * width}  -> {check.fix}")
    failed = [c for c in checks if c.status == FAIL]
    warned = [c for c in checks if c.status == WARN]
    lines.append("")
    if failed:
        lines.append(f"{len(failed)} problem(s) to fix"
                     + (f", {len(warned)} warning(s)" if warned else "") + ".")
    elif warned:
        lines.append(f"No problems. {len(warned)} warning(s) — StepStitch will run, "
                     "but some of the loop is not wired yet.")
    else:
        lines.append("Everything checks out.")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stepstitch",
        description="StepStitch command line tools.",
    )
    sub = parser.add_subparsers(dest="command")
    doctor = sub.add_parser(
        "doctor",
        help="check that this StepStitch install is wired correctly",
        description="Check the environment, host, database, auth and reproduction config. "
                    "Never prints a secret value.",
    )
    doctor.add_argument("--host", default=os.environ.get("STEPSTITCH_HOST", DEFAULT_HOST),
                        help=f"StepStitch host base URL (default {DEFAULT_HOST})")
    doctor.add_argument("--json", action="store_true", dest="as_json",
                        help="emit machine-readable results")

    start = sub.add_parser(
        "start",
        help="run StepStitch Local: dashboard + SQLite store on 127.0.0.1, no setup",
        description="StepStitch Local. Generates credentials, stores everything in a "
                    "local SQLite file, binds to loopback only, and opens the dashboard. "
                    "No account, no Postgres, no Docker.",
    )
    start.add_argument("--port", type=int, default=None,
                       help="dashboard/API port (default 8321)")
    start.add_argument("--db", default=None,
                       help="path for the local store (default .stepstitch/local.db)")
    start.add_argument("--no-browser", action="store_true",
                       help="do not open the dashboard in a browser")

    args = parser.parse_args(argv)
    if args.command == "start":
        # Imported here, not at module top: doctor must stay importable in a broken or
        # minimal environment (stdlib only); start is where fastapi/uvicorn come in.
        try:
            from stepstitch_service.host.local import DEFAULT_LOCAL_PORT, run_local
        except ImportError as exc:
            print(f"stepstitch start needs the service host installed ({exc}).\n"
                  "  pip install 'stepstitch-service[local]'")
            return 2
        return run_local(
            port=args.port or DEFAULT_LOCAL_PORT,
            db=args.db,
            open_browser=not args.no_browser,
        )
    if args.command != "doctor":
        parser.print_help()
        return 2

    checks = run_doctor(host=args.host)
    if args.as_json:
        print(json.dumps({"checks": [c.as_dict() for c in checks]}, indent=2))
    else:
        print(_render(checks))
    return 1 if any(c.status == FAIL for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
