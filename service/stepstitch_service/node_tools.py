"""How this process starts Node's tools: the one place that knows Windows differs.

On Windows ``npx`` is ``npx.cmd``, a batch file. With ``shell=False`` CreateProcess will not
find it by its bare name, so a bare ``["npx", ...]`` fails there with FileNotFoundError on a
machine that has Node and Playwright installed. Running the batch file by its full path
would work, but it hands every argument to cmd.exe's parser on the way.

So on Windows the command is Node itself running npm's ``npx-cli.js``, which is all
``npx.cmd`` does. npm ships beside ``node.exe`` in the official installer and nvm-windows.
Only when it is not there (volta, a separately upgraded global npm) does this fall back to
the full path of ``npx.cmd``. When nothing is found, the bare name is kept, so the caller's
"install Node" error still fires. Every other platform gets ``npx``, unchanged.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List

_WINDOWS = os.name == "nt"


def npx_argv(*args: str) -> List[str]:
    """The argv that runs ``npx <args>`` on this platform without a shell."""
    if not _WINDOWS:
        return ["npx", *args]
    node = shutil.which("node")
    if node:
        cli = Path(node).parent / "node_modules" / "npm" / "bin" / "npx-cli.js"
        if cli.is_file():
            return [node, str(cli), *args]
    npx = shutil.which("npx")
    return [npx or "npx", *args]
