import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ORIGINAL_ENV = { ...process.env };

function clearBackendEnv() {
  delete process.env.STEPSTITCH_BASE_URL;
  delete process.env.STEPSTITCH_ADMIN_TOKEN;
  delete process.env.STEPSTITCH_DEMO_TRACE_ID;
}

beforeEach(() => {
  vi.resetModules();
  clearBackendEnv();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  process.env = { ...ORIGINAL_ENV };
});

describe("GET /api/demo/trace", () => {
  it("returns the sample trace with Cache-Control no-store when the backend is unconfigured", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    // Import fresh so the route + lib capture the (cleared) env at import time.
    const { GET } = await import("@/app/api/demo/trace/route");
    const res = await GET();

    expect(res.status).toBe(200);
    expect(res.headers.get("Cache-Control")).toBe("no-store");

    const body = await res.json();
    expect(body.source).toBe("sample");
    expect(body.trace_id).toBe("trc_9f4c1ae2b7d04e51");
    // Unconfigured -> no backend call.
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
