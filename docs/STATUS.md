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

## Remaining — gated (not engineering)

| Item | Why it's not "done" | Exact unblocker | Owner |
|---|---|---|---|
| **Live ServiceNow / Salesforce / Copilot send** | Drafts are built + tested; the outbound API call needs a real tenant + auth to verify against. Building an untested HTTP layer on assumptions would violate "no unproven paths." | Provide a sandbox tenant + credentials → implement an injected `Transport` (off by default, governed) and add a live smoke. | **You** (credentials + governance sign-off) |
| **OSS split** (public core vs. private adapters) | A packaging/licensing decision, not code. | Decide public scope → I add the package boundary + `docker compose` + import-linter rule. | **You** (decision) |
| **Additional SDK framework packages** (react/vue/angular) | Deliberately deferred — premature breadth with no consumer. The current SDK + Marvox reference is the only proven need. | A real consumer asks for one. | **Pull-driven** |

## Definition of 100%

Literal 100% of the original maximalist plan = the three gated items above. None can be
*truthfully* marked complete by engineering alone — each needs a credential or a
decision. Until then, the product is **feature-complete and production-proven** for the
standalone evidence-layer use case, which is the responsible "done."
