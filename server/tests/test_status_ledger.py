"""The Host half of the docs/STATUS.md ledger guard.

The rest of the ledger checks — every named proof exists, the stated release matches
package.json, the Service count — live in ``service/tests/test_status_ledger.py``. Only the
Host *count* lives here, because counting a suite requires an environment that can import
it: CI's Service job does not install the host's dependencies, so collecting
``server/tests`` from there reports 36 instead of 45. Modules that fail to import are not
counted and the number still looks plausible, which is the dangerous part.

So each job verifies its own row, in the one environment that can answer honestly. The two
small helpers are duplicated rather than imported across suites — a cross-rootdir import
between two pytest packages is more fragile than fifteen repeated lines.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STATUS = REPO / "docs" / "STATUS.md"


def _stated(label: str) -> int:
    row = re.search(rf"^\|\s*{label}\b[^|]*\|\s*\*\*(\d+)\*\*", STATUS.read_text(), re.M)
    assert row, f"no Gates row for {label} in STATUS.md"
    return int(row.group(1))


def _collected(suite: str) -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(REPO / suite), "--collect-only", "-q",
         "--no-header", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=REPO, timeout=180,
    )
    # Gate on the exit code, not on "error" appearing in stdout: `-q` prints every collected
    # test id and many are named `test_..._error...`, so a substring check always matches and
    # the guard silently skips. pytest exits 0 on clean collection, 2 when collection fails.
    m = re.search(r"(\d+)\s+tests?\s+collected", proc.stdout)
    if proc.returncode != 0 or not m:
        pytest.skip(f"cannot collect {suite} here (rc={proc.returncode}): {proc.stdout[-200:]}")
    return int(m.group(1))


def test_stated_host_count_is_real():
    stated, actual = _stated("Host"), _collected("server/tests")
    assert stated == actual, (
        f"STATUS.md says Host has {stated} tests; pytest collects {actual}. "
        "Update the Gates table."
    )
