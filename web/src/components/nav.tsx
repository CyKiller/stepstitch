import Link from "next/link";
import { GithubLogo } from "@phosphor-icons/react/dist/ssr";
import { Wordmark } from "./wordmark";
import { ThemeToggle } from "./theme-toggle";
import { Button } from "./button";
import { MobileMenu } from "./mobile-menu";
import { GITHUB_URL, DOCS_URL } from "@/lib/links";

// Anchors are absolute (/#id) so they work from sub-pages too.
const desktopLinks = [
  { href: "/#how", label: "How it works" },
  { href: "/#demo", label: "Live demo" },
  { href: "/#compare", label: "Comparison" },
  { href: "/security", label: "Security" },
  { href: DOCS_URL, label: "Docs", external: true },
];

const mobileLinks = [
  { href: "/#how", label: "How it works" },
  { href: "/#workflow", label: "Workflow" },
  { href: "/#demo", label: "Live demo" },
  { href: "/#compare", label: "Comparison" },
  { href: "/#agents", label: "Agents" },
  { href: "/security", label: "Security" },
  { href: "/self-host", label: "Self-host" },
  { href: DOCS_URL, label: "Docs", external: true },
];

export function Nav() {
  return (
    <header className="sticky top-0 z-40">
      <div className="relative mx-auto max-w-7xl px-4 sm:px-6">
        <nav className="mt-4 flex h-14 items-center justify-between rounded-full border border-line/70 bg-bg/70 pl-5 pr-2 shadow-[0_10px_40px_-24px_color-mix(in_oklab,var(--accent)_45%,transparent)] backdrop-blur-xl">
          <Link href="/" aria-label="StepStitch home">
            <Wordmark />
          </Link>

          <div className="hidden items-center gap-6 lg:flex">
            {desktopLinks.map((l) => (
              <a
                key={l.href}
                href={l.href}
                target={l.external ? "_blank" : undefined}
                rel={l.external ? "noreferrer" : undefined}
                className="group relative text-sm text-muted transition-colors hover:text-fg"
              >
                {l.label}
                <span className="absolute -bottom-1.5 left-0 h-px w-full origin-left scale-x-0 bg-accent transition-transform duration-300 ease-[var(--ease-spring)] group-hover:scale-x-100" />
              </a>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noreferrer"
              aria-label="StepStitch on GitHub"
              className="hidden size-11 place-items-center rounded-full border border-line text-muted transition-colors hover:border-fg/30 hover:text-fg sm:grid"
            >
              <GithubLogo size={17} weight="bold" />
            </a>
            <ThemeToggle />
            <div className="hidden sm:block">
              <Button href="/#contact">Book a pilot</Button>
            </div>
            <MobileMenu links={mobileLinks} />
          </div>
        </nav>
      </div>
    </header>
  );
}
