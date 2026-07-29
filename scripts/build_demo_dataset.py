#!/usr/bin/env python3
"""Build the synthetic dataset behind the public demo console.

Every row here is produced by the **real** pipeline — the same scrubber, summary builder,
fingerprint function, replayability scorer and verdict rules that run in production. Nothing
is hand-written to look plausible, because a demo that fakes its own output is worth nothing
as evidence: the whole claim is "this is what StepStitch actually does".

The dataset covers one failure shape per lifecycle stage, so the board shows the entire
journey at once:

    untriaged      reported, nothing done yet
    known_shape    matches a fix already in the corpus
    repro_invalid  the reproduction passed on the buggy build — it never reproduced
    reproduced     the reproduction failed as expected; no fix yet
    fix_failed     a fix was tried and the reproduction still failed
    fixed          failed before the fix, passed after it -> confirmed_fixed

Output is committed at ``server/demo_dataset.json`` and drift-guarded by
``server/tests/test_demo_dataset.py``. Deterministic: fixed ids, fixed timestamps, no clock
and no randomness, so the committed file only changes when the pipeline does.

    PYTHONPATH=service python3 scripts/build_demo_dataset.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "service"))

from stepstitch_service.fix_memory import fingerprint as fix_fingerprint  # noqa: E402
from stepstitch_service.integrations.base import build_trace_summary  # noqa: E402
from stepstitch_service.scrubber import (  # noqa: E402
    FINANCIAL_SERVICES_ENTERPRISE,
    scrub_trace_payload,
)
from stepstitch_service.verification.verdict import derive_verdict  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "server" / "demo_dataset.json"

# A fixed "now" so the committed file is stable. The console renders relative days from these.
NOW = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)


def ts(days_ago: float) -> datetime:
    return NOW - timedelta(days=days_ago)


def steps(route, selector, endpoint, status=500, method="POST", with_input=True):
    """A structural trace of the shape the SDK actually emits: no values, templated routes."""
    out = [
        {"timestamp": "2026-07-01T09:00:00Z", "type": "navigation", "route": route,
         "label": "[masked]"},
    ]
    if with_input:
        out.append({"timestamp": "2026-07-01T09:00:04Z", "type": "input", "route": route,
                    "target": "[data-testid=amount]", "label": "[masked]",
                    "metadata": {"interacted": True}})
    out += [
        {"timestamp": "2026-07-01T09:00:07Z", "type": "click", "route": route,
         "target": selector, "label": "[masked]"},
        {"timestamp": "2026-07-01T09:00:08Z", "type": "api_error", "route": route,
         "label": "[masked]",
         "metadata": {"status": status, "method": method, "endpoint": endpoint}},
    ]
    return out


# Each entry: the raw report as a user would file it, plus the CI outcomes (if any).
# Explanations deliberately contain fake NPI so the scrub can be SEEN working in the console's
# privacy proof — these are the values the demo shows being removed.
SCENARIOS = [
    {
        "id": "trc_demo_transfer_fixed",
        "route": "/accounts/:id/transfer",
        "selector": "[data-testid=send-transfer]",
        "endpoint": "/api/accounts/:id/transfers",
        "explanation": "Sending $250.00 to account 4111 1111 1111 1234 failed. "
                       "Reach me at dana.holt@example.test — my SSN is 000-00-0000.",
        "days_ago": 1.2,
        "verifications": [(False, True, "PR #482 — guard the settlement ledger call",
                           "https://github.com/example/bank/actions/runs/1482")],
    },
    {
        # Nearly the fixed shape — same route, endpoint and status, reached by a different
        # button. That is a DIFFERENT fingerprint (so its own shape) but a high structural
        # similarity, so Fix Memory recognises it and the board says known_shape: "you have
        # fixed this before". Making it an exact match instead would merge the two traces
        # into one shape and the stage would never appear.
        "id": "trc_demo_transfer_repeat",
        "route": "/accounts/:id/transfer",
        "selector": "[data-testid=confirm-and-send]",
        "endpoint": "/api/accounts/:id/transfers",
        "explanation": "Transfer failed again this morning. Card 4111 1111 1111 1234.",
        "days_ago": 0.4,
        "verifications": [],
    },
    {
        "id": "trc_demo_statement_reproduced",
        "route": "/accounts/:id/statements",
        "selector": "[data-testid=download-statement]",
        "endpoint": "/api/accounts/:id/statements",
        "explanation": "Statement download spins forever then errors.",
        "days_ago": 2.5,
        "verifications": [(False, None, None, None)],
    },
    {
        "id": "trc_demo_payee_fix_failed",
        "route": "/payees/:id/edit",
        "selector": "[data-testid=save-payee]",
        "endpoint": "/api/payees/:id",
        "explanation": "Saving a payee returns an error. Call me on 555-012-3456.",
        "days_ago": 3.1,
        "verifications": [(False, False, "PR #468 — first attempt",
                           "https://github.com/example/bank/actions/runs/1468")],
    },
    {
        "id": "trc_demo_search_repro_invalid",
        "route": "/search",
        "selector": "[data-testid=run-search]",
        "endpoint": "/api/search",
        "status": 503,
        "explanation": "Search was down for a minute earlier.",
        "days_ago": 4.6,
        # The reproduction PASSED on the buggy build: it never reproduced. Honest, and a
        # first-class outcome rather than a hidden failure.
        "verifications": [(True, None, None,
                           "https://github.com/example/bank/actions/runs/1455")],
    },
    {
        "id": "trc_demo_card_untriaged",
        "route": "/cards/:id/freeze",
        "selector": "[data-testid=freeze-card]",
        "endpoint": "/api/cards/:id/freeze",
        "explanation": "Freeze card button does nothing.",
        "days_ago": 0.1,
        "verifications": [],
    },
]


def build() -> dict:
    policy = FINANCIAL_SERVICES_ENTERPRISE
    traces, verifications, audit = [], [], []

    for index, scenario in enumerate(SCENARIOS):
        footsteps = steps(
            scenario["route"], scenario["selector"], scenario["endpoint"],
            status=scenario.get("status", 500),
        )
        # The real server-side trust boundary, exactly as ingest runs it.
        scrubbed, scrub_report = scrub_trace_payload(
            {"explanation": scenario["explanation"], "footsteps": footsteps,
             "metadata": {"sdk_version": "0.8.0", "viewport": "1440x900"}},
            policy=policy,
        )
        summary = build_trace_summary(
            scenario["id"], scrubbed["footsteps"], project_id="demo-bank")
        created = ts(scenario["days_ago"])
        traces.append({
            "id": scenario["id"],
            "app_id": "demo-bank-web",
            "project_id": "demo-bank",
            "user_id": f"demo-user-{index + 1}",
            "explanation": scrubbed["explanation"],
            "footsteps": json.dumps(scrubbed["footsteps"]),
            "trace_metadata": json.dumps({**scrubbed.get("metadata", {}),
                                          "_scrub": scrub_report}),
            "consent_version": "demo-v1",
            "created_at": created.isoformat(),
            "fingerprint": json.dumps(
                fix_fingerprint(summary.as_dict(), scrubbed["footsteps"])),
        })
        audit.append({
            "id": f"aud_{scenario['id']}",
            "action": "stepstitch.ingest",
            "actor": f"demo-user-{index + 1}",
            "detail": json.dumps({"trace_id": scenario["id"],
                                  "scrub_status": scrub_report["scrub_status"]}),
            "created_at": created.isoformat(),
        })

        for order, (pre, post, fix_ref, run_url) in enumerate(scenario["verifications"]):
            # The verdict comes from the real rule table, never from a literal.
            verdict = derive_verdict(pre, post)
            reported = created + timedelta(hours=6 + order)
            verifications.append({
                "id": f"ver_{scenario['id']}_{order}",
                "trace_id": scenario["id"],
                "pre_passed": pre,
                "post_passed": post,
                "verdict": verdict,
                "fix_ref": fix_ref,
                "run_url": run_url,
                "fingerprint": traces[-1]["fingerprint"],
                "created_at": reported.isoformat(),
            })
            audit.append({
                "id": f"aud_{scenario['id']}_v{order}",
                "action": "stepstitch.verify",
                "actor": "ci@demo-bank",
                "detail": json.dumps({"trace_id": scenario["id"], "verdict": verdict}),
                "created_at": reported.isoformat(),
            })

    return {
        "schema": "stepstitch.demo_dataset/v1",
        "generated_from": "scripts/build_demo_dataset.py",
        "note": "Synthetic. Produced by the real StepStitch pipeline. No real user data.",
        "profile": policy.name,
        "now": NOW.isoformat(),
        "traces": traces,
        "verifications": verifications,
        "audit": audit,
    }


def main() -> int:
    dataset = build()
    OUT.write_text(json.dumps(dataset, indent=2, sort_keys=True) + "\n")
    verdicts = sorted({v["verdict"] for v in dataset["verifications"]})
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  {len(dataset['traces'])} traces, {len(dataset['verifications'])} verifications")
    print(f"  verdicts: {', '.join(verdicts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
