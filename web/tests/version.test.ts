import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { RELEASE_VERSION, RELEASE_TAG } from "../src/lib/version";
import { LATEST_RELEASE_URL, RELEASES_URL } from "../src/lib/links";

// The site names the shipped version in the footer. That literal used to be hand-written and
// went stale the moment a release landed (it still read v0.6.0 while 0.7.0 was cutting). It is
// now bumped by release-please via the `extra-files` list, and these tests are the thing that
// proves the wiring still holds — a rename or a reflowed marker comment breaks them loudly.
const REPO_ROOT = join(process.cwd(), "..");

function readJson(relativePath: string): Record<string, unknown> {
  return JSON.parse(readFileSync(join(REPO_ROOT, relativePath), "utf8"));
}

describe("the released version is single-sourced", () => {
  it("matches the release-please manifest", () => {
    const manifest = readJson(".release-please-manifest.json");
    expect(RELEASE_VERSION).toBe(manifest["."]);
  });

  it("matches the root package.json", () => {
    expect(RELEASE_VERSION).toBe(readJson("package.json").version);
  });

  it("is registered in release-please extra-files, so it is bumped automatically", () => {
    const config = readJson("release-please-config.json") as {
      packages: Record<string, { "extra-files"?: string[] }>;
    };
    expect(config.packages["."]["extra-files"]).toContain("web/src/lib/version.ts");
  });

  it("keeps the release-please marker on the version line", () => {
    // release-please matches `x-release-please-version` on the SAME line as the literal.
    // Reflowing that line silently stops the bump without failing any build.
    const source = readFileSync(join(REPO_ROOT, "web/src/lib/version.ts"), "utf8");
    const marked = source
      .split("\n")
      .filter((l) => l.includes("x-release-please-version") && !l.trimStart().startsWith("//"));
    expect(marked).toHaveLength(1);
    expect(marked[0]).toContain(`"${RELEASE_VERSION}"`);
  });
});

describe("release links derive from that single source", () => {
  it("tags the version with a v prefix", () => {
    expect(RELEASE_TAG).toBe(`v${RELEASE_VERSION}`);
  });

  it("points the latest-release link at the current tag", () => {
    expect(LATEST_RELEASE_URL).toBe(`${RELEASES_URL}/tag/${RELEASE_TAG}`);
  });

  it("hardcodes no version in the components that display one", () => {
    for (const file of ["src/components/footer.tsx"]) {
      const source = readFileSync(join(process.cwd(), file), "utf8");
      expect(source).not.toMatch(/v?\d+\.\d+\.\d+/);
    }
  });
});
