import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, Code, User, Buildings } from "@phosphor-icons/react/dist/ssr";
import { Section, SectionHeader } from "@/components/section";
import { Reveal } from "@/components/reveal";
import { Button } from "@/components/button";

export const metadata: Metadata = {
  title: "Who StepStitch is for — StepStitch",
  description:
    "StepStitch turns a user-reported bug into safe evidence developers can actually use — without recording the user's screen, typing, or private data. What that means for developers, users, and enterprises.",
  alternates: { canonical: "/who-its-for" },
  openGraph: {
    title: "Who StepStitch is for — StepStitch",
    description:
      "One report, no raw user data, three people who need different things from it: the developer fixing it, the user who filed it, and the enterprise governing it.",
    url: "/who-its-for",
  },
};

const audiences = [
  {
    icon: Code,
    label: "Developer",
    quote: "Fix real user bugs with AI agents without leaking user data.",
    body: "A bug report becomes a replayability-scored, deterministic Playwright test — the same trace, the same repro, every time. An MCP-connected agent reads the sanitized evidence directly, with no raw user data ever in its context.",
  },
  {
    icon: User,
    label: "User",
    quote: "Your issue can be fixed without recording your screen, typing, account info, or private data.",
    body: "StepStitch never captures screens, keystrokes, input values, or page text — by default, not as a setting someone has to remember to turn on. What reaches storage is structure: which control, which route, in what order.",
  },
  {
    icon: Buildings,
    label: "Enterprise",
    quote: "Support, QA, engineering, and compliance get one safe evidence trail.",
    body: "Every trace carries a scrub report, a replayability grade, and — when you want it — a signed, independently-verifiable attestation. Self-hosted by default; governance (SSO, audit retention, compliance packs) is additive, never a prerequisite.",
  },
];

export default function WhoItsForPage() {
  return (
    <main id="main" className="flex-1">
      <Section className="pt-12">
        <Reveal>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-fg"
          >
            <ArrowLeft size={14} weight="bold" /> Back home
          </Link>
        </Reveal>
        <div className="mt-6">
          <SectionHeader
            eyebrow="Who it's for"
            title="One report, no raw user data — three different people need it"
            body="When a user reports a bug, StepStitch turns that report into safe evidence developers can actually use. It does not record the user's screen or private information. It creates a clean reproduction test, checks whether this bug has happened before, and gives developers or AI agents a safe packet to help fix it."
          />
        </div>

        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {audiences.map((a, i) => {
            const Glyph = a.icon;
            return (
              <Reveal key={a.label} delay={i * 0.08}>
                <div className="flex h-full flex-col rounded-2xl border border-line bg-surface p-7">
                  <span className="grid size-9 place-items-center rounded-xl border border-line bg-surface-2/50 text-accent">
                    <Glyph size={18} weight="bold" />
                  </span>
                  <p className="mt-4 font-mono text-[11.5px] uppercase tracking-wide text-muted">
                    {a.label}
                  </p>
                  <p className="mt-2 text-[17px] font-semibold leading-snug text-fg">
                    &ldquo;{a.quote}&rdquo;
                  </p>
                  <p className="mt-4 text-[14px] leading-relaxed text-muted">
                    {a.body}
                  </p>
                </div>
              </Reveal>
            );
          })}
        </div>

        <Reveal>
          <div className="mt-10 flex flex-wrap items-center gap-3">
            <Button href="/quickstart" trailingIcon={null}>
              Try the 10-minute quickstart
            </Button>
            <Button href="/self-host" variant="secondary" trailingIcon={null}>
              Self-host free
            </Button>
          </div>
        </Reveal>
      </Section>
    </main>
  );
}
