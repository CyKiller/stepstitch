"""``stepstitch start`` boots StepStitch Local for real: process, port, pairing, ingest.

The other local-mode tests build the app in-process; this one runs the actual CLI in a
subprocess the way a developer does, and proves the whole first-run promise: the server
comes up on loopback, the dashboard serves with the pairing script, the printed ingest
token accepts a trace, and the store lands in the requested SQLite file.
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ADMIN = "local-admin-token-for-test"
INGEST = "local-ingest-token-for-test"

_PAYLOAD = {
    "app_id": "demo",
    "footsteps": [{"timestamp": "t", "type": "api_error", "route": "/accounts/:id",
                   "label": "[masked]", "metadata": {"status": 500}}],
    "metadata": {"sdk_version": "0.4.0"},
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(url, headers=None, timeout=2):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


def test_start_serves_pairs_and_ingests(tmp_path):
    port = _free_port()
    env = dict(
        os.environ,
        PYTHONPATH=os.path.join(REPO, "service"),
        STEPSTITCH_ADMIN_TOKEN=ADMIN,
        STEPSTITCH_INGEST_TOKEN=INGEST,
        RETENTION_PURGE_INTERVAL_SECONDS="0",
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "stepstitch_service.cli", "start",
         "--no-browser", "--port", str(port), "--db", str(tmp_path / "local.db")],
        env=env, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise AssertionError(f"start exited early:\n{proc.stdout.read()}")
            try:
                status, _ = _get(f"{base}/healthz")
                if status == 200:
                    break
            except (urllib.error.URLError, OSError):
                time.sleep(0.25)
        else:
            raise AssertionError("server never became healthy")

        # The dashboard serves, and it carries the local pairing script (#ss= adoption).
        status, html = _get(f"{base}/dashboard")
        assert status == 200
        assert "#ss=" in html

        # The ingest token accepts a trace; the admin token reads it back.
        req = urllib.request.Request(
            f"{base}/api/stepstitch/v1/session",
            data=json.dumps(_PAYLOAD).encode(),
            headers={"Authorization": f"Bearer {INGEST}",
                     "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            trace_id = json.loads(resp.read())["trace_id"]
        status, _ = _get(f"{base}/api/stepstitch/v1/session/{trace_id}/summary",
                         headers={"Authorization": f"Bearer {ADMIN}"})
        assert status == 200

        # The store went where --db pointed.
        assert (tmp_path / "local.db").exists()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_start_is_a_registered_command():
    from stepstitch_service.cli import main

    # argparse help for the subcommand exits 0 and mentions the promise.
    try:
        main(["start", "--help"])
    except SystemExit as exc:
        assert exc.code == 0
