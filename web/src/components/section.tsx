import type { ReactNode } from "react";
import { Reveal } from "./reveal";

export function Section({
  id,
  children,
  className,
}: {
  id?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      id={id}
      className={`mx-auto max-w-7xl px-4 py-24 sm:px-6 md:py-32 ${className ?? ""}`}
    >
      {children}
    </section>
  );
}

// Vertical-stack header (headline on top, body below). No split-header,
// no floating corner paragraph. Eyebrow is optional and used sparingly.
export function SectionHeader({
  eyebrow,
  title,
  body,
  as = "h2",
}: {
  eyebrow?: string;
  title: ReactNode;
  body?: string;
  as?: "h1" | "h2";
}) {
  const Heading = as;

  return (
    <Reveal>
      <div className="max-w-2xl">
        {eyebrow ? (
          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-accent">
            {eyebrow}
          </p>
        ) : null}
        <Heading className="text-balance text-3xl font-semibold tracking-tight text-fg md:text-4xl">
          {title}
        </Heading>
        {body ? (
          <p className="mt-4 text-pretty text-lg leading-relaxed text-muted">
            {body}
          </p>
        ) : null}
      </div>
    </Reveal>
  );
}
