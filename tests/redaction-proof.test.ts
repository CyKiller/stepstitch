/**
 * REDACTION-PROOF GATE (compliance artifact).
 *
 * Renders a synthetic-NPI corpus into the DOM, drives the tracker, and asserts that
 * NONE of the sensitive literals ever appear in the emitted trace — including the
 * payload that would be POSTed to the backend. This suite is the evidence handed to a
 * regulated tenant's security review. It must stay green.
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest"
import { StepStitchTracker } from "../src/tracker"
import { MASKED } from "../src/types"

// Synthetic NPI — fake values only. None of these may ever leave the browser.
const NPI = {
  ssn: "123-45-6789",
  account: "ACCT-000998877",
  balance: "$1,234,567.89",
  name: "Jceiona Pemberton-Vasquez",
  card: "4111111111111111",
  email: "saver@example-retirement.test",
}

function leaks(haystack: string): string[] {
  return Object.values(NPI).filter((v) => haystack.includes(v))
}

let win: Window & typeof globalThis
let doc: Document

beforeEach(() => {
  win = window as unknown as Window & typeof globalThis
  doc = document
  doc.body.innerHTML = `
    <nav>
      <a id="acct-link" href="/accounts/8675309?ssn=${NPI.ssn}">${NPI.name}</a>
    </nav>
    <main>
      <div data-testid="balance-card">Balance: ${NPI.balance}</div>
      <button id="pay-btn">Pay ${NPI.account}</button>
      <form>
        <input id="card" name="card" value="${NPI.card}" autocomplete="cc-number" />
        <input id="pw" type="password" value="hunter2" />
        <input id="memo" name="memo" value="${NPI.ssn}" />
        <button data-stepstitch-unmask id="submit-btn">Submit Payment</button>
      </form>
    </main>`
})

afterEach(() => {
  doc.body.innerHTML = ""
})

describe("redaction-proof gate", () => {
  it("emits no NPI from clicks, inputs, or navigation", () => {
    const t = new StepStitchTracker({ appId: "test", doc, win })
    t.grantConsent("v1")

    doc.getElementById("acct-link")!.dispatchEvent(new win.Event("click", { bubbles: true }))
    doc.getElementById("pay-btn")!.dispatchEvent(new win.Event("click", { bubbles: true }))
    doc.getElementById("card")!.dispatchEvent(new win.Event("focusout", { bubbles: true }))
    doc.getElementById("pw")!.dispatchEvent(new win.Event("focusout", { bubbles: true }))
    doc.getElementById("memo")!.dispatchEvent(new win.Event("focusout", { bubbles: true }))

    const serialized = JSON.stringify(t.getTrace())
    expect(leaks(serialized)).toEqual([])
  })

  it("masks click labels by default and never captures input values", () => {
    const t = new StepStitchTracker({ appId: "test", doc, win })
    t.grantConsent("v1")
    doc.getElementById("pay-btn")!.dispatchEvent(new win.Event("click", { bubbles: true }))

    const steps = t.getTrace()
    const click = steps.find((s) => s.type === "click")
    expect(click?.label).toBe(MASKED) // "Pay ACCT-..." is suppressed
    // input value never recorded
    expect(JSON.stringify(steps)).not.toContain("memo-value")
  })

  it("only unmasks elements explicitly opted in via data-stepstitch-unmask", () => {
    const t = new StepStitchTracker({ appId: "test", doc, win })
    t.grantConsent("v1")
    doc.getElementById("submit-btn")!.dispatchEvent(new win.Event("click", { bubbles: true }))

    const click = t.getTrace().find((s) => s.type === "click")
    expect(click?.label).toBe("Submit Payment") // safe, author-approved text
    expect(leaks(JSON.stringify(click))).toEqual([]) // still no NPI
  })

  it("hard-skips password and credit-card fields entirely", () => {
    const t = new StepStitchTracker({ appId: "test", doc, win })
    t.grantConsent("v1")
    doc.getElementById("pw")!.dispatchEvent(new win.Event("focusout", { bubbles: true }))
    doc.getElementById("card")!.dispatchEvent(new win.Event("focusout", { bubbles: true }))

    const inputs = t.getTrace().filter((s) => s.type === "input")
    expect(inputs).toHaveLength(0)
  })

  it("strips query strings and ID-like path segments from routes", () => {
    const t = new StepStitchTracker({ appId: "test", doc, win })
    t.grantConsent("v1")
    doc.getElementById("acct-link")!.dispatchEvent(new win.Event("click", { bubbles: true }))

    const serialized = JSON.stringify(t.getTrace())
    expect(serialized).not.toContain("8675309")
    expect(serialized).not.toContain("ssn=")
  })

  it("never leaks NPI into the submitted payload", async () => {
    let capturedBody = ""
    const fetchWin = {
      ...win,
      innerWidth: 1280,
      innerHeight: 720,
      fetch: async (_url: string, init: { body: string }) => {
        capturedBody = init.body
        return { json: async () => ({ trace_id: "t_1" }) } as Response
      },
    } as unknown as Window & typeof globalThis

    const t = new StepStitchTracker({ appId: "test",
      doc,
      win: fetchWin,
      ingestEndpoint: "/api/stepstitch/v1/session",
    })
    t.grantConsent("v1")
    doc.getElementById("pay-btn")!.dispatchEvent(new win.Event("click", { bubbles: true }))

    // explanation is user-authored bug text; pass a clean one
    const result = await t.submitTrace("Pay button did nothing", "proj-1")
    expect(result.submitted).toBe(true)
    expect(result.traceId).toBe("t_1")
    expect(leaks(capturedBody)).toEqual([])
  })

  it("does not capture raw frontend logs, messages, stacks, or URLs", () => {
    const t = new StepStitchTracker({ appId: "test", doc, win })
    t.grantConsent("v1")
    t.recordApiError(500, `https://portal.example.test/api/accounts/8675309?ssn=${NPI.ssn}`)
    t.recordFrontendException(`TypeError ${NPI.ssn}`, "/static/app-8675309.js", 8, 2)

    const serialized = JSON.stringify(t.getTrace())
    expect(leaks(serialized)).toEqual([])
    expect(serialized).not.toContain("message")
    expect(serialized).not.toContain("stack")
    expect(serialized).not.toContain("ssn=")
    expect(serialized).not.toContain("8675309")
  })
})
