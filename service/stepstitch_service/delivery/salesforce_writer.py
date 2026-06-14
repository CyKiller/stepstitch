"""Salesforce direct-write — POST a Case draft to the sObject REST API.

Sends the same sanitized draft that ``integrations.salesforce.build_case_draft`` produces.
The host injects an ``http_post`` closure carrying the instance URL + auth.
"""
from __future__ import annotations

from typing import Any, Dict

from .base import DeliveryError, DeliveryResult, HttpPostFn, RecordWriter


class SalesforceWriter(RecordWriter):
    name = "salesforce"

    def __init__(
        self, http_post: HttpPostFn, *, sobject: str = "Case", api_version: str = "v60.0"
    ) -> None:
        self._post = http_post
        self._path = f"/services/data/{api_version}/sobjects/{sobject}"

    async def _create(self, draft: Dict[str, Any]) -> DeliveryResult:
        resp = await self._post(self._path, draft)
        record_id = resp.get("id") if isinstance(resp, dict) else None
        success = resp.get("success", bool(record_id)) if isinstance(resp, dict) else False
        if not record_id or not success:
            raise DeliveryError(f"salesforce: create not confirmed ({resp!r})")
        return DeliveryResult("salesforce", str(record_id), False, {"id": record_id})
