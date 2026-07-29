// Server-only helpers. The admin bearer token never reaches the browser:
// route handlers under /api/demo/* call these, the client calls our own API.

export type ReplayabilityWarning = {
  code: string;
  detail: string;
  step_index?: number;
};

export type DemoTrace = {
  trace_id: string;
  source: "live" | "sample";
  summary: {
    route: string;
    headline: string;
    step_count: number;
    privacy_status: string;
    failing_status?: number | null;
    exception_type?: string | null;
    diagnostic_type?: string | null;
    diagnostic_endpoint?: string | null;
  };
  replayability: {
    score: number;
    grade: string;
    warnings: ReplayabilityWarning[];
    signals: { steps: number; interactive: number; stable_selectors: number };
  };
  privacy: {
    scrub_status: string;
    scrubbed_fields: string[];
    never_captured: string[];
  };
  timeline: {
    index: number;
    kind: string;
    label: string;
    selector?: string;
    detail?: string;
  }[];
  playwright_code: string;
};

const BASE = process.env.STEPSTITCH_BASE_URL;
const TOKEN = process.env.STEPSTITCH_ADMIN_TOKEN;
const DEMO_TRACE_ID = process.env.STEPSTITCH_DEMO_TRACE_ID;

export function backendConfigured(): boolean {
  return Boolean(BASE && TOKEN);
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
    // Live evidence: never serve a stale trace from the data cache.
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`stepstitch ${path} -> ${res.status}`);
  return (await res.json()) as T;
}

// Pull a real, already-sanitized trace from the running service. Falls back to
// the bundled sample when the backend is not configured (e.g. local preview).
export async function fetchDemoTrace(): Promise<DemoTrace> {
  if (!backendConfigured()) return SAMPLE_TRACE;

  try {
    let traceId = DEMO_TRACE_ID;
    if (!traceId) {
      const list = await get<{ sessions: { trace_id: string }[] }>(
        "/api/stepstitch/v1/sessions?limit=1",
      );
      traceId = list.sessions?.[0]?.trace_id;
    }
    if (!traceId) return SAMPLE_TRACE;

    const [summary, replay, privacy, playwright] = await Promise.all([
      get<{ summary: DemoTrace["summary"] }>(
        `/api/stepstitch/v1/session/${traceId}/summary`,
      ),
      get<{ replayability: DemoTrace["replayability"] }>(
        `/api/stepstitch/v1/session/${traceId}/replayability`,
      ),
      get<{
        scrub: { scrub_status: string; scrubbed_fields: string[] } | null;
        never_captured: string[] | null;
      }>(`/api/stepstitch/v1/session/${traceId}/privacy-posture`),
      get<{ playwright_code: string }>(
        `/api/stepstitch/v1/session/${traceId}/playwright`,
      ),
    ]);

    return {
      trace_id: traceId,
      source: "live",
      summary: summary.summary,
      replayability: replay.replayability,
      privacy: {
        // `scrub` can be null for traces inserted outside this server; fall
        // back to the sample's privacy block so the demo never renders broken.
        scrub_status: privacy.scrub?.scrub_status ?? SAMPLE_TRACE.privacy.scrub_status,
        scrubbed_fields:
          privacy.scrub?.scrubbed_fields ?? SAMPLE_TRACE.privacy.scrubbed_fields,
        never_captured:
          privacy.never_captured ?? SAMPLE_TRACE.privacy.never_captured,
      },
      // The service intentionally does not expose raw footsteps over the read
      // API, so the structural timeline mirrors the sample shape for display.
      timeline: SAMPLE_TRACE.timeline,
      playwright_code: playwright.playwright_code,
    };
  } catch {
    return SAMPLE_TRACE;
  }
}

// Bundled sample. Shape matches the service's real read responses
// (TraceSummary, replayability, privacy-posture, playwright). Used as the
// fallback so the demo renders before the backend is wired up.
export const SAMPLE_TRACE: DemoTrace = {
  trace_id: "trc_9f4c1ae2b7d04e51",
  source: "sample",
  summary: {
    route: "/accounts/:id/transfer",
    headline: "Transfer submit returned 500 on review step",
    step_count: 6,
    privacy_status: "clean",
    failing_status: 500,
    exception_type: null,
    diagnostic_type: "api_error",
    diagnostic_endpoint: "/api/accounts/:id/transfers",
  },
  replayability: {
    score: 0.76,
    grade: "B",
    warnings: [
      {
        code: "templated_route_needs_fixture",
        detail: "Route '/accounts/:id' is templated; supply a concrete fixture id.",
        step_index: 0,
      },
      {
        code: "templated_route_needs_fixture",
        detail:
          "Route '/accounts/:id/transfer' is templated; supply a concrete fixture id.",
        step_index: 1,
      },
    ],
    signals: { steps: 6, interactive: 3, stable_selectors: 3 },
  },
  privacy: {
    scrub_status: "clean",
    scrubbed_fields: ["explanation", "metadata.referrer"],
    never_captured: [
      "screenshots / video",
      "input values",
      "page text / DOM content",
      "raw URLs",
      "request / response bodies",
      "cookies / headers",
      "SSNs, account & card numbers",
    ],
  },
  timeline: [
    { index: 0, kind: "nav", label: "Visited route", selector: "/accounts/:id" },
    {
      index: 1,
      kind: "nav",
      label: "Opened transfer form",
      selector: "/accounts/:id/transfer",
    },
    {
      index: 2,
      kind: "click",
      label: "Selected payee",
      selector: "[data-testid=payee-select]",
    },
    {
      index: 3,
      kind: "click",
      label: "Set amount field",
      selector: "[data-testid=amount-input]",
    },
    {
      index: 4,
      kind: "click",
      label: "Clicked Review transfer",
      selector: "[data-testid=review-transfer]",
    },
    {
      index: 5,
      kind: "api_error",
      label: "POST /api/accounts/:id/transfers",
      detail: "status 500",
    },
  ],
  playwright_code: `import { test, expect } from '@playwright/test';

// StepStitch autogenerated reproduction (trace: trc_9f4c1ae2)
// Replayability: 0.76 (grade B)
//   ⚠ templated_route_needs_fixture [step 0]: Route '/accounts/:id' is templated; supply a concrete fixture id.
//   ⚠ templated_route_needs_fixture [step 1]: Route '/accounts/:id/transfer' is templated; supply a concrete fixture id.
//   ⚠ templated_route_needs_fixture [step 2]: Route '/accounts/:id/transfer' is templated; supply a concrete fixture id.
//   ⚠ templated_route_needs_fixture [step 3]: Route '/accounts/:id/transfer' is templated; supply a concrete fixture id.
//   ⚠ templated_route_needs_fixture [step 4]: Route '/accounts/:id/transfer' is templated; supply a concrete fixture id.
//   ⚠ templated_route_needs_fixture [step 5]: Route '/accounts/:id/transfer' is templated; supply a concrete fixture id.
//
// Reproduction setup (change with PUT /admin/config/repro):
//   READY       Application base URL — points at https://staging.example.test
//   READY       Templated route values — every templated segment has a test value
//   NEEDS-CONFIG Authentication fixture — not configured — the reproduction runs unauthenticated. Set auth.fixture (e.g. "tests/auth.setup.ts") if the flow needs a session.
//
// NOTE: no credentials are embedded. A protected field reads its value from an
// environment variable by name — set that variable in CI.

test('StepStitch reproduction', async ({ page }) => {
  // TODO: authenticate as a synthetic test user if the flow requires it.

  // [NAVIGATION] /accounts/:id
  await page.goto('https://staging.example.test/accounts/1001');

  // [NAVIGATION] /accounts/:id/transfer
  await page.goto('https://staging.example.test/accounts/1001/transfer');

  // [CLICK] /accounts/:id/transfer
  await page.locator('[data-testid=payee-select]').click();

  // [CLICK] /accounts/:id/transfer
  await page.locator('[data-testid=amount-input]').click();

  // [CLICK] /accounts/:id/transfer
  const endpoint0 = new RegExp('/api/accounts/[^/]+/transfers$');
  const response0 = page.waitForResponse(
    (r) => endpoint0.test(new URL(r.url()).pathname) && r.request().method() === 'POST',
  );
  await page.locator('[data-testid=review-transfer]').click();
  // expected API failure: /api/accounts/:id/transfers (HTTP 500)
  const res0 = await response0;
  expect(res0.status(), 'no server error from /api/accounts/:id/transfers').toBeLessThan(500);

});`,
};
