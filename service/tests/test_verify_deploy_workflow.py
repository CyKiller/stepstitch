"""Guard the deploy-verification workflow against regressing into a false green.

`.github/workflows/verify-deploy.yml` is the only thing standing between "main was pushed"
and "the public product proof is actually serving that commit". Its first version had a
soft path: a missing /healthz revision became the string "unknown", which warned and
exited 0 — so an old deployment could keep the check green forever. These tests pin the
strict contract: exact-SHA confirmation or failure, 403 mutation probes on BOTH hosts,
and no word-split curl construction.

Validation tooling note: neither actionlint nor shellcheck is installed here or used
anywhere in this repository, so this file is the workflow's only static coverage. As a
substitute for shellcheck it runs `bash -n` (syntax only, not lint) over every `run:`
script in the touched workflows; the YAML itself is proven parseable with PyYAML, the
same approach test_github_content.py takes for the customer-facing workflow template.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
VERIFY = REPO / ".github" / "workflows" / "verify-deploy.yml"
CLEAN_INSTALL = REPO / ".github" / "workflows" / "clean-install.yml"


def _doc() -> dict:
    return yaml.safe_load(VERIFY.read_text(encoding="utf-8"))


def _steps() -> dict[str, str]:
    """Map step name -> run script for the verify job."""
    job = _doc()["jobs"]["verify"]
    return {s["name"]: s.get("run", "") for s in job["steps"]}


def test_workflow_parses_and_is_credential_free():
    doc = _doc()
    assert doc["permissions"] == {}, "verification needs no token; keep permissions empty"
    assert list(doc["jobs"]) == ["verify"]


def test_revision_step_requires_an_exact_sha_match_or_fails():
    script = _steps()["Railway serves exactly this commit"]
    # The only success path is an exact comparison against this commit's SHA.
    assert 'want="${GITHUB_SHA}"' in script
    assert '[ "$observed" = "$want" ]' in script
    # Missing the deadline is a hard failure, never a warning.
    assert "exit 1" in script
    assert "::warning::" not in script, "an unconfirmed revision must fail, not warn"
    # The old soft path marked the unknown state as an output and exited 0.
    assert "confirmed=unknown" not in script, "the 'unknown succeeds' path must not return"


def test_unknown_or_missing_revision_cannot_reach_the_success_exit():
    script = _steps()["Railway serves exactly this commit"]
    # Exactly one `exit 0`, and it sits inside the exact-match branch: the only text
    # between the comparison and the success exit is the confirmed output bookkeeping.
    assert script.count("exit 0") == 1
    match_branch = script.split('[ "$observed" = "$want" ]')[1].split("exit 0")[0]
    assert 'confirmed=yes' in match_branch


def test_both_hosts_probe_the_full_public_contract():
    steps = _steps()
    railway, vercel = steps["Railway public contract"], steps["Vercel public contract"]
    # Railway: console + read + both mutation refusals.
    assert 'probe GET  "$RAILWAY_HOST/demo/dashboard" 200 "Synthetic demo"' in railway
    assert 'probe GET  "$RAILWAY_HOST/demo/api/stepstitch/v1/sessions?limit=1" 200' in railway
    assert 'probe POST "$RAILWAY_HOST/demo/api/stepstitch/v1/session/probe/verify" 403' in railway
    assert 'probe PUT  "$RAILWAY_HOST/demo/admin/config/repro" 403' in railway
    # Vercel, through the rewrite: same four.
    assert 'probe GET  "$SITE/dashboard/demo" 200 "Synthetic demo"' in vercel
    assert 'probe GET  "$SITE/dashboard/demo/api/stepstitch/v1/sessions?limit=1" 200' in vercel
    assert 'probe POST "$SITE/dashboard/demo/api/stepstitch/v1/session/probe/verify" 403' in vercel
    assert 'probe PUT  "$SITE/dashboard/demo/admin/config/repro" 403' in vercel


def test_contract_failures_still_fail_the_job_through_the_gate():
    job = _doc()["jobs"]["verify"]
    by_name = {s["name"]: s for s in job["steps"]}
    # continue-on-error exists so ALL contracts report; the gate makes failure real.
    assert by_name["Railway public contract"]["continue-on-error"] is True
    assert by_name["Vercel public contract"]["continue-on-error"] is True
    assert by_name["Contact relay canary"]["continue-on-error"] is True
    gate = by_name["Gate on both contracts"]["run"]
    assert "exit 1" in gate
    assert "steps.railway.outcome" in gate and "steps.vercel.outcome" in gate
    assert "steps.contact.outcome" in gate


def test_contact_canary_is_labeled_delivered_for_real_and_gated():
    """The canary must prove an actual delivery (200 + canary:true echoed), be
    unmistakably synthetic to the receiving channel, and hard-fail otherwise —
    a missing CONTACT_WEBHOOK_URL must never verify green."""
    script = _steps()["Contact relay canary"]
    assert '\'{"canary": true}\'' in script
    assert '"$SITE/api/contact"' in script
    assert '[ "$code" = "200" ]' in script
    assert 'grep -q \'"canary":true\'' in script
    assert "exit 1" in script
    assert "::warning::" not in script, "an undelivered canary must fail, not warn"


def test_probes_are_quoted_functions_not_word_split_strings():
    steps = _steps()
    for name in ("Railway public contract", "Vercel public contract"):
        script = steps[name]
        assert "probe() {" in script, f"{name} must define the shared probe function"
        assert '-X "$method"' in script and '"$url"' in script
    whole = VERIFY.read_text(encoding="utf-8")
    # The original defect: curl arguments assembled by word-splitting an unquoted var.
    assert '$probe' not in whole, "no word-split curl command strings"


def test_summary_reports_shas_and_both_contract_outcomes():
    script = _steps()["Write summary"]
    assert "${GITHUB_SHA}" in script
    assert "steps.revision.outputs.observed" in script
    assert "steps.revision.outputs.confirmed" in script
    assert "steps.railway.outcome" in script
    assert "steps.vercel.outcome" in script
    assert "steps.contact.outcome" in script


@pytest.mark.parametrize("workflow", [VERIFY, CLEAN_INSTALL], ids=lambda p: p.name)
def test_every_run_script_is_valid_bash(workflow):
    """bash -n over each run: block — the strongest shell validation available here."""
    doc = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    scripts = [
        step["run"]
        for job in doc["jobs"].values()
        for step in job["steps"]
        if isinstance(step.get("run"), str)
    ]
    assert scripts, f"{workflow.name} has no run scripts?"
    for script in scripts:
        # Neutralise ${{ … }} expressions: Actions substitutes them before bash ever
        # runs, and bash -n would otherwise choke on the braces.
        neutered = script
        while "${{" in neutered:
            pre, rest = neutered.split("${{", 1)
            _, post = rest.split("}}", 1)
            neutered = pre + "GITHUB_EXPR" + post
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
            fh.write(neutered)
            path = fh.name
        proc = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
        assert proc.returncode == 0, f"bash -n failed in {workflow.name}: {proc.stderr}"
