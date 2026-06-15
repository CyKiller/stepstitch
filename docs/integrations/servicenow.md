# ServiceNow integration

StepStitch produces a **flat, sanitized ServiceNow Incident draft** (`build_incident_draft`,
`integrations/servicenow.py`), built only from the sanitized `TraceSummary`.

A real Incident is created either by a **Microsoft native ServiceNow connector / Power
Platform flow** (default — see `copilot/connector-field-map.md`) or by the optional
**governed direct-write** module (`stepstitch_service/delivery/`, off by default,
human-approval-gated).

## Draft → Incident field mapping

| Draft field | ServiceNow Incident field | Notes |
|---|---|---|
| `short_description` | `short_description` | Capped to **160 chars** by StepStitch (visible `…` marker; truncation noted in `work_notes`) |
| `description` | `description` | Sanitized summary only — no screens, field values, raw URLs, or page text |
| `category` | `category` | Default `software` (adapter-configurable) |
| `subcategory` | `subcategory` | Default `portal` (adapter-configurable) |
| `impact` | `impact` | Validated ∈ `1..5` |
| `urgency` | `urgency` | Validated ∈ `1..5` |
| `correlation_id` | `correlation_id` | `stepstitch:<trace_id>` — reconciles the Incident to the trace |
| `work_notes` | `work_notes` | Replayability score/grade, repro availability, privacy status |

`impact`/`urgency` default to `3`. The stock scale is `1..3`; instances that use `1..5` are
also accepted. Out-of-range values fail loudly at draft time rather than at send time.

## Setup checklist

1. Ensure the target table is **Incident** (or map the draft fields onto your table in the
   connector/flow).
2. Confirm `category`/`subcategory` values exist in your instance, or construct the adapter
   with values that do: `ServiceNowAdapter(category="...", subcategory="...")`.
3. Use `correlation_id` as the reconciliation key — store it and, optionally, make it
   searchable so support can jump from an Incident back to the trace.

## Production direct-write (Mode B)

Enable with `STEPSTITCH_DIRECT_WRITE=servicenow` and inject a configured writer. The
`[delivery]` extra ships reference HTTP clients (timeout + bounded retry/backoff; credentials
live in the closure, not in StepStitch core):

```python
# pip install "stepstitch-service[delivery]"
from stepstitch_service.delivery import ServiceNowWriter
from stepstitch_service.delivery.clients import servicenow_basic
writer = ServiceNowWriter(servicenow_basic("https://acme.service-now.com", user, pw))
# create_stepstitch_router(..., record_writers=[writer])
```

For idempotency that survives restarts/replicas, pass a durable store:
`DeliveryService(writers, idempotency_store=my_redis_backed_dict)` — keyed by
`target:idempotency_key`, so a retried `/deliver` never creates a duplicate incident.

## Reverse lookup

```
GET /stepstitch/v1/correlation/stepstitch:<trace_id>/summary
```

returns the sanitized summary for the `correlation_id` carried on the Incident.

## Privacy

`assert_flat` guarantees the draft is flat scalars with no forbidden keys; it can never carry
footsteps, the explanation, the user id, selectors, raw URLs, page text, or bodies.
