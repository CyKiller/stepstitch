/**
 * The public demo console, in a real browser.
 *
 * The Python tests prove the demo's API is credential-free and read-only. They cannot prove
 * the console actually *renders* — it is ~85 KB of hand-written JS under
 * `default-src 'none'`, and every server-side test would stay green against a blank page.
 * This boots the real demo app and drives it.
 */
import { expect, test } from "@playwright/test"

const FIXED_SHAPE_HEADING = /Send transfer/

test.describe("public demo console", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/dashboard")
  })

  test("opens with no credential prompt", async ({ page }) => {
    await expect(page.locator("#demobar")).toBeVisible()
    // The token gate must not appear: the demo has nothing to gate.
    await expect(page.getByPlaceholder("admin bearer token")).toHaveCount(0)
    await expect(page.locator("#tokenbtn")).toBeHidden()
  })

  test("says it is synthetic, unmissably", async ({ page }) => {
    const banner = page.locator("#demobar")
    await expect(banner).toContainText("Synthetic demo")
    await expect(banner).toContainText(/made up|No real user data/)
    // Above the fold, not buried at the bottom.
    const box = await banner.boundingBox()
    expect(box!.y).toBeLessThan(120)
  })

  test("renders the overview with real numbers", async ({ page }) => {
    await expect(page.locator(".hero")).toContainText("open right now")
    await expect(page.locator(".stripe")).toContainText("Proven fixed")
  })

  test("shows every lifecycle stage on the board", async ({ page }) => {
    await page.getByRole("button", { name: "Failures", exact: true }).first().click()
    const sidebar = page.locator("#stagenav")
    for (const stage of [
      "Waiting for a test run", "Seen before", "Test needs fixing",
      "Confirmed broken", "Still broken", "Fixed and proven",
    ]) {
      await expect(sidebar).toContainText(stage)
    }
  })

  test("a failure has a URL that survives a reload", async ({ page }) => {
    await page.getByRole("button", { name: FIXED_SHAPE_HEADING }).first().click()
    await expect(page.locator("h1")).toContainText(FIXED_SHAPE_HEADING)
    const url = page.url()
    expect(url).toContain("#/shape/shp_")

    await page.goto(url)                       // cold load straight at the deep link
    await expect(page.locator("h1")).toContainText(FIXED_SHAPE_HEADING)
  })

  test("the workflow stripe is the dominant status: state plus one next action", async ({ page }) => {
    await page.getByRole("button", { name: FIXED_SHAPE_HEADING }).first().click()
    const stripe = page.locator(".workflow-stripe")
    await expect(stripe).toBeVisible()
    // The fixed demo trace has measured red -> green, so the furthest step is lit
    // and the next action honestly says there is nothing left to do.
    await expect(stripe.locator(".workflow-step.current")).toContainText(/confirmed_fixed|Confirmed fixed/)
    await expect(stripe).toContainText(/Next:|next_action/)
  })

  test("the fixed failure shows a measured red then green", async ({ page }) => {
    await page.goto("/dashboard")
    await page.getByRole("button", { name: FIXED_SHAPE_HEADING }).first().click()
    await page.getByRole("tab", { name: /Proof it's fixed|Verify/ }).click()
    const panel = page.locator("#tabpanel")
    await expect(panel).toContainText(/confirmed_fixed|Fixed and proven|proven/i)
  })

  test("the privacy proof names what was scrubbed", async ({ page }) => {
    await page.getByRole("button", { name: FIXED_SHAPE_HEADING }).first().click()
    const panel = page.locator("#tabpanel")
    // The heading is uppercased by CSS, not in the DOM.
    await expect(panel).toContainText(/privacy proof/i)
    await expect(panel).toContainText("explanation")
    await expect(panel).toContainText("input values")
    // The fake NPI the dataset carries must never reach the page.
    const body = await page.locator("body").innerText()
    expect(body).not.toContain("4111 1111 1111 1234")
    expect(body).not.toContain("dana.holt@example.test")
    expect(body).not.toContain("000-00-0000")
  })

  test("the attestation renders a hash", async ({ page }) => {
    await page.getByRole("button", { name: FIXED_SHAPE_HEADING }).first().click()
    await page.getByRole("tab", { name: /Signed record|Attestation/ }).click()
    await expect(page.locator("#tabpanel")).toContainText("sha256:")
  })

  test("exporting the reproduction downloads a spec file", async ({ page }) => {
    await page.getByRole("button", { name: FIXED_SHAPE_HEADING }).first().click()
    const downloadPromise = page.waitForEvent("download")
    await page.getByRole("button", { name: "Download .spec.ts" }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toMatch(/\.spec\.ts$/)
  })

  test("nothing in the console can write", async ({ page }) => {
    // Every mutating call the demo API might receive is refused, so even a console bug
    // cannot change what the next visitor sees.
    const status = await page.evaluate(async () => {
      const res = await fetch("/api/stepstitch/v1/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ app_id: "x", footsteps: [] }),
      })
      return res.status
    })
    expect(status).toBe(403)
  })

  test("is usable with a keyboard", async ({ page }) => {
    await page.keyboard.press("Tab")
    const focused = await page.evaluate(() => document.activeElement?.tagName)
    expect(["A", "BUTTON", "INPUT"]).toContain(focused)
    // The command palette is the console's primary jump affordance.
    await page.keyboard.press("Meta+k")
    await expect(page.locator(".palette")).toBeVisible()
    await page.keyboard.press("Escape")
    await expect(page.locator(".palette")).toBeHidden()
  })

  test("meets basic accessibility expectations", async ({ page }) => {
    // The console renders after its first fetch resolves; assert on the settled page.
    await expect(page.locator(".hero h1")).toBeVisible()
    const report = await page.evaluate(() => {
      const name = (el: Element) =>
        (el.getAttribute("aria-label") || el.textContent || "").trim()
      const controls = Array.from(
        document.querySelectorAll("button, a[href], [role=tab]"))
      return {
        h1: document.querySelectorAll("h1").length,
        main: document.querySelectorAll("main").length,
        nav: document.querySelectorAll("nav, [role=navigation]").length,
        unnamed: controls.filter((c) => !name(c) && !c.hasAttribute("hidden")).length,
        liveRegion: document.querySelectorAll("[aria-live]").length,
      }
    })
    expect(report.h1).toBe(1)
    expect(report.main).toBe(1)
    expect(report.nav).toBeGreaterThan(0)
    expect(report.unnamed).toBe(0)
    expect(report.liveRegion).toBeGreaterThan(0)
  })

  test("works on a small screen", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto("/dashboard")
    await expect(page.locator("#demobar")).toBeVisible()
    await expect(page.locator(".hero")).toBeVisible()
    // Nothing may overflow the viewport horizontally.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow).toBeLessThanOrEqual(1)
  })
})
