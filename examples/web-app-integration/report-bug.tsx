"use client"

/**
 * Reference integration: the shipped reporter widget, mounted from React.
 *
 * The widget itself is plain DOM (`mountReporter`, exported by @stepstitch/tracker) so
 * that Vue, Svelte and vanilla hosts get the same control without React. This file shows
 * the React seam: mount in an effect, unmount on teardown, and mirror the host's existing
 * consent state into the tracker.
 *
 * The widget is unstyled on purpose — every node carries a `stepstitch-reporter__*` class
 * for the host's own CSS.
 */

import { useEffect, useRef } from "react"
import { StepStitchTracker, mountReporter } from "@stepstitch/tracker"

export function StepStitchReporter({
  hasConsent,
  consentVersion = "v1",
  projectId,
}: {
  hasConsent: boolean
  consentVersion?: string
  projectId?: string
}) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const trackerRef = useRef<StepStitchTracker | null>(null)

  // One tracker + one widget for the app lifetime; same-origin ingest via the host's
  // own route, so the ingest token stays on the server.
  useEffect(() => {
    const tracker = new StepStitchTracker({
      appId: "host-app",
      ingestEndpoint: "/api/stepstitch/v1/session",
    })
    trackerRef.current = tracker

    const reporter = mountReporter({
      tracker,
      projectId,
      container: hostRef.current ?? undefined,
    })

    return () => {
      reporter.unmount()
      tracker.destroy()
    }
  }, [projectId])

  // Mirror the host's consent state into the tracker.
  useEffect(() => {
    const tracker = trackerRef.current
    if (!tracker) return
    if (hasConsent) tracker.grantConsent(consentVersion)
    else tracker.revokeConsent()
  }, [hasConsent, consentVersion])

  return <div ref={hostRef} />
}
