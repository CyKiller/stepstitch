/**
 * The claim registry — every material marketing statement, mapped to the thing
 * that proves it.
 *
 * The rule this encodes: **the site may not assert an absolute the code cannot
 * demonstrate.** "No NPI captured" was such an absolute — the server-side
 * scrubber redacts SSNs, cards, emails, phone numbers, dates and long digit
 * runs, but a customer's *name* or street address in free text survives every
 * one of those patterns. The product's own vocabulary already said this
 * honestly (`customer_data_status: "not_verified"`, the from_production /
 * from_reproduction split in `agent_packet.py`); the site did not.
 *
 * Scope, stated precisely so this file does not itself overclaim: the high-risk
 * surfaces — the financial-services pilot page, the FAQ's compliance answer, and the
 * competitor comparison — import their sentences from here, so copy and evidence move
 * together. The remaining entries are an evidence index: they are checked to point at
 * files that exist, and the rendered copy is independently policed by the
 * absolute-claim scanner in `web/tests/copy-claims.test.ts`. Wiring a sentence here is
 * the stronger guarantee; the scanner is the floor under every page.
 *
 * So each claim here carries:
 *   - `text`     the exact sentence rendered on the page, imported by the page
 *                so copy and evidence cannot drift apart
 *   - `kind`     measured (a test/CI job runs it) | architectural (true by
 *                construction — the code path does not exist) | policy (a
 *                default or posture, configurable)
 *   - `evidence` a repo path a reader can open, plus the test that pins it
 *   - `asOf` / `source` required for anything said about a competitor
 *
 * `web/tests/claims-registry.test.ts` asserts every evidence path exists, and
 * `web/tests/copy-claims.test.ts` refuses absolute language on the buyer pages
 * unless it belongs to a registered `measured` or `architectural` claim.
 */

export type ClaimKind = "measured" | "architectural" | "policy";

export type Claim = {
  /** Stable id — what the tests and the page both refer to. */
  id: string;
  /** The exact sentence the page renders. */
  text: string;
  kind: ClaimKind;
  /** Where a reader verifies it. `test` is the named proof, when there is one. */
  evidence: { path: string; test?: string };
  /** Required for competitor claims: when it was checked, and against what. */
  asOf?: string;
  source?: string;
};

export const CLAIMS: Claim[] = [
  // --- What the SDK does not capture (architectural: no such code path) -------
  {
    id: "no-screen-capture",
    text:
      "StepStitch never records the screen, the session, or what anyone typed — there is no code path that captures them.",
    kind: "architectural",
    evidence: { path: "src/redaction.ts", test: "tests/redaction-proof.test.ts" },
  },
  {
    id: "no-input-values",
    text:
      "Input footsteps record that an interaction happened and nothing else; password, credit-card and [data-sensitive] fields are skipped entirely.",
    kind: "architectural",
    evidence: { path: "src/tracker.ts", test: "tests/redaction-proof.test.ts" },
  },
  {
    id: "routes-are-templates",
    text:
      "URLs are reduced to route templates (/accounts/:id) before they leave the browser, and again on the server.",
    kind: "architectural",
    evidence: { path: "src/redaction.ts", test: "service/tests/test_scrubber.py" },
  },

  // --- What the server proves (measured: a test or CI job runs it) ------------
  {
    id: "strict-schema-passed",
    text:
      "Under the financial-services-strict profile the server refuses free text, unapproved selectors and undeclared routes with HTTP 422, and stamps what survived strict_schema_passed.",
    kind: "measured",
    evidence: {
      path: "service/stepstitch_service/scrubber.py",
      test: "service/tests/test_strict_policy.py",
    },
  },
  {
    id: "hostile-post-cannot-persist",
    text:
      "A hand-rolled hostile POST cannot persist the values it carries: the server scrubs every ingestion before storage, independent of the SDK, and records what it stripped.",
    kind: "measured",
    evidence: {
      path: "service/stepstitch_service/scrubber.py",
      test: "service/tests/test_scrubber.py",
    },
  },
  {
    id: "browser-to-database-measured",
    text:
      "CI runs the whole chain with no mocks — real browser, real SDK, same-origin proxy, real scrubber, then reads the stored database row back — and asserts no form value reached storage.",
    kind: "measured",
    evidence: {
      path: "scripts/live_financial_loop.py",
      test: ".github/workflows/ci.yml",
    },
  },
  {
    id: "red-to-green-measured",
    text:
      "confirmed_fixed is derived from two measured runs — the same frozen test failing before the fix and passing after — never from a caller asserting it.",
    kind: "measured",
    evidence: {
      path: "service/stepstitch_service/verification/verdict.py",
      test: "service/tests/test_verdict.py",
    },
  },
  {
    id: "tenant-fixtures-verifiable",
    text:
      "stepstitch policy verify runs your own hostile fixtures through the live scrub boundary and reports, per fixture, whether it was rejected, dropped or redacted.",
    kind: "measured",
    evidence: {
      path: "service/stepstitch_service/policy_verify.py",
      test: "service/tests/test_policy_verify.py",
    },
  },

  // --- What StepStitch does NOT claim (the honest limit) ----------------------
  {
    id: "reproduction-not-certified",
    text:
      "Evidence from a local reproduction is scrubbed and never comes from the reported session, but the application under test is yours — so StepStitch marks that data customer_data_status: not_verified rather than certifying it.",
    kind: "architectural",
    evidence: {
      path: "service/stepstitch_service/agent_packet.py",
      test: "service/tests/test_agent_packet.py",
    },
  },
  {
    id: "controls-not-certification",
    text:
      "StepStitch provides technical controls and evidence, not a compliance certification.",
    kind: "policy",
    evidence: { path: "COMPLIANCE-EVIDENCE.md", test: "service/tests/test_compliance.py" },
  },

  // --- Independent verification (the second pillar) ---------------------------
  {
    id: "attestation-self-verifiable",
    text:
      "The attestation is canonical JSON hashed with SHA-256 and signed with a key only your tenant holds — anyone can recompute the hash or run cosign verify-blob without asking us anything.",
    kind: "measured",
    evidence: {
      path: "service/stepstitch_service/attestation.py",
      test: "service/tests/test_attestation.py",
    },
  },
  {
    id: "agent-cannot-self-verify",
    text:
      "The credential handed to a coding agent cannot write a verdict: the verify scope sits outside the agent scope ladder, so the token that proposes a fix can never be the token that records it worked.",
    kind: "architectural",
    evidence: {
      path: "service/stepstitch_service/host/agents.py",
      test: "server/tests/test_agents.py",
    },
  },
  {
    id: "evidence-grade-uncounterfeitable",
    text:
      "Evidence grades are derived from how an outcome was obtained, never accepted from a caller — a payload claiming a signed grade is recorded as asserted.",
    kind: "measured",
    evidence: {
      path: "service/stepstitch_service/evidence.py",
      test: "service/tests/test_evidence.py",
    },
  },
  {
    id: "fixproof-offline-verifiable",
    text:
      "A FixProof is an in-toto statement whose hash is reproducible from the document alone — stepstitch proof verify checks it offline against your policy, with no host, no account, and no trust in whoever handed it over.",
    kind: "measured",
    evidence: {
      path: "service/stepstitch_service/fixproof.py",
      test: "service/tests/test_proof_cli.py",
    },
  },
  {
    id: "fixproof-mutation-covered",
    text:
      "Every leaf of the proof statement is mutation-tested: altering, deleting, or inserting any field makes offline verification refuse the document, and the mutation surface is enumerated from the statement itself so it cannot silently shrink.",
    kind: "measured",
    evidence: {
      path: "service/stepstitch_service/fixproof.py",
      test: "service/tests/test_fixproof.py",
    },
  },
  {
    id: "fixproof-no-raw-values",
    text:
      "The proof binds digests, statuses, and identities — a proof built from a hostile ingest is scanned against the canary values and none of them appear in the exported document.",
    kind: "measured",
    evidence: {
      path: "service/stepstitch_service/fixproof.py",
      test: "service/tests/test_fixproof.py",
    },
  },
  {
    id: "fixproof-signature-verified",
    text:
      "The signature check is cryptographic, not cosmetic: an Ed25519 signature verified against keys your policy names — a fabricated document with a recomputed hash, a fake signature string, and a valid signature by an untrusted key are each refused, and each refusal is a permanent test.",
    kind: "measured",
    evidence: {
      path: "service/stepstitch_service/fixproof.py",
      test: "service/tests/test_fixproof_adversarial.py",
    },
  },

  // --- Posture defaults (policy: configurable, but this is the default) -------
  {
    id: "consent-gated",
    text:
      "Capture is off until your consent manager calls grantConsent(), and it honors Global Privacy Control and Do-Not-Track.",
    kind: "policy",
    evidence: { path: "src/tracker.ts", test: "tests/tracker.test.ts" },
  },
  {
    id: "self-hosted",
    text:
      "Self-hosted and Apache-2.0: the evidence stays inside your boundary and every line is auditable.",
    kind: "policy",
    evidence: { path: "LICENSE" },
  },
];

const BY_ID = new Map(CLAIMS.map((c) => [c.id, c]));

/** The exact registered sentence. Throws on an unknown id so a typo fails the build. */
export function claim(id: string): string {
  const found = BY_ID.get(id);
  if (!found) throw new Error(`unknown claim id: ${id}`);
  return found.text;
}

export function getClaim(id: string): Claim {
  const found = BY_ID.get(id);
  if (!found) throw new Error(`unknown claim id: ${id}`);
  return found;
}

/**
 * Competitor comparison rows. Separated from CLAIMS because they carry a
 * different burden of proof: a statement about someone else's product must say
 * when it was checked and against what, or it is just an assertion that ages
 * badly. Rendered with a dated footnote.
 */
export type CompetitorClaim = {
  id: string;
  subject: string;
  text: string;
  asOf: string;
  source: string;
};

export const COMPETITOR_CLAIMS: CompetitorClaim[] = [
  {
    id: "replay-records-sessions",
    subject: "Session replay (FullStory, LogRocket)",
    text: "Session-replay tools reconstruct the user's session as a watchable recording; masking is a configuration applied on top.",
    asOf: "2026-08-04",
    source: "https://help.fullstory.com/hc/en-us/articles/360020623434",
  },
  {
    id: "openreplay-records-sessions",
    subject: "OpenReplay",
    text: "OpenReplay is self-hosted and open source, and still produces a session recording as its primary artifact.",
    asOf: "2026-08-04",
    source: "https://docs.openreplay.com/en/deployment/",
  },
  {
    id: "apm-error-first",
    subject: "APM and error tracking (Sentry, Datadog)",
    text: "Error and APM tools capture stack traces and breadcrumbs from the failure, and offer session replay as a separate product.",
    asOf: "2026-08-04",
    source: "https://docs.sentry.io/product/explore/session-replay/",
  },
];

export const COMPETITOR_CLAIMS_AS_OF = "2026-08-04";
