"""Reference community adapters (Apache-2.0) — worked examples of the connector SDK."""
from .jira import JiraAdapter
from .zendesk import ZendeskAdapter

__all__ = ["JiraAdapter", "ZendeskAdapter"]
