import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

// The /dashboard page is a server component returning plain JSX, but its Reveal wrappers use
// motion's useInView / useReducedMotion, which need browser APIs jsdom omits.
beforeAll(() => {
  class IO {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  }
  vi.stubGlobal("IntersectionObserver", IO);
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }));
});

afterEach(() => {
  cleanup();
  vi.resetModules();
  delete process.env.STEPSTITCH_DEMO_HOST;
});

async function renderPage() {
  // The page reads the env var at module scope, so it has to be imported fresh per case.
  const mod = await import("@/app/dashboard/page");
  render(<mod.default />);
}

describe("/dashboard", () => {
  it("links to the console when the demo host is configured", async () => {
    process.env.STEPSTITCH_DEMO_HOST = "http://127.0.0.1:8020";
    await renderPage();
    const link = screen.getByRole("link", { name: /Open the console/i });
    expect(link.getAttribute("href")).toBe("/dashboard/demo");
  });

  it("stays useful when the demo host is not configured", async () => {
    await renderPage();
    // No dead link to a proxy that is not wired…
    expect(screen.queryByRole("link", { name: /Open the console/i })).toBeNull();
    // …and the page still tells you how to see the same thing.
    expect(screen.getByText(/offline right now/i)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Run it locally/i })).toBeTruthy();
  });

  it("says plainly that the data is synthetic", async () => {
    await renderPage();
    expect(screen.getByText(/synthetic dataset built by the real pipeline/i)).toBeTruthy();
    expect(screen.getByText(/Made up/)).toBeTruthy();
    expect(screen.getByText(/no real person behind any of it/i)).toBeTruthy();
  });

  it("names every lifecycle stage the demo shows", async () => {
    await renderPage();
    for (const stage of [
      "Fixed and proven",
      "Waiting for a test run",
      "Seen before",
      "Confirmed broken",
      "Still broken",
      "Test needs fixing",
    ]) {
      // Some stage names also appear in the ConsoleBoard illustration below.
      expect(screen.getAllByText(stage).length).toBeGreaterThan(0);
    }
  });

  it("does not claim the console captures anything it does not", async () => {
    // Mirrors tests/copy-claims.test.ts: buyer-facing copy must never imply screen capture.
    await renderPage();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/session (recording|replay)/i);
    expect(text).not.toMatch(/records? (the )?(screen|session)/i);
  });
});
