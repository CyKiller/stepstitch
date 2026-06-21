import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Wordmark } from "@/components/wordmark";

// Wordmark is a pure presentational component: inline SVG + text, no client
// hooks and no Next-runtime-only imports, so it renders cleanly under jsdom.
afterEach(() => {
  cleanup();
});

describe("Wordmark", () => {
  it("renders the brand text without throwing", () => {
    render(<Wordmark />);
    expect(screen.getByText("StepStitch")).toBeTruthy();
  });

  it("merges a provided className onto the wrapper", () => {
    const { container } = render(<Wordmark className="custom-class" />);
    const span = container.querySelector("span");
    expect(span?.className).toContain("custom-class");
  });
});
