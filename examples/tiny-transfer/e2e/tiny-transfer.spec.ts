/**
 * TinyTransfer end-to-end — the privacy claims, checked against the actual bytes.
 *
 * Hermetic: no Python service, no database, no network. A stub HTTP server stands in for the
 * StepStitch host and keeps every payload it receives, so the assertions run against exactly
 * what left the browser rather than against a description of it.
 *
 * The load-bearing test is `no captured payload contains any value from the form`. It scans
 * the raw JSON for each fake value, so a regression anywhere in the SDK — a new field, a
 * changed selector strategy, an accidental label — fails here rather than in production.
 */
import { spawn, type ChildProcess } from "node:child_process"
import { createServer, type Server } from "node:http"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

import { expect, test } from "@playwright/test"

const HERE = dirname(fileURLToPath(import.meta.url))
const APP_PORT = 4319
const STUB_PORT = 4320
const APP_URL = `http://localhost:${APP_PORT}`

// The exact values the form submits. None may ever appear in a captured payload.
const RECIPIENT_ACCOUNT = "4111 1111 1111 1234"
const AMOUNT = "250.00"
const EMAIL = "dana.holt@example.test"
const SYNTHETIC_QUERY = "FAKE-QUERY-SECRET-123"

let app: ChildProcess
let stub: Server
let received: any[] = []

async function waitFor(url: string, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url)
      if (res.ok) return
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 150))
  }
  throw new Error(`timed out waiting for ${url}`)
}

test.beforeAll(async () => {
  // The stand-in StepStitch host: accept anything, remember everything.
  stub = createServer((req, res) => {
    const chunks: Buffer[] = []
    req.on("data", (c) => chunks.push(c))
    req.on("end", () => {
      const body = Buffer.concat(chunks).toString("utf8")
      try {
        received.push(JSON.parse(body))
      } catch {
        received.push({ unparsed: body })
      }
      res.writeHead(200, { "Content-Type": "application/json" })
      res.end(JSON.stringify({ status: "ok", trace_id: `trc_stub_${received.length}` }))
    })
  })
  await new Promise<void>((resolve) => stub.listen(STUB_PORT, resolve))

  app = spawn("node", [join(HERE, "..", "server.mjs")], {
    env: {
      ...process.env,
      PORT: String(APP_PORT),
      STEPSTITCH_HOST: `http://localhost:${STUB_PORT}`,
      STEPSTITCH_INGEST_TOKEN: "stub-ingest-token",
    },
    stdio: "ignore",
  })
  await waitFor(`${APP_URL}/__bug`)
})

test.afterAll(async () => {
  app?.kill()
  await new Promise<void>((resolve) => stub.close(() => resolve()))
})

test.beforeEach(async ({ page }) => {
  received = []
  await fetch(`${APP_URL}/__bug`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active: true }),
  })
  await page.goto(APP_URL)
})

// --- consent ---------------------------------------------------------------------------

test("consent starts off", async ({ page }) => {
  await expect(page.getByTestId("consent-toggle")).not.toBeChecked()
  await expect(page.locator("#consent-state")).toHaveText(/capture off/)
})

test("nothing is captured before consent is granted", async ({ page }) => {
  await page.getByTestId("recipient-account").fill("9999 8888 7777 6666")
  await page.getByTestId("send-transfer").click()
  await expect(page.locator("#status")).toContainText("consent is off")
  // A failed transfer, a filled field, a click — and still no payload.
  expect(received).toHaveLength(0)
})

test("revoking consent stops capture again", async ({ page }) => {
  await page.getByTestId("consent-toggle").check()
  await page.getByTestId("consent-toggle").uncheck()
  await expect(page.locator("#consent-state")).toHaveText(/buffer cleared/)
  await page.getByTestId("send-transfer").click()
  await expect(page.locator("#status")).toContainText("consent is off")
  expect(received).toHaveLength(0)
})

// --- the failure ---------------------------------------------------------------------------

test("the transfer really returns HTTP 500", async ({ request }) => {
  const res = await request.post(`${APP_URL}/api/accounts/8842/transfer`, { data: {} })
  expect(res.status()).toBe(500)
})

test("a failure after consent is reported through the app's own server", async ({ page }) => {
  await page.getByTestId("consent-toggle").check()
  await page.getByTestId("send-transfer").click()
  await expect(page.locator("#status")).toContainText("Reported as trc_stub_")
  expect(received).toHaveLength(1)

  const payload = received[0]
  expect(payload.app_id).toBe("tiny-transfer")
  expect(payload.consent_version).toBe("tiny-transfer-v1")
  expect(payload.footsteps.length).toBeGreaterThan(0)
})

test("the captured evidence is structural", async ({ page }) => {
  await page.getByTestId("consent-toggle").check()
  await page.getByTestId("recipient-account").click()
  await page.getByTestId("transfer-amount").click()
  await page.getByTestId("send-transfer").click()
  await expect(page.locator("#status")).toContainText("Reported as")

  const footsteps = received[0].footsteps
  const types = footsteps.map((f: any) => f.type)
  expect(types).toContain("api_error")

  const apiError = footsteps.find((f: any) => f.type === "api_error")
  expect(apiError.metadata.status).toBe(500)
  expect(apiError.metadata.method).toBe("POST")
  // Templated route, not the concrete account id.
  expect(apiError.metadata.endpoint).toBe("/api/accounts/:id/transfer")
  expect(apiError.metadata.endpoint).not.toContain("8842")
})

// --- the privacy claims (the reason this example exists) ---------------------------------

test("the captured evidence contains no value from the form", async ({ page }) => {
  await page.getByTestId("consent-toggle").check()
  // Touch every field so each produces an input footstep.
  await page.getByTestId("recipient-account").click()
  await page.getByTestId("transfer-amount").click()
  await page.getByTestId("contact-email").click()
  await page.getByTestId("send-transfer").click()
  await expect(page.locator("#status")).toContainText("Reported as")

  // Everything the SDK *observed*: footsteps and payload metadata. The explanation is
  // excluded here deliberately — it is free text a human typed, and it gets its own test
  // below, because it is scrubbed at a different boundary.
  const { explanation, ...observed } = received[0]
  const raw = JSON.stringify(observed)

  expect(raw).not.toContain(RECIPIENT_ACCOUNT)
  expect(raw).not.toContain(RECIPIENT_ACCOUNT.replace(/ /g, ""))
  expect(raw).not.toContain(EMAIL)
  expect(raw).not.toContain("dana.holt")
  expect(raw).not.toContain(`"${AMOUNT}"`)
  // The query parameter — proof that URLs are stripped, not merely shortened.
  expect(raw).not.toContain(SYNTHETIC_QUERY)
  expect(raw).not.toContain("sessionRef")
  // The concrete account id from the URL path.
  expect(raw).not.toContain("8842")
})

test("free text the user typed is left for the SERVER to scrub", async ({ page }) => {
  /**
   * This is the boundary that matters, and the one most easily misunderstood.
   *
   * The SDK never *reads* an input, so no typed value can reach it by accident. But the
   * explanation is different: the user deliberately hands it over, and it routinely contains
   * exactly the data you least want stored — here an account number, an email and an SSN.
   *
   * The SDK does not redact it, and pretending otherwise would be the dangerous design: a
   * client-side scrubber can be bypassed by anyone willing to POST their own JSON. Redaction
   * happens server-side in scrubber.py, on every payload, before storage — which is why that
   * is called the final trust boundary. Run `npm run verify` against a real host and the
   * stored explanation comes back with those values replaced.
   */
  await page.getByTestId("consent-toggle").check()
  await page.getByTestId("send-transfer").click()
  await expect(page.locator("#status")).toContainText("Reported as")

  const explanation: string = received[0].explanation
  expect(explanation).toContain(RECIPIENT_ACCOUNT)   // arrives intact…
  expect(explanation).toContain("000-00-0000")       // …including the obvious ones…
  // …and the structural evidence beside it is still clean.
  expect(JSON.stringify(received[0].footsteps)).not.toContain(RECIPIENT_ACCOUNT)
})

test("input footsteps record that a field was used, never what was typed", async ({ page }) => {
  await page.getByTestId("consent-toggle").check()
  await page.getByTestId("recipient-account").click()
  await page.getByTestId("transfer-amount").click()   // blur the previous field
  await page.getByTestId("send-transfer").click()
  await expect(page.locator("#status")).toContainText("Reported as")

  const inputs = received[0].footsteps.filter((f: any) => f.type === "input")
  expect(inputs.length).toBeGreaterThan(0)
  for (const step of inputs) {
    expect(step.metadata).toEqual({ interacted: true })
    expect(step.label).toBe("[masked]")
    expect(JSON.stringify(step)).not.toContain(RECIPIENT_ACCOUNT)
  }
})

test("no screenshots, page text, bodies, headers or cookies are ever sent", async ({ page }) => {
  await page.getByTestId("consent-toggle").check()
  await page.getByTestId("send-transfer").click()
  await expect(page.locator("#status")).toContainText("Reported as")

  const raw = JSON.stringify(received).toLowerCase()
  for (const forbidden of [
    "screenshot", "dom_snapshot", "innerhtml", "page_text", "request_body",
    "response_body", "headers", "cookie", "set-cookie", "console", "stack",
  ]) {
    expect(raw).not.toContain(forbidden)
  }
})

test("the ingest token never reaches the browser", async ({ page }) => {
  // It lives in server.mjs. Nothing the page can load should contain it.
  const appJs = await (await fetch(`${APP_URL}/app.js`)).text()
  const html = await (await fetch(APP_URL)).text()
  for (const source of [appJs, html]) {
    expect(source).not.toContain("stub-ingest-token")
    expect(source).not.toContain("Authorization")
  }
  const leaked = await page.evaluate(() =>
    JSON.stringify({ ls: { ...localStorage }, ss: { ...sessionStorage } }))
  expect(leaked).not.toContain("stub-ingest-token")
})

// --- red to green -------------------------------------------------------------------------

test("applying the fix turns 500 into 200", async ({ page, request }) => {
  const before = await request.post(`${APP_URL}/api/accounts/8842/transfer`, { data: {} })
  expect(before.status()).toBe(500)

  await page.getByTestId("apply-fix").click()
  await expect(page.locator("#bug-state")).toHaveText(/fixed/)

  const after = await request.post(`${APP_URL}/api/accounts/8842/transfer`, { data: {} })
  expect(after.status()).toBe(200)

  await page.getByTestId("reset-bug").click()
  await expect(page.locator("#bug-state")).toHaveText(/bug active/)
})

test("a successful transfer reports nothing", async ({ page }) => {
  await page.getByTestId("consent-toggle").check()
  await page.getByTestId("apply-fix").click()
  await expect(page.locator("#bug-state")).toHaveText(/fixed/)
  await page.getByTestId("send-transfer").click()
  await expect(page.locator("#status")).toContainText("Transfer sent")
  // StepStitch is for failures. A working flow is not evidence of anything.
  expect(received).toHaveLength(0)
})
