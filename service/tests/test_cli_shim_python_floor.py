"""The launcher must tell uv which Python to use, and it must be the engine's floor.

Found by running the PUBLISHED 0.10.0 the way a stranger would, on a Mac. `npx stepstitch
start` died with:

    Because the current Python version (3.9.7) does not satisfy Python>=3.10 and you
    require stepstitch-service[local]==0.10.0, we can conclude that your requirements
    are unsatisfiable.

The shim ran `uvx --from <spec> stepstitch ...` with no `--python`, so uv resolved against
whatever interpreter it happened to prefer. On a stock macOS that is /usr/bin/python3 —
3.9 — so the very machine the shim exists to serve ("uv manages the Python; the developer
needs nothing else") is the machine it failed on. The message blames the package, not the
environment, so it reads as a broken release.

Why nothing caught it: the release pipeline's stranger job runs `actions/setup-python` with
3.11 BEFORE invoking npx, so uv's default interpreter is already above the floor and the
missing flag is invisible. A gate that provisions the very condition it is meant to test
cannot fail. That makes this the third shim defect to ship green — the file's own comments
record the registry 404 and the missing `[local]` extra before it.

These tests read the shim source rather than executing it: running uvx needs a network and
a real uv, which is exactly the coupling that let the gate lie.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SHIM = REPO / "packages" / "cli-shim" / "bin" / "stepstitch.js"
PYPROJECT = REPO / "service" / "pyproject.toml"


def _shim() -> str:
    return SHIM.read_text(encoding="utf-8")


def test_the_launcher_passes_a_python_constraint_to_uv():
    """Without this flag uv picks the ambient interpreter and the install fails."""
    src = _shim()
    spawn = re.search(r"spawnSync\(\s*uvx,\s*\[(.*?)\]", src, re.S)
    assert spawn, "could not find the uvx spawnSync call — did the shim change shape?"
    argv = spawn.group(1)
    assert "'--python'" in argv or '"--python"' in argv, (
        "the shim invokes uvx without --python, so uv resolves against whatever "
        "interpreter it prefers; on a stock macOS that is 3.9 and the install fails"
    )


def test_the_constraint_precedes_the_from_spec():
    """uv reads --python as a global option; behind --from it is passed to the tool."""
    argv = re.search(r"spawnSync\(\s*uvx,\s*\[(.*?)\]", _shim(), re.S).group(1)
    assert argv.index("--python") < argv.index("--from"), (
        "--python must come before --from, or uv treats it as an argument to the tool"
    )


def test_the_floor_matches_the_engine_it_launches():
    """A shim pinning >=3.9 while the engine needs >=3.10 fails at resolve time, and a
    shim pinning >=3.12 refuses Pythons the engine supports. One source of truth."""
    declared = re.search(r'^requires-python\s*=\s*"([^"]+)"',
                         PYPROJECT.read_text(encoding="utf-8"), re.M)
    assert declared, "service/pyproject.toml must declare requires-python"

    floor = re.search(r"PYTHON_FLOOR\s*=\s*'([^']+)'", _shim())
    assert floor, "the shim must name its floor in one constant, not inline in argv"
    assert floor.group(1) == declared.group(1), (
        f"shim pins Python {floor.group(1)!r} but the engine requires "
        f"{declared.group(1)!r} — update both or the launcher lies about what it supports"
    )
