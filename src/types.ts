/**
 * StepStitch SDK public types.
 *
 * Privacy contract: a UserFootstep is STRUCTURAL by default. It never carries
 * human-readable text, input values, or raw URLs unless an element is explicitly
 * opted in via `data-stepstitch-unmask`. See `redaction.ts` for enforcement.
 */

export type FootstepType =
  | "navigation"
  | "click"
  | "input"
  | "api_error"
  | "exception"

/** The masked placeholder emitted wherever readable text is suppressed. */
export const MASKED = "[masked]" as const

export interface UserFootstep {
  /** ISO-8601 timestamp (UTC). */
  timestamp: string
  type: FootstepType
  /** Route TEMPLATE, never a raw URL (e.g. `/accounts/:id`). */
  route: string
  /** Stable structural selector for the target element, if any. */
  target?: string
  /**
   * Human label for the step. Defaults to MASKED. Only carries real text when the
   * source element is explicitly marked `data-stepstitch-unmask`.
   */
  label: string
  /**
   * Structural, structural metadata only. Useful keys include status, method, endpoint,
   * error_type, source_path, line, and column. Raw logs/messages/stacks/bodies are
   * forbidden by contract and scrubbed again server-side.
   */
  metadata?: Record<string, string | number | boolean>
}

export interface ConsentState {
  granted: boolean
  /** Recorded for audit; travels with the submitted trace. */
  consentVersion?: string
}

export interface StepStitchConfig {
  /** Logical app/tenant id. **Required** — every app using StepStitch names itself;
   *  there is no built-in default. */
  appId: string
  /**
   * Same-tenant ingestion endpoint. Required to submit. There is intentionally NO
   * default cloud URL — the SDK must not phone home.
   */
  ingestEndpoint?: string
  /** Max footsteps retained in the in-memory ring buffer. */
  maxFootsteps?: number
  /**
   * Attribute marking elements whose text is safe to capture unmasked.
   * Defaults to `data-stepstitch-unmask`.
   */
  unmaskAttribute?: string
  /**
   * When true (default), honor `navigator.globalPrivacyControl` and
   * `navigator.doNotTrack`. If either is set, capture stays disabled.
   */
  respectPrivacySignals?: boolean
  /** Override for testing; defaults to the live document. */
  doc?: Document
  /** Override for testing; defaults to the live window. */
  win?: (Window & typeof globalThis) | undefined
}

export interface SubmitResult {
  /** Trace id assigned by the backend, or null when capture was suppressed. */
  traceId: string | null
  submitted: boolean
  reason?: "no-consent" | "privacy-signal" | "no-endpoint" | "empty"
}
