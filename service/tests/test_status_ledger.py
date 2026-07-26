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


def _collected(path: Path) -> int:
    """Ask pytest itself how many tests live under `path`."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(path), "--collect-only", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=REPO,
        env={"PYTHONPATH": str(REPO / "service"), "PATH": "/usr/bin:/bin"},
        timeout=180,
    )
    m = re.search(r"(\d+)\s+tests?\s+collected", proc.stdout)
    if not m:
        pytest.skip(f"could not collect {path.name}: {proc.stdout[-200:]}")
    return int(m.group(1))


@pytest.mark.parametrize("suite,label", [("service/tests", "Service"), ("server/tests", "Host")])
def test_stated_test_counts_are_real(suite: str, label: str):
    """The counts in the Gates table must match what pytest actually collects.

    Runs pytest in a subprocess purely to count — the alternative is a number in prose
    that drifts the moment anyone adds a test, which is precisely what happened.
    """
    row = re.search(rf"^\|\s*{label}\b[^|]*\|\s*\*\*(\d+)\*\*", _doc(), re.M)
    assert row, f"no Gates row for {label} in STATUS.md"
    stated = int(row.group(1))
    actual = _collected(REPO / suite)
    assert stated == actual, (
        f"STATUS.md says {label} has {stated} tests; pytest collects {actual}. "
        "Update the Gates table."
    )
