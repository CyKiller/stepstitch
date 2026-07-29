import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  DOCKER_DOCTOR,
  DOCKER_SEED,
  DOCKER_UP,
  MANUAL_HOST,
  OFFLINE_DEMO,
  SDK_INSTALL,
} from "@/lib/quickstart-commands";

// The quickstart page renders these exact commands; this test asserts the repository
// README documents the same sequences verbatim, so a stranger copying from either place
// runs identical commands. Multiline blocks are compared line by line because the README
// wraps them in its own fences.

const readme = readFileSync(join(process.cwd(), "..", "README.md"), "utf8");

function linesOf(block: string): string[] {
  return block
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}

describe("README and website quickstart cannot drift", () => {
  it("documents the SDK install", () => {
    expect(readme).toContain(SDK_INSTALL);
  });

  it("documents the offline demo sequence, line for line", () => {
    for (const line of linesOf(OFFLINE_DEMO)) {
      expect(readme, `README is missing offline-demo line: ${line}`).toContain(line);
    }
  });

  it("documents the Docker path, including the in-container doctor", () => {
    expect(readme).toContain(DOCKER_UP);
    expect(readme).toContain(DOCKER_DOCTOR);
    for (const line of linesOf(DOCKER_SEED)) {
      expect(readme, `README is missing seed line: ${line}`).toContain(line);
    }
  });

  it("documents the manual path in a working order", () => {
    const manualLines = linesOf(MANUAL_HOST);
    for (const line of manualLines) {
      expect(readme, `README is missing manual-path line: ${line}`).toContain(line);
    }
    // Install must appear before uvicorn in the README text itself.
    expect(readme.indexOf("pip install ./service")).toBeLessThan(
      readme.indexOf("uvicorn server.app:app"),
    );
  });

  it("never documents doctor on the host shell after Compose", () => {
    // The old broken instruction: doctor outside the container cannot see Compose env.
    expect(readme).not.toContain("pip install ./service && stepstitch doctor");
  });

  it("never documents seeding without the required variables", () => {
    expect(readme).not.toMatch(/^node scripts\/seed-demo-trace\.mjs/m);
  });

  it("the quickstart page renders from the shared command module", () => {
    const page = readFileSync(
      join(process.cwd(), "src", "app", "quickstart", "page.tsx"),
      "utf8",
    );
    expect(page).toContain('from "@/lib/quickstart-commands"');
    // No hand-typed duplicate of a shared command inside the page.
    expect(page).not.toContain("docker compose exec stepstitch");
  });
});
