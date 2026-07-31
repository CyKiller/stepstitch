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
from pathlib import Path
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
_VERDICT_HEADLINES = {
    "reproduced": "Reproduced",
    "not_reproduced": "Could not reproduce",
    "needs_setup": "Needs setup",
    "inconclusive": "Inconclusive",
}


def _reproduce_command(args: Any) -> int:
    """Fetch a session's reproduction, run it, and print what StepStitch observed.

    Exit codes are for scripting, not for judgement: 0 when a verdict was reached
    (reproduced or not), 1 when the run could not answer the question (needs setup,
    inconclusive, refused). "Reproduced" is not a failure of this command.
    """
    # Imported here so `doctor` stays stdlib-only and importable in a broken environment.
    from stepstitch_service.diagnostics import EnvelopeMismatch
    from stepstitch_service.runner import RunnerError, run_reproduction, script_digest

    base = args.host.rstrip("/")
    admin = os.environ.get("STEPSTITCH_ADMIN_TOKEN")
    headers = {"Authorization": f"Bearer {admin}"} if admin else {}

    status, payload = _http(f"{base}/api/stepstitch/v1/session/{args.session}/playwright",
                            "GET", headers, None)
    if status != 200 or not isinstance(payload, dict):
        print(f"Could not fetch the reproduction for {args.session}: "
              f"{base} responded {status or 'nothing'}.\n"
              "Is the host running, and is STEPSTITCH_ADMIN_TOKEN set? "
              "Run `stepstitch doctor`.")
        return 1
    script = payload.get("playwright_code") or ""

    # Readiness comes from the host, which owns the project's reproduction settings.
    ready_status, ready_payload = _http(f"{base}/admin/config/repro", "GET", headers, None)
    readiness: List[Dict[str, Any]] = []
    if ready_status == 200 and isinstance(ready_payload, dict):
        readiness = ready_payload.get("readiness") or []

    app_url = args.app_url or os.environ.get("STEPSTITCH_APP_BASE_URL")
    if not app_url:
        print("No application address. Pass --app-url or set STEPSTITCH_APP_BASE_URL — "
              "a reproduction has to run against something.")
        return 1

    try:
        result = run_reproduction(
            session_id=args.session, script=script, base_url=app_url,
            readiness=readiness, runs=args.runs, timeout_seconds=args.timeout,
        )
    except (RunnerError, EnvelopeMismatch) as exc:
        # Both are refusals. EnvelopeMismatch cannot subclass RunnerError — diagnostics.py
        # is deliberately runner-free — so it has to be named alongside it everywhere a
        # refusal is caught, or it escapes as a crash instead of an answer.
        print(f"Refused: {exc}")
        return 1

    if args.as_json:
        print(json.dumps(result.as_dict(), indent=2))
    else:
        print(f"\n{_VERDICT_HEADLINES.get(result.verdict, result.verdict)} — "
              f"{result.detail}")
        if result.blockers:
            print("\nWhat is missing:")
            for blocker in result.blockers:
                print(f"  - {blocker.get('title')}: {blocker.get('detail')}")
        print(f"\nfrozen script sha256: {script_digest(script)[:16]}…")
    return 0 if result.verdict in ("reproduced", "not_reproduced") else 1


def _connect_command(args: Any) -> int:
    """Wire an installed coding agent to this StepStitch, with least privilege.

    Registration goes through the agent's OWN ``mcp add`` command, which knows its config
    format and preserves anything already configured — hand-writing another vendor's TOML
    is how you clobber somebody's unrelated MCP server.
    """
    from stepstitch_service.connect import (
        AGENT_SCOPE,
        CODEX_APPROVAL_LINE,
        apply,
        detect,
        ensure_codex_tool_approval,
        list_command,
        plan,
        render_plan,
        resolve,
        token_path,
        verify,
        write_token,
    )

    host = args.host.rstrip("/")
    platforms = detect(args.agent)
    if not platforms:
        wanted = args.agent or "claude, codex or gemini"
        print(f"No supported coding agent found ({wanted}).\n"
              "Looked on PATH and in the usual desktop-app bundles.\n"
              "Install one, or see docs/connect-an-agent.md to configure it by hand.")
        return 1

    base_url = f"{host}/api/stepstitch/v1"
    if args.dry_run:
        print("\nWould connect:\n")
        for platform in platforms:
            print(render_plan(plan(platform, base_url, token_path("<agent-id>"))))
        return 0

    # The admin token is needed to REGISTER an agent. `stepstitch start` already owns it,
    # which is why `start --connect` is the smoother path — nobody has to paste anything.
    admin = os.environ.get("STEPSTITCH_ADMIN_TOKEN")
    if not admin:
        print("STEPSTITCH_ADMIN_TOKEN is not set, so a scoped agent token cannot be "
              "issued.\nEasiest path: `stepstitch start --connect "
              f"{args.agent or 'claude'}` — that process already holds the credential.")
        return 1

    status, payload = _http(f"{host}/admin/agents", "POST",
                            {"Authorization": f"Bearer {admin}",
                             "Content-Type": "application/json"},
                            json.dumps({"name": f"{platforms[0].key}-local",
                                        "scope": AGENT_SCOPE}).encode())
    if status != 200 or not isinstance(payload, dict) or not payload.get("token"):
        print(f"Could not register an agent with {host} (HTTP {status or 'no response'}). "
              "Is `stepstitch start` running?")
        return 1

    # Shown once by the host, then ours to store safely. It never touches a config file.
    # The register endpoint returns the agent under "id" (see host.post /admin/agents).
    # Naming the file after it is what makes revocation obvious later — every agent gets
    # its own file rather than all of them sharing one.
    token_file = write_token(str(payload.get("id") or payload.get("agent_id") or "agent"),
                             payload["token"])

    failures = 0
    for platform in platforms:
        # Resolve once and reuse: registering with the bundled CLI and then checking a
        # PATH name that does not exist would report a working connection as broken.
        exe = resolve(platform) or platform.executable
        result = apply(platform, base_url, token_file, exe=exe)
        if not result["ok"]:
            print(f"  could not connect {platform.label}: {result['detail']}")
            failures += 1
            continue
        # Registered is not the same as working. The vendor command can write a perfect
        # config that launches an engine which cannot start — which is exactly what
        # happens when the pinned version predates `stepstitch mcp`.
        if verify(list_command(platform, exe)):
            print(f"  {platform.label}: connected ({result['config']})")
            # Codex denies every MCP call in `codex exec` unless its own table says
            # otherwise — and reports the server as enabled the whole time. Without this
            # the connection works interactively and silently refuses in automation.
            if platform.key == "codex":
                outcome = ensure_codex_tool_approval(
                    Path(os.path.expanduser("~/.codex/config.toml")))
                if outcome == "added":
                    print("    non-interactive use enabled "
                          "(default_tools_approval_mode). Scope still limits the agent.")
                elif outcome.startswith("skipped"):
                    print(f"    note: could not enable non-interactive tool calls "
                          f"({outcome}). `codex exec` will refuse them; add\n"
                          f"    `{CODEX_APPROVAL_LINE}` under [mcp_servers.stepstitch].")
        else:
            failures += 1
            print(f"  {platform.label}: registered in {result['config']}, but it does "
                  f"not start.\n"
                  f"    Check with `{exe} mcp list`. The usual cause is an engine\n"
                  f"    without the `stepstitch mcp` entry point — it needs a version "
                  f"that ships it.")

    if failures:
        return 1
    print(f"\nScope: {AGENT_SCOPE} — the agent can read the failure and the "
          "reproduction,\nand cannot record the verdict on its own fix.")
    print(f"Token: {token_file} (owner-only; delete it or revoke in the dashboard)")
    return 0


def _mcp_command(args: Any) -> int:
    """Serve the MCP tools over stdio.

    A public entry point on purpose: the portable launch command becomes
    ``uvx --from 'stepstitch-service[mcp]==X' stepstitch mcp`` rather than an incantation
    naming an internal module, which is both nicer to read in an agent's config file and
    something we can keep working across refactors.
    """
    import asyncio

    from stepstitch_service.mcp_cli import _build_http_call_route, read_token
    from stepstitch_service.mcp_server import serve_stdio

    base_url = args.base_url or os.environ.get("STEPSTITCH_BASE_URL")
    if not base_url:
        print("STEPSTITCH_BASE_URL is required (the service mount, including "
              "/api/stepstitch/v1). Run `stepstitch connect <agent>` to write a config "
              "that sets it.", file=sys.stderr)
        return 2
    asyncio.run(serve_stdio(_build_http_call_route(base_url, read_token())))
    return 0


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


def _browsers_check() -> Check:
    """Is the browser a reproduction would actually launch present on this machine?

    A separate function so tests can stub it: the probe shells out, and a doctor test that
    reaches the real filesystem answers differently on every machine.

    WARN, never FAIL — the same reasoning as its siblings above. Capture, scrubbing and
    evidence all work with no browser installed; only local execution does not.
    """
    from .runner import _browser_identity

    identity = _browser_identity(headless=True)
    if identity.present is True:
        return Check("playwright browsers", PASS, identity.build, "")
    if identity.present is False:
        return Check(
            "playwright browsers", WARN,
            f"{identity.build} is not installed",
            "Reproductions cannot run until it is: npx playwright install chromium",
        )
    # None — the probe could not answer. Not the same as absent, and not worth a warning
    # that would fire on every unusual but working layout (pnpm, Yarn PnP).
    return Check("playwright browsers", PASS, "could not be determined", "")


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
        # A separate check, because the package and the browser fail separately and the
        # package answering says nothing about the browser. `playwright --version` above
        # passes with every browser deleted — which is exactly how a machine that cannot
        # run anything used to look healthy here.
        if playwright:
            checks.append(_browsers_check())

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

    reproduce = sub.add_parser(
        "reproduce",
        help="run a session's reproduction locally and report what happened",
        description="Fetch the compiled reproduction for a session, run it against your "
                    "application, and report one of: reproduced, needs setup, could not "
                    "reproduce, inconclusive. StepStitch derives the verdict from what it "
                    "observed — it is never asserted by the caller.",
    )
    reproduce.add_argument("session", help="trace id to reproduce")
    reproduce.add_argument("--host", default=os.environ.get("STEPSTITCH_HOST", DEFAULT_HOST),
                           help=f"StepStitch host base URL (default {DEFAULT_HOST})")
    reproduce.add_argument("--runs", type=int, default=1,
                           help="run it N times to detect flakiness (capped at 10)")
    reproduce.add_argument("--timeout", type=int, default=120,
                           help="seconds per run (capped at 600)")
    reproduce.add_argument("--app-url", default=None,
                           help="the application to run against "
                                "(default: STEPSTITCH_APP_BASE_URL)")
    reproduce.add_argument("--json", action="store_true", dest="as_json",
                           help="emit machine-readable results")

    connect = sub.add_parser(
        "connect",
        help="connect a coding agent (claude, codex, gemini) to a running StepStitch",
        description="Register StepStitch's MCP tools with an installed coding agent, "
                    "using that agent's own `mcp add` command. Issues a least-privilege "
                    "token stored outside the agent's config, and checks the connection.",
    )
    connect.add_argument("agent", nargs="?", default=None,
                         choices=["claude", "codex", "gemini"],
                         help="which agent (default: every one that is installed)")
    connect.add_argument("--host", default=os.environ.get("STEPSTITCH_HOST", DEFAULT_HOST),
                         help=f"the running StepStitch host (default {DEFAULT_HOST})")
    connect.add_argument("--dry-run", action="store_true", dest="dry_run",
                         help="print exactly what would be done, and do nothing")

    mcp = sub.add_parser(
        "mcp",
        help="serve the StepStitch MCP tools over stdio (an agent client launches this)",
        description="Speak MCP over stdio so any agent client can use StepStitch's "
                    "read-only/draft tools. Started by the agent, not by you — "
                    "`stepstitch connect <agent>` writes the config that runs it.",
    )
    mcp.add_argument("--base-url", default=None,
                     help="service mount incl. prefix (default: STEPSTITCH_BASE_URL)")

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
    if args.command == "connect":
        return _connect_command(args)
    if args.command == "mcp":
        return _mcp_command(args)
    if args.command == "reproduce":
        return _reproduce_command(args)
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
