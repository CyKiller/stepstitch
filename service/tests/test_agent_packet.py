"""The handoff packet: honest about origin, and clear about what is a guess.

The claim these tests defend is the one that would otherwise rot silently. The packet used
to say ``never_included: stack traces``. Deep diagnostics make that false — but only for
evidence from the *reproduction*, never from the reported session. Splitting the posture by
origin is what keeps both halves true instead of softening one into uselessness.
"""
import json

from stepstitch_service.agent_packet import (
    COLLECTED_FROM_REPRODUCTION,
    NEVER_FROM_PRODUCTION,
    NOT_AN_AGENT_INSTRUCTION,
    build_packet,
    likely_files,
    privacy_posture,
    verification_command,
)

DIAGS = {
    "source": "local_reproduction",
    "customer_data_status": "not_verified",
    "failure_stack": [
        "Error: must not reproduce",
        "/app/src/payments/transfer.ts:42:9",
        "/app/.stepstitch/repro-abc/tests/repro.spec.ts:8:81",
        "/app/node_modules/@playwright/test/lib/x.js:1:1",
    ],
    "console_errors": ["pay failed"],
    "failed_requests": [{"method": "POST", "path": "/api/accounts/:id/pay", "status": 500}],
}


def _packet(**over):
    base = dict(
        trace_id="t-1", summary={"route": "/transfer"}, replayability={"score": 1.0},
        policy_name="financial-services-enterprise", scrub={"scrub_status": "clean"},
        recommended_next_step="Route to frontend engineering.",
        playwright_code="import { test } from '@playwright/test'",
    )
    base.update(over)
    return build_packet(**base)


# --- the origin split ---------------------------------------------------------------------

def test_the_two_halves_are_labelled_by_where_they_came_from():
    """A reader must be able to tell reproduction evidence from production evidence without
    knowing how StepStitch works internally."""
    posture = _packet(diagnostics=DIAGS)["privacy_posture"]
    assert posture["from_production"]["never_captured"] == NEVER_FROM_PRODUCTION
    assert posture["from_reproduction"]["source"] == "local_reproduction"
    assert posture["from_reproduction"]["customer_data_status"] == "not_verified"


def test_the_production_promise_is_not_weakened_by_deep_diagnostics():
    """The whole design: collecting more from the reproduction must take nothing more from
    the person who reported the bug."""
    with_diags = _packet(diagnostics=DIAGS)["privacy_posture"]
    without = _packet()["privacy_posture"]
    assert with_diags["from_production"] == without["from_production"]
    for item in ("screenshots", "page text", "input values", "request/response bodies"):
        assert item in with_diags["from_production"]["never_captured"]


def test_a_session_with_no_reproduction_claims_no_reproduction_evidence():
    """Listing what we *could* collect, when we collected nothing, would be a claim about
    data that does not exist."""
    posture = _packet()["privacy_posture"]
    assert posture["from_reproduction"]["collected"] == []
    assert "no reproduction has been run" in posture["from_reproduction"]["detail"]


def test_reproduction_evidence_is_listed_when_it_exists():
    posture = _packet(diagnostics=DIAGS)["privacy_posture"]
    assert posture["from_reproduction"]["collected"] == COLLECTED_FROM_REPRODUCTION
    assert any("stack" in item for item in posture["from_reproduction"]["collected"])


def test_the_legacy_posture_keys_survive_for_existing_readers():
    """The packet is drift-guarded against the individual endpoints; changing these keys
    would break that guard rather than the callers noticing."""
    posture = _packet()["privacy_posture"]
    assert posture["policy"] == "financial-services-enterprise"
    assert posture["never_captured"] == NEVER_FROM_PRODUCTION
    assert posture["scrub"] == {"scrub_status": "clean"}


# --- likely files are suggestions, and say so ---------------------------------------------

def test_generated_and_vendor_frames_are_not_suggested():
    """The reproduction spec is the thing doing the asserting, not the thing that is
    broken. Suggesting it sends an agent to edit the test."""
    paths = [f["path"] for f in likely_files(DIAGS)]
    assert paths == ["/app/src/payments/transfer.ts"]
    assert not any("repro.spec.ts" in p or "node_modules" in p for p in paths)


def test_suggestions_are_labelled_as_suggestions():
    """An agent told 'the bug is here' will edit that file with confidence. A stack frame
    is where execution was, not necessarily where the mistake is."""
    packet = _packet(diagnostics=DIAGS)
    assert "Suggestions only" in packet["likely_files_note"]
    assert all(f["why"] for f in packet["likely_files"])


def test_no_diagnostics_means_no_guesses():
    assert likely_files(None) == []
    assert _packet()["likely_files"] == []


# --- the reproduction and how it will be judged -------------------------------------------

def test_a_frozen_session_says_so_and_carries_both_digests():
    packet = _packet(frozen={"script_sha256": "a" * 64,
                             "execution_envelope_sha256": "b" * 64})
    repro = packet["reproduction"]
    assert repro["frozen"] is True
    assert repro["script_sha256"] == "a" * 64
    assert repro["execution_envelope_sha256"] == "b" * 64
    assert "changing the test does not change the verdict" in repro["detail"]


def test_an_unfrozen_session_does_not_pretend_to_be_frozen():
    repro = _packet()["reproduction"]
    assert repro["frozen"] is False
    assert repro["script_sha256"] is None
    assert "Not frozen yet" in repro["detail"]


def test_the_agent_is_told_exactly_how_it_will_be_marked():
    """No advantage in hiding a marking scheme that cannot be gamed: the script and the
    envelope are frozen, and the agent holds no credential that can write a verdict."""
    verification = _packet()["verification"]
    assert "verify-fix" in verification["command"]
    assert verification["verdicts"] == [
        "fixed", "still_failing", "different_failure", "unable_to_verify"]
    assert "cannot record a verdict" in verification["detail"]


def test_the_verification_command_names_the_session():
    assert "t-1" in verification_command("t-1")


def test_every_command_says_who_runs_it():
    """Found by a real trial, not by review: given a field called ``command``, a capable
    model went looking for the binary. Neither command is runnable by the agent — one is a
    local action rather than a read, the other needs the admin credential it is deliberately
    never given — so each must say so where it is read."""
    packet = _packet(frozen={"script_sha256": "a" * 64})
    for block in ("reproduction", "verification"):
        assert packet[block]["run_by"] == NOT_AN_AGENT_INSTRUCTION, block
        assert "never by this agent" in packet[block]["run_by"], block


def test_a_command_is_never_published_without_its_run_by():
    """The pairing is the point. A future field carrying a command and no ``run_by`` would
    reintroduce exactly the misreading this fixes."""
    packet = _packet(diagnostics=DIAGS, frozen={"script_sha256": "a" * 64})
    carries_a_command = [k for k, v in packet.items()
                         if isinstance(v, dict) and "command" in v]
    assert carries_a_command == ["reproduction", "verification"]
    assert all(packet[k].get("run_by") for k in carries_a_command)


# --- composition --------------------------------------------------------------------------

def test_the_packet_carries_the_reproduction_and_the_diagnostics():
    packet = _packet(diagnostics=DIAGS)
    assert packet["playwright_code"].startswith("import")
    assert packet["diagnostics"]["console_errors"] == ["pay failed"]
    assert packet["reproduction"]["command"] == "stepstitch reproduce t-1"


def test_repository_context_appears_only_when_known():
    assert "repository" not in _packet()
    packet = _packet(repository={"remote": "github.com/acme/app", "commit": "abc123"})
    assert packet["repository"]["commit"] == "abc123"


def test_posture_is_consistent_whichever_way_it_is_built():
    direct = privacy_posture("p", {"scrub_status": "clean"}, has_diagnostics=True)
    assert _packet(diagnostics=DIAGS, policy_name="p")["privacy_posture"] == direct


# --- the claim that would otherwise rot ---------------------------------------------------

def test_the_never_included_list_says_what_it_is_scoped_to():
    """It reads 'stack traces are never included'. Deep diagnostics make that false in
    general and true of the reported session — so the packet states which."""
    from stepstitch_service.agent_packet import NEVER_FROM_REPORTED_SESSION

    diagnostic = _packet(diagnostics=DIAGS)["diagnostic"]
    assert "stack traces" in diagnostic["never_included"]
    assert diagnostic["never_included"] == NEVER_FROM_REPORTED_SESSION
    assert "from the reported session" in diagnostic["never_included_scope"]


def test_a_stack_trace_is_present_and_the_packet_is_not_lying_about_it():
    """The two statements must be simultaneously true and locatable: no stack from the
    session, a stack from the reproduction."""
    packet = _packet(diagnostics=DIAGS)
    assert packet["diagnostics"]["failure_stack"]
    assert "stack traces" in packet["diagnostic"]["never_included"]
    assert packet["privacy_posture"]["from_reproduction"]["source"] == \
        "local_reproduction"
    assert any("stack" in c
               for c in packet["privacy_posture"]["from_reproduction"]["collected"])


def test_a_malformed_diagnostics_record_does_not_cost_the_packet():
    """Diagnostics are the extra; the reproduction and the summary are the product."""
    packet = _packet(diagnostics=["not", "a", "record"])
    assert packet["likely_files"] == []
    assert packet["playwright_code"]


def test_the_reproduction_posture_states_what_the_architecture_proves_and_no_more():
    """`STEPSTITCH_APP_BASE_URL` can point at an operator's staging application, and
    StepStitch does not enforce that it holds only synthetic records. So "no customer was
    in it" was never provable. What IS provable: nothing came from the reported session,
    and every string passed the scrubber. The posture must say exactly that."""
    packet = _packet(diagnostics={"failure_stack": ["at f (app.js:1:1)"]})
    posture = packet["privacy_posture"]["from_reproduction"]
    assert posture["source"] == "local_reproduction"
    assert posture["from_reported_session"] is False
    assert posture["content_scrubbed"] is True
    assert posture["environment_assurance"] == "operator_configured"
    assert posture["customer_data_status"] == "not_verified"
    assert "contains_customer_session_data" not in posture
    blob = json.dumps(packet)
    assert "No customer was in it" not in blob
    assert "contains_customer_session_data" not in blob
