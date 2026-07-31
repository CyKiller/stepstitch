"""`stepstitch connect`: least privilege, no hand-edited config, and no token in a config.

The gap this closes was measured, not imagined: before the scope-parity fix, five of the
thirteen MCP tools — including ``get_agent_packet`` — were unreachable by any scoped token,
so the shipped `.mcp.json` used the **admin** token. "Least-privilege connection" was
impossible while looking solved. These tests keep it solved.
"""
import os
import stat
import subprocess

import pytest
from stepstitch_service.connect import (
    AGENT_SCOPE,
    CODEX_APPROVAL_LINE,
    PLATFORMS,
    apply,
    ensure_codex_tool_approval,
    connection_env,
    detect,
    list_command,
    plan,
    render_plan,
    resolve,
    token_path,
    verify,
    write_token,
)

BASE = "http://127.0.0.1:8321/api/stepstitch/v1"


def _ok(*_a, **_k):
    return subprocess.CompletedProcess([], 0, stdout="stepstitch: connected", stderr="")


def _fail(*_a, **_k):
    return subprocess.CompletedProcess([], 1, stdout="", stderr="server already exists")


# --- least privilege ----------------------------------------------------------------------

def test_a_connected_agent_gets_repros_never_verify():
    """The separation the product rests on: an agent may read everything it needs to fix a
    failure, and may never write the evidence that says its fix worked."""
    assert AGENT_SCOPE == "repros"
    entry = plan(PLATFORMS["claude"], BASE, token_path("a1"))
    assert entry["scope"] == "repros"
    assert "verify" not in str(entry)


# --- the token is not in the config -------------------------------------------------------

def test_the_config_carries_a_path_not_a_token(tmp_path):
    """Agent config files are read by editors, synced by dotfile managers, and pasted into
    bug reports. A path leaks nothing; a bearer token leaks by accident."""
    path = write_token("a1", "ssa_supersecrettoken", home=tmp_path)
    env = connection_env(BASE, path)
    assert env["STEPSTITCH_TOKEN_FILE"] == str(path)
    assert "ssa_supersecrettoken" not in str(env)
    assert "STEPSTITCH_TOKEN" not in env


def test_the_token_file_is_owner_only(tmp_path):
    path = write_token("a1", "ssa_secret", home=tmp_path)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600, f"token file is {oct(mode)}, must be 0600"
    assert path.read_text() == "ssa_secret"


def test_an_existing_token_file_is_tightened_not_trusted(tmp_path):
    path = token_path("a1", tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("old")
    os.chmod(path, 0o644)                       # a previous run, or a careless hand
    write_token("a1", "ssa_new", home=tmp_path)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_the_token_never_appears_in_argv(tmp_path):
    """argv is visible to every process on the machine via `ps`."""
    path = write_token("a1", "ssa_verysecret", home=tmp_path)
    for platform in PLATFORMS.values():
        argv = platform.add_argv(platform.executable, connection_env(BASE, path))
        assert "ssa_verysecret" not in " ".join(argv)


# --- native vendor commands ---------------------------------------------------------------

@pytest.mark.parametrize("key,expected", [
    ("claude", "claude"), ("codex", "codex"), ("gemini", "gemini")])
def test_each_platform_is_configured_by_its_own_command(key, expected, tmp_path):
    """Vendor commands know the format and preserve what is already configured. Writing
    TOML/JSON ourselves risks clobbering an unrelated MCP server.

    ``exe`` is pinned rather than resolved so the assertion describes the code and not the
    machine — on a developer laptop these resolve to absolute paths.
    """
    argv = plan(PLATFORMS[key], BASE, token_path("a1", tmp_path), exe=expected)["command"]
    assert argv[0] == expected and argv[1] == "mcp" and argv[2] == "add"


def test_the_launch_command_works_without_stepstitch_installed(tmp_path):
    """A connect command that requires a prior install is not a connect command."""
    argv = plan(PLATFORMS["claude"], BASE, token_path("a1", tmp_path))["command"]
    tail = " ".join(argv)
    assert "uvx" in tail and "stepstitch-service[mcp]" in tail
    assert tail.endswith("stepstitch mcp"), "should use the public entry point"


def test_the_launch_command_pins_an_interpreter_floor(tmp_path):
    """uvx resolves against whatever `python3` the machine has — on macOS still the system
    3.9 — and the resulting unresolvable graph reaches the user only as
    "Failed to connect". Found on a real machine during the agent trials."""
    from stepstitch_service.connect import MIN_PYTHON

    argv = plan(PLATFORMS["claude"], BASE, token_path("a1", tmp_path))["command"]
    assert "--python" in argv
    assert argv[argv.index("--python") + 1] == MIN_PYTHON


def test_a_failing_vendor_command_is_reported_not_swallowed(tmp_path):
    """A half-done connect sends someone hunting through config files — the exact
    experience this replaces."""
    result = apply(PLATFORMS["codex"], BASE, token_path("a1", tmp_path), runner=_fail)
    assert result["ok"] is False
    assert "already exists" in result["detail"]


def test_a_missing_vendor_binary_is_reported(tmp_path):
    def boom(*_a, **_k):
        raise OSError("No such file or directory: 'codex'")
    result = apply(PLATFORMS["codex"], BASE, token_path("a1", tmp_path), runner=boom)
    assert result["ok"] is False and "could not run" in result["detail"]


def test_a_successful_connect_says_where_it_wrote(tmp_path):
    result = apply(PLATFORMS["codex"], BASE, token_path("a1", tmp_path), runner=_ok)
    assert result["ok"] is True
    assert result["config"] == "~/.codex/config.toml"


# --- detection and verification -----------------------------------------------------------

def test_only_installed_platforms_are_offered():
    found = detect(lookup=lambda exe: "/usr/local/bin/claude" if exe == "claude" else None,
                   runnable=lambda path: False)
    assert [p.key for p in found] == ["claude"]


# --- finding a CLI that a desktop app never put on PATH ------------------------------------

def test_a_cli_bundled_in_a_desktop_app_counts_as_installed():
    """The ChatGPT app ships a complete, signed-in Codex CLI inside its bundle and puts
    nothing on PATH. A PATH-only check told the user Codex was not installed while they
    were actively using it."""
    bundled = "/Applications/ChatGPT.app/Contents/Resources/codex"
    exe = resolve(PLATFORMS["codex"],
                  lookup=lambda _: None,
                  runnable=lambda path: path == bundled)
    assert exe == bundled


def test_a_standalone_cli_on_path_always_wins():
    """Someone who installed the plain CLI chose it. A copy inside a desktop app must
    never shadow that — otherwise `connect` registers a different binary than the one the
    user runs, and the two can be different versions."""
    exe = resolve(PLATFORMS["codex"],
                  lookup=lambda name: "/usr/local/bin/codex" if name == "codex" else None,
                  runnable=lambda path: True)      # bundle present too, and ignored
    assert exe == "/usr/local/bin/codex"


def test_the_resolved_executable_is_the_one_that_gets_registered(tmp_path):
    """Registering with the bundle path and then checking a bare `codex` would report a
    working connection as broken, because the bare name does not exist."""
    bundled = "/Applications/ChatGPT.app/Contents/Resources/codex"
    entry = plan(PLATFORMS["codex"], BASE, token_path("a1", tmp_path), exe=bundled)
    assert entry["command"][0] == bundled
    assert entry["executable"] == bundled
    assert list_command(PLATFORMS["codex"], bundled) == [bundled, "mcp", "list"]


def test_an_uninstalled_platform_is_still_absent():
    """The fallbacks must not make everything look installed."""
    assert resolve(PLATFORMS["codex"],
                   lookup=lambda _: None, runnable=lambda _: False) is None


# --- Codex refuses every tool call in automation unless told not to ------------------------

CODEX_CONFIG = '''\
model = "gpt-5.6-sol"

[mcp_servers.playwright]
command = "npx"
args = ["@playwright/mcp@latest"]

[mcp_servers.stepstitch]
command = "uvx"
args = ["stepstitch", "mcp"]

[mcp_servers.stepstitch.env]
STEPSTITCH_BASE_URL = "http://127.0.0.1:8321/api/stepstitch/v1"

[projects."/some/repo"]
trust_level = "trusted"
'''


def test_codex_needs_permission_to_call_tools_without_a_human(tmp_path):
    """`codex exec` denies every MCP call with "user cancelled" while `codex mcp list`
    reports the server as enabled — connected interactively, refusing in automation."""
    cfg = tmp_path / "config.toml"
    cfg.write_text(CODEX_CONFIG)
    assert ensure_codex_tool_approval(cfg) == "added"
    assert CODEX_APPROVAL_LINE in cfg.read_text()


def test_only_stepstitch_own_table_is_touched(tmp_path):
    """Someone else's MCP server lives in this file. Granting it blanket tool approval
    because we happened to be editing nearby would be a real widening of their trust."""
    cfg = tmp_path / "config.toml"
    cfg.write_text(CODEX_CONFIG)
    ensure_codex_tool_approval(cfg)
    body = cfg.read_text()
    playwright = body.split("[mcp_servers.playwright]")[1].split("[mcp_servers.stepstitch]")[0]
    assert "default_tools_approval_mode" not in playwright
    assert body.count(CODEX_APPROVAL_LINE) == 1


def test_everything_else_in_the_file_survives(tmp_path):
    """The file is hand-maintained. Re-serialising it through a TOML writer would silently
    reformat comments and ordering that belong to the user."""
    cfg = tmp_path / "config.toml"
    cfg.write_text(CODEX_CONFIG)
    ensure_codex_tool_approval(cfg)
    body = cfg.read_text()
    for kept in ('model = "gpt-5.6-sol"', "[mcp_servers.playwright]",
                 '[projects."/some/repo"]', 'trust_level = "trusted"',
                 "[mcp_servers.stepstitch.env]"):
        assert kept in body, kept


def test_running_connect_twice_does_not_stack_the_key(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(CODEX_CONFIG)
    assert ensure_codex_tool_approval(cfg) == "added"
    assert ensure_codex_tool_approval(cfg) == "already set"
    assert cfg.read_text().count("default_tools_approval_mode") == 1


def test_a_missing_or_unreadable_config_is_reported_not_crashed(tmp_path):
    assert ensure_codex_tool_approval(tmp_path / "nope.toml").startswith("skipped")
    other = tmp_path / "other.toml"
    other.write_text("[mcp_servers.playwright]\ncommand = \"npx\"\n")
    assert ensure_codex_tool_approval(other) == "skipped: no stepstitch table"
    assert "default_tools_approval_mode" not in other.read_text()


def test_every_fallback_is_an_absolute_or_home_relative_path():
    """A bare name here would re-enter PATH lookup by the back door and could pick up
    whatever happens to be on PATH under that name."""
    for platform in PLATFORMS.values():
        for candidate in platform.fallbacks:
            assert candidate.startswith("/") or candidate.startswith("~"), candidate


def test_verification_asks_the_platform_rather_than_assuming():
    """Connecting is not the same as connected."""
    assert verify(["claude", "mcp", "list"], runner=_ok) is True
    assert verify(["claude", "mcp", "list"],
                  runner=lambda *a, **k: subprocess.CompletedProcess([], 0, "other-server", "")
                  ) is False


# --- dry run ------------------------------------------------------------------------------

def test_a_dry_run_shows_the_command_and_never_a_secret(tmp_path):
    path = write_token("a1", "ssa_topsecret", home=tmp_path)
    rendered = render_plan(plan(PLATFORMS["gemini"], BASE, path, exe="gemini"))
    assert "gemini mcp add" in rendered
    assert "ssa_topsecret" not in rendered
    assert str(path) in rendered
    assert "cannot record a verdict" in rendered


# --- verification must check that it WORKS, not that it is listed -------------------------

def _listing(text):
    return lambda *_a, **_k: subprocess.CompletedProcess([], 0, stdout=text, stderr="")


def test_a_registered_but_broken_server_is_not_reported_as_connected():
    """`claude mcp list` prints the server name even when it cannot start. A
    name-substring check therefore reports success for exactly the failure it exists to
    catch — which it did, for a config pointing at an engine without the entry point."""
    broken = "stepstitch: uvx --from stepstitch-service[mcp] stepstitch mcp - ✗ Failed to connect"
    assert verify(["claude", "mcp", "list"], runner=_listing(broken)) is False


def test_a_working_server_is_reported_as_connected():
    good = "stepstitch: uvx --from stepstitch-service[mcp] stepstitch mcp - ✓ Connected"
    assert verify(["claude", "mcp", "list"], runner=_listing(good)) is True


def test_the_launch_command_pins_the_engine_version(tmp_path):
    """An unpinned spec resolves to whatever is on PyPI today; `stepstitch mcp` only exists
    from the release that added it, so an unpinned config can register and then fail."""
    from stepstitch_service.connect import engine_version

    argv = plan(PLATFORMS["claude"], BASE, token_path("a1", tmp_path))["command"]
    spec = argv[argv.index("--from") + 1]
    installed = engine_version()
    if installed:
        assert spec == f"stepstitch-service[mcp]=={installed}"


# --- the command the error message recommends must exist --------------------------------

def test_the_connect_remedy_actually_parses():
    """The trap this closes: the no-token error's only remedy was `stepstitch start
    --connect claude` — a flag no parser defined, so the one recovery path the software
    offered was a command it could not read. Exit 1, remedy, exit 2, dead end."""
    from stepstitch_service.cli import build_parser

    args = build_parser().parse_args(["start", "--connect", "claude"])
    assert args.connect == "claude"
    for agent in ("codex", "gemini"):
        assert build_parser().parse_args(["start", "--connect", agent]).connect == agent


def test_connect_without_a_token_recommends_a_command_that_parses(monkeypatch, capsys):
    """Stronger than checking the flag exists once: extract the backticked command from
    the actual error output and feed it to the actual parser, so the message and the
    parser cannot drift apart again without this failing."""
    import re as _re

    from stepstitch_service.cli import build_parser, main

    monkeypatch.delenv("STEPSTITCH_ADMIN_TOKEN", raising=False)
    rc = main(["connect", "claude", "--host", "http://127.0.0.1:9"])
    assert rc == 1
    out = capsys.readouterr().out
    recommended = _re.search(r"`stepstitch ([^`]+)`", out)
    assert recommended, f"the error must offer a remedy: {out!r}"
    args = build_parser().parse_args(recommended.group(1).split())
    assert args.command == "start" and args.connect == "claude"


def test_connect_agent_registers_with_the_admin_token_it_was_handed(monkeypatch, tmp_path):
    """The seam start --connect uses: the credential arrives as an argument, not from the
    environment — one process starts the host, issues the token, registers the agent."""
    import stepstitch_service.cli as cli_mod
    from stepstitch_service.connect import Platform

    seen = {}

    def fake_http(url, method, headers, body):
        seen["url"], seen["auth"] = url, headers.get("Authorization")
        return 200, {"id": "agent-1", "token": "ssa_fake_token_for_testing"}

    platform = Platform(key="claude", label="Claude Code", executable="claude",
                        add_argv=lambda exe, env: [exe, "mcp", "add"],
                        config_hint="~/.claude.json")
    monkeypatch.setattr(cli_mod, "_http", fake_http)
    monkeypatch.setattr("stepstitch_service.connect.detect", lambda which=None: [platform])
    monkeypatch.setattr("stepstitch_service.connect.resolve", lambda p, **kw: "/bin/claude")
    monkeypatch.setattr("stepstitch_service.connect.write_token",
                        lambda agent_id, token, home=None: tmp_path / f"{agent_id}.token")
    monkeypatch.setattr("stepstitch_service.connect.apply",
                        lambda *a, **kw: {"ok": True, "config": "~/.claude.json"})
    monkeypatch.setattr("stepstitch_service.connect.verify", lambda *a, **kw: True)

    rc = cli_mod.connect_agent("http://127.0.0.1:8321", "the-admin-token", "claude")
    assert rc == 0
    assert seen["auth"] == "Bearer the-admin-token"
    assert seen["url"].endswith("/admin/agents")


def test_reconnecting_replaces_the_existing_registration(tmp_path):
    """Re-running connect must not be an error. The vendor CLIs refuse to add a name that
    exists, so the second `start --connect` on the same machine failed with "already
    exists" — punishing exactly the person re-pairing after a new port or a revoked token.
    Found live: the first journey run passed, the second failed."""
    from stepstitch_service.connect import SERVER_NAME, apply
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[1:3] == ["mcp", "add"] and len(calls) == 1:
            return subprocess.CompletedProcess(
                argv, 1, stdout="",
                stderr=f"MCP server {SERVER_NAME} already exists in user config")
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    platform = PLATFORMS["claude"]
    result = apply(platform, "http://127.0.0.1:8321/api/stepstitch/v1",
                   tmp_path / "t.token", runner=fake_run, exe="/bin/claude")
    assert result["ok"] is True, result
    assert calls[1][1:4] == ["mcp", "remove", SERVER_NAME], \
        "cleared through the vendor's own remove, never by editing its config"
    assert calls[2][1:3] == ["mcp", "add"], "then registered again"
