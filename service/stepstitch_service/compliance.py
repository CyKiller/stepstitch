"""Compliance evidence — generated from the live ScrubPolicy, never hand-maintained.

A security reviewer's first question is "what do you capture, and what do you never
capture?". This module answers it from *code*: the capture/never-capture matrix is
derived directly from the active :class:`ScrubPolicy` (allowlists + forbidden keys), so
the evidence packet cannot drift from what the scrubber actually enforces. The drift
guard in ``service/tests/test_compliance.py`` fails CI if the committed
``COMPLIANCE-EVIDENCE.md`` stops matching the policy.

Output is deterministic (no timestamps) precisely so it can be drift-guarded.
"""
from __future__ import annotations

from typing import List

from .profiles import PROFILES
from .scrubber import FINANCIAL_SERVICES_ENTERPRISE, ScrubPolicy

__all__ = ["build_evidence", "NEVER_CAPTURED_CATEGORIES", "ALWAYS_STRUCTURAL"]

# Human-facing categories the product never records (independent of key names).
NEVER_CAPTURED_CATEGORIES = (
    "Screenshots / video",
    "Input values (what a user typed)",
    "Page text / DOM content",
    "Raw URLs (templated to routes)",
    "Request / response bodies",
    "Console messages",
    "Network headers / cookies",
    "SSNs, account/card numbers, emails, phone numbers (redacted from free text)",
)

ALWAYS_STRUCTURAL = (
    "Route templates (e.g. /accounts/:id)",
    "Stable selectors (data-testid preferred)",
    "API status codes",
    "Exception types",
    "Masked labels",
)


def _bullets(items) -> List[str]:
    return [f"- {i}" for i in items]


def build_evidence(policy: ScrubPolicy = FINANCIAL_SERVICES_ENTERPRISE) -> str:
    """Return the compliance evidence packet (Markdown) for ``policy``."""
    forbidden = sorted(policy.forbidden_keys)
    meta_allow = sorted(policy.metadata_allowlist)
    fs_meta_allow = sorted(policy.footstep_metadata_allowlist)

    lines: List[str] = [
        "# StepStitch — Compliance Evidence",
        "",
        "> Generated from the live `ScrubPolicy` by "
        "`scripts/generate_compliance_evidence.py`. Do not edit by hand — the drift "
        "guard in `service/tests/test_compliance.py` keeps this file equal to the code.",
        "",
        f"**Active policy:** `{policy.name}`  ",
        f"**Free-text handling:** `{policy.free_text}` (max {policy.max_text_len} chars)  ",
        f"**Forbidden key on payload →** "
        f"{'reject (HTTP 422)' if policy.reject_on_forbidden else 'dropped + reported'}",
        "",
        "## What StepStitch never captures",
        "",
        *_bullets(NEVER_CAPTURED_CATEGORIES),
        "",
        "## What StepStitch captures (structural only)",
        "",
        *_bullets(ALWAYS_STRUCTURAL),
        "",
        "## Server-side enforcement (defense-in-depth)",
        "",
        "Every ingestion is scrubbed server-side before storage, independent of the SDK "
        "(`service/stepstitch_service/scrubber.py`). The browser SDK also redacts, but "
        "the server never trusts the client.",
        "",
        "### Metadata allowlist (everything else dropped)",
        "",
        f"- Top-level: {', '.join(f'`{k}`' for k in meta_allow)}",
        f"- Footstep: {', '.join(f'`{k}`' for k in fs_meta_allow)}",
        "",
        "### Forbidden keys (dropped as a leak signal)",
        "",
        *_bullets(f"`{k}`" for k in forbidden),
        "",
        "## Operational controls",
        "",
        "- Consent required before capture; GPC and DNT respected (capture stays off).",
        "- Admin-only operator reads; **every** read writes an audit event.",
        "- Right-to-delete removes trace bodies; the deletion audit record is retained.",
        "- Split retention: bodies purged on a short clock; audit records on a separate "
        "5-year clock (SEC Reg S-P 2024).",
        "- Org-wide kill switch refuses ingestion (HTTP 503) with no row written; a "
        "broken flag fails safe (capture OFF).",
        "- Per-trace scrub report stored at `trace_metadata._scrub` and returned on "
        "ingestion.",
        "",
        "## Deployment profiles",
        "",
        "| Profile | free_text | forbidden-key handling |",
        "|---|---|---|",
    ]
    for name in sorted(PROFILES):
        scrub = PROFILES[name]["scrub"]
        handling = "reject (422)" if scrub.get("reject_on_forbidden") else "drop"
        lines.append(f"| `{name}` | {scrub.get('free_text')} | {handling} |")

    lines += [
        "",
        "## Verification",
        "",
        "- `pytest service/tests` — scrubber, replayability, profiles, integrations, "
        "Copilot surface, retention, compiler, router.",
        "- `ruff check service` — lint.",
        "- `sbom.cdx.json` — supply-chain bill of materials.",
        "",
    ]
    return "\n".join(lines) + "\n"
