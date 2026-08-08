"""`stepstitch init` — guided first-run wiring, proven safe and idempotent.

The properties that matter:
  - detection is data-driven (package.json), never guessy prompts
  - rerunning init never overwrites a file the user edited
  - --uninstall removes exactly what init wrote, and keeps edited files
  - no generated file and no output line ever contains a secret value
  - the host steps (repro config, sample report) go through the same wire
    shapes the live host validates, and degrade to copyable next steps when
    the host or tokens are absent
"""
import json

from stepstitch_service.cli import build_parser, main, run_init
from stepstitch_service.scaffold import (
    FRAMEWORKS,
    MANIFEST_NAME,
    detect_framework,
    scaffold_files,
)

HOST = "http://127.0.0.1:9999"


def _transport(overrides=None, calls=None):
    """Doctor-style fake transport: url-substring -> (status, payload)."""
    overrides = overrides or {}
    calls = calls if calls is not None else []

    def fake(url, method, headers, body):
        calls.append({"url": url, "method": method, "headers": headers, "body": body})
        for fragment, response in overrides.items():
            if fragment in url:
                return response
        return 200, {}

    return fake


def _healthy(extra=None):
    overrides = {
        "/healthz": (200, {"status": "ok"}),
        "/admin/config/repro": (200, {"config": {}}),
        "/api/stepstitch/v1/session": (200, {"trace_id": "trc_init_1"}),
    }
    overrides.update(extra or {})
    return overrides


# --- detection -------------------------------------------------------------------


def test_detection_is_dependency_driven():
    assert detect_framework(None) == "browser"
    assert detect_framework({"dependencies": {"next": "15.0.0"}}) == "next"
    assert detect_framework({"devDependencies": {"express": "4.0.0"}}) == "express"
    assert detect_framework({"dependencies": {"react": "19.0.0"}}) == "browser"


def test_every_framework_scaffolds_and_no_file_contains_a_secret_slot():
    for fw in FRAMEWORKS:
        files = scaffold_files(framework=fw, app_id="acme", host=HOST)
        assert "stepstitch/tracker-setup.js" in files
        assert "stepstitch/README.md" in files
        joined = "\n".join(files.values())
        # The credential is read from the server env at runtime, never templated in.
        assert "STEPSTITCH_INGEST_TOKEN" in joined
        assert "Bearer ci-" not in joined
        assert "token_urlsafe" not in joined


# --- write/rerun/uninstall lifecycle --------------------------------------------


def test_init_writes_reruns_unchanged_and_uninstalls_cleanly(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"express": "4"}}))
    code, lines, summary = run_init(
        directory=tmp_path, host=HOST, env={}, transport=_transport({"/healthz": (0, "down")}),
    )
    assert code == 0
    assert summary["framework"] == "express"
    assert "stepstitch/ingest-proxy.mjs" in summary["written"]
    assert (tmp_path / MANIFEST_NAME).is_file()

    # Rerun: everything unchanged, nothing rewritten.
    code, lines, summary2 = run_init(
        directory=tmp_path, host=HOST, env={}, transport=_transport({"/healthz": (0, "down")}),
    )
    assert code == 0
    assert not summary2["written"]
    assert sorted(summary2["unchanged"]) == sorted(summary["written"])

    # Uninstall removes exactly what init wrote, plus the manifest.
    code, lines, summary3 = run_init(
        directory=tmp_path, host=HOST, env={}, uninstall=True,
        transport=_transport(),
    )
    assert code == 0
    assert sorted(summary3["removed"]) == sorted(summary["written"])
    assert not (tmp_path / MANIFEST_NAME).exists()
    assert not (tmp_path / "stepstitch").exists()
    assert (tmp_path / "package.json").is_file()  # user files untouched

    # Uninstall twice is a no-op, not an error.
    code, lines, _ = run_init(
        directory=tmp_path, host=HOST, env={}, uninstall=True, transport=_transport(),
    )
    assert code == 0


def test_an_edited_file_is_never_overwritten_and_never_uninstalled(tmp_path):
    run_init(directory=tmp_path, host=HOST, env={},
             transport=_transport({"/healthz": (0, "down")}))
    target = tmp_path / "stepstitch" / "tracker-setup.js"
    target.write_text("// the user rewrote this entirely\n")

    code, lines, summary = run_init(
        directory=tmp_path, host=HOST, env={}, transport=_transport({"/healthz": (0, "down")}),
    )
    assert code == 0
    assert "stepstitch/tracker-setup.js" in summary["kept"]
    assert target.read_text() == "// the user rewrote this entirely\n"

    # The rerun dropped the edited file from the manifest, so uninstall leaves it
    # alone without comment — it is simply not init's file anymore.
    code, lines, summary = run_init(
        directory=tmp_path, host=HOST, env={}, uninstall=True, transport=_transport(),
    )
    assert code == 0
    assert "stepstitch/tracker-setup.js" not in summary["removed"]
    assert target.is_file()
    assert not (tmp_path / MANIFEST_NAME).exists()


def test_editing_then_uninstalling_directly_keeps_the_edit(tmp_path):
    """No rerun in between: the manifest still lists the original sha, and the
    mismatch must read as 'the user's file now', never as 'safe to delete'."""
    run_init(directory=tmp_path, host=HOST, env={},
             transport=_transport({"/healthz": (0, "down")}))
    target = tmp_path / "stepstitch" / "tracker-setup.js"
    target.write_text("// the user rewrote this entirely\n")

    code, lines, summary = run_init(
        directory=tmp_path, host=HOST, env={}, uninstall=True, transport=_transport(),
    )
    assert code == 0
    assert "stepstitch/tracker-setup.js" in summary["kept"]
    assert target.read_text() == "// the user rewrote this entirely\n"
    assert not (tmp_path / MANIFEST_NAME).exists()


# --- host steps ------------------------------------------------------------------


def test_host_steps_write_repro_config_and_ingest_a_sample(tmp_path):
    calls = []
    code, lines, summary = run_init(
        directory=tmp_path, host=HOST, app_id="acme",
        env={"STEPSTITCH_ADMIN_TOKEN": "adm", "STEPSTITCH_INGEST_TOKEN": "ing"},
        transport=_transport(_healthy(), calls),
    )
    assert code == 0
    assert summary["trace_id"] == "trc_init_1"
    put = next(c for c in calls if c["method"] == "PUT")
    assert json.loads(put["body"])["config"]["base_url"].startswith("http://localhost:")
    post = next(c for c in calls if c["method"] == "POST")
    payload = json.loads(post["body"])
    assert payload["app_id"] == "acme"
    assert all(step["label"] == "[masked]" for step in payload["footsteps"])


def test_an_existing_repro_config_is_never_clobbered(tmp_path):
    calls = []
    run_init(
        directory=tmp_path, host=HOST,
        env={"STEPSTITCH_ADMIN_TOKEN": "adm"},
        transport=_transport(_healthy({
            "/admin/config/repro": (200, {"config": {"base_url": "https://staging.acme.test"}}),
        }), calls),
    )
    assert not any(c["method"] == "PUT" for c in calls)


def test_missing_tokens_degrade_to_next_steps_not_failures(tmp_path):
    code, lines, summary = run_init(
        directory=tmp_path, host=HOST, env={}, transport=_transport(_healthy()),
    )
    assert code == 0
    text = "\n".join(lines)
    assert "STEPSTITCH_ADMIN_TOKEN not set" in text
    assert "STEPSTITCH_INGEST_TOKEN not set" in text
    assert "trace_id" not in summary


def test_no_secret_value_ever_appears_in_output(tmp_path):
    secret_admin = "adm-secret-value-123"
    secret_ingest = "ing-secret-value-456"
    code, lines, summary = run_init(
        directory=tmp_path, host=HOST,
        env={"STEPSTITCH_ADMIN_TOKEN": secret_admin,
             "STEPSTITCH_INGEST_TOKEN": secret_ingest},
        transport=_transport(_healthy()),
    )
    blob = "\n".join(lines) + json.dumps(summary)
    for path in (tmp_path / "stepstitch").rglob("*"):
        blob += path.read_text()
    assert secret_admin not in blob
    assert secret_ingest not in blob


# --- CLI surface -----------------------------------------------------------------


def test_init_parses_and_every_recommended_command_parses(tmp_path):
    parser = build_parser()
    args = parser.parse_args(["init", "--dir", str(tmp_path), "--framework", "next",
                              "--app-id", "acme", "--uninstall", "--json"])
    assert args.command == "init"
    # Commands init prints as remedies must themselves parse.
    for recommended in (["start"], ["doctor"], ["init", "--uninstall"]):
        assert parser.parse_args(recommended) is not None


def test_cli_json_output_is_machine_readable(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code = main(["init", "--dir", str(tmp_path), "--framework", "browser",
                 "--host", HOST, "--json"])
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["framework"] == "browser"
    assert "stepstitch/ingest-proxy.mjs" in summary["written"]
