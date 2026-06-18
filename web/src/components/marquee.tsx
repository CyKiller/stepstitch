import type { ReactNode } from "react";

// One continuous horizontal marquee (capped at one per page). The track holds
// two copies of the children so the loop is seamless; pauses on hover.
export function Marquee({ children }: { children: ReactNode }) {
  return (
    <div className="marquee-paused relative overflow-hidden [mask-image:linear-gradient(to_right,transparent,#000_8%,#000_92%,transparent)]">
      <div className="marquee-track flex w-max items-center gap-3 py-1">
        <div className="flex shrink-0 items-center gap-3">{children}</div>
        <div aria-hidden className="flex shrink-0 items-center gap-3">
          {children}
        </div>
      </div>
    </div>
  );
}
