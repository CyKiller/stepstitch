"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "@phosphor-icons/react";

export function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">("dark");

  useEffect(() => {
    // Sync to the theme the pre-hydration inline script already resolved on
    // <html>. This intentional one-time DOM read is the source of truth.
    const current = document.documentElement.getAttribute("data-theme");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (current === "light" || current === "dark") setTheme(current);
  }, []);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("ss-theme", next);
    } catch {}
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      className="grid size-9 place-items-center rounded-full border border-line text-muted transition-colors hover:text-fg hover:border-fg/30 active:scale-[0.97]"
    >
      {theme === "dark" ? (
        <Sun size={17} weight="bold" />
      ) : (
        <Moon size={17} weight="bold" />
      )}
    </button>
  );
}
