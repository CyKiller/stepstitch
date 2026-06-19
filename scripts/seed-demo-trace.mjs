#!/usr/bin/env node
/*
 * Seed one realistic demo trace into a running StepStitch service so the
 * marketing site's live demo (web/) always has real, already-sanitized data
 * to render. Structural footsteps only: no input values, no page text, no PII.
 *
 * Usage:
 *   STEPSTITCH_BASE_URL="https://<railway-app>" \
 *   STEPSTITCH_INGEST_TOKEN="<ingest-bearer>" \
 *   node scripts/seed-demo-trace.mjs
 *
 * Prints the created trace_id. Put that in the web app's STEPSTITCH_DEMO_TRACE_ID
 * (optional: the site otherwise just shows the most recent trace).
 */

const BASE = process.env.STEPSTITCH_BASE_URL;
const TOKEN = process.env.STEPSTITCH_INGEST_TOKEN;

if (!BASE || !TOKEN) {
  console.error(
    "Set STEPSTITCH_BASE_URL and STEPSTITCH_INGEST_TOKEN before running.",
  );
  process.exit(1);
}

const footsteps = [
  { timestamp: "2026-06-02T08:00:00.000Z", type: "navigation", route: "/accounts/:id", label: "[masked]" },
  { timestamp: "2026-06-02T08:00:03.000Z", type: "navigation", route: "/accounts/:id/transfer", label: "[masked]" },
  { timestamp: "2026-06-02T08:00:06.000Z", type: "click", route: "/accounts/:id/transfer", target: "[data-testid=payee-select]", label: "[masked]" },
  { timestamp: "2026-06-02T08:00:08.000Z", type: "click", route: "/accounts/:id/transfer", target: "[data-testid=amount-input]", label: "[masked]" },
  { timestamp: "2026-06-02T08:00:11.000Z", type: "click", route: "/accounts/:id/transfer", target: "[data-testid=review-transfer]", label: "[masked]" },
  {
    timestamp: "2026-06-02T08:00:11.400Z",
    type: "api_error",
    route: "/accounts/:id/transfer",
    metadata: { status: 500, method: "POST", endpoint: "/api/accounts/:id/transfers" },
  },
];

const body = {
  app_id: "stepstitch-demo",
  project_id: "demo",
  explanation: "Transfer review returned 500 after selecting payee and amount.",
  footsteps,
  consent_version: "v1",
  metadata: { sdk_version: "demo", viewport: "1280x720" },
};

const res = await fetch(`${BASE}/api/stepstitch/v1/session`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${TOKEN}`,
  },
  body: JSON.stringify(body),
});

if (!res.ok) {
  console.error(`Seed failed: ${res.status} ${await res.text()}`);
  process.exit(1);
}

const json = await res.json();
console.log("Seeded demo trace:", json.trace_id);
console.log("Set STEPSTITCH_DEMO_TRACE_ID to this value in the web app (optional).");
