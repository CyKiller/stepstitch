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

async function loadPage() {
  // The page reads the env var at module scope, so the module registry has to be cleared
  // BEFORE the import, not just after. Resetting only in afterEach passes in isolation and
  // fails in a full run, because whatever ran first leaves the module cached.
  vi.resetModules();
  return import("@/app/dashboard/page");
}

async function renderPage() {
  const mod = await loadPage();
  render(<mod.default />);
  return mod;
}

// Generous timeout: every test here re-imports the page module after vi.resetModules()
// (the env var is read at module scope), and that re-evaluation of the icon/motion
// graph can exceed the default 5s under full-suite worker contention. A timeout mid-
// mount also leaks the render past cleanup(), cascading duplicate-DOM failures into
// the next test — so the budget is the fix, not looser assertions.
describe("/dashboard", { timeout: 20_000 }, () => {
  it("links to the console when the demo host is configured", async () => {
    process.env.STEPSTITCH_DEMO_HOST = "http://127.0.0.1:8020";
    await renderPage();
    const link = screen.getByRole("link", { name: /Open the live console/i });
    expect(link.getAttribute("href")).toBe("/dashboard/demo");
    expect(screen.getByText("Console preview")).toBeTruthy();
  });

  it("never says 'live' anywhere when the demo host is not configured", async () => {
    const mod = await renderPage();
    expect(String(mod.metadata.title)).not.toMatch(/live/i);
    expect(String(mod.metadata.description)).not.toMatch(/live/i);
    expect(screen.getByText("Console preview")).toBeTruthy();
    expect(screen.queryByText("Live synthetic console")).toBeNull();
  });

  it("stays useful when the demo host is not configured", async () => {
    await renderPage();
    expect(screen.queryByRole("link", { name: /Open the live console/i })).toBeNull();
    expect(screen.getByRole("link", { name: /Explore the preview/i })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Run it on your data/i })).toBeTruthy();
  });

  it("says plainly that the data is synthetic", async () => {
    await renderPage();
    expect(screen.getAllByText(/committed synthetic dataset/i).length).toBeGreaterThan(0);
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
