import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  DOCKER_DOCTOR,
  DOCKER_SEED,
  DOCKER_UP,
  MANUAL_HOST_TERMINAL_1,
  MANUAL_HOST_TERMINAL_2,
  OFFLINE_DEMO,
  SDK_INSTALL,
} from "@/lib/quickstart-commands";

// The quickstart page renders these exact commands; this test asserts the repository
// README documents the same sequences verbatim, so a stranger copying from either place
// runs identical commands. Multiline blocks are compared line by line because the README
// wraps them in its own fences. The clean-install CI gate must also run the SAME strings
// it would be pointless to prove a private variation works.

const REPO = join(process.cwd(), "..");
const readme = readFileSync(join(REPO, "README.md"), "utf8");
const quickstartPage = readFileSync(
  join(process.cwd(), "src", "app", "quickstart", "page.tsx"),
  "utf8",
);
const cleanInstall = readFileSync(
  join(REPO, ".github", "workflows", "clean-install.yml"),
  "utf8",
);

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

  it("documents both manual-path terminals, line for line", () => {
    for (const line of [...linesOf(MANUAL_HOST_TERMINAL_1), ...linesOf(MANUAL_HOST_TERMINAL_2)]) {
      expect(readme, `README is missing manual-path line: ${line}`).toContain(line);
    }
    // Install must appear before uvicorn in the README text itself.
    expect(readme.indexOf("pip install ./service")).toBeLessThan(
      readme.indexOf("uvicorn server.app:app"),
    );
  });

  it("the quickstart page renders from the shared command module", () => {
    expect(quickstartPage).toContain('from "@/lib/quickstart-commands"');
    // No hand-typed duplicate of a shared command inside the page.
    expect(quickstartPage).not.toContain("docker compose exec");
  });
});

describe("commands are literally executable in the order shown", () => {
  it("Docker up detaches, so the next command has a terminal to run in", () => {
    expect(DOCKER_UP).toMatch(/ -d$/);
    // The old foreground form must not survive anywhere as a standalone command line.
    expect(readme).not.toMatch(/^docker compose up --build$/m);
  });

  it("the manual path is two terminals, never 'same shell' after a foreground server", () => {
    // uvicorn holds Terminal 1, so Terminal 2 must rebuild doctor's environment itself.
    expect(MANUAL_HOST_TERMINAL_1).toMatch(/uvicorn server\.app:app --port 8000$/);
    expect(MANUAL_HOST_TERMINAL_2.split("\n")[0]).toBe("source .venv/bin/activate");
    expect(MANUAL_HOST_TERMINAL_2).toMatch(/stepstitch doctor$/);
    for (const required of [
      "DATABASE_URL",
      "STEPSTITCH_INGEST_TOKEN",
      "STEPSTITCH_ADMIN_TOKEN",
      "STEPSTITCH_APP_BASE_URL",
    ]) {
      expect(MANUAL_HOST_TERMINAL_2, `Terminal 2 must export ${required}`).toContain(required);
    }
    // The impossible instruction — run doctor in the shell uvicorn occupies — is banned.
    expect(readme).not.toMatch(/same shell/i);
    expect(quickstartPage).not.toMatch(/same shell/i);
  });

  it("clean-install CI runs the exact documented Docker commands, not private variants", () => {
    expect(cleanInstall).toContain(DOCKER_UP);
    expect(cleanInstall).toContain(DOCKER_DOCTOR);
  });

  it("never documents doctor on the host shell after Compose", () => {
    // The old broken instruction: doctor outside the container cannot see Compose env.
    expect(readme).not.toContain("pip install ./service && stepstitch doctor");
  });

  it("never documents seeding without the required variables", () => {
    expect(readme).not.toMatch(/^node scripts\/seed-demo-trace\.mjs/m);
  });
});
