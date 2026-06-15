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
