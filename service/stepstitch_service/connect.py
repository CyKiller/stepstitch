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

# Matches requires-python in service/pyproject.toml. Kept as a specifier rather than an
# exact version so uv may use anything new enough that is already installed.
MIN_PYTHON = ">=3.10"


@dataclass(frozen=True)
class Platform:
    """One agent client: how to detect it, and how it likes to be told about a server."""

    key: str
    label: str
    executable: str
    # Native `mcp add` argv, built once the executable and the values are known. Preferred
    # over writing files because the vendor's own command preserves what is already there.
    add_argv: Callable[[str, Dict[str, str]], List[str]]
    config_hint: str
    # Where the CLI also lives when it is not on PATH. A desktop app can ship a complete,
    # authenticated CLI inside its bundle and never put it on PATH — the ChatGPT app does
    # exactly this with Codex — so a PATH-only check reports "not installed" on a machine
    # where the agent is installed, signed in, and working. Checked only after PATH, so a
    # standalone install always wins and someone who prefers the plain CLI is unaffected.
    fallbacks: Sequence[str] = ()


def _claude_add(exe: str, env: Dict[str, str]) -> List[str]:
    argv = [exe, "mcp", "add", SERVER_NAME, "--scope", "user"]
    for key, value in env.items():
        argv += ["--env", f"{key}={value}"]
    return argv + ["--"] + list(_launch_command())


def _codex_add(exe: str, env: Dict[str, str]) -> List[str]:
    argv = [exe, "mcp", "add", SERVER_NAME]
    for key, value in env.items():
        argv += ["--env", f"{key}={value}"]
    return argv + ["--"] + list(_launch_command())


def _gemini_add(exe: str, env: Dict[str, str]) -> List[str]:
    argv = [exe, "mcp", "add", SERVER_NAME]
    for key, value in env.items():
        argv += ["-e", f"{key}={value}"]
    return argv + ["--"] + list(_launch_command())


# Bundled-CLI locations, tried in order and only when PATH has nothing. `~` is expanded at
# lookup time rather than import time so a test can point HOME somewhere harmless.
_CODEX_BUNDLED: Sequence[str] = (
    "/Applications/ChatGPT.app/Contents/Resources/codex",          # macOS, system-wide
    "~/Applications/ChatGPT.app/Contents/Resources/codex",         # macOS, per-user
    "~/AppData/Local/Programs/ChatGPT/resources/codex.exe",        # Windows
    "/opt/ChatGPT/resources/codex",                                # Linux
)

_CLAUDE_BUNDLED: Sequence[str] = (
    "~/.local/bin/claude",
    "~/.claude/local/claude",
)

PLATFORMS: Dict[str, Platform] = {
    "claude": Platform("claude", "Claude Code", "claude", _claude_add,
                       "~/.claude.json or .mcp.json", _CLAUDE_BUNDLED),
    "codex": Platform("codex", "Codex (CLI, ChatGPT app, IDE)", "codex", _codex_add,
                      "~/.codex/config.toml", _CODEX_BUNDLED),
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
    spec = override
    if not spec:
        resolved = version or engine_version()
        spec = (f"stepstitch-service[mcp]=={resolved}" if resolved
                else "stepstitch-service[mcp]")
    # Pin the interpreter floor. uvx otherwise resolves against whatever `python3` the
    # machine happens to have — on macOS that is still the system 3.9 — and the failure is
    # an unresolvable dependency graph that the agent client surfaces only as
    # "Failed to connect". Naming the floor turns an opaque dead end into uv fetching a
    # suitable Python by itself.
    return ["uvx", "--python", MIN_PYTHON, "--from", spec, "stepstitch", "mcp"]


# Codex asks a human before every MCP tool call unless the server says otherwise. In an
# interactive session that is a sensible default; in `codex exec` — the non-interactive mode
# an automated fix loop actually uses — there is nobody to ask, so every call comes back
# `user cancelled MCP tool call` while `codex mcp list` cheerfully reports the server as
# enabled. Registered, listed, and refusing everything.
#
# Auto-approving StepStitch's tools is safe *here specifically* because the limit on what
# the agent may do is the token's scope, enforced server-side, not the client's prompt. A
# `repros` token cannot record a verdict however many times it is called. Approving reads
# that were already going to be permitted is not a widening of anything.
#
# Written as a single inserted line under the table `connect` itself just created, rather
# than by re-serialising the file: `~/.codex/config.toml` is hand-maintained and full of
# other people's servers, comments and formatting, and a round-trip through a TOML writer
# would quietly rewrite all of it.
CODEX_APPROVAL_LINE = 'default_tools_approval_mode = "approve"'
_CODEX_TABLE = f"[mcp_servers.{SERVER_NAME}]"


def ensure_codex_tool_approval(config_path: Path) -> str:
    """Add the approval key to StepStitch's own table. Returns what happened."""
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return "skipped: config not readable"
    lines = text.splitlines()
    try:
        header = next(i for i, line in enumerate(lines) if line.strip() == _CODEX_TABLE)
    except StopIteration:
        return "skipped: no stepstitch table"
    # Only within our own table — the next table header ends it.
    end = len(lines)
    for i in range(header + 1, len(lines)):
        if lines[i].lstrip().startswith("["):
            end = i
            break
    if any(line.strip().startswith("default_tools_approval_mode")
           for line in lines[header + 1:end]):
        return "already set"
    lines.insert(header + 1, CODEX_APPROVAL_LINE)
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "added"


def _runnable(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def resolve(platform: Platform,
            lookup: Optional[Callable[[str], Optional[str]]] = None,
            runnable: Optional[Callable[[str], bool]] = None) -> Optional[str]:
    """The command to actually invoke for this platform, or None if it is not installed.

    PATH first, always: a standalone CLI is what the user chose to install, and a bundled
    copy inside a desktop app should never shadow it. Only when PATH has nothing do the
    bundle locations get a look — otherwise ``connect codex`` tells someone Codex is
    missing while their signed-in Codex sits inside ChatGPT.app.
    """
    find = lookup or shutil.which
    on_path = find(platform.executable)
    if on_path:
        return on_path
    can_run = runnable or _runnable
    for candidate in platform.fallbacks:
        expanded = os.path.expanduser(candidate)
        if can_run(expanded):
            return expanded
    return None


def detect(which: Optional[str] = None,
           lookup: Optional[Callable[[str], Optional[str]]] = None,
           runnable: Optional[Callable[[str], bool]] = None) -> List[Platform]:
    """Which agent clients are actually installed. Injectable lookups for testing."""
    wanted = [PLATFORMS[which]] if which else list(PLATFORMS.values())
    return [p for p in wanted if resolve(p, lookup, runnable)]


def list_command(platform: Platform, exe: Optional[str] = None) -> List[str]:
    """The platform's own 'is it working?' command, using the resolved executable."""
    return [exe or resolve(platform) or platform.executable, "mcp", "list"]


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


def plan(platform: Platform, base_url: str, token_file: Path,
         exe: Optional[str] = None) -> Dict[str, Any]:
    """What ``connect`` would do, without doing it. Backs ``--dry-run``.

    The dry run shows the *resolved* executable — an absolute path when the CLI came from
    an app bundle. Printing a bare ``codex`` that the reader cannot run themselves would
    make the preview a worse guide than the thing it previews.
    """
    env = connection_env(base_url, token_file)
    resolved = exe or resolve(platform) or platform.executable
    return {
        "platform": platform.key,
        "label": platform.label,
        "command": platform.add_argv(resolved, env),
        "config": platform.config_hint,
        "env": env,
        "scope": AGENT_SCOPE,
        "executable": resolved,
    }


def apply(platform: Platform, base_url: str, token_file: Path,
          runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
          exe: Optional[str] = None) -> Dict[str, Any]:
    """Register the server with the platform's own command.

    A non-zero exit is reported, never swallowed: a connect that silently half-worked would
    send someone hunting through config files, which is the exact experience this replaces.
    """
    run = runner or subprocess.run
    resolved = exe or resolve(platform) or platform.executable
    argv = platform.add_argv(resolved, connection_env(base_url, token_file))
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
