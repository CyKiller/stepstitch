/**
 * StepStitchTracker — privacy-by-default footsteps recorder.
 *
 * Capture is OFF until `grantConsent()` and stays off if a privacy signal (GPC/DNT)
 * is present. The recorder never reads input values, never patches `window.fetch`,
 * masks all text by default, and tears down cleanly via `destroy()`.
 */

import { BUILD_HASH } from "./buildinfo.js"
import {
  buildSelector,
  isBlockedMedia,
  isSensitiveInput,
  routeTemplate,
  safeLabel,
} from "./redaction.js"
import type {
  ConsentState,
  StepStitchConfig,
  SubmitResult,
  UserFootstep,
} from "./types.js"

export const SDK_VERSION = "0.9.1" // x-release-please-version

const DEFAULT_MAX_FOOTSTEPS = 50
const DEFAULT_UNMASK_ATTR = "data-stepstitch-unmask"

export class StepStitchTracker {
  private readonly appId: string
  private readonly ingestEndpoint: string | undefined
  private readonly maxFootsteps: number
  private readonly unmaskAttribute: string
  private readonly respectPrivacySignals: boolean
  private readonly doc: Document | undefined
  private readonly win: (Window & typeof globalThis) | undefined

  private footsteps: UserFootstep[] = []
  private consent: ConsentState = { granted: false }
  private killed = false
  private listening = false

  // Bound handlers retained so teardown can remove the exact references.
  private readonly onClick = (e: Event) => this.handleClick(e)
  private readonly onFocusOut = (e: Event) => this.handleFocusOut(e)
  private readonly onError = (e: Event) => this.handleError(e as ErrorEvent)
  private readonly onPopState = () => this.recordNavigation()

  constructor(config: StepStitchConfig) {
    // Required — StepStitch is a standalone connector; the host app must name itself.
    // Guarded at runtime too, so JS callers (no type checking) fail fast and clearly.
    if (!config || !config.appId) {
      throw new Error(
        "StepStitchTracker: `appId` is required — name the app/tenant using StepStitch."
      )
    }
    this.appId = config.appId
    this.ingestEndpoint = config.ingestEndpoint
    this.maxFootsteps = config.maxFootsteps ?? DEFAULT_MAX_FOOTSTEPS
    this.unmaskAttribute = config.unmaskAttribute ?? DEFAULT_UNMASK_ATTR
    this.respectPrivacySignals = config.respectPrivacySignals ?? true

    const globalWin =
      typeof window !== "undefined"
        ? (window as Window & typeof globalThis)
        : undefined
    this.win = config.win ?? globalWin
    this.doc = config.doc ?? this.win?.document
  }

  // ---- consent + kill switch -------------------------------------------------

  /** Detect GPC / DNT. Either signal disables capture when respected. */
  private privacySignalPresent(): boolean {
    if (!this.respectPrivacySignals) return false
    const nav = this.win?.navigator as
      | (Navigator & { globalPrivacyControl?: boolean; doNotTrack?: string })
      | undefined
    if (!nav) return false
    if (nav.globalPrivacyControl === true) return true
    const dnt = nav.doNotTrack ?? (this.win as unknown as { doNotTrack?: string })?.doNotTrack
    return dnt === "1" || dnt === "yes"
  }

  private canCapture(): boolean {
    return (
      !this.killed &&
      this.consent.granted &&
      !this.privacySignalPresent() &&
      !!this.doc
    )
  }

  /** Host consent manager calls this once the user has opted in. */
  grantConsent(consentVersion?: string): void {
    if (this.killed) return
    this.consent = { granted: true, consentVersion }
    if (this.canCapture()) {
      this.attach()
      this.recordNavigation()
    }
  }

  /** Withdraw consent: stop capturing and drop anything buffered. */
  revokeConsent(): void {
    this.consent = { granted: false }
    this.detach()
    this.footsteps = []
  }

  /**
   * Kill switch — the first action in an incident-response runbook. Permanently
   * disables this instance: detaches, clears, and blocks future capture/submit.
   */
  disable(): void {
    this.killed = true
    this.detach()
    this.footsteps = []
  }

  // ---- listener lifecycle ----------------------------------------------------

  private attach(): void {
    if (this.listening || !this.doc) return
    // Capture phase so we see the event even if the app stops propagation.
    this.doc.addEventListener("click", this.onClick, true)
    this.doc.addEventListener("focusout", this.onFocusOut, true)
    if (typeof this.win?.addEventListener === "function") {
      this.win.addEventListener("error", this.onError)
      this.win.addEventListener("popstate", this.onPopState)
    }
    this.listening = true
  }

  private detach(): void {
    if (!this.listening || !this.doc) return
    this.doc.removeEventListener("click", this.onClick, true)
    this.doc.removeEventListener("focusout", this.onFocusOut, true)
    if (typeof this.win?.removeEventListener === "function") {
      this.win.removeEventListener("error", this.onError)
      this.win.removeEventListener("popstate", this.onPopState)
    }
    this.listening = false
  }

  /** Remove all listeners and clear state. Safe to call multiple times. */
  destroy(): void {
    this.detach()
    this.footsteps = []
  }

  // ---- capture ---------------------------------------------------------------

  private currentRoute(): string {
    const path = this.win?.location?.pathname ?? "/"
    return routeTemplate(path)
  }

  private push(step: UserFootstep): void {
    this.footsteps.push(step)
    if (this.footsteps.length > this.maxFootsteps) this.footsteps.shift()
  }

  private base(type: UserFootstep["type"]): Pick<UserFootstep, "timestamp" | "type" | "route" | "label"> {
    return {
      timestamp: new Date().toISOString(),
      type,
      route: this.currentRoute(),
      label: "[masked]",
    }
  }

  private handleClick(event: Event): void {
    if (!this.canCapture()) return
    const el = event.target as Element | null
    if (!el || isBlockedMedia(el)) return
    const clickable = el.closest('button,a,[role="button"],[role="link"],input[type="submit"]')
    if (!clickable) return
    this.push({
      ...this.base("click"),
      target: buildSelector(clickable),
      label: safeLabel(clickable, this.unmaskAttribute),
    })
  }

  private handleFocusOut(event: Event): void {
    if (!this.canCapture()) return
    const el = event.target as Element | null
    if (!el) return
    const tag = el.tagName
    if (tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") return
    if (isSensitiveInput(el)) return // never record sensitive fields at all
    this.push({
      ...this.base("input"),
      target: buildSelector(el),
      // No value, ever — only that an interaction occurred with this field.
      metadata: { interacted: true },
    })
  }

  private handleError(event: ErrorEvent): void {
    if (!this.canCapture()) return
    // Capture structure only — NOT event.message or stack, which can interpolate NPI.
    const err = event.error as { name?: string } | undefined
    this.push({
      ...this.base("exception"),
      metadata: {
        error_type: err?.name ?? "Error",
        source_path: routeTemplate(safePath(event.filename)),
        line: event.lineno ?? 0,
        column: event.colno ?? 0,
      },
    })
  }

  /** Record an SPA route change. Hosts may call this from their router hook. */
  recordNavigation(): void {
    if (!this.canCapture()) return
    this.push({ ...this.base("navigation") })
  }

  /**
   * Record a failed API call. The SDK does NOT patch fetch — the host calls this
   * from its own client. Only status + route template are stored, never URLs with
   * query strings or response bodies.
   */
  recordApiError(status: number, urlOrPath: string, method = "GET"): void {
    if (!this.canCapture()) return
    this.push({
      ...this.base("api_error"),
      metadata: {
        status,
        method: method.toUpperCase().slice(0, 12),
        endpoint: routeTemplate(safePath(urlOrPath)),
      },
    })
  }

  /**
   * Host-reported frontend exception. This is for framework error boundaries that
   * already know the exception class/type; do not pass raw messages or stack traces.
   */
  recordFrontendException(errorType: string, sourcePath = "/", line = 0, column = 0): void {
    if (!this.canCapture()) return
    this.push({
      ...this.base("exception"),
      metadata: {
        error_type: safeToken(errorType),
        source_path: routeTemplate(safePath(sourcePath)),
        line,
        column,
      },
    })
  }

  // ---- access + submit -------------------------------------------------------

  /** Snapshot of the current buffer (defensive copy). */
  getTrace(): UserFootstep[] {
    return this.footsteps.map((f) => ({ ...f }))
  }

  async submitTrace(explanation?: string, projectId?: string): Promise<SubmitResult> {
    if (this.killed || !this.consent.granted) {
      return { traceId: null, submitted: false, reason: "no-consent" }
    }
    if (this.privacySignalPresent()) {
      return { traceId: null, submitted: false, reason: "privacy-signal" }
    }
    if (!this.ingestEndpoint) {
      return { traceId: null, submitted: false, reason: "no-endpoint" }
    }
    if (this.footsteps.length === 0) {
      return { traceId: null, submitted: false, reason: "empty" }
    }

    const fetchFn = this.win?.fetch?.bind(this.win)
    if (!fetchFn) return { traceId: null, submitted: false, reason: "no-endpoint" }

    const body = {
      app_id: this.appId,
      project_id: projectId ?? null,
      explanation: explanation ?? null,
      footsteps: this.getTrace(),
      consent_version: this.consent.consentVersion ?? null,
      metadata: {
        sdk_version: SDK_VERSION,
        sdk_build: BUILD_HASH,
        viewport: `${this.win?.innerWidth ?? 0}x${this.win?.innerHeight ?? 0}`,
        user_agent: this.win?.navigator?.userAgent ?? "",
      },
    }

    const res = await fetchFn(this.ingestEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      credentials: "include",
    })
    const data = (await res.json().catch(() => ({}))) as { trace_id?: string }
    return { traceId: data.trace_id ?? null, submitted: true }
  }
}

/** Reduce a script URL/filename to its pathname; tolerate non-URL strings. */
function safePath(value: string | undefined): string {
  if (!value) return "/"
  try {
    return new URL(value).pathname
  } catch {
    return value.split("?")[0] ?? value
  }
}

/** Keep diagnostic type labels structural; drop whitespace-heavy/free-text values. */
function safeToken(value: string): string {
  return value.replace(/[^a-zA-Z_.:]/g, "").slice(0, 80) || "Error"
}
