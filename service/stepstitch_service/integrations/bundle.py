"""Bundled system-of-record draft adapters — built-in pack (Apache-2.0).

The concrete ServiceNow / Salesforce / Genesys / Jira / Zendesk / GitHub Issues / Linear /
Slack draft builders. The core never imports this module; a host wires the adapters into
the router:

    from stepstitch_service import create_stepstitch_router
    from stepstitch_service.integrations.bundle import default_draft_adapters
    router = create_stepstitch_router(..., draft_adapters=default_draft_adapters())

Keeping this isolated (enforced as a *layering* rule by tests/test_open_core_boundary.py +
.importlinter — core never imports a concrete adapter; adapters only see ``TraceSummary``)
means the service runs with zero adapters by default and the adapter set stays cleanly
swappable. A future commercially-licensed edition may ship additional adapters the same way.
"""
import logging
from typing import List

from .base import DraftAdapter
from .contrib.jira import JiraAdapter, build_jira_issue_draft
from .contrib.zendesk import ZendeskAdapter, build_zendesk_ticket_draft
from .genesys import GenesysAdapter, build_genesys_context_draft
from .github import GitHubIssuesAdapter, build_github_issue_draft
from .linear import LinearAdapter, build_linear_issue_draft
from .salesforce import SalesforceAdapter, build_case_draft
from .servicenow import ServiceNowAdapter, build_incident_draft
from .slack import SlackAdapter, build_slack_message_draft

logger = logging.getLogger("stepstitch")

# Third-party adapters register under this entry-point group (see docs/connectors.md):
#   [project.entry-points."stepstitch.adapters"]
#   my_adapter = "my_pkg:MyAdapter"
_ADAPTER_ENTRY_POINT_GROUP = "stepstitch.adapters"

__all__ = [
    "ServiceNowAdapter",
    "SalesforceAdapter",
    "GenesysAdapter",
    "JiraAdapter",
    "ZendeskAdapter",
    "GitHubIssuesAdapter",
    "LinearAdapter",
    "SlackAdapter",
    "build_incident_draft",
    "build_case_draft",
    "build_genesys_context_draft",
    "build_jira_issue_draft",
    "build_zendesk_ticket_draft",
    "build_github_issue_draft",
    "build_linear_issue_draft",
    "build_slack_message_draft",
    "default_draft_adapters",
    "discovered_draft_adapters",
    "all_draft_adapters",
]


def default_draft_adapters() -> List[DraftAdapter]:
    """The bundled draft adapters, in canonical order: enterprise support systems first
    (ServiceNow, Salesforce, Genesys), then general ticketing (Jira, Zendesk), then
    developer-first issue trackers (GitHub Issues, Linear), then chat notification (Slack)."""
    return [
        ServiceNowAdapter(),
        SalesforceAdapter(),
        GenesysAdapter(),
        JiraAdapter(),
        ZendeskAdapter(),
        GitHubIssuesAdapter(),
        LinearAdapter(),
        SlackAdapter(),
    ]


def discovered_draft_adapters() -> List[DraftAdapter]:
    """Load third-party adapters registered under the ``stepstitch.adapters`` entry point.

    Each entry point resolves to a ``DraftAdapter`` subclass, an instance, or a zero-arg
    factory returning one (or a list). A broken plugin is logged and skipped rather than
    crashing the host.
    """
    adapters: List[DraftAdapter] = []
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover - importlib.metadata always present on 3.8+
        return adapters

    eps = entry_points()
    if hasattr(eps, "select"):  # Python 3.10+
        selected = eps.select(group=_ADAPTER_ENTRY_POINT_GROUP)
    else:  # Python 3.9 returns a dict keyed by group
        selected = eps.get(_ADAPTER_ENTRY_POINT_GROUP, [])  # type: ignore[attr-defined,arg-type]

    for ep in selected:
        try:
            obj = ep.load()
            instance = obj() if isinstance(obj, type) or callable(obj) else obj
            if isinstance(instance, list):
                adapters.extend(instance)
            else:
                adapters.append(instance)
        except Exception:  # never let one bad plugin take down discovery
            logger.exception("stepstitch: failed to load adapter plugin %r", ep)
    return adapters


def all_draft_adapters() -> List[DraftAdapter]:
    """Built-in adapters plus any discovered third-party adapters."""
    return default_draft_adapters() + discovered_draft_adapters()
