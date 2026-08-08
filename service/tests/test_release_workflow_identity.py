"""Guard the release workflow's identity invariant: what publishes is what was tagged.

Found during the 0.12.0 readiness audit. `release.yml`'s publish jobs checked out the
workflow's own ref — which on a `workflow_dispatch` from main is main's CURRENT HEAD, not
the tag. `inputs.version` only named the asset upload and the registry poll. Concretely:
cut v0.12.0 at commit X, land anything on main, dispatch with version=0.12.0 — and npm,
PyPI and GHCR all receive commit Y's code labeled 0.12.0 while the tag points at X.
Environment approval cannot catch this: the run LOOKS like the release being approved.

The invariant these tests pin: an `identity` job resolves the requested version to the
tag's peeled commit and asserts every version manifest at that commit agrees; every
publish job then checks out exactly that commit and re-asserts it. The workflow
DEFINITION still runs from main on dispatch — that is deliberate and documented in the
workflow — but the SOURCE being built is structurally the tag's.

Same coverage approach as test_verify_deploy_workflow.py: PyYAML parse + content pins,
because no actionlint/shellcheck exists in this repository.
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
RELEASE = REPO / ".github" / "workflows" / "release.yml"

PUBLISH_JOBS = ("npm", "pypi", "docker")


def _doc() -> dict:
    return yaml.safe_load(RELEASE.read_text(encoding="utf-8"))


def _job(name: str) -> dict:
    return _doc()["jobs"][name]


def _checkout_steps(job: dict) -> list[dict]:
    return [s for s in job.get("steps", [])
            if "actions/checkout" in str(s.get("uses", ""))]


def test_an_identity_job_resolves_the_requested_version_to_the_tags_commit():
    identity = _doc()["jobs"].get("identity")
    assert identity is not None, (
        "release.yml has no identity job: nothing resolves the requested version to the "
        "tag's commit, so a dispatch from main publishes main's HEAD as that version"
    )
    scripts = " ".join(s.get("run", "") for s in identity.get("steps", []))
    # The peel (^{commit}) is the point: the tag's target, not whatever HEAD is.
    assert "^{commit}" in scripts, "identity must peel the tag to its commit"
    outputs = identity.get("outputs", {})
    assert "sha" in outputs and "version" in outputs, (
        "identity must output the resolved sha and version for the publish jobs to pin to"
    )


def test_identity_asserts_every_version_manifest_at_the_tagged_commit():
    scripts = " ".join(s.get("run", "")
                       for s in _job("identity").get("steps", []))
    for manifest in ("package.json",
                     "packages/cli-shim/package.json",
                     "service/pyproject.toml"):
        assert manifest in scripts, (
            f"identity does not check {manifest}: that manifest could disagree with the "
            "requested version and still publish under it"
        )


def test_every_publish_job_checks_out_the_identity_sha_not_the_workflow_ref():
    for name in PUBLISH_JOBS:
        job = _job(name)
        needs = job.get("needs", [])
        needs = [needs] if isinstance(needs, str) else list(needs)
        assert "identity" in needs, f"{name} does not depend on the identity job"
        checkouts = _checkout_steps(job)
        assert checkouts, f"{name} has no checkout step"
        for step in checkouts:
            ref = str(step.get("with", {}).get("ref", ""))
            assert "needs.identity.outputs.sha" in ref, (
                f"{name}'s checkout has ref {ref!r}: without the identity sha it builds "
                "the workflow's own ref — main's HEAD on a dispatch — as the release"
            )


def test_every_publish_job_reasserts_the_checkout_after_the_fact():
    """Belt to the checkout's suspenders: `git rev-parse HEAD` must equal the pinned sha.

    checkout@ref is an input, and inputs can be refactored away silently; an in-job
    assertion fails loudly at run time if the pin is ever lost.
    """
    for name in PUBLISH_JOBS:
        scripts = " ".join(s.get("run", "") for s in _job(name).get("steps", []))
        assert "rev-parse HEAD" in scripts and "needs.identity.outputs.sha" in scripts, (
            f"{name} never re-asserts that HEAD is the identity sha"
        )


def test_no_publish_job_derives_its_version_from_the_workflow_ref():
    """`inputs.version || github.ref_name` inside a publish job is the pre-hardening
    pattern: a free-floating version string with no tie to the source being built. All
    version identity must flow from the identity job's outputs."""
    for name in PUBLISH_JOBS:
        scripts = " ".join(s.get("run", "") for s in _job(name).get("steps", []))
        assert "github.ref_name" not in scripts, (
            f"{name} still derives a version from the workflow ref instead of identity"
        )


def test_the_stranger_install_polls_the_identity_version():
    scripts = " ".join(s.get("run", "")
                       for s in _job("installable").get("steps", []))
    assert "needs.identity.outputs.version" in scripts, (
        "installable polls a version derived from the workflow ref; it must verify the "
        "version the identity job resolved"
    )


# --- the CI evidence must describe the commit being published -----------------------------
#
# Second finding, same audit. The identity job pinned every PUBLISH job to the tag's
# commit, but `verify` still ran the reusable ci.yml against the workflow's own ref — on a
# dispatch from main, main's CURRENT HEAD. Cut v0.12.0 at X, land Y on main, dispatch:
# identity and the publish jobs correctly use X while every green CI check describes Y.
# The release ships evidence about code it did not publish. The invariant is end to end:
# requested version -> peeled tag commit -> manifests -> release CI source -> artifacts.

CI = REPO / ".github" / "workflows" / "ci.yml"
PINNED_REF = "${{ inputs.source_sha || github.sha }}"


def _ci() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


def test_verify_depends_on_identity_and_tests_the_identity_sha():
    verify = _doc()["jobs"]["verify"]
    needs = verify.get("needs", [])
    needs = [needs] if isinstance(needs, str) else list(needs)
    assert "identity" in needs, (
        "verify does not depend on identity: the CI gate can run against a different "
        "commit than the one being published"
    )
    source = str(verify.get("with", {}).get("source_sha", ""))
    assert source == "${{ needs.identity.outputs.sha }}", (
        f"verify passes source_sha {source!r}: unless it is exactly the identity sha, the "
        "release's CI evidence describes the workflow's own ref — main's HEAD on a "
        "dispatch — not the tagged commit being published"
    )


def test_ci_declares_the_source_sha_input_for_release_calls():
    on = _ci().get("on") or _ci().get(True)  # PyYAML 1.1 parses bare `on:` as boolean True
    call = (on or {}).get("workflow_call") or {}
    inputs = (call or {}).get("inputs") or {}
    spec = inputs.get("source_sha")
    assert spec is not None, (
        "ci.yml declares no source_sha workflow_call input, so release.yml cannot point "
        "the CI gate at the tagged commit"
    )
    assert spec.get("type") == "string" and not spec.get("required", False), (
        "source_sha must be an optional string: push/PR runs supply nothing and must "
        "fall back to the triggering commit"
    )


def test_every_ci_job_checks_out_the_pinned_source():
    """Enumerated, not sampled — the coverage cannot silently shrink.

    Iterating every job and every checkout means a future job or checkout added without
    the pin fails here by construction; requiring at least one checkout per job means a
    job cannot drift out of coverage by dropping checkout entirely while still claiming
    to gate the release.
    """
    jobs = _ci()["jobs"]
    # ci.yml is the release gate via workflow_call; gutting it to a stub would let the
    # invariant "pass" vacuously. 10 = its job count when this guard landed.
    assert len(jobs) >= 10, f"ci.yml has only {len(jobs)} jobs — the release gate shrank"
    for name, job in jobs.items():
        checkouts = [s for s in job.get("steps", [])
                     if "actions/checkout" in str(s.get("uses", ""))]
        assert checkouts, (
            f"ci.yml job {name!r} has no checkout step: it cannot be testing the "
            "release source at all"
        )
        for step in checkouts:
            ref = str(step.get("with", {}).get("ref", ""))
            assert ref == PINNED_REF, (
                f"ci.yml job {name!r} checkout ref is {ref!r}, not {PINNED_REF!r}: on a "
                "release run it would test the workflow's ref instead of the tagged commit"
            )


def test_no_verification_path_derives_its_source_from_a_free_floating_ref():
    """`github.ref_name`/`github.head_ref` in ci.yml run scripts, or a verify-level
    source that is not the identity output, would reintroduce the X-published-Y-tested
    split under a different name."""
    for name, job in _ci()["jobs"].items():
        scripts = " ".join(s.get("run", "") for s in job.get("steps", []) or [])
        for floating in ("github.ref_name", "github.head_ref"):
            assert floating not in scripts, (
                f"ci.yml job {name!r} reads {floating}: a release-gate job must know its "
                "source only through the pinned checkout"
            )
