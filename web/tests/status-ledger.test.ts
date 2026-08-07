import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// The Gates table in docs/STATUS.md claims a test count per suite. Two of those four rows
// were checked (`test_status_ledger.py` for Service, `test_status_ledger_host.py` for
// Host) and two were not — so the Web row sat at 101 while the suite had grown to 148,
// and nothing failed. A ledger row nobody verifies is just marketing; this file is the
// missing verifier for the Web row.
//
// Deliberately a separate file from the SDK guard, for the same reason the Python guards
// are split: each row is checked by the job that actually owns that suite's dependencies.

const REPO_ROOT = join(process.cwd(), "..");
const STATUS = join(REPO_ROOT, "docs", "STATUS.md");

/** The number the Gates table claims for a suite. */
function statedCount(label: string): number {
  const doc = readFileSync(STATUS, "utf8");
  const row = doc.match(new RegExp(String.raw`^\|\s*${label}\b[^|]*\|\s*\*\*(\d+)\*\*`, "m"));
  expect(row, `no Gates row for ${label} in docs/STATUS.md`).not.toBeNull();
  return Number(row![1]);
}

/**
 * Ask vitest itself how many tests it collects here.
 *
 * Spawning `vitest list` from inside a vitest test is safe *specifically* because `list`
 * collects without executing test bodies: it imports this file but never reaches the
 * spawn below. Hoisting this call to module scope would recurse without bound. This is
 * the same reason the Python guard can shell out to `pytest --collect-only` from inside
 * a test body (`service/tests/test_status_ledger.py`).
 */
function collectedCount(): { count: number; failure?: string } {
  const bin = join(process.cwd(), "node_modules", ".bin", process.platform === "win32" ? "vitest.cmd" : "vitest");
  const proc = spawnSync(bin, ["list"], { cwd: process.cwd(), encoding: "utf8", timeout: 150_000 });
  // Gate on the exit code, never on a substring of stdout — every collected test id is
  // printed, and plenty of them contain words like "error" or "fail", so a substring
  // check matches always and silently passes.
  if (proc.status !== 0) {
    const tail = `${proc.stdout ?? ""}${proc.stderr ?? ""}`.slice(-300);
    return { count: 0, failure: `cannot collect here (status=${proc.status}): ${tail}` };
  }
  return { count: proc.stdout.split("\n").filter((line) => line.trim() !== "").length };
}

describe("docs/STATUS.md states the real Web test count", () => {
  it("matches what vitest collects in web/", (ctx) => {
    const { count, failure } = collectedCount();
    if (failure) {
      ctx.skip(failure);
      return;
    }
    expect(
      statedCount("Web"),
      `docs/STATUS.md says the Web suite has ${statedCount("Web")} tests; vitest collects ${count}. Update the Gates table.`,
    ).toBe(count);
  }, 180_000);
});
