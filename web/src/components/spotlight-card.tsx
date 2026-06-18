"use client";

import type { ReactNode } from "react";

// Card that lifts on hover and shows a cursor-following emerald spotlight.
// The spotlight (::after) and lift are CSS; reduced-motion users keep the lift
// off via the media query on the transition utility is acceptable (transform
// hover is a discrete state change, not continuous motion).
export function SpotlightCard({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  function onMove(e: React.MouseEvent<HTMLDivElement>) {
    const el = e.currentTarget;
    const rect = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${e.clientX - rect.left}px`);
    el.style.setProperty("--my", `${e.clientY - rect.top}px`);
  }

  return (
    <div
      onMouseMove={onMove}
      className={`spotlight relative transition-[transform,border-color] duration-300 ease-[var(--ease-spring)] hover:-translate-y-1 hover:border-accent/40 ${className ?? ""}`}
    >
      {children}
    </div>
  );
}
