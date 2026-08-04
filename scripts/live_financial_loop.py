#!/usr/bin/env python3
"""The financial release gate, executed with no mocks anywhere in the chain:

    TinyTransfer in real Chromium
      -> real @stepstitch/tracker SDK
      -> same-origin ingest proxy (server.mjs, token server-side)
      -> real strict scrubber + real SQLite database (financial-services-strict)
      -> stored ROW read raw from the database, not the outbound payload
      -> the same evidence retrieved over real MCP stdio with a repros-scoped token
      -> verify.mjs with a verify-scoped token: measured red -> fix -> measured green
      -> freeze / verify-fix: confirmed_fixed with evidence_grade='measured',
         asserted from the raw stepstitch_verifications row

Each numbered step is measured; a mismatch exits non-zero. The hermetic
tiny-transfer CI job proves the outbound payload; THIS job proves the other half
nothing else covers — what actually persisted, and that the strict profile's
deny-by-default boundary holds against a live browser and a hostile POST.

    python3 scripts/live_financial_loop.py
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / "examples" / "tiny-transfer"
ADMIN = "live-loop-admin-token"
INGEST = "live-loop-ingest-token"

# The operator config for THIS app: the strict profile ships deny-by-default, and
# these are the only static values TinyTransfer legitimately produces.
APPROVED_TESTIDS = ["consent-toggle", "recipient-account", "transfer-amount",
                    "contact-email", "send-transfer", "apply-fix", "reset-bug"]
ROUTE_TEMPLATES = ["/"]

# Values that must never persist (same canaries the hermetic suite watches).
CANARIES = ("4111 1111 1111 1234", "250.00", "dana.holt@example.test",
            "FAKE-QUERY-SECRET-123", "8842")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def call(url: str, method: str = "GET", body: dict | None = None,
         token: str = ADMIN, timeout: float = 300.0) -> dict:
    data = json.dumps(body or {}).encode() if method in ("POST", "PUT") else None
    headers = {"Authorization": f"Bearer {token}"}
    if data:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return {"status": "http_error", "code": exc.code,
                "detail": exc.read().decode("utf-8", "replace")}


def step(number: int, text: str) -> None:
    print(f"\n{number}. {text}")


def check(condition: bool, message: str) -> None:
    print(f"   {'ok  ' if condition else 'FAIL'} {message}")
    if not condition:
        sys.exit(1)


def wait_healthy(url: str, proc: subprocess.Popen, what: str, seconds: int = 60) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            print(proc.stdout.read() if proc.stdout else "")
            print(f"{what} exited before becoming healthy")
            sys.exit(1)
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except OSError:
            time.sleep(0.3)
    print(f"{what} never became healthy at {url}")
    sys.exit(1)


def mcp_fetch(host: str, token: str, trace_id: str) -> dict:
    """Retrieve the evidence over REAL MCP stdio — the exact client an agent runs."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "stepstitch_service.mcp_cli"],
        env={**os.environ,
             "PYTHONPATH": str(REPO / "service"),
             "PYTHONUNBUFFERED": "1",
             "STEPSTITCH_BASE_URL": f"{host}/api/stepstitch/v1",
             "STEPSTITCH_TOKEN": token},
    )

    async def session() -> dict:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as sess:
                await sess.initialize()
                out: dict = {}
                for tool, key in (("get_privacy_posture", "posture"),
                                  ("get_agent_packet", "packet"),
                                  ("generate_playwright_repro", "repro")):
                    result = await sess.call_tool(tool, {"trace_id": trace_id})
                    text = "".join(b.text for b in result.content
                                   if getattr(b, "type", "") == "text")
                    out[key] = json.loads(text)
                return out

    return asyncio.run(asyncio.wait_for(session(), timeout=120))


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="stepstitch-live-"))
    db_path = work / "live.db"
    app_port, host_port = free_port(), free_port()
    app_url = f"http://127.0.0.1:{app_port}"
    host = f"http://127.0.0.1:{host_port}"

    host_env = dict(
        os.environ,
        PYTHONPATH=str(REPO / "service"),
        STEPSTITCH_ADMIN_TOKEN=ADMIN,
        STEPSTITCH_INGEST_TOKEN=INGEST,
        STEPSTITCH_APP_BASE_URL=app_url,
        STEPSTITCH_PROFILE="financial-services-strict",
        RETENTION_PURGE_INTERVAL_SECONDS="0",
    )
    stepstitch = subprocess.Popen(
        [sys.executable, "-m", "stepstitch_service.cli", "start", "--no-browser",
         "--port", str(host_port), "--db", str(db_path)],
        env=host_env, cwd=str(REPO),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    app = None
    try:
        wait_healthy(f"{host}/healthz", stepstitch, "StepStitch host")

        step(1, "operator scopes the deny-by-default profile (approved testids + routes)")
        saved = call(f"{host}/admin/config/scrub", "PUT", {
            "extra_redactions": [], "extra_forbidden_keys": [],
            "approved_testids": APPROVED_TESTIDS,
            "route_templates": ROUTE_TEMPLATES,
        })
        check(saved.get("status") == "ok", "scrub-overrides document saved")
        cfg = call(f"{host}/admin/config/scrub")
        check(cfg.get("base_profile") == "financial-services-strict",
              f"host runs the strict profile ({cfg.get('base_profile')})")
        check(cfg.get("approved_testids") == APPROVED_TESTIDS,
              "the allowlists round-tripped through the stored document")

        step(2, "TinyTransfer starts against the live host (real proxy, token server-side)")
        app = subprocess.Popen(
            ["node", "server.mjs"],
            cwd=str(EXAMPLE),
            env=dict(os.environ, PORT=str(app_port), STEPSTITCH_HOST=host,
                     STEPSTITCH_INGEST_TOKEN=INGEST),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        wait_healthy(f"{app_url}/__bug", app, "TinyTransfer")

        step(3, "a real browser hits the bug and reports it through the real SDK")
        result = subprocess.run(
            ["node", "live-report.mjs", app_url],
            cwd=str(EXAMPLE), capture_output=True, text=True, timeout=180,
        )
        check(result.returncode == 0,
              f"browser run completed ({(result.stderr or '')[:200]})")
        report = json.loads(result.stdout)
        trace_id = report.get("trace_id")
        check(bool(trace_id), f"trace ingested under strict: {str(trace_id)[:8]}…")

        step(4, "the LITERAL wire payload carries no form value")
        wire = " ".join(report.get("ingest_bodies", []))
        check(bool(wire), "captured the bytes that left the browser")
        for canary in CANARIES:
            check(canary not in wire, f"wire payload does not contain {canary!r}")

        step(5, "the stored DATABASE ROW is strict-clean (read raw, not via the API)")
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT explanation, footsteps, trace_metadata FROM stepstitch_traces "
            "WHERE id = ?", (trace_id,),
        ).fetchone()
        check(row is not None, "the row exists")
        explanation, footsteps_json, meta_json = row
        stored_blob = json.dumps([explanation, footsteps_json, meta_json])
        for canary in CANARIES:
            check(canary not in stored_blob, f"stored row does not contain {canary!r}")
        check(explanation is None, "no free text persisted (strict disables it)")
        footsteps = json.loads(footsteps_json)
        check(len(footsteps) > 0, f"{len(footsteps)} structural footsteps stored")
        check(all(s.get("label") == "[masked]" for s in footsteps),
              "every stored label is [masked]")
        approved = {f'[data-testid="{t}"]' for t in APPROVED_TESTIDS}
        check(all((s.get("target") in approved or s.get("target") is None)
                  for s in footsteps),
              "every stored selector is operator-approved")
        check(all(s.get("route") in ROUTE_TEMPLATES for s in footsteps),
              "every stored route matches a declared template")
        scrub = json.loads(meta_json).get("_scrub", {})
        check(scrub.get("schema_status") == "strict_schema_passed",
              "the row carries schema_status=strict_schema_passed")
        rows_before = conn.execute(
            "SELECT COUNT(*) FROM stepstitch_traces").fetchone()[0]

        step(6, "semantic customer data is REJECTED in strict mode (measured 422)")
        hostile = call(f"{host}/api/stepstitch/v1/session", "POST", {
            "app_id": "tiny-transfer",
            "explanation": "customer Jane Doe SSN 000-00-0000",
            "footsteps": [
                {"timestamp": "t", "type": "navigation",
                 "route": "/customers/jane-doe-smith", "label": "[masked]"},
                {"timestamp": "t", "type": "click", "route": "/",
                 "target": '[data-testid="customer-ssn-field"]', "label": "[masked]"},
            ],
            "metadata": {},
        }, token=INGEST)
        check(hostile.get("code") == 422, f"hostile POST refused: {hostile.get('code')}")
        rows_after = conn.execute("SELECT COUNT(*) FROM stepstitch_traces").fetchone()[0]
        check(rows_after == rows_before, "and nothing was stored")

        step(7, "an agent retrieves the same evidence over REAL MCP stdio (repros scope)")
        minted = call(f"{host}/admin/agents", "POST",
                      {"name": "live-loop-reader", "scope": "repros"})
        repros_token = minted.get("token", "")
        check(bool(repros_token), f"repros-scoped token minted ({minted.get('scope')})")
        mcp = mcp_fetch(host, repros_token, trace_id)
        posture = mcp["posture"]
        check(posture.get("schema_status") == "strict_schema_passed",
              "MCP posture reports strict_schema_passed")
        direct = call(f"{host}/api/stepstitch/v1/session/{trace_id}/playwright")
        check(mcp["repro"].get("playwright_code") == direct.get("playwright_code"),
              "MCP repro is byte-identical to the direct read")
        check("playwright" in json.dumps(mcp["packet"]).lower(),
              "the agent packet carries the reproduction")

        step(8, "verify.mjs: measured red -> fix -> measured green -> confirmed_fixed "
                "(verify-scoped token)")
        minted = call(f"{host}/admin/agents", "POST",
                      {"name": "live-loop-ci", "scope": "verify"})
        verify_token = minted.get("token", "")
        check(bool(verify_token), "verify-scoped token minted")
        verify = subprocess.run(
            ["node", "verify.mjs"],
            cwd=str(EXAMPLE),
            env=dict(os.environ, STEPSTITCH_HOST=host,
                     STEPSTITCH_VERIFY_TOKEN=verify_token,
                     TRACE_ID=trace_id, TINY_TRANSFER_URL=app_url),
            capture_output=True, text=True, timeout=600,
        )
        print("   " + "\n   ".join((verify.stdout or "").strip().splitlines()[-6:]))
        check(verify.returncode == 0, "verify.mjs measured red then green")

        step(9, "freeze / verify-fix: the measured-grade path, asserted from the raw row")
        # verify.mjs left the bug re-armed, so the freeze measures a genuine red.
        frozen = call(f"{host}/admin/session/{trace_id}/freeze", "POST",
                      {"runs": 1, "timeout_seconds": 120})
        check(frozen.get("ready_for_agent") is True,
              f"freeze measured red: {frozen.get('red', {}).get('verdict')}")
        fixed_state = call(f"{app_url}/__bug", "POST", {"active": False}, token="")
        check(fixed_state.get("active") is False, "the fix is applied")
        verdict = call(f"{host}/admin/session/{trace_id}/verify-fix", "POST",
                       {"runs": 1, "timeout_seconds": 120})
        check(verdict.get("verdict") == "fixed",
              f"frozen bytes rerun: {verdict.get('verdict')}")
        vrow = conn.execute(
            "SELECT pre_passed, post_passed, verdict, evidence_grade "
            "FROM stepstitch_verifications WHERE trace_id = ? "
            "AND evidence_grade = 'measured' ORDER BY created_at DESC LIMIT 1",
            (trace_id,),
        ).fetchone()
        check(vrow is not None, "a measured verification row exists")
        pre, post, v, grade = vrow
        check(not pre and bool(post) and v == "confirmed_fixed" and grade == "measured",
              f"raw row: pre={pre} post={post} verdict={v} grade={grade}")
        conn.close()

        print("\nBrowser -> proxy -> strict scrubber -> database -> MCP -> red-to-green, "
              "with every claim asserted\nagainst the stored bytes. No mocks were involved.")
        return 0
    finally:
        for proc in (app, stepstitch):
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()


if __name__ == "__main__":
    sys.exit(main())
