"""Deployment profiles — a named privacy/scrub posture, switchable by config.

A profile is the human-facing compliance posture (what is captured, what is never
captured, how free text and forbidden keys are handled) *plus* the knobs that build
the server-side :class:`ScrubPolicy`. The dict definitions here are the single source
of truth; the repo-root ``profiles/*.json`` files are generated to match and are
guarded against drift by ``service/tests/test_profiles.py``.

Default deployment posture is ``financial-services-enterprise`` (matches the scrubber
default). A host selects a profile and passes ``policy_from_profile(...)`` to
``create_stepstitch_router(scrub_policy=...)``.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .scrubber import ScrubPolicy, derive_policy

__all__ = [
    "PROFILES",
    "available_profiles",
    "get_profile",
    "policy_from_profile",
    "load_profile",
]

# --- Canonical profile definitions (single source of truth) ------------------

PROFILES: Dict[str, Dict[str, Any]] = {
    "financial-services-enterprise": {
        "name": "financial-services-enterprise",
        "description": "Strict NPI posture for regulated financial operations. "
                       "Free text is PII-scrubbed; forbidden keys are dropped.",
        "scrub": {"free_text": "scrub", "max_text_len": 280, "reject_on_forbidden": False},
        "posture": {
            "screenshots": False, "video": False, "dom_text": False,
            "input_values": False, "raw_urls": False,
            "request_bodies": False, "response_bodies": False,
            "console_messages": False, "network_headers": False,
            "consent_required": True, "respect_gpc": True, "respect_dnt": True,
            "admin_reads_audited": True, "right_to_delete": True,
            "retention_enabled": True, "kill_switch": True,
        },
    },
    "healthcare-strict": {
        "name": "healthcare-strict",
        "description": "Maximum strictness for PHI-adjacent surfaces. Free text is "
                       "dropped entirely and forbidden keys hard-reject the POST (422).",
        "scrub": {"free_text": "disabled", "max_text_len": 0, "reject_on_forbidden": True},
        "posture": {
            "screenshots": False, "video": False, "dom_text": False,
            "input_values": False, "raw_urls": False,
            "request_bodies": False, "response_bodies": False,
            "console_messages": False, "network_headers": False,
            "free_text_reports": False,
            "consent_required": True, "respect_gpc": True, "respect_dnt": True,
            "admin_reads_audited": True, "right_to_delete": True,
            "retention_enabled": True, "kill_switch": True,
        },
    },
    "internal-enterprise": {
        "name": "internal-enterprise",
        "description": "Internal apps with lower regulatory load. Free text is still "
                       "PII-scrubbed but a longer note is allowed; forbidden keys dropped.",
        "scrub": {"free_text": "scrub", "max_text_len": 1000, "reject_on_forbidden": False},
        "posture": {
            "screenshots": False, "video": False, "dom_text": False,
            "input_values": False, "raw_urls": False,
            "request_bodies": False, "response_bodies": False,
            "console_messages": False, "network_headers": False,
            "consent_required": True, "respect_gpc": True, "respect_dnt": True,
            "admin_reads_audited": True, "right_to_delete": True,
            "retention_enabled": True, "kill_switch": True,
        },
    },
    "open-source-default": {
        "name": "open-source-default",
        "description": "Sensible privacy-first default for the OSS distribution. Free "
                       "text PII-scrubbed; forbidden keys dropped.",
        "scrub": {"free_text": "scrub", "max_text_len": 280, "reject_on_forbidden": False},
        "posture": {
            "screenshots": False, "video": False, "dom_text": False,
            "input_values": False, "raw_urls": False,
            "request_bodies": False, "response_bodies": False,
            "console_messages": False, "network_headers": False,
            "consent_required": True, "respect_gpc": True, "respect_dnt": True,
            "admin_reads_audited": True, "right_to_delete": True,
            "retention_enabled": True, "kill_switch": True,
        },
    },
}

DEFAULT_PROFILE = "financial-services-enterprise"


def available_profiles() -> List[str]:
    return sorted(PROFILES.keys())


def get_profile(name: str) -> Dict[str, Any]:
    if name not in PROFILES:
        raise KeyError(f"unknown profile {name!r}; available: {available_profiles()}")
    return PROFILES[name]


def policy_from_profile(profile: Dict[str, Any]) -> ScrubPolicy:
    """Build a :class:`ScrubPolicy` from a profile dict (in-repo or externally loaded).

    Only the ``scrub`` knobs vary by profile; the allowlists/forbidden-key sets are the
    hardened scrubber defaults so a profile cannot *weaken* the NPI boundary, only
    tighten free-text/rejection behavior.
    """
    scrub = profile.get("scrub", {})
    # max_text_len of 0 means "no free text" — represented via free_text="disabled".
    max_len = scrub.get("max_text_len", 280) or 1
    return derive_policy(
        name=profile["name"],
        free_text=scrub.get("free_text", "scrub"),
        max_text_len=max_len,
        reject_on_forbidden=bool(scrub.get("reject_on_forbidden", False)),
    )


def load_profile(name: str = DEFAULT_PROFILE) -> ScrubPolicy:
    """Convenience: name -> ScrubPolicy using the in-repo registry."""
    return policy_from_profile(get_profile(name))
