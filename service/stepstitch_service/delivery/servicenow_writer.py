"""ServiceNow direct-write — POST an incident draft to the Table API.

Sends the same sanitized draft that ``integrations.servicenow.build_incident_draft``
produces. The host injects an ``http_post`` closure carrying the instance URL + auth.
"""
from __future__ import annotations

from typing import Any, Dict

from .base import DeliveryError, DeliveryResult, HttpPostFn, RecordWriter


class ServiceNowWriter(RecordWriter):
    name = "servicenow"

    def __init__(self, http_post: HttpPostFn, *, table: str = "incident") -> None:
        self._post = http_post
        self._path = f"/api/now/table/{table}"

    async def _create(self, draft: Dict[str, Any]) -> DeliveryResult:
        resp = await self._post(self._path, draft)
        result = resp.get("result", resp) if isinstance(resp, dict) else {}
        record_id = result.get("sys_id") if isinstance(result, dict) else None
        if not record_id:
            raise DeliveryError("servicenow: response missing sys_id")
        return DeliveryResult(
            "servicenow",
            str(record_id),
            False,
            {"sys_id": record_id, "number": result.get("number")},
        )
