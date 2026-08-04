/**
 * The claim registry is only worth having if its evidence is real.
 *
 * Every claim names a file a reader can open and, where one exists, the test that
 * pins it. This suite asserts those paths actually exist in the repository — a
 * registry that cites a deleted test is worse than no registry, because it looks
 * like diligence.
 */
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  CLAIMS,
  COMPETITOR_CLAIMS,
  COMPETITOR_CLAIMS_AS_OF,
  claim,
  getClaim,
} from "@/lib/claims";

const REPO = join(process.cwd(), "..");

describe("claim registry", () => {
  it("is non-empty and has unique ids", () => {
    expect(CLAIMS.length).toBeGreaterThan(5);
    const ids = CLAIMS.map((c) => c.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it.each(CLAIMS.map((c) => [c.id, c] as const))(
    "%s cites evidence that exists",
    (_id, c) => {
      expect(existsSync(join(REPO, c.evidence.path)), c.evidence.path).toBe(true);
      if (c.evidence.test) {
        expect(existsSync(join(REPO, c.evidence.test)), c.evidence.test).toBe(true);
      }
    },
  );

  it("every measured claim names a test, not just a source file", () => {
    // "measured" is the strongest kind — it asserts something RUNS. It may not rest on
    // a file a reader has to interpret.
    for (const c of CLAIMS.filter((c) => c.kind === "measured")) {
      expect(c.evidence.test, `${c.id} is measured but names no proof`).toBeTruthy();
    }
  });

  it("claim text is a sentence, not a slogan", () => {
    for (const c of CLAIMS) {
      expect(c.text.length, c.id).toBeGreaterThan(40);
      expect(c.text.trim().endsWith("."), c.id).toBe(true);
    }
  });

  it("claim() returns the registered text and rejects a typo", () => {
    expect(claim("strict-schema-passed")).toContain("422");
    expect(() => claim("no-such-claim")).toThrow(/unknown claim id/);
    expect(getClaim("self-hosted").kind).toBe("policy");
  });

  it("no claim asserts an absolute the scrubber cannot demonstrate", () => {
    // The specific failure this registry exists to prevent: a name or street address
    // in free text survives every PII pattern, so "no NPI" was never provable.
    for (const c of CLAIMS) {
      expect(c.text, c.id).not.toMatch(/\b(no|zero) NPI\b/i);
      expect(c.text, c.id).not.toMatch(/\bnever captures? PII\b/i);
      expect(c.text, c.id).not.toMatch(/\bguarantee[sd]?\b/i);
    }
  });
});

describe("the registry is actually consumed by the pages", () => {
  // The registry's whole purpose is that a rendered sentence and its evidence are ONE
  // object. It shipped defined-but-unimported: the pages kept private copies of the
  // same sentences, which is precisely the drift it claims to prevent. These pin the
  // high-risk pages to it — the ones where a false claim costs something.
  const HIGH_RISK = [
    "src/app/financial-services-pilot/page.tsx",
    "src/components/faq.tsx",
    "src/components/comparison.tsx",
  ];

  it.each(HIGH_RISK)("%s imports from the claim registry", (rel) => {
    const text = readFileSync(join(process.cwd(), rel), "utf8");
    expect(text).toMatch(/from "@\/lib\/claims"/);
  });

  it("the pilot page renders registered sentences, not retyped copies", () => {
    const text = readFileSync(
      join(process.cwd(), "src/app/financial-services-pilot/page.tsx"), "utf8");
    expect(text).toContain('claim("strict-schema-passed")');
    expect(text).toContain('claim("reproduction-not-certified")');
  });

  it("every id referenced by a page actually exists in the registry", () => {
    // A typo would otherwise throw only when that page is rendered.
    const ids = new Set(CLAIMS.map((c) => c.id));
    for (const rel of HIGH_RISK) {
      const text = readFileSync(join(process.cwd(), rel), "utf8");
      for (const m of text.matchAll(/claim\("([a-z0-9-]+)"\)/g)) {
        expect(ids, `${rel} references unknown claim ${m[1]}`).toContain(m[1]);
      }
    }
  });
});

describe("competitor claims", () => {
  it("every row is dated and sourced", () => {
    expect(COMPETITOR_CLAIMS.length).toBeGreaterThan(0);
    for (const c of COMPETITOR_CLAIMS) {
      expect(c.asOf, c.id).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(c.source, c.id).toMatch(/^https:\/\//);
      expect(c.subject.length, c.id).toBeGreaterThan(3);
    }
    expect(COMPETITOR_CLAIMS_AS_OF).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("describes what a competitor does, never what it fails at", () => {
    // A comparison that editorializes invites a correction we cannot win. State the
    // other product's own documented behavior and let the reader compare.
    for (const c of COMPETITOR_CLAIMS) {
      expect(c.text, c.id).not.toMatch(/\b(worse|inferior|unsafe|dangerous|bad)\b/i);
    }
  });

  it("the comparison component renders the sourced footnotes", () => {
    const text = readFileSync(
      join(process.cwd(), "src/components/comparison.tsx"),
      "utf8",
    );
    expect(text).toContain("COMPETITOR_CLAIMS");
    expect(text).toContain("checked ");
  });
});
