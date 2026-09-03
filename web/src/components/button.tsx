import { ArrowRight } from "@phosphor-icons/react/dist/ssr";
import type { Icon } from "@phosphor-icons/react";

// Island CTA: a pill whose trailing icon lives in its own circular wrapper and
// reacts on hover (button-in-button kinetic tension). Spring easing, no naked
// arrow. Primary = accent fill with brand-tinted glow; secondary = glass.
export function Button({
  href,
  children,
  variant = "primary",
  external = false,
  leadingIcon: Leading,
  trailingIcon: Trailing = ArrowRight,
  event,
}: {
  href: string;
  children: React.ReactNode;
  variant?: "primary" | "secondary";
  external?: boolean;
  leadingIcon?: Icon;
  trailingIcon?: Icon | null;
  event?: string;
}) {
  const ext = external ? { target: "_blank", rel: "noreferrer" } : {};
  const base =
    "group inline-flex min-h-11 items-center gap-2.5 rounded-full py-2 pl-5 pr-2 text-sm font-semibold transition-[transform,box-shadow,border-color] duration-300 ease-[var(--ease-spring)] active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-solid focus-visible:ring-offset-2 focus-visible:ring-offset-bg";
  const skin =
    variant === "primary"
      ? "bg-accent-solid text-accent-fg shadow-[var(--shadow-brand)] hover:shadow-[0_28px_80px_-28px_color-mix(in_oklab,var(--accent)_70%,transparent)]"
      : "border border-line bg-surface/70 text-fg backdrop-blur-sm hover:border-fg/30";
  const iconWrap =
    variant === "primary"
      ? "bg-black/15 dark:bg-black/25"
      : "bg-surface-2 text-accent";

  return (
    <a
      href={href}
      {...ext}
      data-analytics-event={event}
      className={`${base} ${skin}`}
    >
      {Leading ? <Leading size={16} weight="bold" /> : null}
      <span>{children}</span>
      {Trailing ? (
        <span
          className={`grid size-8 place-items-center rounded-full transition-transform duration-300 ease-[var(--ease-spring)] group-hover:translate-x-0.5 group-hover:-translate-y-px ${iconWrap}`}
        >
          <Trailing size={15} weight="bold" />
        </span>
      ) : null}
    </a>
  );
}
