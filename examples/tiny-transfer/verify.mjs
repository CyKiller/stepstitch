/**
 * The red→green loop, run against a real StepStitch host.
 *
 * This is what your CI does, condensed into one script so you can watch it happen:
 *
 *   1. make sure the bug is active
 *   2. fetch the generated reproduction for a trace
 *   3. run it            -> expected to FAIL   (red: the bug is real)
 *   4. apply the fix
 *   5. run it again      -> expected to PASS   (green: the fix works)
 *   6. post BOTH measured outcomes to /verify  -> StepStitch derives confirmed_fixed
 *
 * Both runs actually happen. Neither outcome is assumed — that is the whole point, and it is
 * why step 6 sends what steps 3 and 5 measured rather than a hardcoded `pre_passed: false`.
 *
 * Usage:
 *   STEPSTITCH_HOST=http://localhost:8000 \
 *   STEPSTITCH_VERIFY_TOKEN=ssa_… \
 *   TRACE_ID=trc_… \
 *   npm run verify
 *
 * The token should be a `verify`-scoped agent token from the console's Agents tab. It can
 * fetch a reproduction and post a verdict, and nothing else. Do not use your admin token.
 */
import { execFileSync } from "node:child_process"
import { mkdirSync, rmSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const HERE = dirname(fileURLToPath(import.meta.url))
const HOST = process.env.STEPSTITCH_HOST || "http://localhost:8000"
const TOKEN = process.env.STEPSTITCH_VERIFY_TOKEN || process.env.STEPSTITCH_ADMIN_TOKEN
const TRACE_ID = process.env.TRACE_ID
const APP = process.env.TINY_TRANSFER_URL || "http://localhost:4173"

if (!TRACE_ID) {
  console.error("TRACE_ID is required — report a failure in the app first, then pass its id.")
  process.exit(2)
}
if (!TOKEN) {
  console.error("STEPSTITCH_VERIFY_TOKEN is required (issue one in the console's Agents tab).")
  process.exit(2)
}

const work = join(HERE, ".verify-run")

async function setBug(active) {
  const res = await fetch(`${APP}/__bug`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active }),
  })
  if (!res.ok) throw new Error(`could not toggle the bug: HTTP ${res.status}`)
  return (await res.json()).active
}

async function fetchReproduction() {
  const res = await fetch(`${HOST}/api/stepstitch/v1/session/${TRACE_ID}/playwright`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
  })
  if (!res.ok) {
    throw new Error(`could not fetch the reproduction: HTTP ${res.status}. ` +
      `Is TRACE_ID right, and does the token have the 'verify' scope?`)
  }
  return (await res.json()).playwright_code
}

/** Run the reproduction and return whether it PASSED. A failure here is data, not an error. */
function runReproduction(label) {
  try {
    execFileSync("npx", ["playwright", "test", "--config", join(work, "config.ts"), "--reporter=line"],
      { cwd: HERE, stdio: "inherit" })
    console.log(`  ${label}: PASSED`)
    return true
  } catch {
    console.log(`  ${label}: FAILED`)
    return false
  }
}

async function main() {
  console.log(`StepStitch host : ${HOST}`)
  console.log(`Application     : ${APP}`)
  console.log(`Trace           : ${TRACE_ID}\n`)

  const code = await fetchReproduction()
  rmSync(work, { recursive: true, force: true })
  mkdirSync(join(work, "tests"), { recursive: true })
  writeFileSync(join(work, "tests", "repro.spec.ts"), code)
  writeFileSync(join(work, "config.ts"),
    `import { defineConfig } from "@playwright/test"\n` +
    `export default defineConfig({ testDir: "./tests", workers: 1, timeout: 30000,\n` +
    `  use: { headless: true, trace: "off" } })\n`)

  console.log("1/2  RED — running the reproduction against the bug")
  await setBug(true)
  const prePassed = runReproduction("pre-fix")

  console.log("\n2/2  GREEN — applying the fix and running it again")
  await setBug(false)
  const postPassed = runReproduction("post-fix")

  console.log("\nReporting the measured outcomes to StepStitch…")
  const res = await fetch(`${HOST}/api/stepstitch/v1/session/${TRACE_ID}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${TOKEN}` },
    body: JSON.stringify({
      pre_passed: prePassed,
      post_passed: postPassed,
      fix_ref: "tiny-transfer-apply-fix",
      run_url: "https://example.test/ci/tiny-transfer/1",
    }),
  })
  if (!res.ok) throw new Error(`/verify returned HTTP ${res.status}: ${await res.text()}`)
  const { verdict } = await res.json()

  console.log(`\n  pre_passed  = ${prePassed}   (false is what we want: the bug was real)`)
  console.log(`  post_passed = ${postPassed}   (true is what we want: the fix works)`)
  console.log(`  verdict     = ${verdict}`)

  rmSync(work, { recursive: true, force: true })
  await setBug(true) // leave the example broken, ready for the next run

  if (verdict !== "confirmed_fixed") {
    console.error(`\nExpected confirmed_fixed. Got ${verdict}.`)
    process.exit(1)
  }
  console.log("\nconfirmed_fixed — the failure shape is now Fixed on the board.")
}

main().catch((err) => {
  // Node's fetch reports transport problems as a bare "fetch failed"; the cause is where
  // the actual reason lives (ECONNREFUSED, DNS, TLS). Printing only the message sends you
  // looking in the wrong place.
  console.error(`\n${err.message}`)
  if (err.cause) console.error(`  cause: ${err.cause.message ?? err.cause}`)
  process.exit(1)
})
