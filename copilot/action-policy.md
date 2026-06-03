# StepStitch Copilot action policy

**Architecture:** StepStitch is the core; the agent reaches supporting systems
(ServiceNow, Salesforce) through Microsoft's **native connectors**, fed by StepStitch's
sanitized draft. StepStitch itself never creates records in a system of record.

This policy bounds what a Microsoft Copilot Studio custom agent may do with StepStitch.
It is enforced two ways: (1) the agent is only given the tools in `openapi-v2.json`, and
(2) the StepStitch service audits every operator action regardless of caller.

## Allowed (read-only / draft)

| Tool | Operation | Why it is safe |
|---|---|---|
| `ListRecentTraces` | `GET /sessions` | metadata only; admin + audited |
| `GetTraceSummary` | `GET /session/{id}/summary` | structure-derived; no NPI |
| `GetReplayabilityScore` | `GET /session/{id}/replayability` | derived score only |
| `GetPrivacyPosture` | `GET /session/{id}/privacy-posture` | scrub report + never-captured list |
| `GeneratePlaywrightRepro` | `GET /session/{id}/playwright` | returns code text; never executed here |
| `CreateExportPreview` | `POST /session/{id}/export-preview` | builds drafts; sends nothing |

## Forbidden — never expose these as Copilot tools

- Deleting traces (`DELETE /session/by-user/{id}`)
- Changing retention or running the purge (`POST /maintenance/purge-expired`)
- Toggling the org-wide kill switch
- Exporting raw trace JSON or the full `GET /session/{id}` (carries `explanation`)
- Reading unmasked page text or input values (the product never stores these)
- Running Playwright against production
- **A StepStitch tool** writing to ServiceNow / Salesforce. StepStitch is preview/draft
  only. Record creation happens through the agent's **native** ServiceNow/Salesforce
  connector — a governed, human-approved step, mapped from the StepStitch draft per
  `connector-field-map.md`, and constrained by a Power Platform DLP policy.

## Operating rules for the agent

1. Never claim a ticket was *created* — say a **draft/preview** was produced.
2. Always surface the privacy posture ("no SSNs, input values, page text, screenshots,
   raw URLs were captured") alongside any summary.
3. If a tool returns 404/403, report it plainly; do not retry destructive alternatives.
4. Keep the tool set tight (≤ ~25 per Microsoft's guidance); these six are sufficient.
