# StepStitch — completion status & definition of done

This is the acceptance ledger for the enterprise evidence-layer plan. "Done" means:
backed by code **and** proven by a named test/gate. The single end-to-end acceptance
test is `service/tests/test_golden_path.py`.

## Scoring

- **100% of engineering-completable scope is done.** Everything that can be built and
  proven without external credentials or a product decision is shipped and green.
- The remaining items are **decision-gated** or **credential-gated**, not engineering
  work. They are listed below with their exact unblocker.

## Shipped — done (proven)

| Capability | Code | Proof |
|---|---|---|
| Privacy-by-default SDK + redaction | `src/` | `tests/redaction-proof.test.ts` |
| Deterministic Playwright compiler | `service/.../compiler.py` | `service/tests/test_compiler.py`, `scripts/prove-repro-executes.mjs` |
| Decoupled router (host injects auth/DB) | `service/.../router.py` | `service/tests/test_router_smoke.py` |
| **Per-operator OIDC SSO + RBAC (host)** | `server/oidc.py` (RS256/JWKS verifier + `require_roles`); `router.py` injected `require_destructive` | `server/tests/test_oidc.py` (real audit actor per operator; operator denied destructive, admin allowed) + `server/tests/test_pg_integration.py` (real Postgres) |
| Consent / GPC / DNT, kill switch, split retention | SDK + `router.py` + `retention.py` | router + retention tests |
| **Server-side scrubber (NPI trust boundary)** | `scrubber.py` | `test_scrubber.py` |
| **Replayability score** | `replayability.py` | `test_replayability.py` |
| **Deployment profiles** | `profiles.py` + `profiles/*.json` | `test_profiles.py` (incl. drift guard) |
| **Sanitized frontend diagnostics** | SDK + `scrubber.py` + router | SDK tests + `test_scrubber.py` |
| **Financial-services support drafts (ServiceNow/Salesforce/Genesys)** | `integrations/` | `test_integrations.py` |
| **Copilot-safe surface + OpenAPI pack** | router + `copilot/` | `test_copilot_surface.py` |
| **MCP universal connector** (PRODUCT-PLAN P0+P1) | `mcp_server.py`, `mcp_cli.py` | `test_mcp_surface.py` (3-way parity + no-destructive + E2E dispatch) |
| **Connector enablement (MCP + OpenAPI)** (PRODUCT-PLAN P2) | `copilot/MCP-SETUP.md`, `copilot/SETUP.md` | `test_copilot_pack.py` (tool-SSOT drift + MCP path linked) |
| **Open-core split** (PRODUCT-PLAN P3) | adapters injected (`router.py` + `integrations/bundle.py`); Apache-2.0 `LICENSE` + `COMMERCIAL.md`; `Dockerfile.mcp` + `docs/DEPLOY.md` | `test_open_core_boundary.py` + `.importlinter` (contract KEPT) |
| **Compliance pack** (PRODUCT-PLAN P4) | regulatory crosswalk + MRM section generated from live policy (`compliance.py`); profile-aware (Reg S-P + 2026 MRM / HIPAA) | `test_compliance.py` (crosswalk + drift guard) |
| **Reproduction-quality eval gate** (PRODUCT-PLAN P5) | quality oracle on compiler + scorer; `release-gate:evidence` npm script | `test_repro_eval.py` |
| **Compliance evidence (generated)** | `compliance.py` | `test_compliance.py` (drift guard) |
| **End-to-end golden path** | (all of the above) | `test_golden_path.py` |
| Supply chain (SBOM, SRI, signed tag) | `scripts/`, `RELEASE.md` | `sbom.cdx.json`, release tag |
| Reference integration | re-vendored @ v0.3.0 | reference app `test_stepstitch_*` (incl. real-Postgres proof) |

Gates: **169 service + 25 host (incl. OIDC/RBAC + real-Postgres) + 22 SDK tests green; type-check clean; executable repro proof green; import-linter contract KEPT.**

## Architecture decision: StepStitch core, integrations via Copilot

**Chosen model:** StepStitch is the core privacy engine. The "supporting areas"
(ServiceNow, Salesforce, Genesys workflows, …) are reached through a **Microsoft Copilot
Studio** agent using Microsoft's **native connectors** or governed Power Platform flows
— *not* through StepStitch-built HTTP adapters. StepStitch exposes sanitized reads,
sanitized diagnostics, and flat connector-ready **drafts**; the agent's native
connector/flow performs the governed, human-approved create or handoff.

Consequence: the **default** model builds no outbound CRM send layer — the agent's native
connector/flow performs the governed create. The enablement is documentation + Copilot
configuration, shipped in `copilot/`: `SETUP.md`, `connector-field-map.md`,
`openapi-v2.json`, `system-prompt.md`, `action-policy.md`.

**Update (path-to-100):** an *optional* governed direct-write
(`service/stepstitch_service/delivery/`) is being added for customers not on Power Platform.
It is **off by default**, human-approval-gated, audited, and deliberately **excluded from the
agent/MCP surface** — so the draft-only default and the no-NPI guarantee are unchanged.

## Current PR scope

The v0.4.0 scope is the generic financial-services support pack: sanitized frontend
diagnostics, ServiceNow/Salesforce/Genesys draft previews, and Copilot/Power Platform
workflow docs. It intentionally contains no customer naming or unrelated platform scope.

## Remaining — gated (not engineering)

| Item | Why it's not "done" | Exact unblocker | Owner |
|---|---|---|---|
| **Stand up the Copilot agent** | The blueprint + connector field map are shipped; building the agent is a Power Platform configuration task in the customer tenant. | Follow `copilot/SETUP.md` in Copilot Studio: import the connector, attach native ServiceNow/Salesforce connectors, apply DLP + approval. | **You** (tenant config) |
| ~~**OSS split** (public core vs. private adapters)~~ **— DECIDED** | Resolved: the project is **fully Apache-2.0 for now** (incl. the ServiceNow/Salesforce/Genesys adapters). The import boundary is kept as a *layering* rule, not a license one. A commercial edition may return later (`COMMERCIAL.md`). | Done. | **Decided** |
| **Additional SDK framework packages** (react/vue/angular) | Deliberately deferred — premature breadth with no consumer. The current SDK + reference app is the only proven need. | A real consumer asks for one. | **Pull-driven** |

## Definition of 100%

Literal 100% of the original maximalist plan = the three gated items above. None can be
*truthfully* marked complete by engineering alone — each needs a credential or a
decision. Until then, the product is **feature-complete and production-proven** for the
standalone evidence-layer use case, which is the responsible "done."
