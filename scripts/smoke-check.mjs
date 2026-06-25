#!/usr/bin/env node
/*
 * One-command privacy smoke test for the red-to-green demo bundle.
 *
 * Reads demo/evidence-bundle.json (regenerate it first with `npm run demo`) and asserts the
 * full moat is present AND that no forbidden field or raw placeholder value survived the
 * scrub. Zero dependencies; exits non-zero on any violation so it can gate CI.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const bundlePath = join(root, "demo", "evidence-bundle.json");

let bundle;
try {
  bundle = JSON.parse(readFileSync(bundlePath, "utf8"));
} catch (e) {
  console.error(`smoke: cannot read ${bundlePath} — run \`npm run demo\` first.\n${e.message}`);
  process.exit(1);
}

const failures = [];
const ok = (cond, msg) => { if (!cond) failures.push(msg); };

const s = bundle.steps || {};

// Moat is present.
ok(bundle.demo === true, "bundle.demo is not true");
ok(s["3_privacy_scrub"]?.scrub_status, "missing scrub_status");
ok((s["3_privacy_scrub"]?.scrubbed_fields || []).length > 0, "scrubbed_fields is empty");
ok(typeof s["5_playwright_repro"]?.playwright_code === "string"
  && s["5_playwright_repro"].playwright_code.includes("StepStitch reproduction"),
  "missing Playwright reproduction");
ok(s["7_ci_verification"]?.verdict === "confirmed_fixed",
  `verdict is ${s["7_ci_verification"]?.verdict}, expected confirmed_fixed`);
ok(s["7_ci_verification"]?.pre_passed === false && s["7_ci_verification"]?.post_passed === true,
  "confirmed_fixed must derive from pre_passed=false + post_passed=true");
ok(s["6_drafts"]?.servicenow && s["6_drafts"]?.salesforce, "missing draft previews");

// Sanitized regions must not leak forbidden VALUES. The labeled raw_unsafe_input block is
// the one place placeholder PII is allowed (it exists to show the before-state), so we scan
// everything *except* that block.
const sanitized = JSON.parse(JSON.stringify(bundle));
if (sanitized.steps?.["1_bug_report"]) delete sanitized.steps["1_bug_report"].raw_unsafe_input;
const sanitizedText = JSON.stringify(sanitized);
const FORBIDDEN_VALUES = [
  "PLACEHOLDER", "session=", "Bearer ", "bank.example.test/accounts",
  "user@example.test", "000-00-0000",
];
for (const tok of FORBIDDEN_VALUES) {
  ok(!sanitizedText.includes(tok), `forbidden value leaked into sanitized bundle: ${tok}`);
}

// Forbidden KEYS must never appear in any kept footstep metadata.
const FORBIDDEN_KEYS = ["cookies", "request_body", "response_body", "url", "headers", "raw_url"];
for (const step of s["2_structural_capture"]?.footsteps || []) {
  for (const k of Object.keys(step.metadata || {})) {
    ok(!FORBIDDEN_KEYS.includes(k), `forbidden key '${k}' kept in footstep metadata`);
  }
}

if (failures.length) {
  console.error("smoke FAILED:");
  for (const f of failures) console.error("  ✗ " + f);
  process.exit(1);
}
console.log("smoke OK: privacy gate + red-to-green moat verified in demo/evidence-bundle.json");
