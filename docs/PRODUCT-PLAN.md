# StepStitch — Product Plan (standalone product · universal agentic connector)

Status: **draft for review** · Created 2026-06-10 · Owner: you
Companion to [`STATUS.md`](STATUS.md) (acceptance ledger) and [`../contracts/stepstitch.md`](../contracts/stepstitch.md) (frozen contract).

This plan takes StepStitch from a *feature-complete, embedded evidence layer* (today, proven
inside the reference app) to **its own product** that any agentic network can call — so a
financial-services-grade deployment can be stood up against real customers.

---

## 1. Thesis (the one decision everything follows from)

**StepStitch is a capability *provider*, not an agent *orchestrator*.** It perceives a
user-reported failure, scores reproducibility, compiles a runnable Playwright repro, builds a
privacy/compliance record, and drafts a ticket — deterministically, read-only/draft-only,
human-gated. It never plans, never acts autonomously, never files.

Therefore StepStitch must **never build its own agentic network.** Its "universal connector"
is to **be the best tool that every agent network can call.** Concretely that means one
capability contract surfaced two ways:

```
   ONE capability contract  (contracts/stepstitch.md  +  copilot/openapi-v2.json)
   ListRecentTraces · GetTraceSummary · GetReplayabilityScore · GetPrivacyPosture
   · GetDiagnosticSummary · GeneratePlaywrightRepro · MatchVerifiedFixes
   · GetAttestation · GetFragilityMap · GenerateMinimalRepro · GetAgentPacket (composed)
   · CreateExportPreview · CreateFinancialServicesExportPreview
                                   │
        ┌──────────────────────────┴──────────────────────────┐
        ▼                                                     ▼
  ① MCP SERVER (universal)                          ② MS Copilot connector
     write once →                                      (Copilot Studio /
     Copilot Studio, OpenAI,                           Foundry custom connector)
     Vertex, LangGraph,                                — Microsoft enterprise
     Bedrock, Claude                                     path
```

**StepStitch the product = the connectors: ① (MCP, the spine) + ② (Microsoft Copilot
connector, already in [`../copilot/`](../copilot/)).** ① is the only net-new build, and
because every major platform is an MCP client in 2026 it unlocks all the others for ~free.
This satisfies the "not agentic until thought out for each company" principle: the autonomy
lives in *the customer's* network; StepStitch stays a deterministic, governed tool.

---

## 2. What is already done (build the plan on this, not on a rewrite)

Per [`STATUS.md`](STATUS.md) — all backed by named, green tests:

- Privacy-by-default SDK + redaction (`src/`), server-side scrubber trust boundary (`scrubber.py`).
- Deterministic Playwright compiler (`compiler.py`), replayability score (`replayability.py`).
- Decoupled FastAPI router (`router.py`) — host injects auth + DB; org-wide kill switch; split retention.
- 4 deployment profiles (`profiles/*.json`, drift-guarded): `financial-services-enterprise` (default), `healthcare-strict`, `internal-enterprise`, `open-source-default`.
- Draft-only integrations (ServiceNow / Salesforce / Genesys) consuming only a flat `TraceSummary` — never raw footsteps, explanation, or user id.
- **Copilot-safe surface + OpenAPI pack** (`copilot/`), guarded by `test_copilot_surface.py` to expose **no destructive operation** and only real routes.
- Compliance evidence generator (`compliance.py`), SBOM, golden-path E2E (`test_golden_path.py`).

**The capability surface is already frozen and proven non-destructive.** P0 below is therefore
mostly formalization, and the MCP server (P1) is a thin wrapper over the *same* operations.

---

## 3. The connector decision — financial-services primary, others optional

Research (June 2026): MCP has ~97M monthly SDK downloads, is adopted by Microsoft, OpenAI,
Google, AWS, and Anthropic, and is governed under the Linux Foundation (Agentic AI Foundation).
Copilot Studio consumes MCP servers via its connector infrastructure.

**Primary target = Microsoft (for a regulated financial-services customer).**
- Enterprise path (②/①): **Copilot Studio** (Microsoft's default enterprise agent platform; DLP/ALM/governance) via custom connector (`openapi-v2.json`) **or** MCP server; **Azure AI Foundry Agent Service** for heavier/long-running orchestration.

**Optional networks — near-zero marginal cost (all are MCP clients → "validate + document," not "engineer"):**

| Rank | Network | Why / when | Lift |
|---|---|---|---|
| 1 | **LangGraph** v1.0 | Default for regulated stateful workflows (durable execution + native HITL; JPMorgan, BlackRock); consumes MCP via adapter | Doc + smoke test |
| 2 | **AWS Bedrock AgentCore** | Regulated-env controls, Claude-native; AWS-shop clients | Doc + smoke test |
| 3 | **Google Vertex AI Agent Builder / ADK** | Multimodal; ships Workday/ServiceNow agents; GCP clients | Doc + smoke test |
| 4 | **OpenAI Agents SDK** | Lowest-lift; the reference app already speaks OpenAI | Trivial |

---

## 4. Workstreams (phased; acceptance = code **and** a named test/gate, per house DoD)

### P0 — Capability contract as single source of truth  ✅ **SHIPPED**
`COPILOT_SAFE_OPERATIONS` in `service/stepstitch_service/mcp_server.py` is now the SSOT
shared by the MCP tools, `copilot/openapi-v2.json`, and the live router routes.
- **Acceptance (green):** `test_mcp_surface.py::test_mcp_matches_openapi_exactly` (operationId+method+path parity vs OpenAPI) and `::test_mcp_paths_are_real_routes` (every tool maps to a live route) — fails on any drift.

### P1 — MCP server  ✅ **SHIPPED**  *(the universal connector)*
`mcp_server.py` exposes the 12 read-only/draft operations as MCP tools; `mcp_cli.py` runs it
over stdio. Pure tool-registry + `dispatch_tool` are dependency-free; only `serve_stdio` needs
the optional `mcp` extra (`pip install 'stepstitch-service[mcp]'`). Dispatch proxies the host's
deployed service via an injected `call_route`, so the scrubber, admin auth, and `stepstitch.*`
read-audit stay centralized in the service.
- **Default posture (enforced):** read-only + draft-only; `is_destructive` guard runs at import and **no** `delete`/`purge`/kill-switch/retention/raw-`explanation` tool can ship.
- **Acceptance (green):** `test_mcp_surface.py` — `test_no_destructive_mcp_tool`, `test_tool_definitions_have_schemas`, and `test_dispatch_drives_service_sanitized_and_audited` (E2E: tool call → real service → sanitized, structure-derived, audited). **The full service suite is a required-green CI gate.**

### P2 — Connector enablement, finished  ✅ **SHIPPED**  *(product scope: connectors only)*
`copilot/` documents **two live-service connector paths**, both sharing `system-prompt.md`
+ `action-policy.md` + `connector-field-map.md`:
- **① MCP server (universal connector)** — `copilot/MCP-SETUP.md` (from P1): registration for Claude, OpenAI, LangGraph, Vertex, Bedrock, and Copilot Studio. The product's primary connector.
- **② Microsoft Copilot connector** — OpenAPI custom connector (`copilot/SETUP.md`, pre-existing): Copilot Studio + native ServiceNow/Salesforce connectors + DLP + human approval per `SETUP.md` §3.
- **Acceptance (green):** `test_copilot_pack.py` — the MCP doc can't drift from the tool SSOT, and `SETUP.md` links the MCP path. A tenant stands up either connector from docs alone. (Live tenant config remains customer-gated — see §6.)

### P3 — Productization & packaging  ✅ **SHIPPED (open core)**  *(publish steps credential-gated)*
Open-core boundary is now real and **enforced**, not just declared:
- **Boundary:** the concrete system-of-record adapters (ServiceNow/Salesforce/Genesys — all Apache-2.0 today) moved behind injection — `create_stepstitch_router(draft_adapters=...)` + `integrations/bundle.py`. This is a **layering rule, not a licensing one**: the core never imports a concrete adapter; with no adapters it still serves every read-only/draft op (export-preview returns `{}`).
- **Enforcement (green):** `test_open_core_boundary.py` (dependency-free AST check) **and** the `.importlinter` contract in `pyproject.toml` — `lint-imports` reports **KEPT**.
- **License:** everything Apache-2.0 today — `LICENSE` + SDK `package.json` (`Apache-2.0`, `publishConfig.access=public`); future commercial editions scoped in `COMMERCIAL.md` (additive only, nothing currently open would be closed).
- **Posture knob:** `STEPSTITCH_PROFILE` documented in `docs/DEPLOY.md` (FS default / healthcare-strict / internal / open-source).
- **Packaging:** `service/Dockerfile.mcp` (the MCP connector image) + `docs/DEPLOY.md` (install, mount, run).
- **Still gated (credentials, not engineering):** `npm publish` (the SDK `package.json` is already `publishConfig.access=public`), `twine upload` to PyPI, building/pushing the image.

### P4 — Governance/compliance pack  ✅ **SHIPPED**  *(the axis-2/3 moat — corrected frameworks)*
The compliance evidence packet (`compliance.py` → `COMPLIANCE-EVIDENCE.md`) now carries a
code-derived, profile-aware **regulatory crosswalk** + **MRM evidence** section:
- **FS profile → SEC Reg S-P (2024) + the April-2026 interagency MRM guidance superseding SR 11-7** + NIST AI RMF. *(Not GLBA/NAIC — earlier mis-cite, corrected.)*
- **`healthcare-strict` → HIPAA** + NIST AI RMF (Reg S-P/MRM columns dropped).
- The release gates (golden path, scrubber, profile drift, repro-executes, **the P5 eval**, the import-linter contract, the evidence drift guard) are reframed as named MRM validation / ongoing-monitoring evidence.
- **Acceptance (green):** `test_compliance.py` — `test_fs_crosswalk_cites_reg_sp_and_2026_mrm`, `test_healthcare_profile_crosswalk_cites_hipaa_not_reg_sp`, plus the existing drift guard (committed packet == live policy).

### P5 — Eval harness  ✅ **SHIPPED**  *(quality bar every adapter inherits)*
`test_repro_eval.py` is a quality oracle over the compiler + scorer that fails on a bad
reproduction: strong trace ⇒ runnable, well-graded (A/B) Playwright; **missing terminal
action ⇒ `no_terminal_action` warning + never grade A**; **unexecutable step type ⇒
`unknown_step_type` warning + never grade A** (found live: a typo'd `navigate` scored 1.00/A
over a script with no `page.goto`); empty ⇒ F; templated route flags
id substitution; no compiled repro/summary carries credentials or a forbidden field;
strong > weak (monotonicity). Wired as the `release-gate:evidence` npm script.
- **Acceptance (green):** `release-gate:evidence` runs `test_repro_eval` + `test_compliance` + `test_golden_path`.
- **✅ Resolved:** the scorer previously graded a *navigation-only* trace B (0.75) despite the `no_terminal_action` warning. The penalty was tightened (−0.50) so a no-terminal trace now grades **D**; locked by `test_replayability.py` + `test_repro_eval.py`.

### P6 — GTM wedge  *(no new code)*
README already nails the wedge (issue→repro, not session replay; privacy-safe; regulated/self-host).
Motion: **land via the MCP server** (drops into whatever agent stack the customer already runs —
zero migration) → **expand via the compliance pack**. A regulated financial-services customer is the lighthouse, reached through Microsoft.

---

## 5. P1 hand-off — MCP tool schema sketch (ready for an engineer)

Tools = the frozen Copilot-safe operation set, 1:1. All read-only or draft; all audited.

| MCP tool | Wraps (router) | Input | Returns | Mutates? |
|---|---|---|---|---|
| `list_recent_traces` | `GET /sessions` | `user_id?`, `project_id?`, `limit≤200` | trace list (no bodies) | no |
| `get_trace_summary` | `GET /session/{id}/summary` | `trace_id` | flat `TraceSummary` | no |
| `get_replayability_score` | `GET /session/{id}/replayability` | `trace_id` | `{score, grade, warnings, signals}` | no |
| `get_privacy_posture` | `GET /session/{id}/privacy-posture` | `trace_id` | scrub report + never-captured list | no |
| `get_diagnostic_summary` | `GET /session/{id}/diagnostic-summary` | `trace_id` | sanitized diagnostic + next-step | no |
| `generate_playwright_repro` | `GET /session/{id}/playwright` | `trace_id` | runnable Playwright code (header score) | no |
| `match_verified_fixes` | `GET /session/{id}/similar-fixes` | `trace_id`, `limit≤50` | structural matches to prior verified fixes | no |
| `get_attestation` | `GET /session/{id}/attestation` | `trace_id` | signed, independently-verifiable evidence bundle | no |
| `get_fragility_map` | `GET /session/{id}/fragility` | `trace_id` | per-step fragility ranking, worst-first | no |
| `generate_minimal_repro` | `GET /session/{id}/minimal-repro` | `trace_id` | smallest failing path compiled to Playwright | no |
| `get_agent_packet` (**Safe Agent Packet**) | `GET /session/{id}/agent-packet` | `trace_id` | the six rows above, composed into one call | no |
| `create_export_preview` | `POST /session/{id}/export-preview` | `trace_id` | ServiceNow/Salesforce/Genesys **drafts** | no (sends nothing) |
| `create_fs_export_preview` | `POST /session/{id}/financial-services-export-preview` | `trace_id` | named FS support **draft** pack | no (sends nothing) |

**Deliberately absent** (must never be MCP tools): raw `GET /session/{id}` (carries
`explanation`), `DELETE /session/by-user/{id}`, `POST /maintenance/purge-expired`, kill-switch,
retention. Same omissions as `openapi-v2.json`. Reuse `copilot/system-prompt.md` and
`copilot/action-policy.md` verbatim as the MCP server's guidance/guardrails.

---

## 6. Sequencing & gates

**Critical path (the spine):** P0 → P1 (MCP) → P2 (connectors) → P3 (open core) → P4 (compliance) → P5 (eval). **P0–P5 shipped (2026-06-10).**
**Remaining:** P6 (GTM — no code). All engineering-completable scope is done; the rest is credential-gated (publish) or a product decision (the P5 grade-band tightening).

P0–P6 is the **product** play (StepStitch "for all").

### Decision-gated / customer-gated (not engineering) — mirrors STATUS.md
| Item | Unblocker | Owner |
|---|---|---|
| ~~OSS split~~ ✅ done | Boundary injected + import-linter contract KEPT (P3) | — |
| ~~License~~ ✅ done | Everything Apache-2.0 today; future commercial editions scoped in `COMMERCIAL.md` (additive only) (P3) | — |
| Publish artifacts | `npm publish` (SDK already `publishConfig.access=public`), `twine upload`, build/push `Dockerfile.mcp` | **you** (credentials) |
| Stand up Copilot agent in tenant | Follow `copilot/SETUP.md` / `MCP-SETUP.md` in the customer's Copilot Studio | **customer tenant** |
| Optional networks (LangGraph/Bedrock/Vertex) | Pull-driven: a real consumer asks | **pull-driven** |

---

## 7. Open questions for you
1. **Scope now:** product spine (P0–P2) vs. just polish the reference integration?
2. **Canonical reference app** for the reference integration: keep using the confirmed main app as the proof app?
3. **OSS/licensing** direction (gates P3) — open core, or closed commercial?
