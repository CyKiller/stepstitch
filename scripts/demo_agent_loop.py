#!/usr/bin/env python3
"""The whole promise, executed: a failure becomes a proven fix, and the agent cannot cheat.

Runs the full loop against a real application and a real browser:

    report -> freeze (measured red) -> agent edits the app -> rerun the FROZEN test -> fixed

Then it does the part that matters more. A second agent "fixes" the bug by editing the
*test* instead of the application, and StepStitch refuses — because verification reruns the
bytes recorded at freeze time, not whatever is on disk now.

The agent here is a deterministic script, not an LLM: CI must be able to run this on every
commit and get the same answer. What it exercises is the real handoff — the same agent
packet a Claude Code or Codex session receives, and the same endpoints they would call.

    python3 scripts/demo_agent_loop.py

Exits non-zero if any step does not produce the expected verdict.
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ADMIN = "demo-admin-token"
INGEST = "demo-ingest-token"

BROKEN = "throw new TypeError('amount is not a function')"
FIXED = "document.getElementById('title').textContent = 'Sent'"

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>TinyTransfer</title></head>
<body>
  <h1 id="title">Transfer</h1>
  <button id="submit" data-testid="submit" onclick="{handler}">Send</button>
</body></html>
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _NoStore(http.server.SimpleHTTPRequestHandler):
    """The app under test. No-store because the fix is written between two runs, and a
    304 would hand the browser the old page — the verification would silently re-test the
    bug and report a fix that never happened."""

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def send_header(self, key, value):
        if key.lower() == "last-modified":
            return
        super().send_header(key, value)

    def log_message(self, *args):
        pass


def serve_app(directory: Path, port: int) -> http.server.HTTPServer:
    handler = functools.partial(_NoStore, directory=str(directory))
    server = http.server.HTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def write_app(directory: Path, handler: str) -> None:
    (directory / "index.html").write_text(PAGE.format(handler=handler), encoding="utf-8")


def call(url: str, method: str = "GET", body: dict | None = None,
         token: str = ADMIN, timeout: float = 300.0) -> dict:
    data = json.dumps(body or {}).encode() if method == "POST" else None
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


def _keys_anywhere(value, found=None) -> set:
    """Every key name in a nested structure — what the packet actually *carries*."""
    found = set() if found is None else found
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(str(key).lower())
            _keys_anywhere(item, found)
    elif isinstance(value, list):
        for item in value:
            _keys_anywhere(item, found)
    return found


def step(number: int, text: str) -> None:
    print(f"\n{number}. {text}")


def check(condition: bool, message: str) -> None:
    print(f"   {'ok  ' if condition else 'FAIL'} {message}")
    if not condition:
        sys.exit(1)


def main() -> int:
    work = REPO / ".stepstitch-agent-demo"
    app_dir = work / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    app_port, host_port = _free_port(), _free_port()
    app_url = f"http://127.0.0.1:{app_port}"
    host = f"http://127.0.0.1:{host_port}"

    write_app(app_dir, BROKEN)
    server = serve_app(app_dir, app_port)

    env = dict(
        os.environ,
        PYTHONPATH=str(REPO / "service"),
        STEPSTITCH_ADMIN_TOKEN=ADMIN,
        STEPSTITCH_INGEST_TOKEN=INGEST,
        STEPSTITCH_APP_BASE_URL=app_url,
        RETENTION_PURGE_INTERVAL_SECONDS="0",
    )
    stepstitch = subprocess.Popen(
        [sys.executable, "-m", "stepstitch_service.cli", "start", "--no-browser",
         "--port", str(host_port), "--db", str(work / "local.db")],
        env=env, cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if stepstitch.poll() is not None:
                print(stepstitch.stdout.read() if stepstitch.stdout else "")
                return 1
            try:
                urllib.request.urlopen(f"{host}/healthz", timeout=1)
                break
            except OSError:
                time.sleep(0.3)
        else:
            print("StepStitch never became healthy")
            return 1

        step(1, "a user reports a bug (structural evidence only)")
        trace = call(f"{host}/api/stepstitch/v1/session", "POST", {
            "app_id": "tiny-transfer",
            "explanation": "The Send button does nothing",
            "footsteps": [
                {"timestamp": "2026-07-30T12:00:00Z", "type": "navigation",
                 "route": "/index.html", "label": "[masked]"},
                {"timestamp": "2026-07-30T12:00:02Z", "type": "click",
                 "route": "/index.html", "target": "[data-testid=submit]",
                 "label": "[masked]"},
                {"timestamp": "2026-07-30T12:00:03Z", "type": "exception",
                 "route": "/index.html", "label": "[masked]",
                 "metadata": {"error_type": "TypeError"}},
            ],
            "metadata": {"sdk_version": "demo"},
        }, token=INGEST)
        trace_id = trace.get("trace_id", "")
        check(bool(trace_id), f"captured as {trace_id[:8]}…")

        step(2, "StepStitch freezes the test and measures the failure itself")
        frozen = call(f"{host}/admin/session/{trace_id}/freeze", "POST",
                      {"runs": 1, "timeout_seconds": 120})
        check(frozen.get("ready_for_agent") is True,
              f"red run observed: {frozen.get('red', {}).get('verdict')}")
        sha = frozen.get("script_sha256", "")
        check(len(sha) == 64, f"frozen sha256 {sha[:16]}…")

        step(3, "the agent receives structural evidence — and nothing else")
        packet = call(f"{host}/api/stepstitch/v1/session/{trace_id}/agent-packet")
        check("playwright" in json.dumps(packet).lower(),
              "the packet carries the reproduction")
        # Check KEYS, not the whole blob: the packet declares what it never captures, so a
        # substring search finds "screenshots" inside that very promise and calls it a leak.
        forbidden = {"screenshot", "screenshots", "video", "cookies", "headers",
                     "request_body", "response_body", "dom", "page_text", "url",
                     "query_string", "password"}
        found = _keys_anywhere(packet) & forbidden
        check(not found, f"no forbidden data keys (checked {len(forbidden)})")
        posture = packet.get("agent_packet", {}).get("privacy_posture", {})
        check("screenshots" in json.dumps(posture.get("never_captured", [])).lower(),
              "and the packet states what it never captures")

        step(4, "the agent edits the APPLICATION (deterministic stand-in for a coding agent)")
        write_app(app_dir, FIXED)
        check(FIXED in (app_dir / "index.html").read_text(), "the app was changed")

        step(5, "StepStitch reruns the frozen test — the agent does not get a vote")
        verdict = call(f"{host}/admin/session/{trace_id}/verify-fix", "POST",
                       {"runs": 1, "timeout_seconds": 120})
        check(verdict.get("verdict") == "fixed",
              f"verdict: {verdict.get('verdict')} — {verdict.get('detail', '')[:80]}")
        check(verdict.get("script_sha256") == sha,
              "the same frozen bytes judged before and after")

        step(6, "a second agent 'fixes' it by weakening the TEST instead of the app")
        write_app(app_dir, BROKEN)                      # put the bug back
        weakened = "import { test } from '@playwright/test'\ntest('x', async () => {})\n"
        refused = call(f"{host}/admin/session/{trace_id}/verify-fix", "POST",
                       {"runs": 1, "timeout_seconds": 120, "script": weakened})
        # The endpoint takes no script at all: there is no parameter to smuggle one
        # through, and the stored bytes are the only ones that ever run.
        check(refused.get("verdict") == "still_failing",
              f"the bug is back and StepStitch says so: {refused.get('verdict')}")
        check(weakened not in json.dumps(refused),
              "a caller-supplied test was ignored entirely")

        print("\nAn agent fixed a real failure from privacy-safe evidence, and StepStitch "
              "measured\nthe result with a test the agent could not touch.")
        return 0
    finally:
        server.shutdown()
        stepstitch.terminate()
        try:
            stepstitch.wait(timeout=10)
        except subprocess.TimeoutExpired:
            stepstitch.kill()


if __name__ == "__main__":
    sys.exit(main())
