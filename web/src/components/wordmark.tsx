// Simple geometric wordmark: two offset stitch bars resolving into one mark.
// Inline SVG mark + text; renders in both themes via currentColor.
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className ?? ""}`}>
      <svg
        width="22"
        height="22"
        viewBox="0 0 22 22"
        fill="none"
        aria-hidden="true"
        className="text-accent"
      >
        <rect x="2" y="4" width="13" height="3.2" rx="1.6" fill="currentColor" />
        <rect
          x="7"
          y="9.4"
          width="13"
          height="3.2"
          rx="1.6"
          fill="currentColor"
          opacity="0.55"
        />
        <rect
          x="2"
          y="14.8"
          width="13"
          height="3.2"
          rx="1.6"
          fill="currentColor"
        />
      </svg>
      <span className="text-[15px] font-semibold tracking-tight text-fg">
        StepStitch
      </span>
    </span>
  );
}
