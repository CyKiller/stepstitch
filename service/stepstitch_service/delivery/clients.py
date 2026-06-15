"""Reference HTTP clients for governed direct-write (optional ``[delivery]`` extra).

Each factory returns an async ``http_post(path, json_body) -> dict`` closure suitable as a
``RecordWriter`` transport. Credentials live in the closure, never in StepStitch core.
Includes a request timeout and bounded retry with exponential backoff on transient errors.

    pip install "stepstitch-service[delivery]"

    from stepstitch_service.delivery import ServiceNowWriter, SalesforceWriter
    from stepstitch_service.delivery.clients import servicenow_basic, salesforce_bearer
    writers = [
        ServiceNowWriter(servicenow_basic("https://acme.service-now.com", user, pw)),
        SalesforceWriter(salesforce_bearer("https://acme.my.salesforce.com", access_token)),
    ]
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from .base import DeliveryError, HttpPostFn

# Status codes worth retrying (rate-limit + transient server errors).
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}


def http_post_client(
    base_url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
    attempts: int = 3,
    backoff: float = 0.2,
    transport: Any = None,
    auth: Any = None,
) -> HttpPostFn:
    """A generic async POST-JSON closure with timeout + bounded retry.

    ``transport`` is for tests (pass an ``httpx.MockTransport``). Retries fire on transport
    errors and transient status codes; a 4xx (other than 429) fails fast.
    """

    async def post(path: str, json_body: Dict[str, Any]) -> Dict[str, Any]:
        import httpx

        last: Any = None
        client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers or {},
            timeout=timeout,
            transport=transport,
            auth=auth,
        )
        try:
            for attempt in range(attempts):
                try:
                    resp = await client.post(path, json=json_body)
                except httpx.TransportError as exc:
                    last = exc
                else:
                    if resp.status_code in _TRANSIENT_STATUS:
                        last = DeliveryError(f"transient {resp.status_code} from {path}")
                    elif resp.status_code >= 400:
                        raise DeliveryError(
                            f"{resp.status_code} from {path}: {resp.text[:200]}"
                        )
                    else:
                        return resp.json()
                if attempt < attempts - 1:
                    await asyncio.sleep(backoff * (2 ** attempt))
            raise DeliveryError(
                f"direct-write to {path} failed after {attempts} attempts: {last}"
            )
        finally:
            await client.aclose()

    return post


def servicenow_basic(
    instance_url: str, user: str, password: str, **kw: Any
) -> HttpPostFn:
    """ServiceNow Table API client using basic auth."""
    import httpx

    return http_post_client(
        instance_url,
        headers={"Accept": "application/json"},
        auth=httpx.BasicAuth(user, password),
        **kw,
    )


def servicenow_bearer(instance_url: str, token: str, **kw: Any) -> HttpPostFn:
    """ServiceNow Table API client using an OAuth bearer token."""
    return http_post_client(
        instance_url,
        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
        **kw,
    )


def salesforce_bearer(instance_url: str, access_token: str, **kw: Any) -> HttpPostFn:
    """Salesforce REST client using an OAuth access token."""
    return http_post_client(
        instance_url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        **kw,
    )
