"""StepStitch optional governed direct-write (off by default).

Delivers the already-sanitized export-preview draft to a system of record. Off unless a host
injects configured writers; human-approval-gated; audited; and never on the agent surface.
See ``base.py`` for the trust model.
"""
from .base import (
    DeliveryError,
    DeliveryResult,
    DeliveryService,
    HttpPostFn,
    RecordWriter,
)
from .config import enabled_targets_from_env
from .salesforce_writer import SalesforceWriter
from .servicenow_writer import ServiceNowWriter

# Reference HTTP clients require the optional [delivery] extra (httpx); import lazily so the
# core stays dependency-free.
try:  # pragma: no cover - exercised via the [delivery] extra
    from .clients import (
        http_post_client,
        salesforce_bearer,
        servicenow_basic,
        servicenow_bearer,
    )
except Exception:  # noqa: BLE001 - clients are optional
    http_post_client = salesforce_bearer = servicenow_basic = servicenow_bearer = None  # type: ignore

__all__ = [
    "RecordWriter",
    "DeliveryResult",
    "DeliveryError",
    "DeliveryService",
    "HttpPostFn",
    "ServiceNowWriter",
    "SalesforceWriter",
    "enabled_targets_from_env",
    "http_post_client",
    "servicenow_basic",
    "servicenow_bearer",
    "salesforce_bearer",
]
