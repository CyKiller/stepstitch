# Salesforce integration

StepStitch produces a **flat, sanitized Salesforce Case draft** (`build_case_draft`,
`integrations/salesforce.py`). The draft is built only from the sanitized `TraceSummary` —
never raw footsteps, the explanation, the user id, page text, or bodies.

A real Case is created either:
- by a **Microsoft native Salesforce connector / Power Platform flow** (default model — see
  `copilot/connector-field-map.md`), or
- by the optional **governed direct-write** module (`stepstitch_service/delivery/`), off by
  default and human-approval-gated.

Either way, the Case carries the StepStitch fields below so the record reconciles back to the
trace.

## Required custom fields (Case object)

Deploy these six custom fields once. They are the exact fields the draft emits:

| API name | Type | Notes |
|---|---|---|
| `StepStitchTraceId__c` | Text(255), External ID | Opaque trace id (no raw values); enables reverse lookup |
| `RouteTemplate__c` | Text(255) | Templated route, e.g. `/accounts/:id` |
| `ReplayabilityScore__c` | Number(3,2) | 0.00–1.00 reproducibility score |
| `ReplayabilityGrade__c` | Text(1) | Letter grade A–F |
| `PrivacyStatus__c` | Text(40) | e.g. `Policy scrubbed / data unverified` |
| `PlaywrightReproLink__c` | Text(255) | Internal-only pointer; never a public URL |

Stock built-in Case fields used by the draft: `Subject` (capped to 255 chars by StepStitch),
`Origin` (= `StepStitch`), `Status` (= `New`), `Priority` (validated against the stock
picklist: `Low`/`Medium`/`High`/`Critical`).

## Deploying the fields (idempotent)

A ready-to-deploy Salesforce DX package is in [`scripts/salesforce/`](../../scripts/salesforce/).
With the [Salesforce CLI](https://developer.salesforce.com/tools/salesforcecli) authenticated
to your org:

```bash
cd scripts/salesforce
# Preview (no changes):
sf project deploy start --manifest manifest/package.xml --dry-run --target-org <alias>
# Deploy (safe to re-run — metadata deploys are upserts):
sf project deploy start --manifest manifest/package.xml --target-org <alias>
```

Field-level security: grant the relevant profiles/permission sets read/edit on the six
fields after deploy (the metadata deploy creates the fields but not the FLS grants).

## Reverse lookup

A Case's `StepStitchTraceId__c` lets an operator resolve the ticket back to the sanitized
trace via the read-only endpoint:

```
GET /stepstitch/v1/correlation/stepstitch:<trace_id>/summary
```

## Privacy

The draft is validated by `assert_flat` (scalars only, no forbidden keys). It cannot carry
footsteps, the explanation, the user id, selectors, page text, raw URLs, or bodies. Always
surface the privacy posture alongside any Case created from a StepStitch draft.
