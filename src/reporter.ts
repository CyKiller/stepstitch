/**
 * The drop-in "Report a problem" control.
 *
 * Deliberately framework-agnostic plain DOM rather than a React component: the SDK's
 * zero-runtime-dependency promise is a product claim, not an accident, and a peer
 * dependency on React would exclude every Vue/Svelte/vanilla host for no gain. Mount it
 * from any framework — in React, call `mountReporter` in an effect and return its
 * `unmount`.
 *
 * Unstyled by design. Every node carries a `stepstitch-…` class so a host can theme it
 * with its own CSS; no styles are injected into the page.
 *
 * Privacy behavior is the tracker's, unchanged: capture is off until consent is granted,
 * GPC/DNT suppress submission, and the widget sends only the user's own typed
 * explanation plus the structural footsteps the tracker already holds.
 */
import type { StepStitchTracker } from "./tracker.js"
import type { SubmitResult } from "./types.js"

export interface ReporterOptions {
  /** Where to mount. Defaults to `document.body`. */
  container?: HTMLElement
  /** The tracker whose footsteps this report attaches to. */
  tracker: StepStitchTracker
  /** Optional project id passed through to `submitTrace`. */
  projectId?: string
  /** Label for the trigger button. */
  buttonLabel?: string
  /** Heading inside the panel. */
  title?: string
  /** Prompt above the textarea. */
  prompt?: string
  /** Called after a submit attempt, so a host can log or toast its own way. */
  onSubmit?: (result: SubmitResult) => void
}

export interface ReporterHandle {
  /** Open the panel programmatically (e.g. from a host's own menu item). */
  open(): void
  close(): void
  /** Remove every node and listener this widget created. */
  unmount(): void
}

const MESSAGES: Record<string, string> = {
  "no-consent": "Reporting is off until you allow it in this app's privacy settings.",
  "privacy-signal": "Your browser asks sites not to track, so nothing was sent.",
  "no-endpoint": "This app has not finished setting up bug reporting yet.",
  empty: "Nothing to report yet — reproduce the problem, then send this.",
}

function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className: string,
  props: Partial<HTMLElementTagNameMap[K]> = {},
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag)
  node.className = className
  Object.assign(node, props)
  return node
}

/**
 * Mount the reporter. Returns a handle; call `unmount()` on teardown.
 */
export function mountReporter(options: ReporterOptions): ReporterHandle {
  const {
    container = document.body,
    tracker,
    projectId,
    buttonLabel = "Report a problem",
    title = "Report a problem",
    prompt = "What went wrong?",
    onSubmit,
  } = options

  const root = element("div", "stepstitch-reporter")
  const trigger = element("button", "stepstitch-reporter__trigger", {
    type: "button",
    textContent: buttonLabel,
  })
  trigger.setAttribute("aria-expanded", "false")

  const panel = element("div", "stepstitch-reporter__panel", { hidden: true })
  panel.setAttribute("role", "dialog")
  panel.setAttribute("aria-modal", "false")
  panel.setAttribute("aria-label", title)

  const fieldId = `stepstitch-explanation-${Math.random().toString(36).slice(2, 8)}`
  const label = element("label", "stepstitch-reporter__label", {
    htmlFor: fieldId,
    textContent: prompt,
  })
  const textarea = element("textarea", "stepstitch-reporter__input", { id: fieldId })
  const send = element("button", "stepstitch-reporter__send", {
    type: "button",
    textContent: "Send report",
  })
  const cancel = element("button", "stepstitch-reporter__cancel", {
    type: "button",
    textContent: "Cancel",
  })
  // A live region: the outcome must reach screen readers without stealing focus.
  const status = element("p", "stepstitch-reporter__status")
  status.setAttribute("role", "status")

  const note = element("p", "stepstitch-reporter__note", {
    textContent:
      "Sends the steps you took — never your screen, typing, or page content.",
  })

  panel.append(label, textarea, note, send, cancel, status)
  root.append(trigger, panel)
  container.appendChild(root)

  let open = false

  function setOpen(next: boolean): void {
    open = next
    panel.hidden = !next
    trigger.setAttribute("aria-expanded", String(next))
    if (next) textarea.focus()
  }

  async function submit(): Promise<void> {
    send.disabled = true
    const previous = send.textContent
    send.textContent = "Sending…"
    try {
      const result = await tracker.submitTrace(textarea.value.trim() || undefined, projectId)
      status.textContent = result.submitted
        ? "Thanks — the steps that led here were attached to your report."
        : MESSAGES[result.reason ?? ""] ?? "Your report could not be sent."
      if (result.submitted) {
        textarea.value = ""
        setOpen(false)
      }
      onSubmit?.(result)
    } catch {
      // A failed POST is the host's network, not the user's problem to decode.
      status.textContent = "Your report could not be sent. Please try again."
    } finally {
      send.disabled = false
      send.textContent = previous
    }
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.key === "Escape" && open) {
      setOpen(false)
      trigger.focus()
    }
  }

  trigger.addEventListener("click", () => setOpen(!open))
  cancel.addEventListener("click", () => {
    setOpen(false)
    trigger.focus()
  })
  send.addEventListener("click", () => {
    void submit()
  })
  panel.addEventListener("keydown", onKeydown)

  return {
    open: () => setOpen(true),
    close: () => setOpen(false),
    unmount: () => {
      panel.removeEventListener("keydown", onKeydown)
      root.remove()
    },
  }
}
