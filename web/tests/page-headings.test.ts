import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const APP = join(process.cwd(), "src", "app");

function pageFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) return pageFiles(full);
    return entry.name === "page.tsx" ? [full] : [];
  });
}

describe("page heading contract", () => {
  for (const file of pageFiles(APP)) {
    const route = relative(APP, file).replaceAll("\\", "/");

    it(`${route} declares one primary heading`, () => {
      const source = readFileSync(file, "utf8");
      if (route === "page.tsx") {
        expect(source).toContain("<Hero />");
        return;
      }

      expect(source).toMatch(/<SectionHeader\s+as="h1"/);
    });
  }
});
