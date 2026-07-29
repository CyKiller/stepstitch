"""GitHub issue/PR content is privacy-safe, label-correct, and deterministic."""
from stepstitch_service.integrations.base import build_trace_summary
from stepstitch_service.github_bridge.content import (
    build_issue, repro_labels, branch_name, regression_test_path,
)


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
    assert "No NPI" in issue.body or "no NPI" in issue.body
    blob = issue.title + issue.body
    assert "8675309" not in blob and "data-testid" not in blob
    assert build_issue(s) == issue


def test_branch_and_test_path():
    assert branch_name("trace_42") == "stepstitch/trace-trace_42"
    assert regression_test_path("trace_42") == "tests/stepstitch/repro_trace_42.spec.ts"


def test_build_body_matches_issue_body():
    from stepstitch_service.integrations.base import build_trace_summary
    from stepstitch_service.github_bridge.content import build_body, build_issue
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
