/**
 * Behavioral contract for the tracker: consent gating, privacy signals, buffer cap,
 * teardown, kill switch, and selector/route shaping.
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest"
import { StepStitchTracker } from "../src/tracker"
import { buildSelector, routeTemplate } from "../src/redaction"

let win: Window & typeof globalThis
let doc: Document

beforeEach(() => {
  win = window as unknown as Window & typeof globalThis
  doc = document
  doc.body.innerHTML = `<button id="go">Go</button><a data-testid="next">Next</a>`
})
afterEach(() => {
  doc.body.innerHTML = ""
})

function clickGo() {
  doc.getElementById("go")!.dispatchEvent(new win.Event("click", { bubbles: true }))
}

describe("consent gating", () => {
  it("captures nothing before consent is granted", () => {
    const t = new StepStitchTracker({ doc, win })
    clickGo()
    expect(t.getTrace()).toHaveLength(0)
  })

  it("captures after grantConsent and records an initial navigation", () => {
    const t = new StepStitchTracker({ doc, win })
    t.grantConsent("v1")
    clickGo()
    const types = t.getTrace().map((s) => s.type)
    expect(types).toContain("navigation")
    expect(types).toContain("click")
  })

  it("stops capturing and clears the buffer on revokeConsent", () => {
    const t = new StepStitchTracker({ doc, win })
    t.grantConsent("v1")
    clickGo()
    expect(t.getTrace().length).toBeGreaterThan(0)
    t.revokeConsent()
    expect(t.getTrace()).toHaveLength(0)
    clickGo()
    expect(t.getTrace()).toHaveLength(0)
  })
})

describe("privacy signals", () => {
  it("suppresses capture when Global Privacy Control is set", () => {
    const gpcWin = {
      ...win,
      navigator: { ...win.navigator, globalPrivacyControl: true },
    } as unknown as Window & typeof globalThis
    const t = new StepStitchTracker({ doc, win: gpcWin })
    t.grantConsent("v1")
    clickGo()
    expect(t.getTrace()).toHaveLength(0)
  })

  it("suppresses capture when Do Not Track is enabled", () => {
    const dntWin = {
      ...win,
      navigator: { ...win.navigator, doNotTrack: "1" },
    } as unknown as Window & typeof globalThis
    const t = new StepStitchTracker({ doc, win: dntWin })
    t.grantConsent("v1")
    clickGo()
    expect(t.getTrace()).toHaveLength(0)
  })

  it("submitTrace is a no-op under a privacy signal", async () => {
    const gpcWin = {
      ...win,
      navigator: { ...win.navigator, globalPrivacyControl: true },
      fetch: async () => ({ json: async () => ({ trace_id: "x" }) }) as Response,
    } as unknown as Window & typeof globalThis
    const t = new StepStitchTracker({ doc, win: gpcWin, ingestEndpoint: "/api/x" })
    t.grantConsent("v1")
    const res = await t.submitTrace("hi")
    expect(res.submitted).toBe(false)
    expect(res.reason).toBe("privacy-signal")
  })
})

describe("buffer + lifecycle", () => {
  it("caps the ring buffer at maxFootsteps", () => {
    const t = new StepStitchTracker({ doc, win, maxFootsteps: 5 })
    t.grantConsent("v1")
    for (let i = 0; i < 20; i++) clickGo()
    expect(t.getTrace().length).toBeLessThanOrEqual(5)
  })

  it("destroy() removes listeners so later events are ignored", () => {
    const t = new StepStitchTracker({ doc, win })
    t.grantConsent("v1")
    t.destroy()
    clickGo()
    expect(t.getTrace()).toHaveLength(0)
  })

  it("disable() is a permanent kill switch", () => {
    const t = new StepStitchTracker({ doc, win })
    t.grantConsent("v1")
    t.disable()
    t.grantConsent("v1") // ignored after kill
    clickGo()
    expect(t.getTrace()).toHaveLength(0)
  })

  it("submitTrace requires consent and an endpoint", async () => {
    const noConsent = new StepStitchTracker({ doc, win })
    expect((await noConsent.submitTrace()).reason).toBe("no-consent")

    const noEndpoint = new StepStitchTracker({ doc, win })
    noEndpoint.grantConsent("v1")
    clickGo()
    expect((await noEndpoint.submitTrace()).reason).toBe("no-endpoint")
  })
})

describe("selector + route shaping", () => {
  it("prefers data-testid, then id, then a structural path", () => {
    expect(buildSelector(doc.querySelector('[data-testid="next"]')!)).toBe(
      '[data-testid="next"]',
    )
    expect(buildSelector(doc.getElementById("go")!)).toBe("#go")
  })

  it("templates ID-like segments and drops query strings", () => {
    expect(routeTemplate("/accounts/8675309?ssn=1")).toBe("/accounts/:id")
    expect(routeTemplate("/u/550e8400-e29b-41d4-a716-446655440000")).toBe("/u/:id")
    expect(routeTemplate("/dashboard")).toBe("/dashboard")
    expect(routeTemplate("/")).toBe("/")
  })
})
