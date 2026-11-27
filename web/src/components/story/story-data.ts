import bundle from "@/lib/demo-bundle.json";

// Everything the "Follow one request" story shows comes from one committed, real run:
// web/src/lib/demo-bundle.json, produced by scripts/demo_red_to_green.py from the real service
// modules. Numbers and labels are read from it here, never typed into the page, and
// tests/story.test.ts fails if the two drift. It sits under src/components so the
// copy-claims scanner reads every caption in this file.
// Brief: docs/superpowers/specs/2026-10-23-scroll-story-BRIEF.md

const s = bundle.steps;

export const RUN = {
  traceId: bundle.trace_id,
  route: bundle.trace_summary.route,
  endpoint: bundle.trace_summary.diagnostic_endpoint,
  status: bundle.trace_summary.failing_status,
  stepCount: bundle.trace_summary.step_count,
  score: s["4_replayability"].score,
  grade: s["4_replayability"].grade,
  signals: s["4_replayability"].signals,
  warning: s["4_replayability"].warnings[0]?.code ?? null,
  policy: s["3_privacy_scrub"].policy,
  rawExplanation: s["1_bug_report"].raw_unsafe_input.explanation,
  scrubbedExplanation: s["3_privacy_scrub"].explanation_after_scrub,
  scrubbedFields: s["3_privacy_scrub"].scrubbed_fields,
  neverCaptured: s["3_privacy_scrub"].never_captured,
  timeline: s["2_structural_capture"].timeline,
  playwright: s["5_playwright_repro"].playwright_code,
  drafts: s["6_drafts"],
  delivery: s["6_drafts"].delivery,
  verification: s["7_ci_verification"],
  prBody: s["6_drafts"].github.issue.body,
};

/** The four lines of the generated test that do the work, for the proof beat. */
export const TEST_LINES = RUN.playwright
  .split("\n")
  .filter((l) => /await page\.|expect\(/.test(l))
  .map((l) => l.trim());

/** Ticket and alert drafts that carry a priority, exactly as the bundle has them. */
export const PRIORITY_DRAFTS: { tool: string; field: string; value: string }[] = [
  { tool: "Linear", field: "priority", value: RUN.drafts.linear.priority },
  { tool: "Salesforce", field: "Priority", value: RUN.drafts.salesforce.Priority },
  { tool: "Zendesk", field: "priority", value: RUN.drafts.zendesk.priority },
  { tool: "Slack", field: "marker", value: RUN.drafts.slack.text.split(" ")[0] ?? "" },
  { tool: "ServiceNow", field: "urgency", value: RUN.drafts.servicenow.urgency },
];

// The console's own label pairs (service/stepstitch_service/host/dashboard.py): technical
// name first, then what a support lead or QA engineer reads.
export const STAGES = [
  { id: "untriaged", label: "Untriaged", plain: "Waiting for a test run" },
  { id: "known_shape", label: "Known shape", plain: "Seen before" },
  { id: "reproduced", label: "Reproduced", plain: "Confirmed broken" },
  { id: "fix_failed", label: "Fix failed", plain: "Still broken" },
  { id: "fixed", label: "Fixed", plain: "Fixed and proven" },
] as const;

export const TABS = {
  evidence: { label: "Evidence", plain: "What happened" },
  repro: { label: "Repro", plain: "The test" },
  verify: { label: "Verify", plain: "Proof it's fixed" },
  drafts: { label: "Drafts", plain: "Ticket drafts" },
  agent: { label: "Agent view", plain: "What an AI sees" },
  attest: { label: "Attestation", plain: "Signed record" },
} as const;

// The product's real agent scopes (service/stepstitch_service/host/agents.py). "verify" is
// CI-only and never offered to an assistant, so it is shown apart and locked.
export const SCOPES = ["none", "summaries", "repros", "drafts"] as const;
export type Scope = (typeof SCOPES)[number];

/** What an assistant receives at each scope, built from the same run. */
export function packetFor(scope: Scope): { key: string; value: string }[] {
  if (scope === "none") return [];
  const summary = [
    { key: "route", value: RUN.route },
    { key: "failing_status", value: String(RUN.status) },
    { key: "replayability", value: `${RUN.score} (${RUN.grade})` },
  ];
  if (scope === "summaries") return summary;
  const repros = [
    ...summary,
    { key: "timeline", value: `${RUN.stepCount} structural steps` },
    { key: "repro_test", value: "Playwright, deterministic" },
    { key: "replay_diagnostics", value: "from your own replay; customer_data_status: not_verified" },
  ];
  if (scope === "repros") return repros;
  return [...repros, { key: "drafts", value: "ticket and pull-request drafts" }];
}

export type BeatId = "help" | "left" | "board" | "ai" | "proof" | "start";

export type Beat = {
  id: BeatId;
  name: string;
  /** Scroll length in viewport heights. The proof beat is the peak and gets the most. */
  vh: number;
  /** Badge the followed report chip gains in this beat. */
  badge: { plain: string; technical: string; tone: "bad" | "ok" | "neutral" };
  plain: { title: string; body: string };
  technical: { title: string; body: string };
  /** The file a reader can open to check this beat. */
  source: string;
};

export const BEATS: Beat[] = [
  {
    id: "help",
    name: "Someone needs help",
    vh: 100,
    badge: { plain: "Reported", technical: `HTTP ${RUN.status}`, tone: "bad" },
    plain: {
      title: "A transfer won't go through",
      body: "Someone presses Review transfer and gets an error. They tell you what happened, in their own words.",
    },
    technical: {
      title: `HTTP ${RUN.status} on POST ${RUN.endpoint}`,
      body: `The reporter widget submits the user's explanation with the structural footsteps of the session. Capture stays off until consent is granted.`,
    },
    source: "src/reporter.ts",
  },
  {
    id: "left",
    name: "Only the steps leave",
    vh: 110,
    badge: { plain: `${RUN.scrubbedFields.length} details removed`, technical: `scrubbed · ${RUN.scrubbedFields.length} fields`, tone: "neutral" },
    plain: {
      title: "Only the steps leave the browser",
      body: "You get what they did, step by step. What they typed and saw stays with them, and anything private in their message is removed before it's stored.",
    },
    technical: {
      title: `${RUN.stepCount} structural steps, ${RUN.scrubbedFields.length} fields scrubbed`,
      body: `Routes are templated (${RUN.route}), selectors are structural, and the server scrubber re-checks every field under the ${RUN.policy} profile before storage.`,
    },
    source: "service/stepstitch_service/scrubber.py",
  },
  {
    id: "board",
    name: "Sorted and graded",
    vh: 120,
    badge: { plain: `Grade ${RUN.grade}`, technical: `${RUN.score} · ${RUN.grade}`, tone: "neutral" },
    plain: {
      title: "Sorted, graded and drafted",
      body: "It lands on your team's board, graded for whether engineering can reproduce it, with ticket drafts ready for the tools you already use. Nothing is sent until you choose.",
    },
    technical: {
      title: `Replayability ${RUN.score} (grade ${RUN.grade})`,
      body: `${RUN.signals.steps} steps, ${RUN.signals.interactive} interactive, ${RUN.signals.stable_selectors} stable selectors. Drafts carry the priority each tool supports; delivery is ${RUN.delivery}.`,
    },
    source: "service/stepstitch_service/replayability.py",
  },
  {
    id: "ai",
    name: "What an AI sees",
    vh: 120,
    badge: { plain: "AI access: you decide", technical: "scope: repros", tone: "neutral" },
    plain: {
      title: "You decide what the AI sees",
      body: "Turn the dial. Your AI assistant gets more or less to work with, but what your customer saw and typed is never on the list.",
    },
    technical: {
      title: "Scoped agent tokens over MCP",
      body: "Tokens are scoped none, summaries, repros or drafts, and out-of-scope calls are refused. A separate verify key, for CI only, can record a verdict and nothing else.",
    },
    source: "service/stepstitch_service/agent_packet.py",
  },
  {
    id: "proof",
    name: "Proven, not guessed",
    vh: 150,
    badge: { plain: "Fixed and proven", technical: RUN.verification.verdict, tone: "ok" },
    plain: {
      title: "Proven, not guessed",
      body: "The same test runs on the old code and fails, then on the fix and passes. That's the proof. If it still failed, it would go back. A person still decides what merges.",
    },
    technical: {
      title: `pre_passed: ${RUN.verification.pre_passed} → post_passed: ${RUN.verification.post_passed}`,
      body: `Verdict ${RUN.verification.verdict}, evidence grade ${RUN.verification.measurement.evidence_grade}. The verdict derives only from a red run followed by a green one; anything else is not fixed.`,
    },
    source: "service/stepstitch_service/verification/verdict.py",
  },
  {
    id: "start",
    name: "Start",
    vh: 90,
    badge: { plain: "Ready", technical: "ready", tone: "ok" },
    plain: {
      title: "Start in one command",
      body: "Run it on your own machine and connect your AI assistant. Free and open source.",
    },
    technical: {
      title: "npx stepstitch start --connect claude",
      body: "Starts a local console with a SQLite store on your machine and registers the MCP server with your assistant. Self-host with Docker and Postgres when you're ready.",
    },
    source: "packages/cli-shim",
  },
];

export const TOTAL_VH = BEATS.reduce((sum, b) => sum + b.vh, 0);

const STARTS = BEATS.reduce<number[]>((acc, b, i) => {
  acc.push(i === 0 ? 0 : (acc[i - 1] ?? 0) + (BEATS[i - 1]?.vh ?? 0) / TOTAL_VH);
  return acc;
}, []);

/** Which beat a story progress (0 to 1) falls in, and how far through it (0 to 1). */
export function locate(progress: number): { index: number; local: number } {
  const p = Math.min(Math.max(progress, 0), 1);
  for (let i = BEATS.length - 1; i >= 0; i--) {
    const start = STARTS[i] ?? 0;
    if (p >= start) {
      const len = (BEATS[i]?.vh ?? 1) / TOTAL_VH;
      return { index: i, local: Math.min((p - start) / len, 1) };
    }
  }
  return { index: 0, local: 0 };
}

export const BEAT_STARTS = STARTS;
