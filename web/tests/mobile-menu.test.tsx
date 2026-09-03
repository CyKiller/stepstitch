import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { MobileMenu } from "@/components/mobile-menu";

beforeAll(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: true,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }));
});

afterEach(cleanup);

describe("MobileMenu", () => {
  it("traps focus, closes on Escape, and restores focus", async () => {
    render(
      <MobileMenu
        links={[
          { href: "/quickstart", label: "Quickstart" },
          { href: "/security", label: "Security" },
        ]}
      />,
    );

    const trigger = screen.getByRole("button", { name: "Open menu" });
    fireEvent.click(trigger);

    const dialog = screen.getByRole("dialog", { name: "Site navigation" });
    expect(trigger.getAttribute("aria-controls")).toBe(dialog.id);
    expect(document.body.style.overflow).toBe("hidden");
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByRole("link", { name: "Quickstart" }),
      ),
    );

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(trigger);
    expect(document.body.style.overflow).toBe("");
  });
});
