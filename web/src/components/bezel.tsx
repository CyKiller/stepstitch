import type { ReactNode } from "react";

// Double-bezel (Doppelrand): an outer tray holding an inner core with
// concentric radii and an inset top highlight, so the panel reads like a glass
// plate set in a machined frame rather than a flat card.
export function Bezel({
  children,
  className,
  innerClassName,
}: {
  children: ReactNode;
  className?: string;
  innerClassName?: string;
}) {
  return (
    <div className={`bezel-outer border border-line/60 ${className ?? ""}`}>
      <div
        className={`bezel-inner h-full overflow-hidden border border-line bg-surface ${innerClassName ?? ""}`}
      >
        {children}
      </div>
    </div>
  );
}
