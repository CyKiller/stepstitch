# Changelog

All notable changes to StepStitch are recorded here. Versions are repo-wide tags; the
SDK (`@stepstitch/tracker`) and the backend (`stepstitch_service`) are versioned in
lockstep per `RELEASE.md`.

## [0.10.0](https://github.com/CyKiller/stepstitch/compare/v0.9.1...v0.10.0) (2026-07-31)


### Features

* **cli:** stepstitch start --connect — the command the error message promised ([b35d823](https://github.com/CyKiller/stepstitch/commit/b35d82383107f050f60c34cc54183124bc459cd7))
* **connect:** find the CLI, then let it actually call the tools ([ee9a57e](https://github.com/CyKiller/stepstitch/commit/ee9a57e89917947d2af4d38ba7ab2ed90b198c46))
* **connect:** least-privilege agent connection that actually connects ([5322904](https://github.com/CyKiller/stepstitch/commit/5322904097f4aa38e1a286184e270f6f5b50aa8e))
* **diagnostics:** depth from the reproduction, not from the reporter ([4acaddb](https://github.com/CyKiller/stepstitch/commit/4acaddb5ee613869c05838418009fecf85b698aa))
* **diagnostics:** four signals from the trace, and a proof that measures something ([765b8eb](https://github.com/CyKiller/stepstitch/commit/765b8ebfc1736d9093429dc929f183dcd6ee79db))
* **host:** the envelope is stored with the freeze and enforced at verification ([3068d38](https://github.com/CyKiller/stepstitch/commit/3068d38ba1b3f56d6bad54b450b562b19b9c397b))
* **packet:** one handoff, and a privacy claim that stops being wrong ([2879fe7](https://github.com/CyKiller/stepstitch/commit/2879fe70783eb486540aff92ff2c351e946697df))
* **runner:** a missing browser is refused before anything is launched ([68e4d3f](https://github.com/CyKiller/stepstitch/commit/68e4d3f5dd375dfdfcb898b850ac61599ec5daaa))


### Bug Fixes

* **claims:** the packet stops contradicting its own posture, and the replay ([ed8ee53](https://github.com/CyKiller/stepstitch/commit/ed8ee5370ad39fedd950f00f8883ed1302280728))
* **connect:** stop shipping the anti-pattern the scope fix just removed ([34a29cc](https://github.com/CyKiller/stepstitch/commit/34a29cc6c8aa27204c7fe5367084afc30e4b75d0))
* **diagnostics:** claim what the architecture proves, and nothing more ([7257a7c](https://github.com/CyKiller/stepstitch/commit/7257a7c2a256367b8672612816a345c25042c286))
* **diagnostics:** hold reproduction evidence to the bar production evidence gets ([2244217](https://github.com/CyKiller/stepstitch/commit/224421754acd28d349614aaa7704fe3f712818ea))
* **diagnostics:** ship the application's exception, not the test's assertion ([b173fee](https://github.com/CyKiller/stepstitch/commit/b173feed650d6dc75ff449c6fdf95b301ebfa9e3))
* **diagnostics:** the execution envelope was a run id wearing a fingerprint's name ([c420952](https://github.com/CyKiller/stepstitch/commit/c4209528d41ee1e3798e6aca6df9272a756b3aaa))
* **diagnostics:** the snapshot carried the raw URL it promised not to ([4e6351c](https://github.com/CyKiller/stepstitch/commit/4e6351cd7606d3b3fc3b5685e930e567a7043786))
* **diagnostics:** the stored envelope record now explains a trusted mismatch ([bdd7873](https://github.com/CyKiller/stepstitch/commit/bdd7873f77ec01846c4f5c399b04adabc71c2325))
* **host:** an envelope mismatch is a refusal, not a server fault ([772e0dc](https://github.com/CyKiller/stepstitch/commit/772e0dccd5de288b29db5c504a7c75bb3254c3c0))
* **host:** deleted means deleted, diagnostics included ([e30df53](https://github.com/CyKiller/stepstitch/commit/e30df53371fe92ec0a5854f2238dad1b7a38a6fd))
* **migrations:** 0009 must survive being replayed over a bootstrapped schema ([6e1dff4](https://github.com/CyKiller/stepstitch/commit/6e1dff4501764e6a773339448410265dacceb848))
* **release:** make the stranger check reliable, and write down the procedure ([1abe6c5](https://github.com/CyKiller/stepstitch/commit/1abe6c54eb4cc83b723eecdb8158cf49c5bcc2a2))
* **runner:** a missing browser is a fact about the machine, not the app ([d07b127](https://github.com/CyKiller/stepstitch/commit/d07b127e63e49f54d31915d61a78bc895d04e778))
* **runner:** a relative project dir silently found no tests on Python 3.11 ([b8739a5](https://github.com/CyKiller/stepstitch/commit/b8739a5cb847b328129780fde9cf94641a41b873))
* **runner:** record the browser that runs, not the package that ships it ([cb82d85](https://github.com/CyKiller/stepstitch/commit/cb82d85b99ad8deca427213617bb8ed31ddd2402))
* **scripts:** make the inert gate say why, not just that it failed ([0706632](https://github.com/CyKiller/stepstitch/commit/0706632fd8ea18f5986e6b6b30b5abedc5e544ea))
* **scripts:** the inert gate never ran, because it hardcoded a laptop's venv ([58ebf96](https://github.com/CyKiller/stepstitch/commit/58ebf96e607591a5e098e988e378f0f637bf6e0e))
* **service:** an unexecutable footstep can no longer wear a grade A ([2541835](https://github.com/CyKiller/stepstitch/commit/2541835525426919613235c9faaf0598789d192b))
* **tests:** satisfy mypy on the replay-script loader ([1e5695e](https://github.com/CyKiller/stepstitch/commit/1e5695e91bc007cf42df7fa0f9eb581b30a29ca6))

## [0.9.1](https://github.com/CyKiller/stepstitch/compare/v0.9.0...v0.9.1) (2026-07-30)


### Bug Fixes

* **release:** let a dispatch name the version it publishes ([68a15d8](https://github.com/CyKiller/stepstitch/commit/68a15d8916a04b340b8413c51077bf63525e0cb4))
* **release:** publish the launcher people were told to run ([e6fca31](https://github.com/CyKiller/stepstitch/commit/e6fca319e62e031facc5e99e2fca962071253c7b))

## [0.9.0](https://github.com/CyKiller/stepstitch/compare/v0.8.0...v0.9.0) (2026-07-30)


### Features

* **agent:** close the loop — the agent fixes, StepStitch judges ([7c706bf](https://github.com/CyKiller/stepstitch/commit/7c706bfde987cc94063f94741ad51a6cff51cfda))
* **ci:** a clean-install gate that executes the quickstart's promises ([99e776d](https://github.com/CyKiller/stepstitch/commit/99e776d642ace4935265f582b2223eedf87e9239))
* **core:** measure the red run and make reproductions configurable ([71cd6c4](https://github.com/CyKiller/stepstitch/commit/71cd6c462fccf6a6c01d0d690e1bf1e93a6799f0))
* **demo:** serve the real console publicly over synthetic data ([02be1c6](https://github.com/CyKiller/stepstitch/commit/02be1c668d77c324186c3233a291192db98d8fc5))
* **evidence:** say how we know, not just what we found ([b9e23c0](https://github.com/CyKiller/stepstitch/commit/b9e23c0e4161262b2f125c38d3dd133713515238))
* **examples:** add TinyTransfer, a runnable proof of the privacy claims ([df615fb](https://github.com/CyKiller/stepstitch/commit/df615fb955adb334e97a86137bfbce0f0d41437f))
* **install:** add stepstitch doctor and a first-run path that explains itself ([1392a33](https://github.com/CyKiller/stepstitch/commit/1392a3396729741fad0fcb54e8e9b8a67028eb8f))
* **install:** the npm shim behind 'npx stepstitch', measured before locked ([42093db](https://github.com/CyKiller/stepstitch/commit/42093dbad5ded70ad9a0bc47196743039216adba))
* **local:** connect your app without copying a token ([98a6706](https://github.com/CyKiller/stepstitch/commit/98a6706ac4314aceb888fe0d8ce1b161a15cf14f))
* **local:** doctor speaks local mode, and CI proves the first run ([78261f3](https://github.com/CyKiller/stepstitch/commit/78261f36767a65ea1bdcc87fe6fd523e4ca84c2a))
* **local:** stepstitch start — a dashboard in one command, no token pasting ([9dbd802](https://github.com/CyKiller/stepstitch/commit/9dbd8028c43b954d285bff89afa6dae838cb7598))
* **repro:** one button, one command, and three bugs the demo found ([6142c3f](https://github.com/CyKiller/stepstitch/commit/6142c3fe0059b7ccd5fd98da2df47c6edc463a16))
* **runner:** execute a reproduction locally, and refuse to guess ([6985e96](https://github.com/CyKiller/stepstitch/commit/6985e969d848719d788ddd313f7d516d668adfbf))
* **sdk:** ship the Report a problem widget, framework-agnostic ([46d8a3e](https://github.com/CyKiller/stepstitch/commit/46d8a3ee98c88d7a0c2fb0c3e5de2328b7ca96ec))
* **server:** a SQLite local store behind the same seam Postgres serves ([1476b10](https://github.com/CyKiller/stepstitch/commit/1476b10964e6627b14fe0370a2a9469452c43f5a))


### Bug Fixes

* **ci:** deployment has one owner, and verification replaces pretending ([16d6eb5](https://github.com/CyKiller/stepstitch/commit/16d6eb5f379445029527d8ba00a57a6392b2a188))
* **ci:** install what the new gates actually need, and stop the count from moving ([ca3bff3](https://github.com/CyKiller/stepstitch/commit/ca3bff3b2103fe62aabd33de2af1e83737b6be93))
* close the three verified gaps between what we claim and what runs ([719ae57](https://github.com/CyKiller/stepstitch/commit/719ae5714bf1bb3de83bf9d7d8b2b7859c67ec3a))
* **docs:** a quickstart that works on a clean machine, in the order shown ([1477835](https://github.com/CyKiller/stepstitch/commit/1477835b00292ce7bca4ca7823aa573a5488c282))
* **mcp:** the stdio server was broken on the current SDK ([235078b](https://github.com/CyKiller/stepstitch/commit/235078bb3c7ae96a4457d984973fec23cd18ca02))
* **packaging:** declare the package typed, or the shims resolve to nothing ([a9ceb3b](https://github.com/CyKiller/stepstitch/commit/a9ceb3b080855650574f2aa16ddb1946a1bde1bf))
* **sdk:** CJS-flavored declarations so typed require() consumers resolve ([bcd4b9b](https://github.com/CyKiller/stepstitch/commit/bcd4b9b8edc0c64da0739107a5391f12cb0ecc31))
* **web:** correct six inaccuracies in the marketing site ([cbba3fe](https://github.com/CyKiller/stepstitch/commit/cbba3fea43422aca0629e0533f587d6771547867))
* **web:** earn the word 'live' — provenance-truthful copy in every state ([7958058](https://github.com/CyKiller/stepstitch/commit/79580587557f1c85d4bd0cb156cd3a6a1c3f118f))

## [0.8.0](https://github.com/CyKiller/stepstitch/compare/v0.7.0...v0.8.0) (2026-07-26)


### Features

* **server:** rebuild the console as a dashboard — overview, plain language, shape-first ([#52](https://github.com/CyKiller/stepstitch/issues/52)) ([fb62332](https://github.com/CyKiller/stepstitch/commit/fb62332cfe0c4ef06aa8b2b45e6e337956072179))


### Bug Fixes

* **docs:** let release-please bump the release named in STATUS.md ([#65](https://github.com/CyKiller/stepstitch/issues/65)) ([f9b46e2](https://github.com/CyKiller/stepstitch/commit/f9b46e23c0510fc47397695c5cad2efafd3fcecb))
* **hooks:** scope the authorship gate to commits not already on the remote ([e7b2519](https://github.com/CyKiller/stepstitch/commit/e7b2519ebacf0ead3b604ce541186961f2d55e97))

## [0.7.0](https://github.com/CyKiller/stepstitch/compare/v0.6.0...v0.7.0) (2026-07-26)


### Features

* **service:** connector platform — GitHub, Linear, Slack + Safe Agent Packet ([78afb33](https://github.com/CyKiller/stepstitch/commit/78afb3385d545109dac397e67c9a1df0ca2c5570))
* **service:** failure shapes — cluster traces by structural fingerprint ([afb242a](https://github.com/CyKiller/stepstitch/commit/afb242ab25bc7279302e54f7776b725ba18f496c))
* **web:** drop the pricing frame, surface the console board ([023fa9c](https://github.com/CyKiller/stepstitch/commit/023fa9cd73b74930f3a7ba301cdd19c8dbd2a919))
* **web:** positioning reframe — moat-led hero + 'New in 0.6' section ([645f2a8](https://github.com/CyKiller/stepstitch/commit/645f2a87fb3defff32ac1b399c273daeb7e9ae8b))


### Bug Fixes

* **web:** match the console's plain wording on the site board ([10d52f7](https://github.com/CyKiller/stepstitch/commit/10d52f7b8b7aea12125c2ab09c2eece380349d5a))
* **web:** remove the duplicated footer link ([63d94ff](https://github.com/CyKiller/stepstitch/commit/63d94ffb7bf73a9da85a07b8bc71acb089aa36a6))
* **web:** single-source the released version so the site cannot go stale ([4f28465](https://github.com/CyKiller/stepstitch/commit/4f2846535977753ac732df557b4e0ff79621a238))

## [0.6.0](https://github.com/CyKiller/stepstitch/compare/v0.5.0...v0.6.0) (2026-06-28)


### Features

* Evidence Attestation + Fragility Radar (0.6.1, 0.6.2) ([c3e0d47](https://github.com/CyKiller/stepstitch/commit/c3e0d47fb54877c7fde6cc99e448848be698d564))
* Fix Memory — structural match against the verified-fix corpus (0.6.0) ([ad9bc19](https://github.com/CyKiller/stepstitch/commit/ad9bc19ce288d9d6e5072bba32a309572f72ce98))
* **web:** surface the 0.5.0 operator console on the site ([e1db202](https://github.com/CyKiller/stepstitch/commit/e1db20270720ac5519dd69708587045b8c7c02c9))
* **web:** surface the 0.6.x agent tools on the site ([59f2568](https://github.com/CyKiller/stepstitch/commit/59f2568e703c0c99521e992924768a30a2821a5e))

## [0.5.0](https://github.com/CyKiller/stepstitch/compare/v0.4.2...v0.5.0) (2026-06-28)


### Features

* **dashboard:** governed config console — agent scoping, scrub editor, audit ([02da6e8](https://github.com/CyKiller/stepstitch/commit/02da6e865d16430ac91a609da9abb62aedb6ccda))
* product wrapper — evidence cockpit, red-to-green demo, buyer pages ([6fa4a60](https://github.com/CyKiller/stepstitch/commit/6fa4a6063e976a673e1674f4efb2a1077370c34b))
* **web:** audience-altitude homepage, sharpened comparison + launch copy ([659eff2](https://github.com/CyKiller/stepstitch/commit/659eff21132a4cebbca9740dc766b41a7e6f259c))
* **web:** surface enterprise capabilities, fix credibility + taste gaps ([18f9f48](https://github.com/CyKiller/stepstitch/commit/18f9f488775d7e6b84582d5ba42843c5ac738e49))


### Bug Fixes

* **ci:** green up main — bump SDK test node to 20, type the /demo bundle ([b3f6b0c](https://github.com/CyKiller/stepstitch/commit/b3f6b0cabf9989d025457b64aff465a2f5a3d6ca))
* **compiler:** read exception class from error_type, not the dropped name key ([42c05c1](https://github.com/CyKiller/stepstitch/commit/42c05c16a841441c030d32b4fa63a85939525d6c))
* **service:** align pyproject version to 0.4.2 (lockstep with SDK) ([3d8cd2c](https://github.com/CyKiller/stepstitch/commit/3d8cd2ce28dbf8edc8895b38ffb0112c448ae9af))
* **service:** bump pyproject version to 0.4.2 for lockstep with SDK ([4f0b898](https://github.com/CyKiller/stepstitch/commit/4f0b89896a9a02a56d836ea8b67e67e1eaa7ea81))
* **web:** guard contact email validation against ReDoS; add npm badge ([04d3b0c](https://github.com/CyKiller/stepstitch/commit/04d3b0c610f071841f9650d895dbbd7f3f143366))
* **web:** ReDoS guard on contact email + npm badge ([38cfc97](https://github.com/CyKiller/stepstitch/commit/38cfc97f9d070fa29993f50da7d595a60e5a2e59))

## v0.4.2 — First public npm release

- **Published to npm as `@stepstitch/tracker`**, provenance-signed and built by CI.
- **Added `repository`, `homepage`, and `bugs` metadata** to `package.json` — required for
  npm provenance attestation (sigstore verifies the declared repo) and surfaced on the
  npm package page. (v0.4.1's publish was rejected for the missing `repository` field.)

## v0.4.1 — First public npm release

- **Published to npm as `@stepstitch/tracker`.** First release available on the public
  registry, provenance-signed and built by CI from a clean, gated pipeline.
- **Correct ESM resolution.** SDK barrel exports now use explicit `.js` specifiers so the
  published ESM build resolves correctly under Node's native module resolution.
- **Project-branded README.** npm-facing README leads with the StepStitch header, status
  badges (CI, CodeQL, release, license, website), and StepStitch-only branding.

## v0.4.0 — Financial-services support pack

- **Positioning sharpened: issue-to-repro infrastructure, not session replay.** README +
  npm description now lead with privacy-safe debugging evidence and reproducibility
  (scrubbed timeline → diagnostics → replayability → Playwright repro), explicitly
  distinct from the crowded session-replay/observability category.
- **Financial-services support pack.** Added sanitized ServiceNow, Salesforce, and
  Genesys draft previews for Copilot/Power Platform workflows. StepStitch still sends
  nothing and holds no system-of-record credentials.
- **Sanitized frontend diagnostics.** The SDK and backend now preserve useful API/error
  structure (status, method, endpoint template, exception type, source path, line,
  build/release metadata) while raw logs, messages, stacks, bodies, headers, cookies,
  screenshots, page text, input values, and full URLs remain forbidden.
- **Copilot tool expansion.** Added `GetDiagnosticSummary` and
  `CreateFinancialServicesExportPreview` to the read/draft-only OpenAPI pack, with docs
  and policy updates for generic regulated support operations.
- **Golden-path acceptance test** (`service/tests/test_golden_path.py`) — one hostile
  report flows through the whole product (ingest+scrub → list → read → summary →
  privacy-posture → export-preview → compile) as the executable definition of done.
- **Completion ledger** (`docs/STATUS.md`) — maps every plan item to status + proof,
  and names the exact (credential/decision) unblockers for the remaining gated work.
- **Architecture: StepStitch core, integrations via Copilot.** Documented the chosen
  topology — StepStitch exposes sanitized reads + a flat draft; a Copilot Studio agent
  reaches ServiceNow/Salesforce/Genesys workflows through Microsoft's **native
  connectors** and governed Power Platform flows (StepStitch builds no outbound send
  layer, by design). New `copilot/SETUP.md` (agent blueprint)
  and `copilot/connector-field-map.md` (draft → native-connector field maps); refined
  `system-prompt.md` / `action-policy.md` to make the native-connector create explicit.

## v0.3.0 — Enterprise evidence layer

**Intent.** v0.1–v0.2 proved the *privacy* half: structural-only capture, consent, the
deterministic Playwright compiler, audited admin reads, right-to-delete, split
retention, the org-wide kill switch, and supply-chain artifacts (SBOM, SRI, signed
tags). v0.3.0 adds the *trust + usefulness + governance* half so StepStitch reads as a
privacy-safe support-to-engineering evidence layer for regulated digital operations —
not just a bug tool.

### Added (backend, `service/stepstitch_service/`)

- **Server-side scrubber** (`scrubber.py`) — the NPI trust boundary. Runs on every
  ingestion before storage, independent of the SDK. Redacts SSNs, card/account numbers,
  phone, email, DOB-like dates, long numeric IDs and raw URLs from free text;
  re-templates routes; strict-allowlists metadata; drops forbidden keys (request/response
  bodies, console, headers, cookies, screenshots, dom). `reject_on_forbidden` turns a
  leak signal into HTTP 422. Per-trace report returned on ingest + stored at
  `trace_metadata._scrub`.
- **Replayability engine** (`replayability.py`) — deterministic 0–1 score, letter grade,
  and warnings from structural footsteps; surfaced on `GET /session/{id}`, a dedicated
  `/replayability` endpoint, and the compiled repro header.
- **Deployment profiles** (`profiles.py` + `profiles/*.json`) —
  `financial-services-enterprise` (default), `healthcare-strict`, `internal-enterprise`,
  `open-source-default`. A profile can only tighten the NPI boundary.
- **Draft-only integrations** (`integrations/`) — sanitized, flat ServiceNow incident
  and Salesforce case drafts built from a `TraceSummary`; no live API calls.
- **Copilot-safe surface** — `GET /session/{id}/summary`, `/privacy-posture`,
  `POST /session/{id}/export-preview` (all admin-only, audited) + `copilot/`
  (`openapi-v2.json`, `action-policy.md`, `system-prompt.md`).
- **Compliance evidence** (`compliance.py` + `scripts/generate_compliance_evidence.py`)
  — `COMPLIANCE-EVIDENCE.md` generated from the live scrub policy; drift-guarded.

### Notes

- **SDK runtime is functionally unchanged** — `src/` redaction/tracker logic is the same
  as v0.2.0; only `SDK_VERSION` bumped (lockstep). The SRI hash changes only because the
  stamped version string changed; the redaction-proof suite is unchanged and green.
- **Backward compatible.** `create_stepstitch_router(...)` gains an optional
  `scrub_policy` (defaults to the strict financial-services posture). Existing callers
  get server-side scrubbing automatically with no signature change.
- Tests: 76 backend (`service/tests`) + 18 SDK (`tests/`), all green; `ruff` clean.

## v0.2.0

- Org-wide kill switch (`capture_enabled`) and split-retention `purge_expired_traces`.
- SBOM, SRI, signed-tag release runbook; live Chromium repro proof.

## v0.1.0

- Privacy-by-default footsteps SDK + deterministic Playwright compiler + decoupled
  router factory.
