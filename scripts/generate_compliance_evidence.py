#!/usr/bin/env python3
"""Generate COMPLIANCE-EVIDENCE.md from the live ScrubPolicy.

Usage:
    PYTHONPATH=service python scripts/generate_compliance_evidence.py

Writes the packet to the repo root. The content is derived entirely from
``stepstitch_service`` so it cannot drift from what the scrubber enforces; the drift
guard in ``service/tests/test_compliance.py`` keeps the committed file in sync.
"""
from __future__ import annotations

import pathlib
import sys

# Allow running from the repo root without installing the package.
_SERVICE = pathlib.Path(__file__).resolve().parents[1] / "service"
if _SERVICE.is_dir() and str(_SERVICE) not in sys.path:
    sys.path.insert(0, str(_SERVICE))

from stepstitch_service.compliance import build_evidence  # noqa: E402

OUTPUT = pathlib.Path(__file__).resolve().parents[1] / "COMPLIANCE-EVIDENCE.md"


def main() -> int:
    OUTPUT.write_text(build_evidence(), encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
