# StepStitch + Copilot Studio — setup blueprint

**Topology:** StepStitch is the core privacy-safe evidence engine. A Microsoft Copilot
Studio agent is the operator hub. The agent reaches the "supporting areas" (ServiceNow,
Salesforce, …) through **Microsoft's own native connectors** — StepStitch never holds
those credentials and never calls those APIs. StepStitch only exposes sanitized reads
and a flat, connector-ready **draft**; the agent's native connector creates the record.

```
Copilot Studio agent
├── StepStitch (custom connector, from copilot/openapi-v2.json)   ← read-only / draft
│     GetTraceSummary · GetPrivacyPosture · GetReplayabilityScore
│     GeneratePlaywrightRepro · CreateExportPreview · ListRecentTraces
├── ServiceNow (native connector)   ← Create Record (Incident)
└── Salesforce (native connector)   ← Create Record (Case)
```

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
   - the **StepStitch** custom connector actions (all six),
   - the **ServiceNow** native connector → *Create Record* (Incident),
   - the **Salesforce** native connector → *Create Record* (Case).
4. Apply `copilot/action-policy.md` as the guardrail: StepStitch tools are read/draft
   only; record creation happens **only** via the native connectors, as a governed,
   human-approved step.

## 3. Governance (do this before enabling create)

- Put the ServiceNow/Salesforce connectors in a **DLP policy** that blocks them from
  combining with arbitrary HTTP/unknown connectors.
- Require **human approval** in the topic before the native *Create Record* runs.
- Keep StepStitch's tools in the same DLP group so a trace summary can feed a draft but
  cannot be exfiltrated to an unmanaged connector.

## 4. The flow the agent runs

1. `GetTraceSummary` + `GetPrivacyPosture` → state what was captured / never captured.
2. `GetReplayabilityScore` → say whether engineering can reproduce it.
3. `CreateExportPreview` → get the **flat, sanitized draft** for each system.
4. Map the draft fields onto the native connector's *Create Record* (see
   `connector-field-map.md`) and run it **after human approval**.
5. `GeneratePlaywrightRepro` → attach/share the repro internally.

The only data that ever leaves StepStitch is the sanitized summary + flat draft — no
footsteps, no free-text explanation, no user id, no page text.
