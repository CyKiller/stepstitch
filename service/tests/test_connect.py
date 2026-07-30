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
    PLATFORMS,
    apply,
    connection_env,
    detect,
    plan,
    render_plan,
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
        argv = platform.add_argv(connection_env(BASE, path))
        assert "ssa_verysecret" not in " ".join(argv)


# --- native vendor commands ---------------------------------------------------------------

@pytest.mark.parametrize("key,expected", [
    ("claude", "claude"), ("codex", "codex"), ("gemini", "gemini")])
def test_each_platform_is_configured_by_its_own_command(key, expected, tmp_path):
    """Vendor commands know the format and preserve what is already configured. Writing
    TOML/JSON ourselves risks clobbering an unrelated MCP server."""
    argv = plan(PLATFORMS[key], BASE, token_path("a1", tmp_path))["command"]
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
    found = detect(lookup=lambda exe: "/usr/local/bin/claude" if exe == "claude" else None)
    assert [p.key for p in found] == ["claude"]


def test_verification_asks_the_platform_rather_than_assuming():
    """Connecting is not the same as connected."""
    assert verify(["claude", "mcp", "list"], runner=_ok) is True
    assert verify(["claude", "mcp", "list"],
                  runner=lambda *a, **k: subprocess.CompletedProcess([], 0, "other-server", "")
                  ) is False


# --- dry run ------------------------------------------------------------------------------

def test_a_dry_run_shows_the_command_and_never_a_secret(tmp_path):
    path = write_token("a1", "ssa_topsecret", home=tmp_path)
    rendered = render_plan(plan(PLATFORMS["gemini"], BASE, path))
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
