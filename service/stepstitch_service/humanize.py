"""Plain-language rendering of structural evidence.

StepStitch's evidence is structural by design — route templates, HTTP statuses, selectors — and
that vocabulary is exactly right for the engineer who will fix the bug. It is useless to the
support lead who took the customer's call, the QA engineer triaging the queue, or the compliance
reviewer checking what was captured. They all open the same console.

So the translation lives here rather than in the console's markup: it is a pure function of the
fingerprint, which means it is unit-testable, it stays consistent across every surface (console,
MCP, anything later), and it can be part of the API contract instead of a lookup table buried in
a page. Nothing here invents facts — every phrase is derived from a field the scrubber already
cleared, so a plain summary carries no more information than the fingerprint it came from.

Design: pure, deterministic, dependency-free, and deliberately conservative. When a field is
missing the phrasing degrades to something still true rather than guessing.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

# ---- stage labels ----------------------------------------------------------------------
# The stage IDs in shapes.py are the contract (tests and the API depend on them); these are
# only what a human reads. Each answers "what do I do about this?", not "what is its state?".
STAGE_LABELS: Dict[str, str] = {
    "untriaged": "Waiting for a test run",
    "known_shape": "Seen before",
    "repro_invalid": "Test needs fixing",
    "reproduced": "Confirmed broken",
    "fix_failed": "Still broken",
    "fixed": "Fixed and proven",
}

STAGE_HELP: Dict[str, str] = {
    "untriaged": "Nobody has run the generated test against this yet, so we cannot say whether "
                 "it is reproducible.",
    "known_shape": "This broke the same way as something you already fixed. Start from that fix.",
    "repro_invalid": "The test we generated passed even before the fix — so it is not actually "
                     "catching this bug and needs adjusting.",
    "reproduced": "The test fails exactly as reported, so the bug is real and reproducible. It "
                  "is waiting on a fix.",
    "fix_failed": "Someone shipped a fix, but the test still fails. The bug is not gone.",
    "fixed": "The test failed before the fix and passed after it. That is the only thing we "
             "accept as proof.",
}

# ---- confidence ------------------------------------------------------------------------
# Mirrors GRADE_THRESHOLDS in replayability.py, expressed as what it means for the reader.
_CONFIDENCE_BANDS = (
    (0.85, "Reliably reproducible",
     "A developer should be able to reproduce this on the first try."),
    (0.70, "Likely reproducible",
     "There is enough detail here to reproduce it, with minor setup."),
    (0.55, "Might be reproducible",
     "Some steps are vague, so reproducing this may take a few attempts."),
    (0.40, "Hard to reproduce",
     "Key details are missing or unstable — expect to guess at some steps."),
)


def confidence_band(score: Optional[float]) -> str:
    """A 0-1 replayability score as the sentence a non-engineer needs."""
    if score is None:
        return "Not yet assessed"
    for threshold, label, _ in _CONFIDENCE_BANDS:
        if score >= threshold:
            return label
    return "Very hard to reproduce"


def confidence_help(score: Optional[float]) -> str:
    """One sentence explaining what the band means in practice."""
    if score is None:
        return "We have not scored this yet."
    for threshold, _, help_text in _CONFIDENCE_BANDS:
        if score >= threshold:
            return help_text
    return "There is not enough structure captured to rebuild what happened reliably."


# ---- naming ----------------------------------------------------------------------------
_PARAM_SEGMENT = re.compile(r"^[:{*]|^\d+$|^[0-9a-f]{8,}$", re.IGNORECASE)
_TESTID = re.compile(r"""\[\s*data-testid\s*=\s*["']?([^"'\]]+)["']?\s*\]""", re.IGNORECASE)
_WORD_SPLIT = re.compile(r"[-_.]+")


def _titlecase(value: str) -> str:
    """"review-transfer" -> "Review transfer". Sentence case, not Title Case."""
    words = [w for w in _WORD_SPLIT.split(value.strip()) if w]
    if not words:
        return ""
    joined = " ".join(words)
    return joined[0].upper() + joined[1:]


def page_name(route: Optional[str]) -> str:
    """The last meaningful segment of a route template, as a page a person would name.

    ``/accounts/:id/transfer`` -> "Transfer"; ``/checkout`` -> "Checkout"; ``/`` -> "Home".
    Parameter segments are skipped because ``:id`` names nothing.
    """
    if not route:
        return "Unknown page"
    segments = [s for s in str(route).split("/") if s]
    if not segments:
        return "Home"
    for segment in reversed(segments):
        if not _PARAM_SEGMENT.match(segment):
            return _titlecase(segment)
    return "Home"


def action_name(selector: Optional[str]) -> str:
    """The last thing the user touched, from its structural selector.

    ``[data-testid=review-transfer]`` -> "Review transfer". Returns "" when the selector is a
    CSS path rather than a named test id — a class chain names no user-facing action, so
    inventing one would be worse than saying nothing.
    """
    if not selector:
        return ""
    match = _TESTID.search(str(selector))
    if match:
        return _titlecase(match.group(1))
    ident = re.match(r"^#([A-Za-z0-9_-]+)$", str(selector).strip())
    if ident:
        return _titlecase(ident.group(1))
    return ""


def failure_phrase(fp: Dict[str, Any]) -> str:
    """What went wrong, in words, from the diagnostic fields."""
    status = fp.get("failing_status")
    exception = fp.get("exception_type")
    if status is not None:
        try:
            code = int(status)
        except (TypeError, ValueError):
            code = 0
        if code >= 500:
            return "the server errored"
        if code == 404:
            return "something could not be found"
        if code in (401, 403):
            return "access was refused"
        if code >= 400:
            return "the request was rejected"
    # The exception CLASS is often absent (the scrubber drops it when it could carry a message),
    # but the diagnostic type still tells us it was a crash rather than a failed request. Keying
    # only on exception_type would silently downgrade every scrubbed crash to "something went
    # wrong", which is true but useless.
    if exception or fp.get("diagnostic_type") == "exception":
        return "the page crashed"
    if fp.get("diagnostic_type") == "api_error":
        return "a request failed"
    return "something went wrong"


def plain_summary(fp: Optional[Dict[str, Any]]) -> str:
    """One sentence naming the page, the failure, and where it happened.

    "Transfer — the server errored after Review transfer"
    """
    fp = fp or {}
    page = page_name(fp.get("route"))
    phrase = failure_phrase(fp)
    action = action_name(fp.get("terminal_selector"))
    if action:
        return f"{page} — {phrase} after {action}"
    return f"{page} — {phrase}"


# ---- warnings --------------------------------------------------------------------------
# Every code replayability.py can emit, in the reader's terms. A code with no entry falls back
# to its own detail text, so a new warning degrades to today's behaviour rather than vanishing.
_WARNING_TEXT: Dict[str, str] = {
    "templated_route_needs_fixture":
        "the page address contains an ID, so the test needs a real account to run against",
    "unstable_selector":
        "some buttons are identified by their position or styling, which changes when the page "
        "is redesigned — the test may break for the wrong reason",
    "missing_selector":
        "we could not tell which control was used, so the test has to guess",
    "no_terminal_action":
        "the report does not end on a clear action, so there is nothing obvious to assert on",
    "long_trace":
        "the report is long, so the test covers a lot of ground and may be slow or brittle",
    "empty_trace":
        "nothing was captured for this report, so there is nothing to rebuild",
}


def warning_text(code: str, detail: Optional[str] = None) -> str:
    """Plain-language text for a replayability warning code."""
    return _WARNING_TEXT.get(code) or (detail or code.replace("_", " "))


def warning_summary(code: str, count: int, detail: Optional[str] = None) -> str:
    """A grouped warning as one sentence: N occurrences of one problem."""
    body = warning_text(code, detail)
    if count <= 1:
        return f"1 step: {body}"
    return f"{count} steps: {body}"


def stage_label(stage: str) -> str:
    return STAGE_LABELS.get(stage, stage.replace("_", " "))


def stage_help(stage: str) -> str:
    return STAGE_HELP.get(stage, "")


__all__ = [
    "STAGE_LABELS", "STAGE_HELP",
    "confidence_band", "confidence_help",
    "page_name", "action_name", "failure_phrase", "plain_summary",
    "warning_text", "warning_summary", "stage_label", "stage_help",
]
