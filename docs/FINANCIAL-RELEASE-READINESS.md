# Financial release readiness — 0.11 corrective release candidate

Canonical release-evidence report. Every number below was **observed during the run
recorded here**, on the commit named below, on this machine or in the named CI run.
Nothing is inferred from an adjacent suite: a browser claim comes from a browser run, a
PostgreSQL claim comes from a PostgreSQL run.

- **Commit:** `b97d363` (`main`), branch `release/financial-claims-accuracy-rc`
- **Run date:** 2026-08-04
- **Authoritative CI run:** [30947797324](https://github.com/CyKiller/stepstitch/actions/runs/30947797324) — 9/9 jobs green on this exact commit

## Scope of this candidate

The corrective work (financial claims, privacy status, website accuracy, contact
behavior, demo evidence, runner probe, execution states) is **already merged to `main`**
as PRs #95–#105. This document is the release evidence for that work, not a further code
change. See "Provenance" at the end.

## Privacy boundary (the position this release is allowed to claim)

StepStitch **minimizes capture**, and the server scrubs what arrives:

- Input values, page text, and screen/DOM recordings are **not intentionally captured**
  by the SDK — there is no code path that collects them (`src/redaction.ts`, proven by
  `tests/redaction-proof.test.ts`).
- Known patterns and configured fields **are** scrubbed server-side, independently of the
  SDK, before storage (`scrubber.py`, `test_scrubber.py`).
- Under `financial-services-strict`, free text, unapproved selectors and undeclared
  routes are **refused with HTTP 422** rather than stored (`test_strict_policy.py`).

What this release explicitly does **not** claim:

- **Arbitrary customer-data absence is not independently verified.** Semantic data —
  names, street addresses, route slugs, selectors, labels — can survive pattern
  redaction. A person's name matches no SSN, card, email, phone, date or long-digit
  pattern.
- **A scrub report with no matched rules is not proof that customer data is absent.** It
  is a record of which rules fired. The two are different statements and the product
  keeps them apart.
- Reproduction diagnostics run against an **operator-configured** application, so the
  stored stamp is `customer_data_status: "not_verified"` — never "clean"
  (`agent_packet.py`, `diagnostics.py`).
- **Tenant-specific synthetic fixture validation is required** before a financial
  deployment. `stepstitch policy verify <fixtures.json>` exists for exactly this.

Wording banned from the product and site, and guarded by test: "No PII", "No NPI",
"PII-free", "NPI-free", "customer-data free", "guaranteed safe", "zero sensitive data"
(`web/tests/copy-claims.test.ts`, self-tested in both directions).

## Evidence distinctions the product preserves

| Weaker thing | Stronger thing | Kept apart by |
|---|---|---|
| Readiness score | Measured reproduction | `replayability.py` vs `runner.py` verdicts |
| Generated draft | Immediately runnable test | `execution_state`: `draft` vs `ready` |
| Declared outcome | Measured red/green | `evidence_grade`: `asserted` vs `measured` |
| `confirmed_fixed` | Partially executed evidence | `derive_verdict` needs pre-fail **and** post-pass |
| Pattern-clean result | Verified absence of customer data | `customer_data_status: "not_verified"` |

## Verification table — observed this run

### Service
| Gate | Command (as CI runs it) | Result |
|---|---|---|
| Test suite | `pytest service/tests -q` | **686 passed**, 0 failed, 0 skipped |
| Architecture contract | `lint-imports` (cwd `service`) | **1 kept, 0 broken** |
| Ruff | `ruff check service/stepstitch_service` | **pass** |
| mypy | `mypy stepstitch_service` (cwd `service`) | **pass** — 67 source files |

### Host / API
| Gate | Command | Result |
|---|---|---|
| Test suite | `pytest server/tests -q` | **219 passed, 1 skipped** |
| Ruff | `ruff check server` | **pass** |
| mypy | `mypy server` | **local FAIL (environmental)** — see below |
| Real PostgreSQL | CI `host` job | **passed in CI** on this commit |

**mypy server — environmental, not a product defect.** Locally it reports 80
`[attr-defined]` errors against the `server/*.py` compatibility shims (`from
stepstitch_service.host.X import *`). Cause: this workstation has `stepstitch-service`
installed **editable** (and stale at 0.9.1); mypy cannot follow editable-install import
hooks, so the target module resolves to `Any` and the star-import re-exports nothing. CI
installs the package normally (`pip install "./service[test]"`) and mypy passes there.
**Not "fixed" deliberately:** adding `mypy_path = "service"` to the root config would
mask the `py.typed` packaging question that a previous release settled on purpose
(validate against the installed wheel, not the source tree). The authoritative signal is
the CI `host` job, green on this commit.

**The skipped host test** is the real-PostgreSQL round-trip, which self-skips without
`STEPSTITCH_TEST_DATABASE_URL`. A skip is **not** a pass — it was executed and passed in
the CI `host` job against the `postgres:16` service on this commit.

### Browser SDK
| Gate | Command | Result |
|---|---|---|
| Tests | `npm test` | **38 passed** (4 files) |
| Type-check | `npm run type-check` | **pass** (3 tsconfig projects) |
| Build | `npm run build` | **pass** — ESM `dist/index.js`, CJS `dist/cjs/index.js`, types `dist/index.d.ts` |
| Zero-dep invariant | `npm audit --omit=dev --audit-level=high` | **0 vulnerabilities** |

### Website
| Gate | Command | Result |
|---|---|---|
| Tests | `npm test` (cwd `web`) | **95 passed** (11 files) |
| ESLint | `npm run lint` | **pass** |
| TypeScript | `npx tsc --noEmit` | **pass** |
| Production build | `npm run build` | **pass** |

### Generated artifacts and smoke evidence
| Gate | Result |
|---|---|
| `scripts/build_demo_dataset.py` | generated both outputs |
| `server/demo_dataset.json` ≡ `service/stepstitch_service/host/demo_dataset.json` | **identical** |
| Committed-dataset drift | **no drift** |
| `npm run smoke` (red-to-green) | **pass** — privacy gate + moat verified |
| Evidence-bundle drift after smoke | **no drift** |
| Bundle provenance | `evidence_grade=measured`, `red=reproduced`, `green=not_reproduced`, `pre_passed=false`, `post_passed=true` |
| `COMPLIANCE-EVIDENCE.md` drift | **no drift** |

The bundle's red/green is **measured**, not declared: `demo_red_to_green.py --measure`
runs the compiled reproduction in real Chromium against a broken fixture and then a fixed
one, and refuses to write a bundle claiming a transition it did not observe. CI
re-measures on every commit and diffs.

### TinyTransfer financial test project
| Gate | Result |
|---|---|
| Pinned environment | `@playwright/test` **1.62.0** exactly, root and example; Chromium 1.62.0 |
| Application loads | **yes** |
| Deliberate failure returns failing result | **yes** (HTTP 500 while the bug is armed) |
| Fix switch produces successful result | **yes** (`applying the fix turns 500 into 200`) |
| Browser payload/privacy assertions | **13/13 passed**, executed locally under pinned Chromium |

Also executed in the CI `tiny-transfer` job on this commit.

### End-to-end proofs
| Gate | Command | Result |
|---|---|---|
| Compiled reproduction executes | `npm run test:e2e-proof` | **pass** |
| Runner is red-to-green and cannot be talked out of it | `npm run test:runner-proof` | **pass** |
| Full financial chain, no mocks | `scripts/live_financial_loop.py` | **pass** — 9/9 measured steps |
| Tenant fixture validator | `stepstitch policy verify examples/policy/financial-fixtures.json` | **13/13 fixtures passed**, exit 0 |

The live loop ends by reading the raw `stepstitch_verifications` row:
`pre=0 post=1 verdict=confirmed_fixed grade=measured`.

### Final repository checks
| Check | Result |
|---|---|
| `git diff --check` | clean |
| Secret scan | clean — 2 hits are deliberate obviously-fake fixtures (`ssa_AAAA…`, base64 `faketokenfortesting`) |
| Working tree | clean, 0 changed files |

## Grades

Two scores, deliberately distinct.

### 1. Overall product / market readiness — **7.5 / 10**

| Dimension | Weight | Score | Basis |
|---|---|---|---|
| Core engineering and test evidence | 25% | 9.0 | 1,039 tests; 9/9 CI jobs; no-mocks browser→DB→MCP→red-to-green; frozen-envelope enforcement |
| Website and setup accuracy | 20% | 8.5 | Claim registry + absolute-claim scanner; doc examples compile against the real SDK; quickstart parity executed on 3 OSes |
| Installation / developer experience | 15% | 8.5 | One-command `stepstitch start`; doctor names each missing prerequisite; execution states surface blockers |
| Claim accuracy | 15% | 9.0 | Every absolute removed and guarded; competitor rows dated and sourced; demo measured, not declared |
| Financial privacy assurance | 15% | 6.5 | Strict profile + fixture validator are real and measured — but semantic absence remains structurally unverifiable |
| Independent market proof | 10% | 1.0 | No external pilots, no independent security/privacy assessment |

Computed weighted total: **7.65**. **Reported as 7.5 (capped).**

On the cap: the rubric caps at 7.5 while *all four* limiting conditions hold, and one of
them — "strict financial policy validation is not implemented" — is now **false**
(`financial-services-strict` and `stepstitch policy verify` shipped). Read mechanically,
the cap no longer binds. It is applied anyway, because the three substantive limiters do
still hold: semantic customer-data absence is not technically verified, there are no
measured external regulated-pilot results, and there is no independent security or
privacy assessment. Taking 0.15 of a grade on a technicality is the exact behavior this
release exists to remove.

### 2. Corrective-release-candidate readiness — **9.0 / 10**

Every locally executable gate is green, every claim in the shipped copy maps to a named
test, and the evidence is measured rather than asserted. Held below 10 by one external
prerequisite (contact relay unconfigured in production) and because 0.11.0 has not yet
been published.

## Remaining merge blockers

None in code. All 9 CI jobs are green on `b97d363`, including the two that cannot be
proven locally on every machine (real PostgreSQL, TinyTransfer Chromium).

## Remaining production blockers

1. **`CONTACT_WEBHOOK_URL` is not configured.** The contact route returns an honest
   `503 relay_unconfigured` and the form tells the visitor the message was not sent —
   correct behavior, but no enquiry can currently be delivered. The post-deploy canary in
   `verify-deploy.yml` is **red by design** until this is set. Never commit the value.
2. **Synthetic contact-form canary must be observed to actually arrive** at the
   destination, not merely return 200.
3. **Deploy the approved commit**, then live-QA: homepage, self-host instructions,
   financial-services pilot page, privacy and security pages, demo, contact success *and*
   failure behavior, and every primary call to action.

## Next-version priorities

Items 1–5 of the previously recorded backlog **shipped in this cycle** and are no longer
outstanding: the `financial-services-strict` profile, the tenant synthetic-fixture
validator, `stepstitch policy verify`, route/selector/test-ID policy enforcement, and
dashboard display of `customer_data_status` and blockers.

What remains, in priority order:

1. **Independent security and privacy assessment** — the single highest-value next step.
   Everything else in this report is self-attested; this is the only item that converts
   internal evidence into external assurance.
2. **External regulated-pilot metrics** — measured report-to-repro time, genuine-red
   rate, setup-blocker rate, engineering time saved.
3. Semantic (non-pattern) customer-data detection, if it can be done without adding a
   claim the product cannot keep.

## Provenance

The corrective code landed as PRs #95, #96, #97, #99, #100, #101, #102, #103, #104, #105,
merged to `main` before this report. This branch adds only this document. Nothing in the
repository was reset, discarded, reverted or force-pushed to produce it.
