"""Host helper: which direct-write targets are enabled.

Direct-write is off unless ``STEPSTITCH_DIRECT_WRITE`` lists targets, e.g.
``STEPSTITCH_DIRECT_WRITE=servicenow,salesforce``. The host reads this, builds the matching
``RecordWriter`` instances (wiring in credentials), and injects them into the router. The
core never reads credentials.
"""
from __future__ import annotations

import os
from typing import List, Mapping, Optional


def enabled_targets_from_env(env: Optional[Mapping[str, str]] = None) -> List[str]:
    """Parse ``STEPSTITCH_DIRECT_WRITE`` into a list of target names (possibly empty)."""
    raw = (env if env is not None else os.environ).get("STEPSTITCH_DIRECT_WRITE", "")
    return [t.strip() for t in raw.split(",") if t.strip()]
