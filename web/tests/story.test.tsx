import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import bundle from "@/lib/demo-bundle.json";
import { BEATS, RUN, TEST_LINES, TOTAL_VH, locate, packetFor } from "@/components/story/story-data";
import { AiView, BoardView, LeftView, ProofView } from "@/components/story/surface-views";

// The "Follow one request" story must show the committed demo run and nothing else: these
// tests fail if a number on the page stops matching web/src/lib/demo-bundle.json, or if the
// story's own structure (both depths, one peak) is broken.

const s = bundle.steps;

describe("story structure", () => {
  it("has both depths for every beat, and unique ids", () => {
    expect(new Set(BEATS.map((b) => b.id)).size).toBe(BEATS.length);
    for (const b of BEATS) {
      expect(b.plain.title && b.plain.body && b.technical.title && b.technical.body).toBeTruthy();
    }
  });

  it("gives the proof beat, the peak, the largest scroll span", () => {
    const proof = BEATS.find((b) => b.id === "proof")!;
    expect(Math.max(...BEATS.map((b) => b.vh))).toBe(proof.vh);
    expect(BEATS.filter((b) => b.vh === proof.vh)).toHaveLength(1);
  });

  it("maps every scroll position to exactly one beat, in order", () => {
    expect(TOTAL_VH).toBe(BEATS.reduce((sum, b) => sum + b.vh, 0));
    expect(locate(0).index).toBe(0);
    expect(locate(1).index).toBe(BEATS.length - 1);
    let last = 0;
    for (let p = 0; p <= 1; p += 0.01) {
      const { index } = locate(p);
      expect(index).toBeGreaterThanOrEqual(last);
      last = index;
    }
  });
});

describe("the story shows the committed demo run", () => {
  it("reads its numbers from the bundle", () => {
    expect(RUN.score).toBe(s["4_replayability"].score);
    expect(RUN.grade).toBe(s["4_replayability"].grade);
    expect(RUN.scrubbedFields).toEqual(s["3_privacy_scrub"].scrubbed_fields);
    expect(RUN.verification.verdict).toBe("confirmed_fixed");
    expect(RUN.verification.pre_passed).toBe(false);
    expect(RUN.verification.post_passed).toBe(true);
    expect(TEST_LINES.some((l) => l.startsWith("expect("))).toBe(true);
  });

  it("renders the real scrub result in the 'what left the browser' view", () => {
    render(<LeftView t={1} technical={false} />);
    expect(screen.getByText(s["3_privacy_scrub"].explanation_after_scrub)).toBeTruthy();
    expect(screen.getByText(`${s["3_privacy_scrub"].scrubbed_fields.length} private details removed on the server`)).toBeTruthy();
  });

  it("renders the real grade and priorities on the board", () => {
    render(<BoardView t={1} technical />);
    expect(screen.getByText(`${s["4_replayability"].score} · ${s["4_replayability"].grade}`)).toBeTruthy();
    expect(screen.getByText(`priority: ${s["6_drafts"].linear.priority}`)).toBeTruthy();
    expect(screen.getByText(`Priority: ${s["6_drafts"].salesforce.Priority}`)).toBeTruthy();
  });

  it("locks the bundle's never-captured list whatever the AI scope", () => {
    render(<AiView t={1} technical={false} scope="drafts" setScope={() => {}} interactive />);
    for (const item of s["3_privacy_scrub"].never_captured) expect(screen.getByText(item)).toBeTruthy();
    expect(packetFor("none")).toEqual([]);
    const keys = packetFor("drafts").map((p) => p.key);
    for (const banned of ["screenshot", "input", "page_text", "body", "header", "cookie"]) {
      expect(keys.some((k) => k.includes(banned))).toBe(false);
    }
  });

  it("shows the measured verdict, not a hard-coded one", () => {
    render(<ProofView t={1} technical />);
    expect(screen.getByText(RUN.verification.verdict)).toBeTruthy();
    expect(screen.getByText(`evidence: ${s["7_ci_verification"].measurement.evidence_grade}`)).toBeTruthy();
  });
});
