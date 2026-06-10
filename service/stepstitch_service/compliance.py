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
    "Raw frontend logs / console messages / stack traces",
    "Network headers / cookies",
    "SSNs, account/card numbers, emails, phone numbers (redacted from free text)",
)

ALWAYS_STRUCTURAL = (
    "Route templates (e.g. /accounts/:id)",
    "Stable selectors (data-testid preferred)",
    "API status codes",
    "Endpoint templates and source-path templates",
    "Exception types",
    "SDK/build/release metadata",
    "Masked labels",
)

# --- Regulatory crosswalk (code-derived; cites the frameworks a reviewer applies) ----
_REGSP = "SEC Reg S-P (2024)"
_MRM = "2026 interagency MRM (supersedes SR 11-7)"
_HIPAA = "HIPAA"
_NIST = "NIST AI RMF"

# Each control maps to a citation per framework ("—" = not the controlling regime).
_CROSSWALK = (
    ("Server-side scrub / NPI data-minimization (`scrubber.py`)", {
        _REGSP: "Safeguards Rule — protect customer NPI",
        _MRM: "Sound, controlled data inputs",
        _HIPAA: "Minimum-necessary; no PHI stored",
        _NIST: "MAP/MEASURE — data governance",
    }),
    ("Split retention + 5-yr audit clock (`retention.py`)", {
        _REGSP: "Recordkeeping — incident records retained 5 yrs",
        _MRM: "Auditability & traceability of model use",
        _HIPAA: "Retain access/audit records",
        _NIST: "GOVERN — documentation & records",
    }),
    ("Admin-only reads, audit on every read (`router.py`)", {
        _REGSP: "Access controls; incident-response program",
        _MRM: "Traceability / effective challenge",
        _HIPAA: "Access controls & audit logging",
        _NIST: "GOVERN/MANAGE — accountability",
    }),
    ("Org-wide kill switch, fail-safe (`router.py`)", {
        _REGSP: "Incident-response containment",
        _MRM: "Controls & human override",
        _HIPAA: "Contingency / incident response",
        _NIST: "MANAGE — incident response",
    }),
    ("Deterministic compiler + replayability + eval gate "
     "(`compiler.py`, `test_repro_eval.py`)", {
        _REGSP: "—",
        _MRM: "Ongoing monitoring & output quality",
        _HIPAA: "—",
        _NIST: "MEASURE — validity & reliability",
    }),
    ("Draft-only, human-in-the-loop (`integrations/`, `copilot/action-policy.md`)", {
        _REGSP: "—",
        _MRM: "Human oversight — outputs support, not replace, decisions",
        _HIPAA: "—",
        _NIST: "GOVERN — human-AI configuration",
    }),
)

# Release gates reframed as model-risk validation / ongoing-monitoring evidence.
_MRM_GATES = (
    ("End-to-end golden path", "`test_golden_path.py`", "System validation"),
    ("Server-side scrub boundary", "`test_scrubber.py`", "Data-control validation"),
    ("Profile drift guard", "`test_profiles.py`", "Configuration control"),
    ("Executable repro proof", "`scripts/prove-repro-executes.mjs`", "Output validity"),
    ("Reproduction quality eval", "`test_repro_eval.py`", "Ongoing output-quality monitoring"),
    ("Open-core import boundary", "`.importlinter` / `test_open_core_boundary.py`",
     "Change control / segregation of duties"),
    ("Compliance evidence drift guard", "`test_compliance.py`", "Documentation currency"),
)


def _bullets(items) -> List[str]:
    return [f"- {i}" for i in items]


def _frameworks_for(policy: ScrubPolicy) -> List[str]:
    """The framework columns that apply to a profile."""
    if policy.name == "healthcare-strict":
        return [_HIPAA, _NIST]
    return [_REGSP, _MRM, _NIST]


def _crosswalk_section(policy: ScrubPolicy) -> List[str]:
    cols = _frameworks_for(policy)
    lines = [
        "## Regulatory crosswalk",
        "",
        "The controls above mapped to the frameworks a regulated reviewer applies "
        f"(columns selected for the `{policy.name}` profile).",
        "",
        "| Control | " + " | ".join(cols) + " |",
        "|---|" + "|".join("---" for _ in cols) + "|",
    ]
    for control, mapping in _CROSSWALK:
        cells = " | ".join(mapping.get(c, "—") for c in cols)
        lines.append(f"| {control} | {cells} |")
    lines.append("")
    return lines


def _mrm_section() -> List[str]:
    lines = [
        "## Model risk management evidence",
        "",
        "Under the **April-2026 interagency model risk management guidance (superseding "
        "SR 11-7)**, StepStitch's release gates are the validation & ongoing-monitoring "
        "evidence — each a named, runnable check:",
        "",
        "| Gate | Check | MRM role |",
        "|---|---|---|",
    ]
    for gate, check, role in _MRM_GATES:
        lines.append(f"| {gate} | {check} | {role} |")
    lines += [
        "",
        "StepStitch is a deterministic, **draft-only provider**: it produces evidence and "
        "drafts for human decision-makers and never takes autonomous action, keeping AI "
        "outputs in a \"support, not replace\" posture for fiduciary use.",
        "",
    ]
    return lines


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

    lines.append("")
    lines += _crosswalk_section(policy)
    lines += _mrm_section()

    lines += [
        "## Verification",
        "",
        "- `pytest service/tests` — scrubber, replayability, profiles, integrations, "
        "Copilot surface, retention, compiler, router.",
        "- `ruff check service` — lint.",
        "- `sbom.cdx.json` — supply-chain bill of materials.",
        "",
    ]
    return "\n".join(lines) + "\n"
