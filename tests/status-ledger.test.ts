import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// Guards the SDK row of the Gates table in docs/STATUS.md, and — more importantly —
// guards the guard list itself.
//
// The Gates table has always claimed four suites, but only Service and Host were ever
// verified. The Web row drifted to 101 against an actual 148 and nothing failed, because
// the enforcement was an allowlist of rows somebody had to remember to extend. That is
// the third time this release that a check enumerated part of its own surface: first the
// copy scanner enumerated phrases, then it enumerated 11 of 52 files, now this. So the
// second test below inverts the default — every row in the table must name a guard that
// exists, and every guard must still correspond to a row.

const REPO_ROOT = process.cwd();
const STATUS = join(REPO_ROOT, "docs", "STATUS.md");

/** Each suite in the Gates table and the file that verifies its count. */
const GUARDS: Record<string, string> = {
  Service: "service/tests/test_status_ledger.py",
  Host: "server/tests/test_status_ledger_host.py",
  SDK: "tests/status-ledger.test.ts",
  Web: "web/tests/status-ledger.test.ts",
};

function doc(): string {
  return readFileSync(STATUS, "utf8");
}

/** The number the Gates table claims for a suite. */
function statedCount(label: string): number {
  const row = doc().match(new RegExp(String.raw`^\|\s*${label}\b[^|]*\|\s*\*\*(\d+)\*\*`, "m"));
  if (!row?.[1]) throw new Error(`no Gates row for ${label} in docs/STATUS.md`);
  return Number(row[1]);
}

/** The suite label of every data row in the Gates table, e.g. "Service", "Web". */
function gatesRowLabels(): string[] {
  const section = doc().split(/^## /m).find((s) => s.startsWith("Gates"));
  if (!section) throw new Error("docs/STATUS.md has no '## Gates' section");
  return section
    .split("\n")
    .filter((line) => line.startsWith("|") && /\*\*\d+\*\*/.test(line))
    .map((line) => (line.split("|")[1] ?? "").split(" (")[0]?.trim() ?? "");
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
  const bin = join(REPO_ROOT, "node_modules", ".bin", process.platform === "win32" ? "vitest.cmd" : "vitest");
  const proc = spawnSync(bin, ["list"], { cwd: REPO_ROOT, encoding: "utf8", timeout: 150_000 });
  // Gate on the exit code, never on a substring of stdout — every collected test id is
  // printed, and plenty of them contain words like "error" or "fail", so a substring
  // check matches always and silently passes.
  if (proc.status !== 0) {
    const tail = `${proc.stdout ?? ""}${proc.stderr ?? ""}`.slice(-300);
    return { count: 0, failure: `cannot collect here (status=${proc.status}): ${tail}` };
  }
  return { count: proc.stdout.split("\n").filter((line: string) => line.trim() !== "").length };
}

describe("docs/STATUS.md states the real SDK test count", () => {
  it("matches what vitest collects at the repo root", (ctx) => {
    const { count, failure } = collectedCount();
    if (failure) {
      ctx.skip(failure);
      return;
    }
    expect(
      statedCount("SDK"),
      `docs/STATUS.md says the SDK suite has ${statedCount("SDK")} tests; vitest collects ${count}. Update the Gates table.`,
    ).toBe(count);
  }, 180_000);
});

describe("every row of the Gates table is actually guarded", () => {
  it("names a guard that exists for each suite, and no guard without a row", () => {
    const rows = gatesRowLabels();
    expect(rows.length, "the Gates table lost its rows").toBeGreaterThanOrEqual(4);

    const unguarded = rows.filter((label) => !GUARDS[label]);
    expect(unguarded, `Gates rows with no count guard: ${unguarded.join(", ")}. Add one — a row nobody verifies is how the Web row reached 101 against an actual 148.`).toEqual([]);

    const missingFiles = Object.entries(GUARDS)
      .filter(([, path]) => !existsSync(join(REPO_ROOT, path)))
      .map(([label, path]) => `${label} -> ${path}`);
    expect(missingFiles, `guards named here but absent from the repo: ${missingFiles.join(", ")}`).toEqual([]);

    // Rot check: a guard listed for a suite the table no longer has is dead weight that
    // makes coverage look broader than it is.
    const orphaned = Object.keys(GUARDS).filter((label) => !rows.includes(label));
    expect(orphaned, `guards for suites the Gates table no longer lists: ${orphaned.join(", ")}`).toEqual([]);
  });
});
