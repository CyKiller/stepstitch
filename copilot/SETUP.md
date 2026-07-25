# StepStitch + Copilot Studio — setup blueprint

**Topology:** StepStitch is the core privacy-safe evidence engine. A Microsoft Copilot
Studio agent is the operator hub. The agent reaches the "supporting areas" (ServiceNow,
Salesforce, Genesys workflows, …) through **Microsoft's own native connectors** or
governed Power Platform flows — StepStitch never holds those credentials and never calls
those APIs. StepStitch only exposes sanitized reads, sanitized diagnostics, and flat,
connector-ready **drafts**; the agent's native connector/flow performs the create or
handoff.

```
Copilot Studio agent
├── StepStitch (custom connector, from copilot/openapi-v2.json)   ← read-only / draft
│     ListRecentTraces · GetTraceSummary · GetReplayabilityScore · GetPrivacyPosture
│     GetDiagnosticSummary · GeneratePlaywrightRepro · MatchVerifiedFixes
│     GetAttestation · GetFragilityMap · GenerateMinimalRepro · GetAgentPacket
│     CreateExportPreview · CreateFinancialServicesExportPreview
├── ServiceNow (native connector)   ← Create Record (Incident)
└── Salesforce (native connector)   ← Create Record (Case)
└── Genesys workflow/context         ← queue/case context, via governed flow
```

## Choose a connection path

Two ways to connect an agent to the **live** StepStitch service — the same thirteen
read-only/draft operations (the **Safe Agent Packet** and twelve individual reads/drafts),
both sharing `system-prompt.md`, `action-policy.md`, and `connector-field-map.md`.

| Path | Best for | Doc |
|---|---|---|
| **MCP server** (the universal connector) | "for all" — Claude, OpenAI, LangGraph, Vertex, Bedrock, Copilot Studio | [MCP-SETUP.md](MCP-SETUP.md) |
| **OpenAPI custom connector** | Microsoft Copilot Studio specifically | this file (§1–4) |

The sections below cover the **OpenAPI custom connector** path.

## 1. Register StepStitch as a custom connector

1. Power Platform → **Custom connectors → New → Import an OpenAPI file**.
2. Upload `copilot/openapi-v2.json`.
3. Set the host to your StepStitch deployment; security = OAuth2/bearer (same SSO the
   StepStitch admin API already uses — these tools are admin-only and audited).
4. Test `GetTraceSummary` against a known trace id.

## 2. Build the agent

1. Copilot Studio → **Create agent**.
2. Paste `copilot/system-prompt.md` as the agent instructions.
3. Add tools:
   - the **StepStitch** custom connector actions,
   - the **ServiceNow** native connector → *Create Record* (Incident),
   - the **Salesforce** native connector → *Create Record* (Case),
   - the customer's governed Genesys/Power Platform handoff flow, if available.
4. Apply `copilot/action-policy.md` as the guardrail: StepStitch tools are read/draft
   only; record creation happens **only** via the native connectors, as a governed,
   human-approved step.

## 3. Governance (do this before enabling create)

- Put the ServiceNow/Salesforce/Genesys workflow connectors in a **DLP policy** that
  blocks them from combining with arbitrary HTTP/unknown connectors.
- Require **human approval** in the topic before the native *Create Record* runs.
- Keep StepStitch's tools in the same DLP group so a trace summary can feed a draft but
  cannot be exfiltrated to an unmanaged connector.

## 4. The flow the agent runs

1. `GetTraceSummary` + `GetPrivacyPosture` → state what was captured / never captured.
2. `GetDiagnosticSummary` + `GetReplayabilityScore` → identify likely owner and whether
   engineering can reproduce it.
3. `CreateFinancialServicesExportPreview` → get the **flat, sanitized draft** for each system.
4. Map the draft fields onto the native connector's *Create Record* (see
   `connector-field-map.md`) and run it **after human approval**.
5. `GeneratePlaywrightRepro` → attach/share the repro internally.

The only data that ever leaves StepStitch is the sanitized summary, sanitized diagnostic
summary, and flat drafts — no footsteps, no free-text explanation, no user id, no page
text, no raw logs, and no screenshots.
