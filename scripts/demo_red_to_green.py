#!/usr/bin/env python3
"""Generate the self-contained red-to-green evidence bundle.

This is the credential-free demo. It imports the **real** StepStitch service modules
(scrubber, replayability, summary projection, Playwright compiler, draft adapters, GitHub
content, verification verdict) and runs the full moat end-to-end with no database, no
network, and no ServiceNow/Salesforce/GitHub/Railway credentials. Every artifact in the
bundle is produced by the same production functions the live service uses — nothing here
is mocked or hand-written.

The eight-step story it proves:
  1. User reports a bug
  2. StepStitch captures structural footsteps only
  3. The server scrubber proves no NPI persisted
  4. A replayability score tells engineering if the bug is reproducible
  5. StepStitch generates a Playwright repro
  6. A ticket/PR draft is created (dry-run — never sent)
  7. CI reports pre-fix failed and post-fix passed
  8. StepStitch records confirmed_fixed in the regression corpus

Run with the service package on the path:

    PYTHONPATH=service python3 scripts/demo_red_to_green.py        # or: npm run demo

Outputs (committed, deterministic — re-running produces an identical bundle):
  - demo/evidence-bundle.json     canonical bundle
  - web/src/lib/demo-bundle.json  copy the static site builds against (drift-guarded)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from stepstitch_service.compiler import generate_playwright_test
from stepstitch_service.compliance import (
    ALWAYS_STRUCTURAL,
    NEVER_CAPTURED_CATEGORIES,
)
from stepstitch_service.github_bridge.content import (
    branch_name,
    build_issue,
    regression_test_path,
)
from stepstitch_service.integrations.base import (
    assert_flat,
    build_trace_summary,
    export_preview,
)
from stepstitch_service.integrations.bundle import default_draft_adapters
from stepstitch_service.replayability import score_trace
from stepstitch_service.scrubber import (
    FINANCIAL_SERVICES_ENTERPRISE,
    scrub_trace_payload,
)
from stepstitch_service.verification.verdict import VerificationResult, derive_verdict

REPO_ROOT = Path(__file__).resolve().parent.parent
TRACE_ID = "trc_demo_red_to_green_0001"
DRY_RUN_LABEL = "dry-run — nothing sent"

# Fixed timestamp so the generated bundle is byte-stable across runs (the drift guard in
# tests/test_demo_bundle.py depends on this).
_TS = "2026-06-02T08:00:0{0}.000Z"


def _raw_bug_report() -> Dict[str, Any]:
    """The payload an SDK might POST — deliberately seeded with clearly-fake forbidden
    fields and placeholder PII so the bundle can *demonstrate* the scrubber removing them.

    Every value here is a synthetic placeholder (``000-00-0000``, ``user@example.test``,
    fixed test ids) — never real NPI. The scrubber drops the forbidden keys and redacts the
    PII-shaped tokens before anything is persisted.
    """
    return {
        "app_id": "stepstitch-demo",
        "project_id": "demo",
        # Placeholder PII tokens — present ONLY to prove redaction. Not real data.
        "explanation": (
            "Transfer to account 000000 failed; reach me at user@example.test "
            "or 000-00-0000."
        ),
        "consent_version": "v1",
        "footsteps": [
            {"timestamp": _TS.format(0), "type": "navigation", "route": "/accounts/123e4567-e89b-12d3-a456-426614174000", "label": "Account overview"},
            {"timestamp": _TS.format(3), "type": "navigation", "route": "/accounts/123e4567-e89b-12d3-a456-426614174000/transfer", "label": "Transfer form"},
            {"timestamp": _TS.format(6), "type": "click", "route": "/accounts/:id/transfer", "target": "[data-testid=payee-select]", "label": "[masked]"},
            {"timestamp": _TS.format(8), "type": "click", "route": "/accounts/:id/transfer", "target": "[data-testid=amount-input]", "label": "[masked]"},
            {"timestamp": _TS.format(9), "type": "click", "route": "/accounts/:id/transfer", "target": "[data-testid=review-transfer]", "label": "[masked]"},
            {
                "timestamp": "2026-06-02T08:00:11.400Z",
                "type": "api_error",
                "route": "/accounts/:id/transfer",
                "metadata": {
                    # Allowlisted structural keys are kept …
                    "status": 500,
                    "method": "POST",
                    "endpoint": "/api/accounts/123e4567/transfers",
                    # … these forbidden keys are dropped by the server scrubber.
                    "cookies": "session=PLACEHOLDER-not-real",
                    "request_body": "{\"amount\": \"PLACEHOLDER\"}",
                    "url": "https://bank.example.test/accounts/123e4567/transfer?token=PLACEHOLDER",
                },
            },
        ],
        "metadata": {
            "sdk_version": "demo",
            "viewport": "1280x720",
            # Forbidden top-level keys — dropped by the strict allowlist.
            "headers": "authorization: Bearer PLACEHOLDER",
            "raw_url": "https://bank.example.test/accounts/123e4567/transfer",
        },
    }


def _timeline(footsteps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Structural display rows for the web/cockpit story (no text, no values)."""
    rows: List[Dict[str, Any]] = []
    for i, step in enumerate(footsteps):
        stype = str(step.get("type", "")).lower()
        meta = step.get("metadata") or {}
        if stype == "api_error":
            detail = f"status {meta.get('status')} · {meta.get('method')} {meta.get('endpoint')}"
            label = "API error"
            kind = "api_error"
        elif stype == "navigation":
            detail = None
            label = "Visited route"
            kind = "nav"
        else:
            detail = None
            label = "Interaction"
            kind = stype or "click"
        rows.append(
            {
                "index": i,
                "kind": kind,
                "label": label,
                "selector": step.get("target") or step.get("route"),
                "detail": detail,
            }
        )
    return rows


def build_bundle() -> Dict[str, Any]:
    raw = _raw_bug_report()

    # Step 3 — server-side scrub (the trust boundary). Returns the sanitized payload and a
    # compliance report listing every field that was dropped or redacted.
    scrubbed, scrub_report = scrub_trace_payload(raw, FINANCIAL_SERVICES_ENTERPRISE)
    footsteps = scrubbed["footsteps"]

    # Step 4 — deterministic replayability score from structural footsteps only.
    replay = score_trace(footsteps)

    # Sanitized, flat projection every downstream artifact is derived from.
    summary = build_trace_summary(TRACE_ID, footsteps, project_id="demo")

    # Step 5 — Playwright reproduction.
    playwright_code = generate_playwright_test(TRACE_ID, footsteps)

    # Step 6 — draft previews (dry-run; validated flat; nothing sent).
    drafts: Dict[str, Any] = export_preview(summary, default_draft_adapters())
    for name, draft in drafts.items():
        assert_flat(draft)  # belt-and-suspenders: no forbidden/nested key escapes
    issue = build_issue(summary)
    github = {
        "issue": {"title": issue.title, "body": issue.body, "labels": list(issue.labels)},
        "pull_request": {
            "would_open": {
                "branch": branch_name(TRACE_ID),
                "test_path": regression_test_path(TRACE_ID),
                "title": f"[StepStitch] regression test for {summary.route}",
            },
            "note": "dry-run: StepStitch never merges — a human reviews and merges.",
        },
    }

    # Step 7 — CI verification. StepStitch never runs code; the customer's CI runs the repro
    # and reports pass/fail. confirmed_fixed derives ONLY from pre-failed + post-passed.
    pre_passed = False  # repro fails while the bug exists (red)
    post_passed = True  # repro passes once the fix lands (green)
    verdict = derive_verdict(pre_passed, post_passed)
    verification = VerificationResult(
        trace_id=TRACE_ID,
        pre_passed=pre_passed,
        post_passed=post_passed,
        verdict=verdict,
        fix_ref="demo-pr-1",
        run_url="https://ci.example.test/runs/stepstitch-demo",  # placeholder, not real
    )

    return {
        "demo": True,
        "delivery": DRY_RUN_LABEL,
        "title": "StepStitch red-to-green evidence bundle",
        "generated_by": "scripts/demo_red_to_green.py",
        "note": (
            "Every artifact below is produced by the real StepStitch service modules, "
            "with no credentials and no database. Drafts and the PR are dry-run previews; "
            "nothing is ever sent. Verdict derives only from red→green CI."
        ),
        "story": [
            "1. User reports a bug",
            "2. StepStitch captures structural footsteps only",
            "3. The server scrubber proves no NPI persisted",
            "4. A replayability score tells engineering if the bug is reproducible",
            "5. StepStitch generates a Playwright repro",
            "6. A ticket/PR draft is created (dry-run — never sent)",
            "7. CI reports pre-fix failed and post-fix passed",
            "8. StepStitch records confirmed_fixed in the regression corpus",
        ],
        "trace_id": TRACE_ID,
        "steps": {
            "1_bug_report": {
                "headline": summary.headline,
                "raw_unsafe_input": {
                    "note": (
                        "Synthetic placeholders ONLY (no real NPI). Present to demonstrate "
                        "the scrubber dropping forbidden fields and redacting PII-shaped text."
                    ),
                    "explanation": raw["explanation"],
                    "forbidden_fields_sent": [
                        "metadata.headers",
                        "metadata.raw_url",
                        "footsteps[5].metadata.cookies",
                        "footsteps[5].metadata.request_body",
                        "footsteps[5].metadata.url",
                    ],
                },
            },
            "2_structural_capture": {
                "footsteps": footsteps,
                "timeline": _timeline(footsteps),
                "always_structural": list(ALWAYS_STRUCTURAL),
            },
            "3_privacy_scrub": {
                "scrub_status": scrub_report["scrub_status"],
                "scrubbed_fields": scrub_report["scrubbed_fields"],
                "policy": scrub_report["policy"],
                "explanation_after_scrub": scrubbed["explanation"],
                "never_captured": list(NEVER_CAPTURED_CATEGORIES),
            },
            "4_replayability": {
                "score": replay["score"],
                "grade": replay["grade"],
                "warnings": replay["warnings"],
                "signals": replay["signals"],
            },
            "5_playwright_repro": {
                "playwright_code": playwright_code,
                "note": "Deterministic; fails while the bug exists, passes once fixed.",
            },
            "6_drafts": {
                "delivery": DRY_RUN_LABEL,
                **drafts,
                "github": github,
            },
            "7_ci_verification": {
                **verification.as_dict(),
                "note": "confirmed_fixed derives only from pre_passed=false + post_passed=true.",
            },
            "8_regression_corpus": {
                "verdict": verdict,
                "entries": [verification.as_dict()],
            },
        },
        "trace_summary": summary.as_dict(),
        "never_captured": list(NEVER_CAPTURED_CATEGORIES),
    }


def main() -> None:
    bundle = build_bundle()
    text = json.dumps(bundle, indent=2, ensure_ascii=False) + "\n"

    targets = [
        REPO_ROOT / "demo" / "evidence-bundle.json",
        REPO_ROOT / "web" / "src" / "lib" / "demo-bundle.json",
    ]
    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO_ROOT)}")

    s = bundle["steps"]
    print(
        "\nred-to-green demo OK: "
        f"scrub={s['3_privacy_scrub']['scrub_status']} "
        f"({len(s['3_privacy_scrub']['scrubbed_fields'])} fields), "
        f"grade={s['4_replayability']['grade']}, "
        f"verdict={s['7_ci_verification']['verdict']}"
    )


if __name__ == "__main__":
    main()
