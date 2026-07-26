"""Keep docs/STATUS.md honest.

STATUS.md is the acceptance ledger: every row claims a capability is done *and* names the
test that proves it. That only means something if the claims stay true, and they did not —
the doc sat a month stale advertising "183 service + 31 host" tests against an actual
260 + 44, and naming a `test_stepstitch_*` reference-app proof that does not exist in this
repository. A ledger nobody verifies is just marketing.

These tests check the claims mechanically, so the doc fails CI instead of quietly rotting.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STATUS = REPO / "docs" / "STATUS.md"
TEST_ROOTS = (REPO / "service" / "tests", REPO / "server" / "tests")


def _doc() -> str:
    return STATUS.read_text(encoding="utf-8")


def _referenced_test_files(doc: str) -> set[str]:
    """Every test file the ledger names, expanding `test_a_{b,c}.py` brace groups."""
    names: set[str] = set()
    for pre, opts, post in re.findall(r"test_([a-z_]*)\{([a-z,_]+)\}([a-z_]*)\.py", doc):
        names.update(f"test_{pre}{o}{post}.py" for o in opts.split(","))
    names.update(re.findall(r"(test_[a-z0-9_]+\.py)", doc))
    return names


def test_every_named_proof_exists():
    """A row may not cite a test that isn't in the repo — that is how the old
    `test_stepstitch_*` reference-app claim survived for months."""
    have = {p.name for root in TEST_ROOTS for p in root.glob("*.py")}
    missing = sorted(n for n in _referenced_test_files(_doc()) if n not in have)
    assert not missing, f"STATUS.md cites tests that do not exist: {missing}"


def test_it_cites_a_meaningful_number_of_proofs():
    """Guards against someone 'fixing' the test above by deleting the citations."""
    assert len(_referenced_test_files(_doc())) >= 30


def test_stated_release_matches_package_json():
    version = json.loads((REPO / "package.json").read_text())["version"]
    assert f"Current release: {version}" in _doc(), (
        f"STATUS.md does not state the current release ({version}); "
        "release-please bumps package.json but cannot edit prose."
    )


def stated_count(label: str) -> int:
    """The number the Gates table claims for a suite."""
    row = re.search(rf"^\|\s*{label}\b[^|]*\|\s*\*\*(\d+)\*\*", _doc(), re.M)
    assert row, f"no Gates row for {label} in STATUS.md"
    return int(row.group(1))


def collected_count(suite: str) -> int:
    """Ask pytest itself how many tests live under `suite`.

    Only ever call this for the suite the *current* environment owns. Counting another
    suite from here is unreliable: CI's Service job does not install the host's
    dependencies, so collecting server/tests there silently reports 36 instead of 45 —
    modules that cannot import are not counted. That produced a red build on the very
    commit that introduced this file, which is the whole argument for the split.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(REPO / suite), "--collect-only", "-q",
         "--no-header", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=REPO, timeout=180,
    )
    # Gate on the exit code, never on the word "error" appearing in stdout: `-q` prints
    # every collected test id, and plenty of them are named things like
    # `test_api_error_metadata`, so a substring check matches always and silently skips.
    # pytest exits 0 on a clean collection and 2 when collection itself fails.
    m = re.search(r"(\d+)\s+tests?\s+collected", proc.stdout)
    if proc.returncode != 0 or not m:
        pytest.skip(f"cannot collect {suite} here (rc={proc.returncode}): {proc.stdout[-200:]}")
    return int(m.group(1))


def test_stated_service_count_is_real():
    """The Service row must match what pytest collects here.

    The Host row is checked by `server/tests/test_status_ledger_host.py`, which runs in the job
    that actually has the host's dependencies installed.
    """
    stated, actual = stated_count("Service"), collected_count("service/tests")
    assert stated == actual, (
        f"STATUS.md says Service has {stated} tests; pytest collects {actual}. "
        "Update the Gates table."
    )
