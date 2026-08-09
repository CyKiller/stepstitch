"""Packaging metadata honesty: the license the wheel claims is the license it carries.

Two facts pinned here, found while converting to PEP 639 (deadline: the deprecated
table form stops building in 2027):

- ``license`` must be the SPDX expression string, with ``license-files`` naming a real
  file — the metadata form every index and scanner reads going forward;
- ``service/LICENSE`` must be byte-identical to the repository root's ``LICENSE``:
  before this file existed the wheel declared Apache-2.0 while shipping no license
  text at all, and a copy that drifts would be worse than the gap it closed.
"""
from __future__ import annotations

from pathlib import Path

SERVICE = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE.parent


def test_the_license_metadata_is_a_pep_639_spdx_expression():
    pyproject = (SERVICE / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = "Apache-2.0"' in pyproject
    assert 'license-files = ["LICENSE"]' in pyproject
    assert "license = { text" not in pyproject, "the deprecated table form is back"
    assert "setuptools>=77" in pyproject, "PEP 639 needs the setuptools floor"


def test_the_packaged_license_is_the_repository_license_byte_for_byte():
    packaged = (SERVICE / "LICENSE").read_bytes()
    canonical = (REPO_ROOT / "LICENSE").read_bytes()
    assert packaged == canonical, (
        "service/LICENSE drifted from the repository LICENSE — re-copy it; the wheel "
        "must carry exactly the license the project is under"
    )
