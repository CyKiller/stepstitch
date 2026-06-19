import Link from "next/link";
import { GithubLogo } from "@phosphor-icons/react/dist/ssr";
import { Wordmark } from "./wordmark";
import { ThemeToggle } from "./theme-toggle";
import { Button } from "./button";
import { GITHUB_URL } from "@/lib/links";

const links = [
  { href: "#how", label: "How it works" },
  { href: "#workflow", label: "Workflow" },
  { href: "#demo", label: "Live demo" },
  { href: "#compare", label: "Comparison" },
  { href: "#agents", label: "Agents" },
  { href: "#trust", label: "Trust" },
];

export function Nav() {
  return (
    <header className="sticky top-0 z-40">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <nav className="mt-4 flex h-14 items-center justify-between rounded-full border border-line/70 bg-bg/70 pl-5 pr-2 shadow-[0_10px_40px_-24px_color-mix(in_oklab,var(--accent)_45%,transparent)] backdrop-blur-xl">
          <Link href="#top" aria-label="StepStitch home">
            <Wordmark />
          </Link>

          <div className="hidden items-center gap-6 lg:flex">
            {links.map((l) => (
              <a
                key={l.href}
                href={l.href}
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
              className="hidden size-9 place-items-center rounded-full border border-line text-muted transition-colors hover:border-fg/30 hover:text-fg sm:grid"
            >
              <GithubLogo size={17} weight="bold" />
            </a>
            <ThemeToggle />
            <Button href="#contact">Book a pilot</Button>
          </div>
        </nav>
      </div>
    </header>
  );
}
