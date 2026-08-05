# StepStitch Copilot action policy

**Architecture:** StepStitch is the core troubleshooting evidence layer; the agent
reaches supporting systems (ServiceNow, Salesforce, Genesys workflows) through
Microsoft's **native connectors** or governed Power Platform flows, fed by StepStitch's
sanitized drafts. StepStitch itself never creates records in a system of record.

This policy bounds what a Microsoft Copilot Studio custom agent may do with StepStitch.
It is enforced two ways: (1) the agent is only given the tools in `openapi-v2.json`, and
(2) the StepStitch service audits every operator action regardless of caller.

## Allowed (read-only / draft)

| Tool | Operation | Why it is safe |
|---|---|---|
| `ListRecentTraces` | `GET /sessions` | metadata only; admin + audited |
| `GetTraceSummary` | `GET /session/{id}/summary` | structure-derived; no raw values |
| `GetReplayabilityScore` | `GET /session/{id}/replayability` | derived score only |
| `GetPrivacyPosture` | `GET /session/{id}/privacy-posture` | scrub report + never-captured list |
| `GetDiagnosticSummary` | `GET /session/{id}/diagnostic-summary` | sanitized frontend/API diagnostics only |
| `GeneratePlaywrightRepro` | `GET /session/{id}/playwright` | returns code text; never executed here |
| `MatchVerifiedFixes` | `GET /session/{id}/similar-fixes` | structural fingerprint match to prior verified fixes; no raw values |
| `GetAttestation` | `GET /session/{id}/attestation` | signed, independently-verifiable evidence bundle; no raw values |
| `GetFragilityMap` | `GET /session/{id}/fragility` | per-step fragility ranking, worst-first; no raw values |
| `GenerateMinimalRepro` | `GET /session/{id}/minimal-repro` | smallest failing path compiled to Playwright; no raw values |
| `GetAgentPacket` (**Safe Agent Packet**) | `GET /session/{id}/agent-packet` | composed summary + replayability + privacy posture + diagnostic + repro in one call; no new data, no raw values |
| `CreateExportPreview` | `POST /session/{id}/export-preview` | builds drafts; sends nothing |
| `CreateFinancialServicesExportPreview` | `POST /session/{id}/financial-services-export-preview` | builds Salesforce, ServiceNow, Genesys drafts; sends nothing |

## Forbidden — never expose these as Copilot tools

- Deleting traces (`DELETE /session/by-user/{id}`)
- Changing retention or running the purge (`POST /maintenance/purge-expired`)
- Toggling the org-wide kill switch
- Exporting raw trace JSON or the full `GET /session/{id}` (carries `explanation`)
- Reading unmasked page text or input values (the product never stores these)
- Reading or exposing raw frontend logs, raw error messages, stack traces, headers,
  cookies, request/response bodies, screenshots, or full URLs
- Running Playwright against production
- **A StepStitch tool** writing to ServiceNow, Salesforce, or Genesys. The agent surface is
  preview/draft only. Record creation or queue handoff happens through native
  connectors/governed flows as a human-approved step, mapped from the StepStitch draft
  per `connector-field-map.md`, and constrained by a Power Platform DLP policy.
- The optional **governed direct-write** (`POST /session/{id}/deliver`, `delivery/`) is a
  separate, admin-only, human-approval-gated capability for customers not on Power Platform.
  It is **off by default**, defaults to a dry run, sends only the sanitized draft, and is
  **deliberately excluded from this agent/MCP surface** — never expose it as a Copilot tool.

## Operating rules for the agent

1. Never claim a ticket was *created* — say a **draft/preview** was produced.
2. Always surface the privacy posture ("no SSNs, input values, page text, screenshots,
   raw URLs were captured") alongside any summary.
3. If a tool returns 404/403, report it plainly; do not retry destructive alternatives.
4. Keep the tool set tight; these thirteen read/draft tools (the Safe Agent Packet plus the
   twelve individual reads/drafts) are sufficient for the financial-services support pack.
