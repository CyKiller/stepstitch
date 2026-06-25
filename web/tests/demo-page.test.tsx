import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import DemoPage from "@/app/demo/page";
import bundle from "@/lib/demo-bundle.json";

// The /demo page renders the generated red-to-green evidence bundle. It is a server
// component returning plain JSX, but its Reveal wrappers use framer-motion's useInView /
// useReducedMotion, which need browser APIs jsdom omits. Stub them so the page mounts.
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
  vi.stubGlobal(
    "matchMedia",
    (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  );
});

afterEach(() => {
  cleanup();
});

describe("DemoPage", () => {
  it("renders all eight story steps", () => {
    render(<DemoPage />);
    for (const step of bundle.story as string[]) {
      expect(screen.getAllByText(step).length).toBeGreaterThan(0);
    }
  });

  it("labels the data as a dry-run demo", () => {
    render(<DemoPage />);
    expect(screen.getByText(/Demo data/)).toBeTruthy();
    expect(screen.getAllByText(/dry-run/i).length).toBeGreaterThan(0);
  });

  it("shows the confirmed-fixed verdict from the bundle", () => {
    render(<DemoPage />);
    expect(screen.getByText(/verdict: confirmed_fixed/)).toBeTruthy();
  });

  it("shows the privacy scrub status", () => {
    render(<DemoPage />);
    expect(screen.getByText(/Scrub status:/)).toBeTruthy();
  });
});
