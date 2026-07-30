/**
 * The drop-in reporter: it must submit the user's own words, say something useful when a
 * submission is suppressed, and leave nothing behind when unmounted.
 *
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest"
import { mountReporter } from "../src/reporter.js"
import type { StepStitchTracker } from "../src/tracker.js"
import type { SubmitResult } from "../src/types.js"

function fakeTracker(result: SubmitResult, capture?: (a: unknown[]) => void) {
  return {
    submitTrace: vi.fn(async (...args: unknown[]) => {
      capture?.(args)
      return result
    }),
  } as unknown as StepStitchTracker
}

const OK: SubmitResult = { traceId: "t-1", submitted: true }

function ui() {
  return {
    trigger: document.querySelector<HTMLButtonElement>(".stepstitch-reporter__trigger")!,
    panel: document.querySelector<HTMLDivElement>(".stepstitch-reporter__panel")!,
    input: document.querySelector<HTMLTextAreaElement>(".stepstitch-reporter__input")!,
    send: document.querySelector<HTMLButtonElement>(".stepstitch-reporter__send")!,
    cancel: document.querySelector<HTMLButtonElement>(".stepstitch-reporter__cancel")!,
    status: document.querySelector<HTMLParagraphElement>(".stepstitch-reporter__status")!,
  }
}

describe("mountReporter", () => {
  beforeEach(() => {
    document.body.innerHTML = ""
  })

  it("starts closed and opens on the trigger", () => {
    mountReporter({ tracker: fakeTracker(OK) })
    const { trigger, panel } = ui()
    expect(panel.hidden).toBe(true)
    expect(trigger.getAttribute("aria-expanded")).toBe("false")

    trigger.click()
    expect(panel.hidden).toBe(false)
    expect(trigger.getAttribute("aria-expanded")).toBe("true")
  })

  it("submits the typed explanation and the project id, then clears and closes", async () => {
    const seen: unknown[][] = []
    const tracker = fakeTracker(OK, (a) => seen.push(a))
    mountReporter({ tracker, projectId: "proj-9" })
    const { trigger, input, send, panel, status } = ui()

    trigger.click()
    input.value = "  the transfer button did nothing  "
    send.click()
    await vi.waitFor(() => expect(seen.length).toBe(1))

    expect(seen[0]).toEqual(["the transfer button did nothing", "proj-9"])
    await vi.waitFor(() => expect(panel.hidden).toBe(true))
    expect(input.value).toBe("")
    expect(status.textContent).toContain("attached to your report")
  })

  it("sends undefined rather than an empty string when the user types nothing", async () => {
    const seen: unknown[][] = []
    mountReporter({ tracker: fakeTracker(OK, (a) => seen.push(a)) })
    ui().trigger.click()
    ui().send.click()
    await vi.waitFor(() => expect(seen.length).toBe(1))
    expect(seen[0]?.[0]).toBeUndefined()
  })

  it("explains a suppressed submission in the user's terms, and keeps their text", async () => {
    const tracker = fakeTracker({ traceId: null, submitted: false, reason: "privacy-signal" })
    mountReporter({ tracker })
    const { trigger, input, send, panel, status } = ui()

    trigger.click()
    input.value = "still broken"
    send.click()

    await vi.waitFor(() => expect(status.textContent).toContain("asks sites not to track"))
    // Nothing was sent, so the panel stays open with the words they already wrote.
    expect(panel.hidden).toBe(false)
    expect(input.value).toBe("still broken")
  })

  it("survives a rejected submit without leaking the error at the user", async () => {
    const tracker = {
      submitTrace: vi.fn(async () => {
        throw new Error("network down")
      }),
    } as unknown as StepStitchTracker
    mountReporter({ tracker })
    ui().trigger.click()
    ui().send.click()

    await vi.waitFor(() => expect(ui().status.textContent).toContain("could not be sent"))
    expect(ui().send.disabled).toBe(false)   // the button recovers
  })

  it("reports the outcome to the host via onSubmit", async () => {
    const onSubmit = vi.fn()
    mountReporter({ tracker: fakeTracker(OK), onSubmit })
    ui().trigger.click()
    ui().send.click()
    await vi.waitFor(() => expect(onSubmit).toHaveBeenCalledWith(OK))
  })

  it("closes on Escape and on Cancel", () => {
    mountReporter({ tracker: fakeTracker(OK) })
    const { trigger, panel, cancel } = ui()

    trigger.click()
    panel.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }))
    expect(panel.hidden).toBe(true)

    trigger.click()
    cancel.click()
    expect(panel.hidden).toBe(true)
  })

  it("injects no styles and leaves nothing behind after unmount", () => {
    const handle = mountReporter({ tracker: fakeTracker(OK) })
    expect(document.head.querySelector("style")).toBeNull()   // hosts own the styling
    handle.unmount()
    expect(document.querySelector(".stepstitch-reporter")).toBeNull()
  })

  it("mounts where the host asks", () => {
    const host = document.createElement("section")
    document.body.appendChild(host)
    mountReporter({ tracker: fakeTracker(OK), container: host })
    expect(host.querySelector(".stepstitch-reporter")).not.toBeNull()
  })
})
