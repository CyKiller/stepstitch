"""Community ticketing adapters (Apache-2.0) — bundled by default via ``integrations.bundle``,
and also the worked reference for `docs/connectors.md`'s "write your own adapter" guide."""
from .jira import JiraAdapter
from .zendesk import ZendeskAdapter

__all__ = ["JiraAdapter", "ZendeskAdapter"]
