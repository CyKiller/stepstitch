"""Connect a coding agent to StepStitch without anyone hand-editing JSON or TOML.

Three platforms, three config formats, three file locations, and one of them (Codex) is
TOML shared across the ChatGPT desktop app, the CLI and the IDE extension. Asking a
developer to get that right by hand is asking them to clobber an existing MCP server on a
bad day — so this shells out to each vendor's **own** ``mcp add`` command, which knows the
format and preserves what is already there.

**The token never goes in the config file.** Agent config files get read by editors, synced
by dotfile managers, and pasted into bug reports; a bearer token sitting in one leaks by
ordinary accident rather than by attack. The config carries ``STEPSTITCH_TOKEN_FILE``, a
path to an owner-readable file, and ``stepstitch mcp`` reads it at launch. Revoking is
deleting one file. Nothing is ever passed in argv, where it would be visible to every other
process on the machine via ``ps``.

**The agent gets ``repros``, never ``verify``.** It may read everything it needs to
understand and fix a failure, and it may not write the evidence that says its fix worked.
That separation is the product.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

# The scope `connect` issues. A coding agent needs the Safe Agent Packet and the
# reproduction; it must never be able to record a verdict (see host/agents.py).
AGENT_SCOPE = "repros"

SERVER_NAME = "stepstitch"


@dataclass(frozen=True)
class Platform:
    """One agent client: how to detect it, and how it likes to be told about a server."""

    key: str
    label: str
    executable: str
    # Native `mcp add` argv, built once the values are known. Preferred over writing files
    # because the vendor's own command preserves whatever else is configured.
    add_argv: Callable[[Dict[str, str]], List[str]]
    config_hint: str


def _claude_add(env: Dict[str, str]) -> List[str]:
    argv = ["claude", "mcp", "add", SERVER_NAME, "--scope", "user"]
    for key, value in env.items():
        argv += ["--env", f"{key}={value}"]
    return argv + ["--"] + list(_launch_command())


def _codex_add(env: Dict[str, str]) -> List[str]:
    argv = ["codex", "mcp", "add", SERVER_NAME]
    for key, value in env.items():
        argv += ["--env", f"{key}={value}"]
    return argv + ["--"] + list(_launch_command())


def _gemini_add(env: Dict[str, str]) -> List[str]:
    argv = ["gemini", "mcp", "add", SERVER_NAME]
    for key, value in env.items():
        argv += ["-e", f"{key}={value}"]
    return argv + ["--"] + list(_launch_command())


PLATFORMS: Dict[str, Platform] = {
    "claude": Platform("claude", "Claude Code", "claude", _claude_add,
                       "~/.claude.json or .mcp.json"),
    "codex": Platform("codex", "Codex (ChatGPT app, CLI, IDE)", "codex", _codex_add,
                      "~/.codex/config.toml"),
    "gemini": Platform("gemini", "Gemini CLI / Antigravity", "gemini", _gemini_add,
                       "~/.gemini/config/mcp_config.json"),
}


def engine_version() -> Optional[str]:
    """The installed engine version, so a config pins the engine it was tested with."""
    try:
        from importlib.metadata import version as _version

        return _version("stepstitch-service")
    except Exception:
        return None


def _launch_command(version: Optional[str] = None) -> Sequence[str]:
    """How an agent client should start the MCP server.

    ``uvx --from`` so it works on a machine that has never installed StepStitch — a connect
    command that requires a prior install is not a connect command.

    The version is PINNED, and that matters more than it looks: an unpinned spec resolves
    to whatever is currently on PyPI, and `stepstitch mcp` only exists from the release
    that introduced it. Connecting against an older published engine writes a config that
    registers cleanly and then fails to launch — which is how this was found.
    """
    # An escape hatch for working against unreleased code — the agent trials have to run
    # before the release that carries `stepstitch mcp`, and pointing uvx at a local
    # checkout is the only honest way to do that. Not a user-facing feature.
    override = os.environ.get("STEPSTITCH_MCP_SPEC")
    if override:
        return ["uvx", "--from", override, "stepstitch", "mcp"]
    resolved = version or engine_version()
    spec = (f"stepstitch-service[mcp]=={resolved}" if resolved
            else "stepstitch-service[mcp]")
    return ["uvx", "--from", spec, "stepstitch", "mcp"]


def detect(which: Optional[str] = None,
           lookup: Optional[Callable[[str], Optional[str]]] = None) -> List[Platform]:
    """Which agent clients are actually installed. ``lookup`` is injected for testing."""
    find = lookup or shutil.which
    wanted = [PLATFORMS[which]] if which else list(PLATFORMS.values())
    return [p for p in wanted if find(p.executable)]


def token_path(agent_id: str, home: Optional[Path] = None) -> Path:
    return (home or Path.home()) / ".stepstitch" / "agents" / f"{agent_id}.token"


def write_token(agent_id: str, token: str, home: Optional[Path] = None) -> Path:
    """Store the token owner-readable, and never anywhere else.

    Created with 0600 *before* the secret is written, not chmod'ed after: between an
    open() and a chmod() there is a window where the file is world-readable, and a token is
    exactly the thing not to leave lying around during it.
    """
    path = token_path(agent_id, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    handle = os.open(path, flags, stat.S_IRUSR | stat.S_IWUSR)
    try:
        os.write(handle, token.encode("utf-8"))
    finally:
        os.close(handle)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)   # a pre-existing file may differ
    except OSError:
        pass
    return path


def connection_env(base_url: str, token_file: Path) -> Dict[str, str]:
    """What the agent's config carries. Note what is absent: the token itself."""
    return {
        "STEPSTITCH_BASE_URL": base_url.rstrip("/"),
        "STEPSTITCH_TOKEN_FILE": str(token_file),
    }


def plan(platform: Platform, base_url: str, token_file: Path) -> Dict[str, Any]:
    """What ``connect`` would do, without doing it. Backs ``--dry-run``."""
    env = connection_env(base_url, token_file)
    return {
        "platform": platform.key,
        "label": platform.label,
        "command": platform.add_argv(env),
        "config": platform.config_hint,
        "env": env,
        "scope": AGENT_SCOPE,
    }


def apply(platform: Platform, base_url: str, token_file: Path,
          runner: Optional[Callable[..., subprocess.CompletedProcess]] = None
          ) -> Dict[str, Any]:
    """Register the server with the platform's own command.

    A non-zero exit is reported, never swallowed: a connect that silently half-worked would
    send someone hunting through config files, which is the exact experience this replaces.
    """
    run = runner or subprocess.run
    argv = platform.add_argv(connection_env(base_url, token_file))
    try:
        proc = run(argv, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "platform": platform.key,
                "detail": f"could not run `{argv[0]} mcp add`: {exc}"}
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:400]
        return {"ok": False, "platform": platform.key,
                "detail": f"`{' '.join(argv[:3])}` failed: {detail}"}
    return {"ok": True, "platform": platform.key, "label": platform.label,
            "config": platform.config_hint}


# Words the vendor CLIs print when a server is registered but does NOT work. Checking for
# the server's NAME alone is not a check: `claude mcp list` prints
# "stepstitch: uvx … - ✗ Failed to connect" for a completely broken server, so a
# name-substring test reports success for the exact failure it was written to catch.
_BROKEN_MARKERS = ("failed to connect", "✗", "error")


def verify(list_argv: Sequence[str],
           runner: Optional[Callable[..., subprocess.CompletedProcess]] = None) -> bool:
    """Ask the platform whether the server actually WORKS, not whether it is listed.

    Registration and connection are different facts. A config can be written perfectly and
    still launch a command that cannot start — which is precisely what happens when the
    pinned engine version predates the entry point the config names.
    """
    run = runner or subprocess.run
    try:
        proc = run(list(list_argv), capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    for line in (proc.stdout or "").splitlines():
        if SERVER_NAME not in line:
            continue
        lowered = line.lower()
        return not any(marker in lowered for marker in _BROKEN_MARKERS)
    return False


def render_plan(entry: Dict[str, Any]) -> str:
    """Human-readable dry run. Shows the token FILE, never a token."""
    return (
        f"  {entry['label']}\n"
        f"    config : {entry['config']}\n"
        f"    scope  : {entry['scope']} (read the failure and the reproduction; "
        f"cannot record a verdict)\n"
        f"    command: {' '.join(entry['command'])}\n"
        f"    env    : {json.dumps(entry['env'])}\n"
    )
