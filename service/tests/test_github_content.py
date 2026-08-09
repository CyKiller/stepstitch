"""GitHub issue/PR content is privacy-safe, label-correct, and deterministic."""
from stepstitch_service.github_bridge.content import (
    branch_name,
    build_issue,
    regression_test_path,
    repro_labels,
)
from stepstitch_service.integrations.base import build_trace_summary


def _summary(grade_footsteps):
    return build_trace_summary("trace_42", grade_footsteps, project_id="p1")


def _failing():
    return [{"timestamp": "t", "type": "api_error",
             "route": "/accounts/:id/distributions", "label": "[masked]",
             "metadata": {"status": 500, "endpoint": "/api/accounts/:id"}}]


def _nav_only():
    return [{"timestamp": "t", "type": "navigation", "route": "/dashboard",
             "label": "[masked]"}]


def test_repro_ready_labels_for_high_grade():
    labels = repro_labels(_summary(_failing()))
    assert "stepstitch" in labels and "privacy-safe" in labels
    assert "stepstitch:repro-ready" in labels
    assert "stepstitch:needs-data" not in labels


def test_needs_data_labels_for_low_grade():
    labels = repro_labels(_summary(_nav_only()))
    assert "stepstitch:needs-data" in labels
    assert "stepstitch:repro-ready" not in labels


def test_issue_is_privacy_safe_and_deterministic():
    s = _summary(_failing())
    issue = build_issue(s)
    assert issue.title.startswith("[StepStitch]")
    assert "stepstitch:trace_42" in issue.body
    # The body says what the server DID (structural capture, server-side scrubbing),
    # not what it claims is absent: the scrubber's patterns cannot prove a customer's
    # name never appeared, so an issue filed in someone's tracker must not assert it.
    assert "server-scrubbed" in issue.body
    assert "no NPI" not in issue.body.lower()
    blob = issue.title + issue.body
    assert "8675309" not in blob and "data-testid" not in blob
    assert build_issue(s) == issue


def test_branch_and_test_path():
    assert branch_name("trace_42") == "stepstitch/trace-trace_42"
    assert regression_test_path("trace_42") == "tests/stepstitch/repro_trace_42.spec.ts"


def test_build_body_matches_issue_body():
    from stepstitch_service.github_bridge.content import build_body, build_issue
    from stepstitch_service.integrations.base import build_trace_summary
    s = build_trace_summary("trace_42", [
        {"timestamp": "t", "type": "api_error", "route": "/x", "label": "[masked]",
         "metadata": {"status": 500}}], project_id="p1")
    assert build_body(s) == build_issue(s).body


def test_repro_workflow_template_is_runnable_yaml_text():
    from stepstitch_service.github_bridge.workflow import STEPSTITCH_REPRO_WORKFLOW
    t = STEPSTITCH_REPRO_WORKFLOW
    assert "workflow_dispatch" in t
    assert "trace_id" in t
    assert "playwright" in t.lower()
    assert "stepstitch:confirmed-repro" in t


def test_repro_workflow_reports_verify_result():
    from stepstitch_service.github_bridge.workflow import STEPSTITCH_REPRO_WORKFLOW
    t = STEPSTITCH_REPRO_WORKFLOW
    assert "/verify" in t            # CI reports the repro outcome back to StepStitch
    assert "post_passed" in t        # the run result is posted as the post-fix outcome


def test_repro_workflow_parses_as_yaml_with_three_jobs():
    import yaml

    from stepstitch_service.github_bridge.workflow import STEPSTITCH_REPRO_WORKFLOW

    doc = yaml.safe_load(STEPSTITCH_REPRO_WORKFLOW)
    assert list(doc["jobs"]) == ["red", "green", "report"]
    # red and green each publish whether they ran and whether they passed.
    for job in ("red", "green"):
        assert set(doc["jobs"][job]["outputs"]) == {"passed", "ran"}
    assert doc["jobs"]["report"]["needs"] == ["red", "green"]


def test_the_red_half_is_measured_not_assumed():
    """The load-bearing property of this release.

    The previous template hardcoded ``"pre_passed": false`` and ran the reproduction once,
    so ``confirmed_fixed`` rested on a red run that never happened. A verdict built on an
    assumed failure is not evidence.
    """
    from stepstitch_service.github_bridge.workflow import STEPSTITCH_REPRO_WORKFLOW

    t = STEPSTITCH_REPRO_WORKFLOW
    assert '"pre_passed": false' not in t
    assert '\\"pre_passed\\": false' not in t
    # pre_passed comes from the red job's measured outcome.
    assert "PRE: ${{ needs.red.outputs.passed }}" in t
    assert "POST: ${{ needs.green.outputs.passed }}" in t
    # The red job checks out a DIFFERENT ref than the fix, or it proved nothing.
    assert "pre_ref" in t and "git checkout --detach" in t


def test_workflow_uses_a_narrow_verify_token_not_the_admin_token():
    from stepstitch_service.github_bridge.workflow import STEPSTITCH_REPRO_WORKFLOW

    t = STEPSTITCH_REPRO_WORKFLOW
    assert "STEPSTITCH_VERIFY_TOKEN" in t
    assert "STEPSTITCH_ADMIN_TOKEN" not in t, "CI must not be handed admin"


def test_workflow_records_nothing_when_a_run_did_not_complete():
    """A broken pipeline must not become a spurious verdict."""
    from stepstitch_service.github_bridge.workflow import STEPSTITCH_REPRO_WORKFLOW

    t = STEPSTITCH_REPRO_WORKFLOW
    assert "needs.red.outputs.ran == 'true' && needs.green.outputs.ran == 'true'" in t
    assert "StepStitch stores only measured results." in t


# --- the FixProof merge gate template ---------------------------------------------------


def test_fixproof_gate_parses_as_yaml_and_runs_on_pull_request():
    import yaml

    from stepstitch_service.github_bridge import STEPSTITCH_FIXPROOF_GATE_WORKFLOW

    doc = yaml.safe_load(STEPSTITCH_FIXPROOF_GATE_WORKFLOW)
    on = doc.get("on") or doc.get(True)  # PyYAML 1.1 reads bare `on:` as boolean True
    assert "pull_request" in on
    assert list(doc["jobs"]) == ["fixproof"]


def test_fixproof_gate_binds_the_pr_head_not_the_merge_commit():
    """github.sha on a pull_request event is the ephemeral MERGE commit — no exported
    proof can ever name it, so binding it would fail every honest proof and (worse)
    binding nothing would pass a proof about unrelated code."""
    from stepstitch_service.github_bridge import STEPSTITCH_FIXPROOF_GATE_WORKFLOW

    assert "github.event.pull_request.head.sha" in STEPSTITCH_FIXPROOF_GATE_WORKFLOW
    assert "--head-sha" in STEPSTITCH_FIXPROOF_GATE_WORKFLOW
    assert "${{ github.sha }}" not in STEPSTITCH_FIXPROOF_GATE_WORKFLOW


def test_fixproof_gate_needs_no_secret_and_no_token():
    """The gate is offline verification of a document the PR carries. A secret in this
    template would mean the check trusts something other than the proof."""
    from stepstitch_service.github_bridge import STEPSTITCH_FIXPROOF_GATE_WORKFLOW

    assert "secrets." not in STEPSTITCH_FIXPROOF_GATE_WORKFLOW
    assert "STEPSTITCH_ADMIN_TOKEN" not in STEPSTITCH_FIXPROOF_GATE_WORKFLOW
    assert "STEPSTITCH_VERIFY_TOKEN" not in STEPSTITCH_FIXPROOF_GATE_WORKFLOW
    assert "permissions: {}" in STEPSTITCH_FIXPROOF_GATE_WORKFLOW


def test_fixproof_gate_command_parses_under_the_cli():
    """House rule: a command the software hands a customer must itself parse."""
    from stepstitch_service.cli import build_parser

    build_parser().parse_args(
        ["proof", "verify", "fixproof.json", "--policy", "proof-policy.json",
         "--head-sha", "a" * 40])


def test_the_shipped_proof_policy_is_usable_and_strict():
    """The example policy must load, carry no typo'd keys, and hold the measured floor —
    it is what customers will copy verbatim."""
    import json
    from pathlib import Path

    from stepstitch_service.fixproof import POLICY_KEYS

    policy = json.loads(
        (Path(__file__).resolve().parents[2] / "examples" / "proof" /
         "proof-policy.json").read_text(encoding="utf-8"))
    unknown = {k for k in policy if k not in POLICY_KEYS and not k.startswith("_")}
    assert not unknown, f"shipped policy carries unknown keys: {unknown}"
    assert policy["require_grade"] == "measured"
    assert policy["require_pre_red"] is True
    assert policy["require_post_green"] is True
    assert policy["allowed_verifier_kinds"] == ["measured-by-host"]
