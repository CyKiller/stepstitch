"use client"

/**
 * Reference integration: a consent-gated "Report Bug" control for a Next.js host
 * (Marvox is the reference app). Drop this into the host, mount <StepStitchReporter />
 * once near the root, and gate grantConsent() on the host's existing consent manager.
 *
 * The host imports the SDK as a normal dependency:
 *   "@stepstitch/tracker": "github:<org>/stepstitch#workspace=tracker&semver:^0.1.0"
 * (or a published version). Until that dependency resolves, do NOT import this file
 * from the host's compiled graph — webpack cannot resolve a missing bare specifier.
 */

import { useEffect, useRef, useState } from "react"
import { StepStitchTracker } from "@stepstitch/tracker"

export function StepStitchReporter({
  hasConsent,
  consentVersion = "v1",
  projectId,
}: {
  hasConsent: boolean
  consentVersion?: string
  projectId?: string
}) {
  const trackerRef = useRef<StepStitchTracker | null>(null)
  const [open, setOpen] = useState(false)
  const [text, setText] = useState("")
  const [sent, setSent] = useState<string | null>(null)

  // One tracker instance for the app lifetime; same-origin ingest via the rewrite.
  useEffect(() => {
    const tracker = new StepStitchTracker({
      appId: "marvox",
      ingestEndpoint: "/api/stepstitch/v1/session",
    })
    trackerRef.current = tracker
    return () => tracker.destroy()
  }, [])

  // Mirror the host's consent state into the tracker.
  useEffect(() => {
    const t = trackerRef.current
    if (!t) return
    if (hasConsent) t.grantConsent(consentVersion)
    else t.revokeConsent()
  }, [hasConsent, consentVersion])

  async function submit() {
    const t = trackerRef.current
    if (!t) return
    const res = await t.submitTrace(text.trim(), projectId)
    setSent(res.submitted ? "Thanks — your session was attached to the report." : "Report saved without a session trace.")
    setText("")
    setOpen(false)
  }

  return (
    <>
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        Report a bug
      </button>
      {open && (
        <div role="dialog" aria-label="Report a bug">
          <label htmlFor="stepstitch-explanation">What went wrong?</label>
          <textarea
            id="stepstitch-explanation"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <button type="button" onClick={submit}>
            Send report
          </button>
        </div>
      )}
      {sent && <p role="status">{sent}</p>}
    </>
  )
}
