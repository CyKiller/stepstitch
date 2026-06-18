// Ambient hero backdrop: two slow-drifting emerald/teal glows behind a soft
// grid. Pure CSS animation (paused under prefers-reduced-motion via globals).
// Decorative only, pointer-events-none, sits behind content.
export function Aurora() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      <div className="animate-aurora absolute -left-[8%] -top-[18%] h-[68vh] w-[68vh] rounded-full opacity-90 blur-[90px] [background:radial-gradient(circle,color-mix(in_oklab,var(--accent)_55%,transparent),transparent_68%)]" />
      <div className="animate-aurora absolute -right-[6%] -top-[8%] h-[60vh] w-[60vh] rounded-full opacity-80 blur-[90px] [animation-delay:-9s] [background:radial-gradient(circle,color-mix(in_oklab,var(--accent-2)_50%,transparent),transparent_68%)]" />
      <div className="animate-aurora absolute -bottom-[28%] left-[28%] h-[46vh] w-[46vh] rounded-full opacity-60 blur-[90px] [animation-delay:-4s] [background:radial-gradient(circle,color-mix(in_oklab,var(--accent)_40%,transparent),transparent_70%)]" />
      {/* faint grid that organizes the space, fading toward the bottom */}
      <div className="absolute inset-0 opacity-60 [background-image:linear-gradient(to_right,color-mix(in_oklab,var(--line)_70%,transparent)_1px,transparent_1px),linear-gradient(to_bottom,color-mix(in_oklab,var(--line)_70%,transparent)_1px,transparent_1px)] [background-size:54px_54px] [mask-image:radial-gradient(130%_95%_at_50%_0%,#000_28%,transparent_72%)]" />
    </div>
  );
}
