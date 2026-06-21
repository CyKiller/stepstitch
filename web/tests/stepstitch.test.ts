import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DemoTrace } from "@/lib/stepstitch";

// lib/stepstitch.ts captures BASE / TOKEN / DEMO_TRACE_ID at import time, so any
// env-varying test must reset modules and import fresh. Never import the module
// statically at top-of-file for those cases.

const ORIGINAL_ENV = { ...process.env };

function clearEnv() {
  delete process.env.STEPSTITCH_BASE_URL;
  delete process.env.STEPSTITCH_ADMIN_TOKEN;
  delete process.env.STEPSTITCH_DEMO_TRACE_ID;
}

beforeEach(() => {
  vi.resetModules();
  clearEnv();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  process.env = { ...ORIGINAL_ENV };
});

describe("backendConfigured", () => {
  it("is false when env is unset", async () => {
    const mod = await import("@/lib/stepstitch");
    expect(mod.backendConfigured()).toBe(false);
  });

  it("is true when both BASE and TOKEN are set", async () => {
    process.env.STEPSTITCH_BASE_URL = "https://api.example.test";
    process.env.STEPSTITCH_ADMIN_TOKEN = "tok_secret_value";
    const mod = await import("@/lib/stepstitch");
    expect(mod.backendConfigured()).toBe(true);
  });

  it("is false when only one of BASE/TOKEN is set", async () => {
    process.env.STEPSTITCH_BASE_URL = "https://api.example.test";
    const mod = await import("@/lib/stepstitch");
    expect(mod.backendConfigured()).toBe(false);
  });
});

describe("fetchDemoTrace", () => {
  it("returns the SAMPLE_TRACE (source 'sample') when unconfigured, without calling fetch", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const mod = await import("@/lib/stepstitch");
    const trace = await mod.fetchDemoTrace();

    expect(trace).toEqual(mod.SAMPLE_TRACE);
    expect(trace.source).toBe("sample");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  // Trust-seam test: the admin bearer token must be sent on every backend read
  // and must NEVER appear anywhere in the DemoTrace returned to the browser.
  // This MUST fail if lib/stepstitch.ts ever leaks the token into the response.
  it("sends the bearer token on every backend read but never leaks it into the returned trace", async () => {
    const BASE = "https://api.example.test";
    const TOKEN = "tok_super_secret_DO_NOT_LEAK";
    const TRACE_ID = "trc_test_123";
    process.env.STEPSTITCH_BASE_URL = BASE;
    process.env.STEPSTITCH_ADMIN_TOKEN = TOKEN;
    process.env.STEPSTITCH_DEMO_TRACE_ID = TRACE_ID;

    const payloadFor = (url: string): unknown => {
      if (url.endsWith("/summary")) {
        return {
          summary: {
            route: "/x",
            headline: "h",
            step_count: 1,
            privacy_status: "clean",
          },
        };
      }
      if (url.endsWith("/replayability")) {
        return {
          replayability: {
            score: 0.5,
            grade: "B",
            warnings: [],
            signals: { steps: 1, interactive: 1, stable_selectors: 1 },
          },
        };
      }
      if (url.endsWith("/privacy-posture")) {
        return {
          scrub: { scrub_status: "clean", scrubbed_fields: [] },
          never_captured: [],
        };
      }
      if (url.endsWith("/playwright")) {
        return { playwright_code: "// generated" };
      }
      return {};
    };

    const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      // Every read must carry the exact bearer token and hit the configured BASE.
      expect(url.startsWith(BASE)).toBe(true);
      const auth = new Headers(init?.headers).get("Authorization");
      expect(auth).toBe(`Bearer ${TOKEN}`);
      expect(init?.cache).toBe("no-store");
      return {
        ok: true,
        status: 200,
        json: async () => payloadFor(url),
      } as Response;
    });
    vi.stubGlobal("fetch", fetchSpy);

    const mod = await import("@/lib/stepstitch");
    const trace: DemoTrace = await mod.fetchDemoTrace();

    expect(fetchSpy).toHaveBeenCalled();
    expect(trace.source).toBe("live");
    // The token must not surface anywhere in the serialized response.
    expect(JSON.stringify(trace)).not.toContain(TOKEN);
  });

  it("falls back to SAMPLE_TRACE when a backend fetch throws", async () => {
    process.env.STEPSTITCH_BASE_URL = "https://api.example.test";
    process.env.STEPSTITCH_ADMIN_TOKEN = "tok_secret_value";
    process.env.STEPSTITCH_DEMO_TRACE_ID = "trc_test_123";

    const fetchSpy = vi.fn(async () => {
      throw new Error("network down");
    });
    vi.stubGlobal("fetch", fetchSpy);

    const mod = await import("@/lib/stepstitch");
    const trace = await mod.fetchDemoTrace();

    expect(fetchSpy).toHaveBeenCalled();
    expect(trace).toEqual(mod.SAMPLE_TRACE);
    expect(trace.source).toBe("sample");
  });
});
