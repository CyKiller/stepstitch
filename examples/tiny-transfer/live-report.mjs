/**
 * Drive TinyTransfer in a real Chromium and report the bug through the REAL
 * tracker SDK — the browser half of the live financial loop
 * (scripts/live_financial_loop.py). Not a test file: it emits a JSON result on
 * stdout for the orchestrator to assert on.
 *
 *   node live-report.mjs http://127.0.0.1:<app-port>
 *
 * Opens the strict variant of the page (?strict=1 → no free-text explanation,
 * because the financial-services-strict profile hard-rejects free text), grants
 * consent without focusing form fields (so the trace needs no input fixtures),
 * triggers the 500, and lets the SDK submit through the same-origin /ingest
 * proxy. Captures the LITERAL request body that left the browser so the
 * orchestrator can prove no form value was on the wire.
 */
import { chromium } from "@playwright/test"

const APP = process.argv[2]
if (!APP) {
  console.error("usage: node live-report.mjs <app-url>")
  process.exit(2)
}

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage()

const ingestBodies = []
page.on("request", (req) => {
  if (req.method() === "POST" && new URL(req.url()).pathname === "/ingest") {
    ingestBodies.push(req.postData() ?? "")
  }
})

await page.goto(`${APP}/?strict=1`)

// Grant consent by dispatching the change event directly: clicking the checkbox
// would record click/input footsteps against it, and the reproduction has no
// business replaying a consent interaction.
await page.evaluate(() => {
  const box = document.getElementById("consent")
  box.checked = true
  box.dispatchEvent(new Event("change"))
})

// The form ships prefilled with synthetic values; submit without focusing any
// field so the trace carries no input footsteps (nothing to fixture later).
await page.click('[data-testid="send-transfer"]')

await page.waitForFunction(
  () => /Reported as /.test(document.getElementById("status")?.textContent ?? ""),
  undefined,
  { timeout: 20_000 },
)
const statusText = await page.locator("#status").textContent()
const traceId = /Reported as ([A-Za-z0-9_-]+)/.exec(statusText ?? "")?.[1] ?? null

await browser.close()

process.stdout.write(
  JSON.stringify({ trace_id: traceId, status_text: statusText, ingest_bodies: ingestBodies }),
)
