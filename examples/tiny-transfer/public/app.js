/**
 * TinyTransfer front end.
 *
 * The real @stepstitch/tracker module, served from node_modules by server.mjs — not a
 * simplified copy that could quietly diverge from what the SDK actually does.
 *
 * Note what is NOT here: no token, no StepStitch hostname, no fetch patching. The tracker
 * posts to /ingest on this origin and this app's own server attaches the credential.
 */
import { StepStitchTracker } from "/vendor/index.js"

const ACCOUNT_ID = "8842"
// Proof that query strings never survive. If this string ever appears in a captured payload,
// the privacy claim is broken — the e2e test asserts on exactly this value.
const SYNTHETIC_QUERY = "FAKE-QUERY-SECRET-123"

const tracker = new StepStitchTracker({
  appId: "tiny-transfer",
  ingestEndpoint: "/ingest", // same origin; the token lives in server.mjs
  maxFootsteps: 40,
})

const $ = (id) => document.getElementById(id)
const consentBox = $("consent")
const statusEl = $("status")
const payloadEl = $("payload")

// --- consent ---------------------------------------------------------------------------
// Capture is off until this fires. Unticking clears whatever was buffered.
consentBox.addEventListener("change", () => {
  if (consentBox.checked) {
    tracker.grantConsent("tiny-transfer-v1")
    $("consent-state").textContent = "capture on"
    $("consent-state").classList.add("on")
  } else {
    tracker.revokeConsent()
    $("consent-state").textContent = "capture off — buffer cleared"
    $("consent-state").classList.remove("on")
  }
})

// The SDK keeps its buffer private on purpose — an app has no business reading it, so this
// example does not. The count below comes from the payload that was actually submitted,
// which is the only footstep list a host application is ever entitled to see.
function refreshCount(payload) {
  const n = payload ? (payload.footsteps || []).length : null
  $("step-count").textContent =
    n === null ? "buffer is private to the SDK" : (n === 1 ? "1 footstep sent" : `${n} footsteps sent`)
}

// --- the failing transfer ------------------------------------------------------------------
$("transfer-form").addEventListener("submit", async (event) => {
  event.preventDefault()
  statusEl.className = "status"
  statusEl.textContent = ""

  // The query parameter exists purely to prove it gets stripped.
  const url = `/api/accounts/${ACCOUNT_ID}/transfer?sessionRef=${SYNTHETIC_QUERY}`
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      recipient: $("recipient").value,
      amount: $("amount").value,
      email: $("email").value,
    }),
  })

  if (response.ok) {
    statusEl.className = "status ok"
    statusEl.textContent = "Transfer sent. (The fix is applied — this is the green state.)"
    return
  }

  // The SDK does not patch fetch; you tell it when your own client sees a failure.
  tracker.recordApiError(response.status, url, "POST")

  statusEl.className = "status err"
  statusEl.textContent = `Transfer failed (HTTP ${response.status}). Reporting…`

  if (!consentBox.checked) {
    statusEl.textContent =
      `Transfer failed (HTTP ${response.status}). Nothing was recorded — consent is off.`
    return
  }

  // The explanation is free text a user typed, so it is exactly where real data leaks in.
  // These fakes are here to be redacted by the SERVER-side scrubber, which is the actual
  // trust boundary — the SDK cannot be the last line of defence for text a human wrote.
  const explanation =
    `Tried to send $250.00 to account 4111 1111 1111 1234 from dana.holt@example.test ` +
    `and it failed. My SSN is 000-00-0000 if that matters.`

  try {
    const result = await tracker.submitTrace(explanation, "tiny-transfer")
    statusEl.textContent =
      `Transfer failed (HTTP ${response.status}). Reported as ${result?.traceId ?? "(no id)"}.`
    payloadEl.textContent = JSON.stringify(lastSentPayload, null, 2)
    refreshCount(lastSentPayload)
  } catch (err) {
    statusEl.textContent =
      `Transfer failed (HTTP ${response.status}). Could not reach StepStitch: ${err}`
  }
})

// Show the operator the literal bytes that left the browser. Wrapping fetch here is a demo
// affordance so the page can display the payload; the SDK itself never patches fetch.
let lastSentPayload = null
const nativeFetch = window.fetch.bind(window)
window.fetch = async (input, init) => {
  const target = typeof input === "string" ? input : input?.url
  if (target === "/ingest" && init?.body) {
    try { lastSentPayload = JSON.parse(init.body) } catch { /* leave it */ }
  }
  return nativeFetch(input, init)
}

// --- the fix switch ---------------------------------------------------------------------
async function setBug(active) {
  const res = await nativeFetch("/__bug", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active }),
  })
  showBugState((await res.json()).active)
}
function showBugState(active) {
  const pill = $("bug-state")
  pill.textContent = active ? "bug active — transfers return 500" : "fixed — transfers return 200"
  pill.classList.toggle("on", !active)
}
$("apply-fix").addEventListener("click", () => setBug(false))
$("reset-bug").addEventListener("click", () => setBug(true))
nativeFetch("/__bug").then((r) => r.json()).then((s) => showBugState(s.active))
