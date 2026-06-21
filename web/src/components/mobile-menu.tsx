"use client";

import { useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { List, X, GithubLogo } from "@phosphor-icons/react";
import { GITHUB_URL } from "@/lib/links";

type Link = { href: string; label: string; external?: boolean };

// Hamburger menu for < lg. Without this the nav links are unreachable on phones.
export function MobileMenu({ links }: { links: Link[] }) {
  const [open, setOpen] = useState(false);
  const reduce = useReducedMotion();

  return (
    <div className="lg:hidden">
      <button
        type="button"
        aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="grid size-11 place-items-center rounded-full border border-line text-fg transition-colors hover:border-fg/30"
      >
        {open ? <X size={17} weight="bold" /> : <List size={17} weight="bold" />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -8 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="absolute left-4 right-4 top-[4.5rem] z-50 rounded-2xl border border-line bg-bg/95 p-3 shadow-[0_24px_70px_-30px_color-mix(in_oklab,var(--accent)_45%,transparent)] backdrop-blur-xl"
          >
            <nav className="grid gap-1">
              {links.map((l) => (
                <a
                  key={l.href}
                  href={l.href}
                  target={l.external ? "_blank" : undefined}
                  rel={l.external ? "noreferrer" : undefined}
                  onClick={() => setOpen(false)}
                  className="rounded-lg px-3 py-2.5 text-sm font-medium text-fg transition-colors hover:bg-surface-2"
                >
                  {l.label}
                </a>
              ))}
              <div className="mt-2 flex items-center gap-2 border-t border-line pt-3">
                <a
                  href={GITHUB_URL}
                  target="_blank"
                  rel="noreferrer"
                  onClick={() => setOpen(false)}
                  className="grid size-10 place-items-center rounded-full border border-line text-muted"
                  aria-label="StepStitch on GitHub"
                >
                  <GithubLogo size={18} weight="bold" />
                </a>
                <Link
                  href="/#contact"
                  onClick={() => setOpen(false)}
                  className="flex-1 rounded-full bg-accent-solid py-2.5 text-center text-sm font-semibold text-accent-fg"
                >
                  Book a pilot
                </Link>
              </div>
            </nav>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
