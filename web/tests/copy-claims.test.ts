import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// Guard the buyer-facing copy against the one thing StepStitch must never claim: that it
// captures screens, input values, page text, the DOM, keystrokes, or raw data. Honest
// *negated* mentions ("never captures screens") are fine; an affirmative capture claim is not.
const APP = join(process.cwd(), "src", "app");
// The repo root — some claims are backed by files outside web/ (CI workflows, the
// committed evidence bundle), and a claim is only as good as the proof it names.
const REPO = join(process.cwd(), "..");
const PAGES = [
  "demo/page.tsx",
  "financial-services-pilot/page.tsx",
  "privacy-vs-replay/page.tsx",
  "agents/page.tsx",
  "quickstart/page.tsx",
  "who-its-for/page.tsx",
].map((p) => join(APP, p));

// A capture verb immediately followed by a sensitive object.
const CAPTURE_RE =
  /(records?|captures?|recording|screenshots?\s+of)\s+(the\s+|your\s+|a\s+)?(screen|screens|dom|page text|input values?|keystrokes|stack traces?|raw data)/gi;
const NEGATORS = ["never", "no ", "not ", "without", "cannot", "can't", "doesn't", "don't", "isn't", "no-"];

function offendingClaims(text: string): string[] {
  const out: string[] = [];
  for (const m of text.matchAll(CAPTURE_RE)) {
    const start = m.index ?? 0;
    const before = text.slice(Math.max(0, start - 24), start).toLowerCase();
    const negated = NEGATORS.some((n) => before.includes(n));
    if (!negated) out.push(m[0]);
  }
  return out;
}

describe("buyer-facing copy never claims screen/input/raw capture", () => {
  for (const page of PAGES) {
    it(`${page.split("/app/")[1]} makes no affirmative capture claim`, () => {
      const text = readFileSync(page, "utf8");
      expect(offendingClaims(text)).toEqual([]);
    });
  }

  it("the negation-aware scanner actually catches an affirmative claim", () => {
    // Sanity check: a real lie must be flagged, and an honest negation must not be.
    expect(offendingClaims("StepStitch records the screen of every user.")).not.toEqual([]);
    expect(offendingClaims("StepStitch never records the screen.")).toEqual([]);
  });

  it("the privacy comparison states the honest claim", () => {
    const text = readFileSync(join(APP, "privacy-vs-replay/page.tsx"), "utf8");
    expect(text).toContain("not a recording");
  });
});

// The second rule, added with the claim registry: the site may not assert an ABSOLUTE
// the code cannot demonstrate. The scrubber redacts SSNs, cards, emails, phones, dates
// and long digit runs — a customer's name or street address in free text survives all
// of them, so "no NPI" was never a provable statement. What IS provable (a 422, a
// stored row, a measured run) is what the copy is allowed to say.
const UNPROVABLE = [
  { re: /\b(no|zero)\s+NPI\b/gi, why: "the scrubber cannot prove the absence of a name" },
  { re: /\bnever\s+captures?\s+PII\b/gi, why: "free text is user-authored; say what the server does to it" },
  { re: /\bNPI-free\b/gi, why: "states an absence nothing measures" },
  { re: /\bproving\s+no\s+NPI\b/gi, why: "asserts a proof that does not exist" },
  { re: /\bguarantees?\s+(no|zero)\b/gi, why: "a guarantee is not a control" },
];

const ALL_COPY = [
  ...PAGES,
  ...["faq.tsx", "comparison.tsx", "hero.tsx", "case-studies.tsx", "whatsnew.tsx"].map(
    (f) => join(process.cwd(), "src", "components", f),
  ),
];

describe("no absolute PII/NPI claim survives anywhere in the buyer copy", () => {
  for (const file of ALL_COPY) {
    it(`${file.split("/src/")[1]} makes no unprovable absolute claim`, () => {
      const text = readFileSync(file, "utf8");
      const found = UNPROVABLE.flatMap((rule) =>
        [...text.matchAll(rule.re)].map((m) => `${m[0]} — ${rule.why}`),
      );
      expect(found).toEqual([]);
    });
  }

  it("the absolute-claim scanner actually catches one (self-test)", () => {
    const lie = "Our pilot guarantees zero NPI and never captures PII.";
    const found = UNPROVABLE.flatMap((rule) => [...lie.matchAll(rule.re)].map((m) => m[0]));
    expect(found.length).toBeGreaterThanOrEqual(2);
    // …and an honest, measurable statement passes.
    const honest =
      "Free text is refused with HTTP 422 under the strict profile, and the server " +
      "reports exactly what it stripped.";
    expect(
      UNPROVABLE.flatMap((rule) => [...honest.matchAll(rule.re)].map((m) => m[0])),
    ).toEqual([]);
  });
});

describe("'live' claims are conditional, never ambient", () => {
  const COMPONENTS = join(process.cwd(), "src", "components");

  it("the homepage demo section makes no unconditional live-service claim", () => {
    // The LiveDemo panel can silently fall back to the bundled sample, so the static copy
    // around it must not assert liveness — the in-panel disclosure carries that per-source.
    const text = readFileSync(join(COMPONENTS, "demo-section.tsx"), "utf8");
    expect(text).not.toMatch(/live from a running/i);
  });

  it("the demo panel discloses both provenance states", () => {
    const text = readFileSync(join(COMPONENTS, "live-demo.tsx"), "utf8");
    expect(text).toContain("Bundled synthetic sample");
    expect(text).toContain("running StepStitch service");
  });

  it("the demo page may say 'measured' only because CI actually measures it", () => {
    // This used to pin the opposite: the outcomes were declared literals, so the page
    // had to say so. They are measured now — and the word is only allowed here because
    // the workflow below re-runs the reproduction in a real browser and fails on drift.
    const text = readFileSync(join(APP, "demo/page.tsx"), "utf8");
    expect(text).toContain("measured");
    // The scenario is still synthetic; only the red-to-green transition is real.
    expect(text).toContain("synthetic");
    expect(text).not.toContain("CI reports red");

    const ci = readFileSync(join(REPO, ".github/workflows/ci.yml"), "utf8");
    expect(ci).toContain("scripts/demo_red_to_green.py --measure");
    expect(ci).toContain("git diff --exit-code demo/evidence-bundle.json");
  });

  it("the committed bundle carries the provenance of its own measurement", () => {
    const bundle = JSON.parse(
      readFileSync(join(REPO, "demo/evidence-bundle.json"), "utf8"),
    );
    const measurement = bundle.steps["7_ci_verification"].measurement;
    expect(measurement.evidence_grade).toBe("measured");
    // Red then green, stated as what the runner observed rather than as a bare boolean.
    expect(measurement.red_verdict).toBe("reproduced");
    expect(measurement.green_verdict).toBe("not_reproduced");
    expect(measurement.pre_passed).toBe(false);
    expect(measurement.post_passed).toBe(true);
  });
});
