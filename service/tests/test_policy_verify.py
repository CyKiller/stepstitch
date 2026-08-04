"""Tenant fixture validator proof.

Two theses:
1. The shipped financial fixture pack is the gate — every hostile fixture is
   rejected, dropped, or redacted, and no must_not_persist literal survives.
2. The offline classifier can never drift from the live router: every shipped
   fixture is ALSO posted at a real router under the identical policy, and the
   classifications must agree (rejected ↔ 422, everything else ↔ 200 with a
   matching scrub status). If someone adds a schema field or changes the 422
   behavior, this parity test fails before a tenant's fixture run tells a lie.
"""
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stepstitch_service import create_stepstitch_router, generate_playwright_test
from stepstitch_service.cli import main as cli_main
from stepstitch_service.policy_verify import (
    FIXTURE_FILE_VERSION,
    build_policy,
    classify_payload,
    render_report,
    verify_fixtures,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURES_PATH = REPO / "examples" / "policy" / "financial-fixtures.json"


def _fixture_doc():
    return json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


# --- The gate: the shipped pack passes end to end --------------------------------


def test_shipped_financial_pack_holds():
    run = verify_fixtures(_fixture_doc())
    assert run.ok, render_report(run)
    # The pack must actually cover the gate list, not just pass.
    names = " ".join(r.name for r in run.results)
    for shape in ("ssn", "name-and-address", "semantic-route", "semantic-selector",
                  "email", "unmask", "account"):
        assert shape in names, f"fixture pack lost its {shape} coverage"
    # Every hostile fixture (everything but the clean control) ends neutralized.
    for r in run.results:
        if r.name != "clean-structural-payload":
            assert r.outcome in ("rejected", "dropped", "redacted")
        assert r.leaked == []


def test_every_fixture_value_is_obviously_fake():
    # Push-protection + policy: the shipped vectors must be the sanctioned synthetic
    # sentinels, never anything that could be mistaken for real NPI.
    blob = FIXTURES_PATH.read_text(encoding="utf-8")
    assert "000-00-0000" in blob and "4111 1111 1111 1111" in blob
    assert "example.test" in blob
    assert "FAKE-" in blob
    # No plausible real-domain emails.
    assert "@gmail.com" not in blob and "@outlook.com" not in blob


# --- Router parity: the offline mirror can never drift ----------------------------


class _DB:
    def __init__(self):
        self.inserted = None

    async def execute(self, query, params=()):
        if query.strip().upper().startswith("INSERT"):
            self.inserted = params

    async def fetchone(self, query, params=()):
        return None

    async def fetchall(self, query, params=()):
        return []


def _client(policy):
    db = _DB()

    async def audit(action, actor, detail):
        pass

    router = create_stepstitch_router(
        get_user_id=lambda: "user-42",
        require_admin=lambda: {"user_id": "admin-1"},
        execute=db.execute,
        fetchone=db.fetchone,
        fetchall=db.fetchall,
        audit=audit,
        generate_playwright_test=generate_playwright_test,
        scrub_policy=policy,
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app), db


def test_classifier_agrees_with_the_live_router_on_every_shipped_fixture():
    doc = _fixture_doc()
    policy = build_policy(doc["profile"], doc.get("overrides") or {})
    client, db = _client(policy)
    for fx in doc["fixtures"]:
        offline = classify_payload(fx["payload"], policy)
        r = client.post("/api/stepstitch/v1/session", json=fx["payload"])
        if offline.outcome == "rejected":
            assert r.status_code == 422, (
                f"{fx['name']}: classifier says rejected, router returned {r.status_code}"
            )
        else:
            assert r.status_code == 200, (
                f"{fx['name']}: classifier says {offline.outcome}, "
                f"router returned {r.status_code}: {r.text}"
            )
            scrub = r.json()["scrub"]
            if offline.outcome == "accepted":
                assert scrub["scrub_status"] == "clean", fx["name"]
            else:
                assert scrub["scrub_status"] == "scrubbed", fx["name"]
        # Leak scan parity: nothing the classifier cleared may sit in the stored row.
        if r.status_code == 200 and db.inserted is not None:
            stored = json.dumps([str(p) for p in db.inserted])
            for lit in fx.get("must_not_persist") or []:
                assert lit not in stored, f"{fx['name']} leaked {lit!r} into storage"


# --- File validation and CLI surface ----------------------------------------------


def test_unusable_fixture_files_are_named_not_swallowed():
    with pytest.raises(ValueError, match="version"):
        verify_fixtures({"version": 999, "profile": "open-source-default",
                         "fixtures": [{}]})
    with pytest.raises(ValueError, match="profile"):
        verify_fixtures({"version": FIXTURE_FILE_VERSION, "fixtures": [{}]})
    with pytest.raises(ValueError, match="expect"):
        verify_fixtures({"version": FIXTURE_FILE_VERSION,
                         "profile": "open-source-default",
                         "fixtures": [{"name": "x", "expect": "vaporized",
                                       "payload": {"footsteps": []}}]})
    with pytest.raises(ValueError, match="unknown profile"):
        build_policy("does-not-exist", {})


def test_a_leak_fails_the_run_even_when_the_outcome_matches():
    # A fixture may correctly predict "redacted" while a literal still survives —
    # persistence is the question, so that must fail.
    doc = {
        "version": FIXTURE_FILE_VERSION,
        "profile": "financial-services-enterprise",
        "fixtures": [{
            "name": "surviving-literal",
            "expect": "redacted",
            # "Synthetic Way" carries no digits/email shape: the regex scrubber
            # cannot catch it, which is exactly what the leak scan is for.
            "must_not_persist": ["Synthetic Way"],
            "payload": {
                "explanation": "meet at 12 Synthetic Way, also SSN 000-00-0000",
                "footsteps": [{"timestamp": "t", "type": "click", "route": "/x",
                               "label": "[masked]"}],
                "metadata": {},
            },
        }],
    }
    run = verify_fixtures(doc)
    assert not run.ok
    assert run.results[0].outcome == "redacted"
    assert "Synthetic Way" in run.results[0].leaked[0]


def test_cli_exit_codes(tmp_path, capsys):
    # 0: the shipped pack passes.
    assert cli_main(["policy", "verify", str(FIXTURES_PATH)]) == 0
    out = capsys.readouterr().out
    assert "13/13 fixtures passed" in out

    # 1: a failing pack (the leak case above).
    failing = tmp_path / "failing.json"
    failing.write_text(json.dumps({
        "version": 1,
        "profile": "financial-services-enterprise",
        "fixtures": [{
            "name": "leak", "expect": "accepted",
            "must_not_persist": [],
            "payload": {"explanation": "SSN 000-00-0000",
                        "footsteps": [{"timestamp": "t", "type": "click",
                                       "route": "/x", "label": "[masked]"}],
                        "metadata": {}},
        }],
    }))
    assert cli_main(["policy", "verify", str(failing)]) == 1
    assert "FAIL" in capsys.readouterr().out

    # 2: unusable input.
    assert cli_main(["policy", "verify", str(tmp_path / "missing.json")]) == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert cli_main(["policy", "verify", str(bad)]) == 2
    assert cli_main(["policy"]) == 2  # no sub-subcommand → help + usage error


def test_cli_json_output_is_machine_readable(capsys):
    assert cli_main(["policy", "verify", str(FIXTURES_PATH), "--json"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["ok"] is True
    assert body["profile"] == "financial-services-strict"
    assert len(body["results"]) == 13


def test_profile_override_flag_wins(capsys):
    # The same pack under the permissive default profile: hostile free text is
    # scrubbed rather than rejected, so 'expect: rejected' fixtures mismatch → 1.
    assert cli_main(["policy", "verify", str(FIXTURES_PATH),
                     "--profile", "financial-services-enterprise"]) == 1
    out = capsys.readouterr().out
    assert "financial-services-enterprise" in out
