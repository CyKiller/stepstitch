# StepStitch — completion status & definition of done

This is the acceptance ledger. "Done" means backed by code **and** proven by a named
test or gate that exists in this repository — a row with no runnable proof does not
belong here. The single end-to-end acceptance test is `service/tests/test_golden_path.py`.

**Current version: 0.11.0** <!-- x-release-please-version --> — the version this tree
declares. A version's artifacts exist only once the manually-approved release run has
published them to npm, PyPI and GHCR (multi-arch); merging the release PR alone publishes
nothing. The full CI gate is re-run as the release gate before any artifact is pushed.

## Gates

| Suite | Tests | Command |
|---|---|---|
| Service (compiler, router, privacy, connectors) | **902** | `PYTHONPATH=service pytest service/tests/` |
| Host (auth, dashboard, real Postgres) | **240** (1 skipped) | `PYTHONPATH=service pytest server/tests/` |
| SDK (type-check + redaction proof) | **40** | `npx vitest run` |
| Web (marketing site + copy claims) | **158** | `cd web && npx vitest run` |

Counts are the number pytest/vitest **collect**, and every row is enforced: each suite
verifies its own row — `test_status_ledger.py` (Service), `test_status_ledger_host.py`
(Host), `tests/status-ledger.test.ts` (SDK) and `web/tests/status-ledger.test.ts` (Web) —
so CI fails if this table drifts or cites a test that does not exist. The check is split
per suite deliberately — the Service job does not install the host's dependencies, so
counting `server/tests` from there under-reports without erroring. The old version of this
doc sat a month stale claiming "183 service + 31 host" and naming a proof that was not in
the repository. The Web row then repeated the mistake at a different level: only Service
and Host were guarded, so the row read 101 against an actual 148 and nothing failed. The
SDK guard now also asserts that *every* row in this table names a guard that exists, and
that no guard outlives its row, so coverage cannot silently shrink again.

Also blocking: `ruff`, `mypy`, `tsc --noEmit`, `eslint`, CodeQL, the executable-repro proof
(`scripts/prove-repro-executes.mjs`), the compliance-evidence drift guard, the import-linter
layering contract, and three browser jobs the server-side suites cannot replace — `demo-console`
(the console actually renders), `tiny-transfer` (the privacy claims hold against the bytes
the browser sent), and `tiny-transfer-live` (`scripts/live_financial_loop.py`: real browser →
real SDK → same-origin proxy → strict scrubber → the raw SQLite row → real MCP stdio with a
repros-scoped token → verify.mjs with a verify-scoped token → freeze/verify-fix, ending in a
`confirmed_fixed` row with `evidence_grade='measured'` — no mocks anywhere in the chain).

## Shipped — done (proven)

### Core evidence layer

| Capability | Code | Proof |
|---|---|---|
| Privacy-by-default SDK + redaction | `src/` | `tests/redaction-proof.test.ts` |
| Drop-in "Report a problem" widget (framework-agnostic, zero-dep) | `src/reporter.ts` | `tests/reporter.test.ts` |
| Deterministic Playwright compiler | `service/.../compiler.py` | `test_compiler.py`, `scripts/prove-repro-executes.mjs` |
| Decoupled router (host injects auth/DB) | `service/.../router.py` | `test_router_smoke.py` |
| Server-side scrubber (NPI trust boundary); Luhn-labeled card detection (coverage never narrows) + host-injected advisory-detector seam (Presidio-ready, advisory never proof) | `scrubber.py` | `test_scrubber.py`, `test_scrub_overrides.py`, `test_pci_vectors.py` |
| Replayability score | `replayability.py` | `test_replayability.py` |
| Deployment profiles (incl. deny-by-default `financial-services-strict`) | `profiles.py` + `profiles/*.json` | `test_profiles.py` (incl. drift guard), `test_strict_policy.py` |
| Tenant fixture validator — `stepstitch policy verify` runs hostile fixtures through the live scrub boundary, offline classifier router-parity-guarded; pack covers PCI account-data shapes (PAN valid+invalid Luhn, expiry/CVV context, track-data, PIN-block) each refused with nothing stored | `policy_verify.py`, `cli.py`, `examples/policy/financial-fixtures.json` | `test_policy_verify.py` (incl. router parity + leak scan) |
| Consent / GPC / DNT, kill switch, split retention | SDK + `router.py` + `retention.py` | `test_retention.py`, `test_retention_job.py` |
| Reproduction-quality eval gate | quality oracle on compiler + scorer | `test_repro_eval.py` |
| Project reproduction config (base URL, auth fixture, route/form values, API match) | `repro_config.py` | `test_repro_config.py`, `test_repro_config_host.py` |
| Config refuses to store credentials (names only) | `repro_config.py` | `test_repro_config.py::TestSecretRefusal` |
| **Measured** red run in the CI template (no assumed `pre_passed`) | `github_bridge/workflow.py` | `test_github_content.py::test_the_red_half_is_measured_not_assumed` |
| Narrow `verify` CI scope (fetch repro + post verdict, nothing else) | `stepstitch_service/host/agents.py` | `test_agents.py::test_verify_scope_can_do_nothing_else` |
| Reproduction + attestation downloads | `router.py` | `test_repro_config_host.py` (downloads) |
| Fingerprint backfill for pre-0005 traces | `scripts/backfill_fingerprints.py` | `test_backfill_fingerprints.py` |
| `stepstitch doctor` first-run diagnostic (never prints a secret) | `service/.../cli.py` | `test_doctor.py` |
| Startup fails with every misconfiguration named, not `KeyError` | `stepstitch_service/host/envcheck.py` | `test_app_startup.py` |
| `stepstitch start` — local dashboard in one command, no token pasting | `stepstitch_service/host/local.py`, `packages/cli-shim` | `test_local_start.py`, `test_local_onboarding.py`, CI job `first-run` (3 OSes) |
| doctor knows local mode and reproduction prerequisites (node, playwright) | `stepstitch_service/cli.py` | `test_doctor.py` |
| Runnable example proving the privacy claims + red→green | `examples/tiny-transfer/` | CI job `tiny-transfer` (13 Playwright tests over the captured payload) |
| **The whole financial chain with no mocks** — real browser → real SDK → same-origin proxy → strict scrubber → the **stored SQLite row** (not the outbound payload) → real MCP stdio with a `repros` token → `verify.mjs` with a `verify` token → freeze/verify-fix, ending in `confirmed_fixed` + `evidence_grade='measured'` read raw from the row; a hostile semantic POST measured at 422 with nothing stored | `scripts/live_financial_loop.py`, `examples/tiny-transfer/live-report.mjs` | CI job `tiny-transfer-live` |
| **Proof-carrying fixes (FixProof v2)** — an in-toto statement binding fixed/base commit, failure fingerprint, frozen-test + execution-envelope digests, measured pre/post results, privacy-policy digest and verifier identity; `stepstitch proof export` / `proof verify` (offline, 0/1/2); every statement leaf mutation-tested from an enumerated surface; a no-secrets PR-head-bound merge-gate template; the live loop exports the real proof, verifies it offline against the repo HEAD and proves a tampered copy refused — in the same run | `fixproof.py`, `cli.py`, `router.py`, `github_bridge/workflow.py` | `test_fixproof.py`, `test_proof_cli.py`, `test_fixproof_endpoint.py`, `test_demo_bundle.py`, CI job `tiny-transfer-live` (steps 10–12) |
| **FixProof trust chain (cryptographic)** — `require_signature` verifies a real Ed25519 signature (pure-stdlib RFC 8032, pinned to the RFC's own vectors) against `trusted_keys` the policy names — presence is never authenticity; `require_bindings` refuses proofs missing any load-bearing binding; `allowed_verifier_identities` allowlists who may verify; `stepstitch proof keygen` creates the anchor; the gate workflow loads its policy from the protected base branch and pins actions + verifier version; the unconfigured template refuses to run (exit 2); the six trust-audit attacks (fabricate+rehash, fake/forged/untrusted signature, missing binding, in-PR policy change, cross-commit replay, unauthorized identity) are each a permanent refusal test; the live loop signs with an ephemeral run key and proves tampered AND differently-signed copies refused | `_ed25519.py`, `fixproof.py`, `host/signing.py`, `cli.py`, `github_bridge/workflow.py` | `test_ed25519.py`, `test_fixproof_adversarial.py`, `test_proof_cli.py`, `test_fixproof_endpoint.py`, CI job `tiny-transfer-live` (steps 10–13) |
| Public demo console — real UI, synthetic data, no credentials, read-only | `stepstitch_service/host/demo.py`, `scripts/build_demo_dataset.py` | `test_demo_app.py`, CI job `demo-console` (13 browser tests) |
| Deep-linkable failures (`#/shape/…`) | `stepstitch_service/host/dashboard.py` | `test_host.py`, `dashboard-demo.spec.ts` |
| Execution state — `draft` / `ready` / `reproduced` / `confirmed_fixed`, so a compiled draft that cannot run is never mistaken for one that was measured; the console names every missing prerequisite (base URL, route params, form values, auth fixture, browser, strict allowlists) instead of one boolean, and shows whether red and green **actually ran**, the evidence grade, the profile, `schema_status`, `customer_data_status`, and the replayability reasons | `execution.py`, `host.py` `/admin/session/{id}/execution` + `/admin/status`, `dashboard.py` | `test_execution_state.py` (every combination), `test_execution_endpoint.py` |
| Site's advertised MCP tool list matches the server | `web/src/lib/mcp-tools.ts` | `test_mcp_site_parity.py` |
| Claim registry — every material marketing statement mapped to the file and test that proves it; the buyer copy may not assert an absolute the scrubber cannot demonstrate (`no NPI`, `never captures PII`, `guarantees`), and competitor rows carry a source and a date | `web/src/lib/claims.ts`, `comparison.tsx` | `claims-registry.test.ts`, `copy-claims.test.ts` (negation-aware + absolute scanners, both self-tested) |
| Public red-to-green demo is **measured**: the committed evidence bundle records a real Chromium run (broken fixture → red, fixed → green) and CI re-measures it on every commit | `scripts/demo_red_to_green.py --measure` | CI job `demo-console` (bundle drift), `copy-claims.test.ts` |
| Local reproduction runner (frozen script, env allowlist, timeout, cancel, address allowlist) | `stepstitch_service/runner.py` | `test_runner.py`, `scripts/prove-runner-executes.mjs` (real Chromium, red-to-green) |
| Agent loop: freeze the test, measure red, judge the fix (fixed / still failing / different failure / unable to verify) | `stepstitch_service/fixcheck.py`, `host/host.py` freeze + verify-fix | `test_fixcheck.py`, `test_agent_loop.py`, `scripts/demo_agent_loop.py` (CI gate) |
| MCP stdio transport actually spoken by a client | `stepstitch_service/mcp_server.py` | `test_mcp_stdio.py` (spawn, initialize, list, call) |
| Evidence grade — asserted (a caller said so) / measured (StepStitch ran it) / signed; derived, never claimable | `stepstitch_service/evidence.py` | `test_evidence.py`, `test_evidence_endpoints.py` |
| Attestation tamper rejection (altered bundle refused, not flagged) | `stepstitch_service/evidence.py` `verify_bundle` | `test_evidence.py`, `POST /attestation/verify` tests |
| Fix Memory advises from measured evidence only | `router.py` similar-fixes | `test_similar_fixes.py` |
| Deep diagnostics come from the LOCAL reproduction, never the reported session — scrubbed, bounded, and stamped `customer_data_status: not_verified` because the target app is operator-configured | `stepstitch_service/diagnostics.py` | `test_diagnostics.py` |
| Execution envelope frozen with the script and **enforced at verification** — stored on the freeze row, passed by verify-fix, a run under a different browser/timeout/base URL refused, legacy rows degrade with `envelope_enforced: false` | `diagnostics.py` `check_envelope`, `runner.py`, `host.py` freeze + verify-fix, migration 0009 | `test_diagnostics.py`, `test_runner.py` (same-digest across runs), `test_agent_loop.py` (the production freeze→verify path) |
| Diagnostics do not change what they measure (same verdict, hash and failure fingerprint on/off) | `runner.py` config-side tracing | `test_runner.py`, `scripts/prove-diagnostics-are-inert.mjs` (real Chromium, CI) |
| Four signals parsed from the Playwright trace (failure stack, console errors only, failed requests with templated paths, failure snapshot) | `diagnostics.py` `parse_trace` | `test_diagnostics.py` |
| Planted credentials and raw ids never reach a diagnostics record | `diagnostics.py` `scrub_diagnostics` + compiler templating | `test_diagnostics.py` (uses the real redactor) |
| Diagnostics survive the runner's scratch-dir cleanup, with both digests | `host.py` `_store_diagnostics`, migration 0008 | `test_diagnostics_persistence.py` |
| Every MCP tool is reachable by a scoped token, or an explicit documented exclusion | `host/agents.py` `_RULES` | `test_agent_scope_parity.py` |
| A coding agent reads the failure and the reproduction, and can never record a verdict | `host/agents.py`, `connect.py` `AGENT_SCOPE` | `test_agent_scope_parity.py`, `test_connect.py` |
| `stepstitch connect` registers via each vendor's own `mcp add`; token in an owner-only file, never in a config or argv | `connect.py`, `cli.py` | `test_connect.py` (verified live with Claude Code) |
| Agent packet splits privacy by origin: `from_production` (unchanged, minimal) vs `from_reproduction` (rich, scrubbed, qualified — provably not the reported session; customer-data status of the operator-configured target stated as not verified) — both precise | `agent_packet.py` | `test_agent_packet.py` |
| Packet carries both digests, the exact verification command, and file suggestions labelled as suggestions | `agent_packet.py` | `test_agent_packet.py` |
| End-to-end golden path | (all of the above) | `test_golden_path.py` |

### Host, governance and operations

| Capability | Code | Proof |
|---|---|---|
| Per-operator OIDC SSO + RBAC | `server/oidc.py` (RS256/JWKS + `require_roles`) | `test_oidc.py`, `test_pg_integration.py` (real Postgres) |
| Scoped, revocable agent tokens | `stepstitch_service/host/agents.py` | `test_agents.py`, `test_agent_enforcement.py` |
| SQLite local store (`STEPSTITCH_MODE=local`, zero-config; Postgres path untouched) | `stepstitch_service/host/localdb.py` | `test_localdb.py` + shared `storage_suite.py` (also run against real Postgres) |
| Durable audit trail | `stepstitch_service/host/audit.py` | `test_audit_endpoint.py` |
| Editable scrub policy | `server/` scrub config | `test_scrub_config.py` |
| Observability | `stepstitch_service/host/metrics.py` | `test_observability.py` |
| Operator console (read-only, CSP `default-src 'none'`) | `stepstitch_service/host/dashboard.py` | `test_host.py` |
| Overview dashboard — metrics, charts, glyph constellation | `metrics.py` (served on `/shapes`, not recomputed client-side) | `test_metrics.py`, `test_shapes_endpoints.py`, `test_dashboard_charts.py` |
| Plain-language layer (technical detail behind a toggle) | `humanize.py` | `test_humanize.py` |

### Moats (0.6)

| Capability | Code | Proof |
|---|---|---|
| Fix Memory — match a new bug against the verified-fix corpus | `fix_memory.py` | `test_fix_memory.py`, `test_similar_fixes.py` |
| Evidence Attestation — canonical, tamper-evident, tenant-signed | `attestation.py` | `test_attestation.py`, `test_attestation_endpoint.py` |
| Fragility Radar + minimal repro | `fragility.py` | `test_fragility.py`, `test_fragility_endpoints.py` |
| Verified-fix engine (red→green verdict + corpus) | `verification/verdict.py` | `test_verdict.py`, `test_verification_endpoints.py` |

### Connectors and agent surface (0.7)

| Capability | Code | Proof |
|---|---|---|
| MCP universal connector | `mcp_server.py`, `mcp_cli.py` | `test_mcp_surface.py` (3-way parity, no-destructive, E2E dispatch) |
| Copilot-safe surface + OpenAPI pack | router + `copilot/` | `test_copilot_surface.py`, `test_copilot_pack.py` |
| Connector platform — GitHub, Linear, Slack | `integrations/{github,linear,slack}.py` | `test_connector_platform.py` |
| Safe Agent Packet + adapter conformance | `integrations/{validation,conformance}.py` | `test_adapter_profile_robustness.py`, `test_integrations.py` |
| Draft adapters — ServiceNow, Salesforce, Genesys | `integrations/` | `test_integrations.py` |
| Repair Loop / GitHub bridge | `github_bridge/` | `test_github_{bridge,client,content,endpoints}.py` |
| Governed direct-write (opt-in, off by default) | `delivery/` | `test_delivery.py`, `test_delivery_clients.py` |
| **Failure shapes** — cluster traces by structural fingerprint | `shapes.py`, migration `0005` | `test_shapes.py`, `test_shapes_endpoints.py` |

### Licensing, compliance, supply chain

| Capability | Code | Proof |
|---|---|---|
| Open-core split (adapters injected, never imported by core) | `router.py` + `integrations/bundle.py` | `test_open_core_boundary.py` + import-linter contract |
| Compliance pack — regulatory crosswalk + model-risk principles (informational), profile-aware | `compliance.py` | `test_compliance.py` (crosswalk + drift guard) |
| Reproduction Success corpus — 11 categories; ready-rate, refusal-naming, byte-determinism, intended-red gates | `repro_eval.py` + `examples/repro/` | `test_repro_corpus.py` + `prove-repro-corpus.mjs` (e2e-proof) |
| `stepstitch init` — guided wiring: scaffold, repro config, sample report, idempotent uninstall | `scaffold.py` + `cli.py run_init` | `test_init.py` + clean-install `first-run` (3 OSes) |
| Unified workflow status — one state, one next action, above every tab (incl. demo) | `execution.py next_action` + `dashboard.py workflowStripe` | `test_execution_state.py` + `test_host.py` + `dashboard-demo.spec.ts` |
| Supply chain — SBOM, SRI, provenance-signed publish | `scripts/`, `RELEASE.md`, `.github/workflows/release.yml` | `sbom.cdx.json`, signed release assets |

## Architecture decision: StepStitch core, integrations at the edge

StepStitch is the core privacy engine. Supporting systems (ServiceNow, Salesforce,
Genesys, and now GitHub/Linear/Slack) are reached either through an agent's own native
connectors or through StepStitch's flat, connector-ready **drafts** — the agent performs
the governed, human-approved create or handoff.

The **default** builds no outbound send layer. An *optional* governed direct-write
(`delivery/`) exists for customers not on Power Platform: off by default,
human-approval-gated, audited, and deliberately excluded from the agent/MCP surface, so
the draft-only default and the scrub boundary are unchanged.

## Remaining — gated (not engineering)

| Item | Why it's not "done" | Exact unblocker | Owner |
|---|---|---|---|
| **Stand up the Copilot agent** | The blueprint + connector field map are shipped; building the agent is a Power Platform configuration task in the customer tenant. | Follow `copilot/SETUP.md`: import the connector, attach native adapters, apply DLP + approval. | **You** (tenant config) |
| **Additional SDK framework packages** (react/vue/angular) | Deliberately deferred — premature breadth with no consumer. | A real consumer asks for one. | **Pull-driven** |
| ~~**OSS split** (public core vs. private adapters)~~ | **Decided:** fully Apache-2.0, adapters included. The import boundary is kept as a *layering* rule, not a licensing one. | Done — see `COMMERCIAL.md`. | **Decided** |

## Known gaps

- **The red run needs a startable app.** The CI template now measures the pre-fix run for
  real (see above), but it can only do so if the pre-fix ref still builds and boots via
  `npm run stepstitch:app` / `STEPSTITCH_APP_CMD`. When it does not, the workflow records
  nothing rather than guessing — correct, but it means old traces can be unverifiable.
- ~~**Agents are unsupported under OIDC.**~~ **Closed.** Agent-scope enforcement is now
  auth-mode-agnostic: the middleware resolves `ssa_` tokens and stamps the request after
  a `scope_allows` check, and the admin dependency accepts the stamp in both shared-token
  and OIDC modes — no admin-token impersonation anywhere. A scoped agent gets exactly its
  tier, out-of-scope requests are 403 by scope, unregistered/revoked tokens stay 401, and
  operators manage `/admin/agents` under OIDC too — proven by `test_oidc_agent_access.py`.

## Definition of 100%

Literal 100% of the original maximalist plan = the gated items above. Neither can be
*truthfully* marked complete by engineering alone — each needs a credential or a
decision. Until then the product is feature-complete and production-proven for the
standalone evidence-layer use case, which is the responsible "done."
