"""Field validation + length caps for system-of-record drafts.

System-of-record connectors silently truncate over-long fields and reject out-of-range
enum values. Doing both *here* — in the draft builder — makes the behaviour explicit,
testable, and honest: a truncated field is visibly marked, and an invalid enum fails loudly
at draft time instead of mysteriously at send time.

These limits are the safe defaults for the stock objects (ServiceNow Incident, Salesforce
Case). An instance may widen them; an adapter can be constructed with different choices.
"""
from __future__ import annotations

from typing import Iterable, Tuple

# ServiceNow Incident impact/urgency are a small ordinal scale. Stock is 1..3; many
# instances extend to 1..5, so accept the wider, still-safe set.
SERVICENOW_IMPACT_URGENCY = frozenset({"1", "2", "3", "4", "5"})

# Salesforce Case Priority stock picklist. Instances may customise; this is the safe set.
SALESFORCE_PRIORITY = frozenset({"Low", "Medium", "High", "Critical"})

# Jira stock issue types. Instances customise per project scheme; this is the safe default set.
JIRA_ISSUE_TYPES = frozenset({"Bug", "Task", "Story", "Incident"})

# Zendesk stock ticket type + priority picklists.
ZENDESK_TYPE = frozenset({"problem", "incident", "question", "task"})
ZENDESK_PRIORITY = frozenset({"low", "normal", "high", "urgent"})

# Linear's numeric priority scale, as strings: 0=No priority, 1=Urgent, 2=High, 3=Normal,
# 4=Low.
LINEAR_PRIORITY = frozenset({"0", "1", "2", "3", "4"})

# Stock field length limits.
SERVICENOW_SHORT_DESCRIPTION_MAX = 160
SALESFORCE_SUBJECT_MAX = 255
JIRA_SUMMARY_MAX = 255
ZENDESK_SUBJECT_MAX = 150
# GitHub issue titles and Linear issue titles are both capped well below the APIs' hard
# limits, matching the conservative-cap pattern used for every other adapter.
GITHUB_TITLE_MAX = 256
LINEAR_TITLE_MAX = 255
# Slack block/text payload limit (a single `text` block tops out at 3000 chars).
SLACK_TEXT_MAX = 3000

# Marker appended to a value that had to be truncated, so the cut is never silent.
_TRUNCATION_SUFFIX = "…"


def validate_choice(value: str, allowed: Iterable[str], *, field: str) -> str:
    """Return ``value`` if it is in ``allowed``; otherwise raise ``ValueError``."""
    allowed_set = set(allowed)
    if value not in allowed_set:
        raise ValueError(
            f"{field}={value!r} is not an allowed value; expected one of "
            f"{sorted(allowed_set)}"
        )
    return value


def cap(value: str, maxlen: int) -> Tuple[str, bool]:
    """Cap ``value`` to ``maxlen`` characters.

    Returns ``(value, was_truncated)``. When truncation happens the result ends with a
    visible marker and is guaranteed to be ``<= maxlen`` characters, so the connector never
    has to silently cut it.
    """
    if maxlen <= 0:
        raise ValueError("maxlen must be positive")
    if len(value) <= maxlen:
        return value, False
    return value[: maxlen - 1] + _TRUNCATION_SUFFIX, True
