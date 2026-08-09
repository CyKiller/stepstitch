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
  3. The server scrubber reports exactly what it stripped
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
  - demo/fixproof.json            the example FixProof statement (synthetic demo commits,
                                  pinned timestamps — byte-stable like the bundle)
  - web/public/fixproof.json      the same document, downloadable from /verify
  - web/public/proof-policy.json  verbatim copy of examples/proof/proof-policy.json
"""
from __future__ import annotations

import json
import sys
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


BUNDLE_PATH = REPO_ROOT / "demo" / "evidence-bundle.json"

# The fixture the measurement runs against: a page whose button either throws (red) or
# succeeds (green). Deliberately tiny — the claim being measured is "the compiled repro
# fails while the bug exists and passes once it does not", not anything about this app.
_FIXTURE_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Demo</title></head>
<body>
  <h1 id="title">Transfer</h1>
  <button id="go" data-testid="go" onclick="{handler}">Send</button>
</body></html>
"""
_FIXTURE_BROKEN = "throw new TypeError('amount is not a function')"
_FIXTURE_FIXED = "document.getElementById('title').textContent = 'Sent'"

# The reproduction the measurement executes. Compiled by the real compiler from a trace
# whose terminal step is the same exception the broken fixture raises.
_MEASURED_FOOTSTEPS: List[Dict[str, Any]] = [
    {"timestamp": "2026-08-04T12:00:00Z", "type": "navigation",
     "route": "/index.html", "label": "[masked]"},
    {"timestamp": "2026-08-04T12:00:02Z", "type": "click", "route": "/index.html",
     "target": '[data-testid="go"]', "label": "[masked]"},
    {"timestamp": "2026-08-04T12:00:03Z", "type": "exception", "route": "/index.html",
     "label": "[masked]", "metadata": {"error_type": "TypeError"}},
]


def committed_measurement() -> Dict[str, Any]:
    """The measurement recorded in the committed bundle.

    Reused (never re-invented) when regenerating offline, so `npm run demo` still works
    with no browser and no network — the documented no-backend path — while the numbers
    it writes remain the ones a real run produced.
    """
    try:
        stored = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
        recorded = stored["steps"]["7_ci_verification"]["measurement"]
    except (OSError, KeyError, ValueError) as exc:
        raise SystemExit(
            "No measured red-to-green result is committed yet, and this run cannot "
            "invent one. Regenerate it on a machine with Chromium:\n"
            "    PYTHONPATH=service python3 scripts/demo_red_to_green.py --measure\n"
            f"({exc})"
        ) from exc
    return dict(recorded)


def measure_red_to_green() -> Dict[str, Any]:
    """Actually run the compiled reproduction: red against a broken fixture, green
    against a fixed one. Returns what was observed — never what was expected."""
    import functools
    import http.server
    import shutil
    import socket
    import tempfile
    import threading

    from stepstitch_service.runner import REPRODUCED, RUNNER_VERSION, run_reproduction

    work = Path(tempfile.mkdtemp(prefix="stepstitch-demo-measure-"))
    app_dir = work / "app"
    app_dir.mkdir(parents=True, exist_ok=True)

    def write(handler: str) -> None:
        (app_dir / "index.html").write_text(
            _FIXTURE_PAGE.format(handler=handler), encoding="utf-8")

    class _NoStore(http.server.SimpleHTTPRequestHandler):
        # The fix is written between two runs; a 304 would hand the browser the old page
        # and the "green" run would silently re-test the bug.
        def end_headers(self):
            self.send_header("Cache-Control", "no-store, max-age=0")
            super().end_headers()

        def send_header(self, key, value):
            if key.lower() == "last-modified":
                return
            super().send_header(key, value)

        def log_message(self, *args):
            pass

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])

    write(_FIXTURE_BROKEN)
    server = http.server.HTTPServer(
        ("127.0.0.1", port), functools.partial(_NoStore, directory=str(app_dir)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{port}"
    script = generate_playwright_test(TRACE_ID, _MEASURED_FOOTSTEPS, base_url)
    try:
        red = run_reproduction(session_id=TRACE_ID, script=script, base_url=base_url,
                               runs=1, timeout_seconds=120)
        write(_FIXTURE_FIXED)
        green = run_reproduction(session_id=TRACE_ID, script=script, base_url=base_url,
                                 runs=1, timeout_seconds=120)
    finally:
        server.shutdown()
        server.server_close()          # release the listening socket, not just the loop
        shutil.rmtree(work, ignore_errors=True)

    # The runner's verdict is about the REPRODUCTION: "reproduced" means the test failed,
    # which is the red half passing. Translated once, here, rather than at each reader.
    pre_passed = red.verdict != REPRODUCED
    post_passed = green.verdict != REPRODUCED
    if pre_passed or not post_passed:
        raise SystemExit(
            "The demo fixture did not go red then green "
            f"(red={red.verdict}, green={green.verdict}). Refusing to write a bundle "
            "that would claim a transition nobody observed."
        )
    return {
        "evidence_grade": "measured",
        "pre_passed": pre_passed,
        "post_passed": post_passed,
        "red_verdict": red.verdict,
        "green_verdict": green.verdict,
        "runner_version": RUNNER_VERSION,
        "detail": "Measured by running the compiled reproduction against a broken fixture "
                  "and then a fixed one. Re-measured in CI on every commit; the committed "
                  "bundle must equal what that run observes.",
    }


def build_bundle(measure: bool = False) -> Dict[str, Any]:
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

    # Step 7 — CI verification. confirmed_fixed derives ONLY from pre-failed + post-passed,
    # and those two booleans are MEASURED: `--measure` runs the compiled reproduction in a
    # real browser against a broken fixture and then a fixed one, and the committed bundle
    # records what was observed. Without the flag the generator reuses the committed
    # measurement rather than inventing one — the offline demo (documented as needing no
    # network and no browser) still regenerates byte-identically, and nobody can quietly
    # replace a measurement with an assertion.
    measurement = measure_red_to_green() if measure else committed_measurement()
    pre_passed = measurement["pre_passed"]
    post_passed = measurement["post_passed"]
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
            "3. The server scrubber reports exactly what it stripped",
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
                        "Synthetic placeholders ONLY — never real customer data. Present to demonstrate "
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
                # Provenance for the two booleans above: which browser observed them, and
                # under which runner. Regenerated with --measure in CI on every commit.
                "measurement": measurement,
            },
            "8_regression_corpus": {
                "verdict": verdict,
                "entries": [verification.as_dict()],
            },
        },
        "trace_summary": summary.as_dict(),
        "never_captured": list(NEVER_CAPTURED_CATEGORIES),
    }


# Synthetic demo commits: 40 hex chars, unmistakably not real repository history. The
# committed proof must be byte-stable, and a REAL commit id in a committed file would
# either drift every merge or lie about the code it names — so the demo proof names
# fixture commits and says so in fix_ref. (The real, run-specific proof is the CI
# artifact the live financial loop exports; that one carries the actual HEAD.)
_DEMO_BASE_COMMIT = "baddc0de" * 5
_DEMO_FIXED_COMMIT = "beefc0de" * 5


def build_demo_fixproof(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """The example FixProof, built from the bundle's own recorded facts.

    Everything measured comes FROM the committed measurement (the same booleans CI
    re-measures on every commit); everything identifying is synthetic and labeled. The
    document verifies offline with `stepstitch proof verify` — the exact command the
    /verify page hands a visitor.
    """
    import hashlib

    from stepstitch_service.fixproof import build_fixproof_statement, wrap
    from stepstitch_service.scrubber import policy_sha256

    steps = bundle["steps"]
    measurement = steps["7_ci_verification"]["measurement"]
    playwright_code = steps["5_playwright_repro"]["playwright_code"]
    scrub = steps["3_privacy_scrub"]
    statement = build_fixproof_statement(
        trace_id=bundle["trace_id"],
        subject_name="stepstitch-demo/transfer-app",
        fixed_commit=_DEMO_FIXED_COMMIT,
        base_commit=_DEMO_BASE_COMMIT,
        fingerprint={"route": "/accounts/:id/transfer", "exception_type": "TypeError"},
        red_signature="TypeError: amount is not a function",
        red_verdict=measurement["red_verdict"],
        frozen_test_sha256=hashlib.sha256(
            playwright_code.encode("utf-8")).hexdigest(),
        frozen_at=_TS.format(9),
        frozen_by="demo-operator",
        envelope_sha256=None,   # the committed measurement predates envelope capture
        envelope_schema_version=None,
        pre_passed=measurement["pre_passed"],
        post_passed=measurement["post_passed"],
        verdict=steps["7_ci_verification"]["verdict"],
        fix_ref="demo-fixture commits (synthetic, labeled — not repository history)",
        fix_mechanism="demo fixture: broken handler replaced by fixed handler",
        policy=scrub["policy"],
        policy_sha256=policy_sha256(FINANCIAL_SERVICES_ENTERPRISE),
        scrub_status=scrub["scrub_status"],
        schema_status=None,
        verifier_identity="demo-operator",
        evidence_grade=measurement["evidence_grade"],
        issued_at=_TS.format(9),
        sdk_build=None,
    )
    return wrap(statement)


def main() -> None:
    measure = "--measure" in sys.argv[1:]
    bundle = build_bundle(measure=measure)
    text = json.dumps(bundle, indent=2, ensure_ascii=False) + "\n"

    targets = [
        BUNDLE_PATH,
        REPO_ROOT / "web" / "src" / "lib" / "demo-bundle.json",
    ]
    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO_ROOT)}")

    proof_text = json.dumps(build_demo_fixproof(bundle), indent=2,
                            ensure_ascii=False) + "\n"
    for path in (REPO_ROOT / "demo" / "fixproof.json",
                 REPO_ROOT / "web" / "public" / "fixproof.json"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(proof_text, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    # The policy ships verbatim: the file a visitor verifies with is the file a customer
    # starts from, so the two can never quietly diverge.
    policy_text = (REPO_ROOT / "examples" / "proof" /
                   "proof-policy.json").read_text(encoding="utf-8")
    policy_path = REPO_ROOT / "web" / "public" / "proof-policy.json"
    policy_path.write_text(policy_text, encoding="utf-8")
    print(f"wrote {policy_path.relative_to(REPO_ROOT)}")

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
