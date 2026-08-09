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


def connect_agent(host: str, admin: str, agent: Optional[str] = None) -> int:
    """Register a coding agent against a running host, with least privilege.

    The core of ``stepstitch connect``, separated from how the admin credential arrives so
    ``stepstitch start --connect`` can call it with the token it already holds — the whole
    point of that flag is that nobody has to paste anything.

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
        resolve,
        verify,
        write_token,
    )

    host = host.rstrip("/")
    platforms = detect(agent)
    if not platforms:
        wanted = agent or "claude, codex or gemini"
        print(f"No supported coding agent found ({wanted}).\n"
              "Looked on PATH and in the usual desktop-app bundles.\n"
              "Install one, or see docs/connect-an-agent.md to configure it by hand.")
        return 1

    base_url = f"{host}/api/stepstitch/v1"
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


def _connect_command(args: Any) -> int:
    """``stepstitch connect`` — the standalone form, for a host already running."""
    from stepstitch_service.connect import detect, plan, render_plan, token_path

    host = args.host.rstrip("/")
    if args.dry_run:
        platforms = detect(args.agent)
        if not platforms:
            print(f"No supported coding agent found ({args.agent or 'claude, codex or gemini'}).")
            return 1
        print("\nWould connect:\n")
        for platform in platforms:
            print(render_plan(plan(platform, f"{host}/api/stepstitch/v1",
                                   token_path("<agent-id>"))))
        return 0

    # The admin token is needed to REGISTER an agent. `stepstitch start` already owns it,
    # which is why `start --connect` needs no pasting — same process, same credential.
    admin = os.environ.get("STEPSTITCH_ADMIN_TOKEN")
    if not admin:
        print("STEPSTITCH_ADMIN_TOKEN is not set, so a scoped agent token cannot be "
              "issued.\nEasiest path: `stepstitch start --connect "
              f"{args.agent or 'claude'}` — one process starts the host, issues the "
              "token,\nregisters the agent and keeps serving.")
        return 1
    return connect_agent(host, admin, args.agent)


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
    # …and is that address actually serving? A configured-but-unreachable app is the
    # documented gap that turns every red run into `needs_setup`, and until now nothing
    # said so — the operator saw a verdict about their configuration and read it as a
    # verdict about their bug. WARN, never FAIL: the app is legitimately down while
    # someone is only capturing traces.
    if app_base:
        # Through the injected transport, like every other probe: any HTTP status proves
        # something is listening (a 404 on the root still answers the question), while 0
        # is the transport's "could not connect at all".
        app_status, _ = send(app_base, "GET", {}, None)
        reachable = app_status != 0
        checks.append(Check(
            "application under test",
            PASS if reachable else WARN,
            f"{app_base} responded (HTTP {app_status})" if reachable
            else f"{app_base} did not respond",
            "" if reachable else "Start the app (or fix the address). Reproductions run "
                                 "against it — while it is down every run is 'needs setup', "
                                 "which is a verdict about the environment, not the bug.",
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
        # A deny-by-default profile refuses EVERY semantic selector and route until an
        # operator names static values. Correct, and silently catastrophic if nobody
        # said so — a tenant would see nothing but 422s and assume StepStitch is broken.
        if status == 200 and isinstance(body, dict) and body.get("strict_schema"):
            testids = body.get("approved_testids") or []
            routes = body.get("route_templates") or []
            # BOTH lists, not just testids. The strict profile gates selectors AND routes,
            # so approving testids alone still 422s every ingest on the route check — and
            # a testids-only test would report "configured" while nothing can be stored.
            missing = []
            if not testids:
                missing.append("no approved data-testid values")
            if not routes:
                missing.append("no declared route templates")
            configured = not missing
            checks.append(Check(
                "strict allowlists",
                PASS if configured else WARN,
                f"{len(testids)} approved testid(s), {len(routes)} route template(s)"
                if configured else
                f"{body.get('base_profile')} is deny-by-default and "
                + " and ".join(missing),
                "" if configured else
                "Ingestion will be refused with 422 until BOTH lists are populated "
                "(console -> Governance, or PUT /admin/config/scrub).",
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


def build_parser() -> argparse.ArgumentParser:
    """The CLI surface, buildable without running anything.

    Separate from ``main`` so a test can assert that every command this tool prints in an
    error message actually parses — the connect error once recommended
    ``stepstitch start --connect``, a flag no parser defined, so the only recovery path
    the software offered was a command it could not read.
    """
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

    policy = sub.add_parser(
        "policy",
        help="validate a scrub/capture policy against tenant fixtures",
        description="Policy tooling. `stepstitch policy verify fixtures.json` runs every "
                    "fixture through the same scrubber and schema boundary the live "
                    "router uses and reports rejected / dropped / redacted / accepted — "
                    "plus any must_not_persist literal that would have reached storage.",
    )
    policy_sub = policy.add_subparsers(dest="policy_command")
    policy_verify = policy_sub.add_parser(
        "verify",
        help="run a fixtures file against a profile + operator overrides",
        description="Prove, before go-live, that the configured policy refuses the "
                    "payloads you are worried about (synthetic names, account numbers, "
                    "emails, semantic slugs and selectors). Exit 0 = every fixture "
                    "behaved as declared and nothing leaked; 1 = a mismatch or a leak; "
                    "2 = unusable input.",
    )
    policy_verify.add_argument("fixtures", help="path to the fixtures JSON file")
    policy_verify.add_argument("--profile", default=None,
                               help="override the profile named in the file")
    policy_verify.add_argument("--json", action="store_true", dest="as_json",
                               help="emit machine-readable results")

    init = sub.add_parser(
        "init",
        help="wire your application to StepStitch: proxy, tracker, sample report",
        description="Guided first-run wiring. Detects the app framework, writes the "
                    "same-origin ingest proxy and safe tracker wrapper under one "
                    "stepstitch/ directory (never overwriting a file you edited), "
                    "configures a synthetic reproduction base URL, and sends one "
                    "sample report. `--uninstall` removes exactly what init wrote.",
    )
    init.add_argument("--dir", default=".",
                      help="the application directory to wire (default: current)")
    init.add_argument("--host", default=os.environ.get("STEPSTITCH_HOST", DEFAULT_HOST),
                      help=f"the running StepStitch host (default {DEFAULT_HOST})")
    init.add_argument("--app-url", default=None,
                      help="where the application under test runs "
                           "(default: STEPSTITCH_APP_BASE_URL or the framework's dev port)")
    init.add_argument("--app-id", default="my-app",
                      help="identifier traces carry for this app (default: my-app)")
    init.add_argument("--framework", default="auto",
                      choices=["auto", "next", "express", "browser"],
                      help="skip detection and scaffold for this framework")
    init.add_argument("--uninstall", action="store_true",
                      help="remove exactly the files init wrote (edited files are kept)")
    init.add_argument("--json", action="store_true", dest="as_json",
                      help="emit machine-readable results")

    proof = sub.add_parser(
        "proof",
        help="export or independently verify a FixProof (proof-carrying fix)",
        description="FixProof tooling. `export` fetches the in-toto statement a host "
                    "built from its recorded evidence; `verify` checks a proof file "
                    "OFFLINE against a proof policy — no host, no account, no trust "
                    "in whoever handed you the file.",
    )
    proof_sub = proof.add_subparsers(dest="proof_command")
    proof_export = proof_sub.add_parser(
        "export",
        help="fetch a trace's FixProof from a running host and write it to a file",
        description="Exports the proof the host built from what it recorded: fixed/base "
                    "commit, frozen-test and envelope digests, measured pre/post "
                    "results, privacy policy digest, verifier identity. Refused (409) "
                    "when the evidence never named a fixed commit or was never frozen.",
    )
    proof_export.add_argument("trace_id", help="the trace whose proof to export")
    proof_export.add_argument("--format", default="in-toto", choices=["in-toto"],
                              help="statement format (in-toto is the only one, named "
                                   "so a future format is an explicit choice)")
    proof_export.add_argument("--host",
                              default=os.environ.get("STEPSTITCH_HOST", DEFAULT_HOST),
                              help=f"the running StepStitch host (default {DEFAULT_HOST})")
    proof_export.add_argument("--out", default="fixproof.json",
                              help="where to write the proof (default fixproof.json)")
    proof_export.add_argument("--json", action="store_true", dest="as_json",
                              help="also print the document to stdout")
    proof_verify = proof_sub.add_parser(
        "verify",
        help="verify a FixProof file offline against a proof policy",
        description="Recomputes the statement hash and evaluates every policy "
                    "requirement (grade floor, red-before-green, verifier allowlist, "
                    "privacy requirements, head commit). Exit 0 = the proof is intact "
                    "and satisfies the policy; 1 = tampered or a requirement failed; "
                    "2 = unusable input.",
    )
    proof_verify.add_argument("proof_file", help="path to the fixproof.json to check")
    proof_verify.add_argument("--policy", required=True,
                              help="path to the proof policy JSON")
    proof_verify.add_argument("--head-sha", default=None, dest="head_sha",
                              help="the commit being merged (e.g. the PR head); the "
                                   "proof's subject must be exactly this commit")
    proof_verify.add_argument("--json", action="store_true", dest="as_json",
                              help="emit machine-readable results")
    proof_gate = proof_sub.add_parser(
        "gate",
        help="run the merge-gate protocol against a proof-only PR head commit",
        description="The proof-only-commit protocol: the PR head must be a commit "
                    "that adds ONLY fixproof.json on top of the tested code commit, "
                    "and the signed proof's subject must be that parent commit "
                    "(HEAD^). Enforces all of it with read-only git queries — no "
                    "code from the head is ever executed. Exit 0 = the protocol and "
                    "the policy both hold; 1 = refused; 2 = unusable input.",
    )
    proof_gate.add_argument("head_sha",
                            help="the PR head commit (the proof-only commit)")
    proof_gate.add_argument("--policy", required=True,
                            help="path to the proof policy JSON (the merge gate "
                                 "loads this from the protected base branch)")
    proof_gate.add_argument("--repo", default=".",
                            help="path to the git repository (default: cwd)")
    proof_gate.add_argument("--json", action="store_true", dest="as_json",
                            help="emit machine-readable results")
    proof_keygen = proof_sub.add_parser(
        "keygen",
        help="generate the ed25519 signing key that makes proofs verifiable",
        description="Writes a new ed25519 signing seed (private — stays on the host; "
                    "point STEPSTITCH_SIGNING_KEY at the file) and prints the public "
                    "key to paste into your proof policy's trusted_keys. The seed is "
                    "never printed. Refuses to overwrite an existing key file.",
    )
    proof_keygen.add_argument("--out", default="stepstitch-signing.key",
                              help="where to write the private seed "
                                   "(default stepstitch-signing.key, mode 0600)")
    proof_keygen.add_argument("--key-id", default="stepstitch-host", dest="key_id",
                              help="the key id recorded in signatures and named in "
                                   "trusted_keys (default stepstitch-host)")

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
    start.add_argument("--connect", metavar="AGENT", default=None,
                       choices=["claude", "codex", "gemini"],
                       help="once the host is up, register this coding agent against it "
                            "with a least-privilege token — no token pasting, because "
                            "this process already holds the credential")
    return parser


def _policy_command(args: Any, parser: argparse.ArgumentParser) -> int:
    if getattr(args, "policy_command", None) != "verify":
        parser.print_help()
        return 2
    # Imported here, not at module top: the fixture runner lives with the scrubber
    # (both stdlib-only), and this module must keep its no-web-stack import guarantee.
    from stepstitch_service.policy_verify import render_report, verify_fixtures

    path = Path(args.fixtures)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"fixtures file not found: {path}")
        return 2
    except json.JSONDecodeError as exc:
        print(f"fixtures file is not valid JSON: {exc}")
        return 2
    try:
        run = verify_fixtures(doc, profile_override=args.profile)
    except ValueError as exc:
        print(f"unusable fixtures file: {exc}")
        return 2
    if args.as_json:
        print(json.dumps(run.as_dict(), indent=2))
    else:
        print(render_report(run))
    return 0 if run.ok else 1


def _proof_command(args: Any, parser: argparse.ArgumentParser,
                   transport: Optional[Transport] = None) -> int:
    command = getattr(args, "proof_command", None)
    if command == "export":
        return _proof_export(args, transport=transport)
    if command == "verify":
        return _proof_verify(args)
    if command == "gate":
        return _proof_gate(args)
    if command == "keygen":
        return _proof_keygen(args)
    parser.print_help()
    return 2


def _proof_export(args: Any, transport: Optional[Transport] = None) -> int:
    send = transport or _http
    base = args.host.rstrip("/")
    admin = os.environ.get("STEPSTITCH_ADMIN_TOKEN")
    headers = {"Authorization": f"Bearer {admin}"} if admin else {}
    status, payload = send(
        f"{base}/api/stepstitch/v1/session/{args.trace_id}/fixproof",
        "GET", headers, None)
    if status == 409 and isinstance(payload, dict):
        # The host's refusal is the useful message: it names the missing binding.
        print(f"proof refused: {payload.get('detail', 'missing prerequisite')}")
        return 1
    if status != 200 or not isinstance(payload, dict) or "fixproof" not in payload:
        print(f"could not export the proof: HTTP {status} from {base}. "
              "Is the host running, and is STEPSTITCH_ADMIN_TOKEN set?")
        return 1
    document = payload["fixproof"]
    out = Path(args.out)
    out.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} (statement {payload.get('statement_sha256', '?')}, "
          f"{'signed' if payload.get('signed') else 'hash-verifiable, unsigned'})")
    if args.as_json:
        print(json.dumps(document, indent=2))
    return 0


def _proof_keygen(args: Any) -> int:
    """Generate the host signing key. The seed is written, never printed: what the
    terminal (and its scrollback, and CI logs) sees is only the public half."""
    import secrets as _secrets

    # Lazy import (module top stays stdlib-only-importable — it is stdlib, but the
    # doctor rule is "the top imports nothing that could be broken").
    from stepstitch_service import _ed25519

    out = Path(args.out)
    if out.exists():
        print(f"refusing to overwrite {out} — an existing signing key may already be "
              "trusted by a policy. Move it aside first if you really mean to rotate.")
        return 2
    seed = _secrets.token_bytes(32)
    out.touch(mode=0o600)
    out.write_text(seed.hex() + "\n", encoding="utf-8")
    public = "ed25519:" + _ed25519.public_key(seed).hex()
    print(f"wrote private signing seed to {out} (mode 0600) — never commit or share it")
    print(f"public key: {public}")
    print()
    print("wire it up:")
    print(f"  1. on the host:   export STEPSTITCH_SIGNING_KEY={out}")
    print(f"                    export STEPSTITCH_SIGNING_KEY_ID={args.key_id}")
    print("  2. in your proof policy's trusted_keys:")
    print(f'       "trusted_keys": {{"{args.key_id}": "{public}"}}')
    return 0


def _load_json_file(path_str: str, label: str) -> Any:
    """A JSON file or None (with the reason printed) — None means unusable input."""
    try:
        return json.loads(Path(path_str).read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"{label} not found: {path_str}")
        return None
    except json.JSONDecodeError as exc:
        print(f"{label} is not valid JSON: {exc}")
        return None


def _report_proof_verification(document: Any, policy: Any,
                               head_sha: Optional[str], as_json: bool) -> int:
    """Run the offline verifier and print its outcome — shared by `verify` (a proof
    file on disk) and `gate` (a proof read out of a commit)."""
    # Imported here, not at module top: this module's top must stay importable with
    # nothing installed so `doctor` can diagnose a broken env.
    from stepstitch_service.evidence import TamperError
    from stepstitch_service.fixproof import verify_fixproof

    try:
        result = verify_fixproof(document, policy, head_sha=head_sha)
    except TamperError as exc:
        print(f"TAMPERED: {exc}")
        return 1
    except ValueError as exc:
        print(f"unusable policy: {exc}")
        return 2
    if as_json:
        print(json.dumps(result.as_dict(), indent=2))
    else:
        for check in result.checks:
            mark = "PASS" if check["passed"] else "FAIL"
            print(f"  {mark}  {check['check']} — {check['detail']}")
        verdict = "proof verified" if result.ok else "proof REJECTED by policy"
        print(f"{verdict} ({sum(c['passed'] for c in result.checks)}/"
              f"{len(result.checks)} checks passed)")
    return 0 if result.ok else 1


def _proof_verify(args: Any) -> int:
    document = _load_json_file(args.proof_file, "proof file")
    if document is None:
        return 2
    policy = _load_json_file(args.policy, "policy file")
    if policy is None:
        return 2
    return _report_proof_verification(document, policy, args.head_sha, args.as_json)


def _proof_gate(args: Any) -> int:
    """The proof-only-commit protocol (docs/integrations/github.md): the head adds
    ONLY fixproof.json, its single parent is the tested code, and the signed proof
    names that parent. Read-only git queries — nothing from the head is executed."""
    import subprocess

    policy = _load_json_file(args.policy, "policy file")
    if policy is None:
        return 2

    def git(*argv: str) -> tuple:
        try:
            proc = subprocess.run(["git", "-C", args.repo, *argv],
                                  capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            return 1, "", str(exc)
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    code, out, err = git("rev-list", "--parents", "-n", "1", args.head_sha)
    if code != 0:
        print(f"cannot resolve {args.head_sha} in {args.repo}: "
              f"{(err or out).strip() or 'not a git repository?'}")
        return 2
    parts = out.split()
    head, parents = parts[0], parts[1:]
    if len(parents) != 1:
        print("REFUSED: the head must be a proof-only commit with exactly one "
              f"parent (the tested code commit); {head[:12]} has "
              f"{len(parents)} parents.")
        return 1
    parent = parents[0]

    code, out, _diff_err = git("diff", "--name-only", parent, head)
    if code != 0:
        print(f"cannot diff {parent[:12]}..{head[:12]}: is the history complete "
              "(fetch depth >= 2)?")
        return 2
    changed = [line.strip() for line in out.splitlines() if line.strip()]
    if changed != ["fixproof.json"]:
        print("REFUSED: on top of the tested code the head commit must change "
              "only fixproof.json; it changes: "
              f"{', '.join(changed) or '(nothing)'}. Code committed after the "
              "proof is untested code riding a stale proof.")
        return 1

    code, out, _show_err = git("show", f"{head}:fixproof.json")
    if code != 0:
        print("REFUSED: the head commit does not carry fixproof.json")
        return 1
    try:
        document = json.loads(out)
    except json.JSONDecodeError as exc:
        print(f"REFUSED: the proof the PR carries is not valid JSON: {exc}")
        return 1

    print(f"proof-only commit {head[:12]} on tested code {parent[:12]} — "
          "verifying the proof against the parent commit")
    return _report_proof_verification(document, policy, parent, args.as_json)


def run_init(
    *,
    directory: Path,
    host: str,
    app_url: Optional[str] = None,
    app_id: str = "my-app",
    framework: str = "auto",
    env: Optional[Dict[str, str]] = None,
    transport: Optional[Transport] = None,
    uninstall: bool = False,
) -> Tuple[int, List[str], Dict[str, Any]]:
    """Guided first-run wiring: scaffold the proxy + tracker files, configure a
    synthetic reproduction, and send one sample report — refusing to touch any
    file the user has edited. Returns ``(exit_code, printable_lines, summary)``.

    Never prints or writes a secret: generated files read the ingest token from
    the server environment at runtime, and this function only checks whether the
    env vars are set.
    """
    # Imported here to keep the module top stdlib-only-importable everywhere.
    from stepstitch_service.scaffold import (
        DEFAULT_APP_URLS,
        MANIFEST_NAME,
        detect_framework,
        scaffold_files,
    )

    http = transport or _http
    env = dict(env if env is not None else os.environ)
    base = host.rstrip("/")
    lines: List[str] = []
    summary: Dict[str, Any] = {"written": [], "unchanged": [], "kept": [], "removed": []}
    manifest_path = directory / MANIFEST_NAME

    if not directory.is_dir():
        return 2, [f"not a directory: {directory}"], summary

    def _sha(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    if uninstall:
        if not manifest_path.is_file():
            return 0, ["nothing to uninstall: no init manifest here"], summary
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for rel, recorded_sha in sorted(manifest.get("files", {}).items()):
            path = directory / rel
            if not path.is_file():
                continue
            if _sha(path.read_text(encoding="utf-8")) != recorded_sha:
                summary["kept"].append(rel)
                lines.append(f"kept {rel} — you edited it, so it is yours now")
                continue
            path.unlink()
            summary["removed"].append(rel)
            lines.append(f"removed {rel}")
        manifest_path.unlink()
        scaffold_dir = directory / "stepstitch"
        if scaffold_dir.is_dir() and not any(scaffold_dir.iterdir()):
            scaffold_dir.rmdir()
        lines.append("uninstall complete")
        return 0, lines, summary

    if framework == "auto":
        pkg = None
        pkg_path = directory / "package.json"
        if pkg_path.is_file():
            try:
                pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
            except ValueError:
                lines.append("package.json is not valid JSON — treating as a browser app")
        framework = detect_framework(pkg)
    summary["framework"] = framework
    lines.append(f"framework: {framework}")

    try:
        files = scaffold_files(framework=framework, app_id=app_id, host=base)
    except ValueError as exc:
        return 2, [str(exc)], summary

    previous = {}
    if manifest_path.is_file():
        previous = json.loads(manifest_path.read_text(encoding="utf-8")).get("files", {})

    manifest_files: Dict[str, str] = {}
    for rel, content in sorted(files.items()):
        path = directory / rel
        desired_sha = _sha(content)
        manifest_files[rel] = desired_sha
        if path.is_file():
            current_sha = _sha(path.read_text(encoding="utf-8"))
            if current_sha == desired_sha:
                summary["unchanged"].append(rel)
                lines.append(f"unchanged {rel}")
                continue
            # Differs. Only ever overwrite bytes init itself wrote earlier — and an
            # edited file leaves the manifest entirely, so a later --uninstall can
            # never delete the user's edits.
            if previous.get(rel) != current_sha:
                summary["kept"].append(rel)
                del manifest_files[rel]
                lines.append(f"kept {rel} — you edited it, so init will not touch it")
                continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        summary["written"].append(rel)
        lines.append(f"wrote {rel}")

    manifest_path.write_text(
        json.dumps({"app_id": app_id, "framework": framework, "files": manifest_files},
                   indent=2) + "\n",
        encoding="utf-8",
    )

    status, _ = http(f"{base}/healthz", "GET", {}, None)
    if status != 200:
        lines.append(f"host not reachable at {base} — run `stepstitch start`, "
                     "then rerun `stepstitch init` to finish the wiring")
        lines.append("next: stepstitch doctor")
        return 0, lines, summary

    admin = env.get("STEPSTITCH_ADMIN_TOKEN")
    resolved_app_url = app_url or env.get("STEPSTITCH_APP_BASE_URL") or DEFAULT_APP_URLS[framework]
    if admin:
        headers = {"Authorization": f"Bearer {admin}", "Content-Type": "application/json"}
        status, current = http(f"{base}/admin/config/repro", "GET", headers, None)
        existing = (current or {}).get("config", {}) if isinstance(current, dict) else {}
        if existing.get("base_url"):
            lines.append("reproduction config already set "
                         f"(base_url {existing['base_url']}) — left as is")
        else:
            body = json.dumps({"config": {"base_url": resolved_app_url}}).encode("utf-8")
            status, _ = http(f"{base}/admin/config/repro", "PUT", headers, body)
            if status == 200:
                summary["repro_base_url"] = resolved_app_url
                lines.append(f"reproduction config: base_url set to {resolved_app_url}")
            else:
                lines.append(f"could not write reproduction config ({status}) — "
                             "set it in the console's Governance tab")
    else:
        lines.append("STEPSTITCH_ADMIN_TOKEN not set — skipped reproduction config; "
                     "`stepstitch start` printed the token")

    ingest = env.get("STEPSTITCH_INGEST_TOKEN")
    if ingest:
        sample = {
            "app_id": app_id,
            "explanation": "Synthetic first report from stepstitch init",
            "footsteps": [
                {"timestamp": "t", "type": "navigation", "route": "/", "label": "[masked]"},
                {"timestamp": "t", "type": "click", "route": "/",
                 "target": '[data-testid="submit"]', "label": "[masked]"},
                {"timestamp": "t", "type": "exception", "route": "/", "label": "[masked]",
                 "metadata": {"error_type": "TypeError"}},
            ],
            "metadata": {},
        }
        status, payload = http(
            f"{base}/api/stepstitch/v1/session", "POST",
            {"Authorization": f"Bearer {ingest}", "Content-Type": "application/json"},
            json.dumps(sample).encode("utf-8"),
        )
        trace_id = payload.get("trace_id") if isinstance(payload, dict) else None
        if status == 200 and trace_id:
            summary["trace_id"] = trace_id
            lines.append(f"sample report ingested: {trace_id}")
            lines.append(f"see it in the console: {base}/dashboard")
        else:
            lines.append(f"sample report was refused ({status}) — run `stepstitch doctor`")
    else:
        lines.append("STEPSTITCH_INGEST_TOKEN not set — skipped the sample report; "
                     "`stepstitch start` printed the token")

    lines.append("next: stepstitch doctor")
    return 0, lines, summary


def _init_command(args: Any) -> int:
    code, lines, summary = run_init(
        directory=Path(args.dir),
        host=args.host,
        app_url=args.app_url,
        app_id=args.app_id,
        framework=args.framework,
        uninstall=args.uninstall,
    )
    if args.as_json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print("\n".join(lines))
    return code


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
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
            connect=args.connect,
        )
    if args.command == "policy":
        return _policy_command(args, parser)
    if args.command == "proof":
        return _proof_command(args, parser)
    if args.command == "init":
        return _init_command(args)
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
