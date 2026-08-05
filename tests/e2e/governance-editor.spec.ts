/**
 * Governance scrub editor — against a REAL host, not the demo stub.
 *
 * The editor shipped broken for two releases: it POSTed to a PUT route with field
 * names the host never accepted, so "Save scrub policy" silently did nothing — and
 * the browser suite never noticed because it drives the demo console, whose
 * endpoints are a read-only stub. This spec boots a real `stepstitch start` host
 * (SQLite, strict profile, known tokens), drives the editor with clicks, and proves
 * a save actually persists across a full page reload and previews actually redact.
 *
 * The cheap companion layer is server/tests/test_dashboard_contract.py (source-level
 * method + field-name pins); this file is the ground truth.
 */
import { expect, test } from "@playwright/test"
import { spawn, type ChildProcess } from "node:child_process"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"

const HOST_PORT = 8341
const HOST = `http://127.0.0.1:${HOST_PORT}`
const ADMIN_TOKEN = "e2e-governance-admin-token"

let host: ChildProcess
let workDir: string

async function waitForHealthz(): Promise<void> {
  const deadline = Date.now() + 45_000
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${HOST}/healthz`)
      if (res.ok) return
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 300))
  }
  throw new Error("real host never became healthy on " + HOST)
}

test.beforeAll(async () => {
  workDir = fs.mkdtempSync(path.join(os.tmpdir(), "stepstitch-gov-"))
  host = spawn(
    "python3",
    ["-m", "stepstitch_service.cli", "start", "--no-browser",
     "--port", String(HOST_PORT), "--db", path.join(workDir, "gov.db")],
    {
      env: {
        ...process.env,
        PYTHONPATH: "service",
        STEPSTITCH_ADMIN_TOKEN: ADMIN_TOKEN,
        STEPSTITCH_INGEST_TOKEN: "e2e-governance-ingest-token",
        // Strict profile so the deny-by-default allowlist editors render too.
        STEPSTITCH_PROFILE: "financial-services-strict",
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  )
  host.stderr?.on("data", (d) => process.env.CI && process.stderr.write(d))
  await waitForHealthz()
})

test.afterAll(async () => {
  host?.kill("SIGTERM")
  fs.rmSync(workDir, { recursive: true, force: true })
})

async function openGovernance(page: import("@playwright/test").Page) {
  // A COLD load every time: `stepstitch start` pairs the console via
  // /dashboard#ss=<token> (the page adopts the token and strips the fragment),
  // then we navigate like an operator — by clicking the Governance tab.
  await page.goto("about:blank")
  await page.goto(`${HOST}/dashboard#ss=${ADMIN_TOKEN}`)

  // Wait for the READ the view depends on, not for the text it eventually paints.
  // renderGovernance() fetches /admin/config/scrub and /audit before it can draw
  // anything; on a cold CI runner those two round-trips against a just-booted host
  // outran the default 5s expect timeout, and the failure looked like "Scrub policy
  // is missing" rather than "the page had not finished loading". Waiting on the
  // response is deterministic — no sleep, no retry, no flake laundered into a pass.
  const config = page.waitForResponse(
    (r) => r.url().includes("/admin/config/scrub") && r.request().method() === "GET",
    { timeout: 30_000 },
  )
  await page.getByText("Governance").first().click()
  await config
  await expect(page.getByText("Scrub policy").first()).toBeVisible({ timeout: 15_000 })
}

test("a saved pattern survives a full reload — the save actually persists", async ({ page }) => {
  await openGovernance(page)

  await page.getByLabel("pattern label").fill("empid")
  await page.getByLabel("pattern regex").fill("EMP-\\d+")
  await page.getByRole("button", { name: "Add pattern" }).click()
  await expect(page.getByText("empid · EMP-\\d+")).toBeVisible()

  await page.getByLabel("metadata key").fill("internal_note")
  await page.getByRole("button", { name: "Add key" }).click()

  const saved = page.waitForResponse(
    (r) => r.url().includes("/admin/config/scrub") && r.request().method() === "PUT",
  )
  await page.getByRole("button", { name: "Save scrub policy" }).click()
  expect((await saved).status()).toBe(200)

  // The proof the old page could never pass: a cold reload reads it back from the DB.
  await openGovernance(page)
  await expect(page.getByText("empid · EMP-\\d+")).toBeVisible()
  await expect(page.getByText("internal_note")).toBeVisible()
})

test("the preview really redacts through the saved + pending patterns", async ({ page }) => {
  await openGovernance(page)

  // A pending (unsaved) pattern must participate in the preview too — that is the
  // whole point of previewing before saving. Self-contained: does not rely on the
  // previous test's save having happened.
  await page.getByLabel("pattern label").fill("empid")
  await page.getByLabel("pattern regex").fill("EMP-\\d+")
  await page.getByRole("button", { name: "Add pattern" }).click()

  await page.getByLabel("text to preview").fill("employee EMP-12345 reported SSN 000-00-0000")
  await page.getByRole("button", { name: "Preview redaction" }).click()

  const out = page.locator("pre").first()
  await expect(out).toContainText("[redacted:custom:empid]")
  await expect(out).toContainText("[redacted:ssn]")
  await expect(out).not.toContainText("EMP-12345")
  await expect(out).not.toContainText("000-00-0000")
})

test("strict profile renders the deny-by-default allowlist editors and persists them", async ({ page }) => {
  await openGovernance(page)
  await expect(page.getByText("Strict allowlists")).toBeVisible()
  await expect(
    page.getByText("every semantic selector is rejected until you approve specific testids"),
  ).toBeVisible()

  await page.getByLabel("approved testid").fill("transfer-submit")
  await page.getByRole("button", { name: "Approve testid" }).click()
  await page.getByLabel("route template").fill("/accounts/:id")
  await page.getByRole("button", { name: "Declare template" }).click()
  await page.getByRole("button", { name: "Save scrub policy" }).click()

  await openGovernance(page)
  await expect(page.getByText("transfer-submit")).toBeVisible()
  await expect(page.getByText("/accounts/:id")).toBeVisible()
})
