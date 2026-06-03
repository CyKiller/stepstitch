# Financial-Services Support Pack

This target pack is for regulated digital-support environments that use Salesforce,
ServiceNow, Genesys/contact-center workflows, and Microsoft Copilot/Power Platform.
It is intentionally generic: no customer names, logos, private system names, or
customer-specific assumptions belong in product code or public-facing docs.

## Product Thesis

StepStitch is the troubleshooting evidence layer between a vague user report and an
engineering-ready reproduction. It gives support and agents a better eye on what failed:

- structural footsteps and route templates,
- sanitized frontend/API diagnostics,
- replayability score and warnings,
- privacy posture for the trace,
- deterministic Playwright repro text,
- flat draft previews for governed downstream routing.

## Diagnostic Boundary

Allowed diagnostic fields are structural only: status, method, endpoint template,
exception type, source path template, line/column, SDK/build, release/environment, and
viewport. The SDK and server must not store raw console logs, raw error messages, stack
traces, request/response bodies, headers, cookies, screenshots, DOM/page text, input
values, user ids in drafts, or full URLs.

## Copilot / Agent Flow

1. List recent traces and select the relevant trace.
2. Read summary, privacy posture, replayability, and diagnostic summary.
3. Explain what was captured and what was never captured.
4. Build financial-services draft previews.
5. After human approval, map drafts to native connectors or governed flows:
   ServiceNow Incident, Salesforce Case, and Genesys support context.
6. Share the internal Playwright repro with engineering.

StepStitch itself does not create tickets, write cases, route conversations, or call
systems of record. It produces auditable, sanitized evidence and draft payloads.

## Marvox Relationship

Marvox is a dogfood/reference tenant only. Product logic, contracts, adapters, Copilot
tooling, and compliance evidence live in StepStitch. Marvox can re-vendor a released
StepStitch version later to demonstrate the same troubleshooting loop in a creative
production product, without financial-services language.
