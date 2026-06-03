# Draft → native-connector field map

StepStitch's `CreateExportPreview` (`POST /session/{id}/export-preview`) returns a flat,
sanitized draft per system. The Copilot agent maps these onto Microsoft's **native**
ServiceNow / Salesforce connector *Create Record* inputs. All values are scalars (the
connectors reject nested objects), and none carry NPI.

## ServiceNow — Create Record (table: `incident`)

| StepStitch draft field | ServiceNow Incident field |
|---|---|
| `short_description` | `short_description` |
| `description` | `description` |
| `category` | `category` |
| `subcategory` | `subcategory` |
| `impact` | `impact` |
| `urgency` | `urgency` |
| `correlation_id` (`stepstitch:<trace_id>`) | `correlation_id` |
| `work_notes` | `work_notes` |

`correlation_id` lets a later real incident be reconciled back to the trace.

## Salesforce — Create Record (object: `Case`)

| StepStitch draft field | Salesforce Case field |
|---|---|
| `Subject` | `Subject` |
| `Origin` (`StepStitch`) | `Origin` |
| `Status` | `Status` |
| `Priority` | `Priority` |
| `StepStitchTraceId__c` | `StepStitchTraceId__c` *(custom)* |
| `RouteTemplate__c` | `RouteTemplate__c` *(custom)* |
| `ReplayabilityScore__c` | `ReplayabilityScore__c` *(custom, number)* |
| `ReplayabilityGrade__c` | `ReplayabilityGrade__c` *(custom, text)* |
| `PrivacyStatus__c` | `PrivacyStatus__c` *(custom, text)* |
| `PlaywrightReproLink__c` | `PlaywrightReproLink__c` *(custom, text/url)* |

**Salesforce setup:** create the five `__c` custom fields on the Case object once. The
draft is intentionally flat (no nested objects) to satisfy the connector's constraints.

## Why StepStitch shapes the draft (instead of the agent free-forming it)

The draft is the **safety contract**: a deterministic, server-produced, flat payload that
is guaranteed sanitized. The agent does not invent field values from raw trace data — it
maps a vetted draft onto the connector, which keeps the create step auditable and keeps
NPI out of the system of record by construction.
