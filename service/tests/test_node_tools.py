"""How StepStitch launches Node's tools on each platform.

On Windows `npx` is a batch file (`npx.cmd`). With ``shell=False`` CreateProcess cannot find
it by its bare name, so every reproduction, every doctor probe and every browser check failed
there with "npx not found" on a machine that had Node and Playwright installed. These tests
pin the command each platform gets, and the last one launches the real tool where it can.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from stepstitch_service import node_tools
from stepstitch_service.node_tools import npx_argv
from stepstitch_service.runner import child_env


def _windows(monkeypatch, found):
    """Pretend to be Windows, with ``found`` answering which(name)."""
    monkeypatch.setattr(node_tools, "_WINDOWS", True)
    monkeypatch.setattr(node_tools.shutil, "which", lambda name: found.get(name))


def test_posix_keeps_the_bare_npx_command(monkeypatch):
    monkeypatch.setattr(node_tools, "_WINDOWS", False)
    assert npx_argv("playwright", "--version") == ["npx", "playwright", "--version"]


def test_windows_runs_npm_bundled_npx_with_node_itself(monkeypatch, tmp_path):
    # The layout of the official installer and nvm-windows: npm ships beside node.exe.
    node = tmp_path / "node.exe"
    node.write_bytes(b"")
    cli = tmp_path / "node_modules" / "npm" / "bin" / "npx-cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("// npx")
    _windows(monkeypatch, {"node": str(node), "npx": str(tmp_path / "npx.CMD")})

    argv = npx_argv("--no-install", "playwright", "test")

    # node.exe is a real executable, so no batch file and no cmd.exe parser sit between
    # the runner and Playwright.
    assert argv == [str(node), str(cli), "--no-install", "playwright", "test"]


def test_windows_falls_back_to_the_full_path_of_npx_cmd(monkeypatch, tmp_path):
    # Shims (volta, a global npm upgrade) keep npx somewhere other than beside node.exe.
    node = tmp_path / "bin" / "node.exe"
    node.parent.mkdir()
    node.write_bytes(b"")
    npx = tmp_path / "npm" / "npx.cmd"
    _windows(monkeypatch, {"node": str(node), "npx": str(npx)})

    assert npx_argv("playwright", "--version") == [str(npx), "playwright", "--version"]


def test_windows_without_node_keeps_the_bare_name_so_the_launch_error_is_honest(monkeypatch):
    # Nothing found: the caller's FileNotFoundError handling ("install Node 18+") must still
    # fire, so the command stays the bare name rather than an invented path.
    _windows(monkeypatch, {})
    assert npx_argv("playwright") == ["npx", "playwright"]


@pytest.mark.skipif(os.name != "nt" or shutil.which("node") is None,
                    reason="launches the real npx on a Windows machine with Node")
def test_npx_really_launches_on_windows_with_the_runner_environment():
    # The end-to-end claim: the exact command, the exact allowlisted environment and
    # shell=False — what a reproduction run uses — start npx and get an answer.
    proc = subprocess.run(npx_argv("--version"), env=child_env(), capture_output=True,
                          text=True, timeout=60, shell=False)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip()[0].isdigit()


def test_the_runner_and_doctor_launch_through_the_same_helper():
    # One place knows the platform difference. A new `["npx", ...]` literal elsewhere is
    # the bug coming back.
    service = Path(node_tools.__file__).parent
    offenders = []
    for path in service.rglob("*.py"):
        if path.name == "node_tools.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if '["npx"' in line.replace(" ", ""):
                offenders.append(f"{path.relative_to(service)}:{number}")
    assert offenders == []
