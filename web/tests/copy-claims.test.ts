import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// Guard the buyer-facing copy against the one thing StepStitch must never claim: that it
// captures screens, input values, page text, the DOM, keystrokes, or raw data. Honest
// *negated* mentions ("never captures screens") are fine; an affirmative capture claim is not.
const APP = join(process.cwd(), "src", "app");
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

  it("the red-to-green demo page never presents its declared outcomes as measured CI", () => {
    const text = readFileSync(join(APP, "demo/page.tsx"), "utf8");
    expect(text).toContain("declared");
    expect(text).toContain("synthetic");
    expect(text).not.toContain("CI reports red");
  });
});
