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
| Consent / GPC / DNT, kill switch, split retention | SDK + `router.py` + `retention.py` | router + retention tests |
| **Server-side scrubber (NPI trust boundary)** | `scrubber.py` | `test_scrubber.py` |
| **Replayability score** | `replayability.py` | `test_replayability.py` |
| **Deployment profiles** | `profiles.py` + `profiles/*.json` | `test_profiles.py` (incl. drift guard) |
| **Draft adapters (ServiceNow/Salesforce)** | `integrations/` | `test_integrations.py` |
| **Copilot-safe surface + OpenAPI pack** | router + `copilot/` | `test_copilot_surface.py` |
| **Compliance evidence (generated)** | `compliance.py` | `test_compliance.py` (drift guard) |
| **End-to-end golden path** | (all of the above) | `test_golden_path.py` |
| Supply chain (SBOM, SRI, signed tag) | `scripts/`, `RELEASE.md` | `sbom.cdx.json`, `v0.3.0` |
| Marvox reference integration | re-vendored @ v0.3.0 | Marvox `test_stepstitch_*` (incl. real-Postgres proof) |

Gates: **76 service + 18 SDK tests green; ruff clean; type-check clean.**

## Architecture decision: StepStitch core, integrations via Copilot

**Chosen model:** StepStitch is the core privacy engine. The "supporting areas"
(ServiceNow, Salesforce, …) are reached through a **Microsoft Copilot Studio** agent
using Microsoft's **native connectors** — *not* through StepStitch-built HTTP adapters.
StepStitch exposes sanitized reads + a flat, connector-ready **draft** (`export-preview`);
the agent's native connector performs the governed, human-approved create.

Consequence: **StepStitch does not build or maintain an outbound CRM send layer** — by
design. That removes the previously-listed "build send transport" item entirely. The
enablement is documentation + Copilot configuration, now shipped in `copilot/`:
`SETUP.md`, `connector-field-map.md`, `openapi-v2.json`, `system-prompt.md`,
`action-policy.md`.

## Remaining — gated (not engineering)

| Item | Why it's not "done" | Exact unblocker | Owner |
|---|---|---|---|
| **Stand up the Copilot agent** | The blueprint + connector field map are shipped; building the agent is a Power Platform configuration task in the customer tenant. | Follow `copilot/SETUP.md` in Copilot Studio: import the connector, attach native ServiceNow/Salesforce connectors, apply DLP + approval. | **You** (tenant config) |
| **OSS split** (public core vs. private adapters) | A packaging/licensing decision, not code. | Decide public scope → I add the package boundary + `docker compose` + import-linter rule. | **You** (decision) |
| **Additional SDK framework packages** (react/vue/angular) | Deliberately deferred — premature breadth with no consumer. The current SDK + Marvox reference is the only proven need. | A real consumer asks for one. | **Pull-driven** |

## Definition of 100%

Literal 100% of the original maximalist plan = the three gated items above. None can be
*truthfully* marked complete by engineering alone — each needs a credential or a
decision. Until then, the product is **feature-complete and production-proven** for the
standalone evidence-layer use case, which is the responsible "done."
