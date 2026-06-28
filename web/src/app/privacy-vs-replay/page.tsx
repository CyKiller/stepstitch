import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, Check, Minus } from "@phosphor-icons/react/dist/ssr";
import { Section, SectionHeader } from "@/components/section";
import { Reveal } from "@/components/reveal";
import { Button } from "@/components/button";

export const metadata: Metadata = {
  title: "Privacy-first alternative to session replay — StepStitch",
  description:
    "A privacy-first alternative to session replay (FullStory, LogRocket, OpenReplay). StepStitch turns a user-reported bug into an executable Playwright regression test — without recording screens, keystrokes, page text, or PII. Built for regulated teams.",
  alternates: { canonical: "/privacy-vs-replay" },
  openGraph: {
    title: "Privacy-first alternative to session replay — StepStitch",
    description:
      "Don't ship a recording of your users to a vendor. StepStitch is capture-minimized by design and produces a regression test, not a replay.",
    url: "/privacy-vs-replay",
  },
};

const categories = [
  {
    name: "Session replay",
    tag: "FullStory, LogRocket, OpenReplay",
    useful:
      "Great for watching exactly what a user did and seeing UX friction in context.",
    tradeoff:
      "Creates a replay/recording artifact of real sessions. Even with masking, the model is record-then-redact, and the recording itself is a thing to govern, store, and protect.",
  },
  {
    name: "Error tracking",
    tag: "Sentry, Datadog",
    useful:
      "Excellent at aggregating exceptions, stack traces, and release health at scale.",
    tradeoff:
      "Tells you something broke, but often stops short of a path to reproduce. An engineer still has to guess the steps that led there.",
  },
  {
    name: "Bug-report tools",
    tag: "Jam, Marker, BugHerd",
    useful:
      "Lower the friction of filing a good report and attach helpful context automatically.",
    tradeoff:
      "Frequently stop at context or a replay clip — the output is a richer ticket, not an executable test.",
  },
];

// Honest framing: every tool *can* be configured for privacy. The differentiator is what
// the output IS (a regression test) and that capture is minimized by default, not bolted on.
const matrix: {
  dimension: string;
  replay: boolean | "partial";
  errors: boolean | "partial";
  stepstitch: boolean | "partial";
  note: string;
}[] = [
  { dimension: "Capture-minimized by default", replay: "partial", errors: "partial", stepstitch: true, note: "Others can be configured to mask; StepStitch never captures the data in the first place." },
  { dimension: "Produces an executable regression test", replay: false, errors: false, stepstitch: true, note: "A deterministic Playwright repro, not a clip or a stack trace." },
  { dimension: "Replayability score / path-to-repro", replay: "partial", errors: false, stepstitch: true, note: "A 0–1 score grading how reproducible the issue is." },
  { dimension: "No screen/DOM recording artifact", replay: false, errors: true, stepstitch: true, note: "Nothing to store, govern, or leak." },
  { dimension: "Verified-fix evidence (red→green)", replay: false, errors: false, stepstitch: true, note: "CI confirms the repro failed before the fix and passes after." },
  { dimension: "Works where there's no screen to record", replay: false, errors: "partial", stepstitch: true, note: "AI agents, APIs, and backend flows leave no visual footprint for session replay; structural capture still works." },
];

function Cell({ value }: { value: boolean | "partial" }) {
  if (value === true) return <Check size={16} weight="bold" className="mx-auto text-ok" />;
  if (value === "partial")
    return <span className="mx-auto block text-center text-[12px] text-muted">configurable</span>;
  return <Minus size={16} weight="bold" className="mx-auto text-muted/50" />;
}

export default function PrivacyVsReplayPage() {
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
            eyebrow="An honest comparison"
            title="A recording to watch, or a test that stays fixed?"
            body="Session replay, error tracking, and bug-report tools are all genuinely useful — and most can be configured for privacy. We are not going to claim otherwise. The real difference is the output: those tools hand you a recording or a stack trace to interpret. StepStitch is capture-minimized by default and its output is an executable regression test, not a recording — one that fails on the bug and passes once it is fixed."
          />
        </div>

        {/* Fair take on each category */}
        <div className="mt-12 grid gap-3 md:grid-cols-3">
          {categories.map((c, i) => (
            <Reveal key={c.name} delay={i * 0.06}>
              <div className="flex h-full flex-col rounded-2xl border border-line bg-surface p-6">
                <h3 className="text-base font-semibold text-fg">{c.name}</h3>
                <p className="font-mono text-[11px] uppercase tracking-wide text-muted">
                  {c.tag}
                </p>
                <p className="mt-3 text-[13.5px] leading-relaxed text-fg/80">
                  <span className="font-medium text-fg">Useful for: </span>
                  {c.useful}
                </p>
                <p className="mt-3 text-[13.5px] leading-relaxed text-muted">
                  <span className="font-medium text-fg">The trade-off: </span>
                  {c.tradeoff}
                </p>
              </div>
            </Reveal>
          ))}
        </div>

        {/* Matrix */}
        <Reveal>
          <div className="mt-5 overflow-x-auto rounded-2xl border border-line bg-surface">
            <table className="w-full min-w-[640px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-line text-left">
                  <th className="px-5 py-4 font-semibold text-fg">Dimension</th>
                  <th className="px-3 py-4 text-center font-medium text-muted">Session replay</th>
                  <th className="px-3 py-4 text-center font-medium text-muted">Error tracking</th>
                  <th className="px-3 py-4 text-center font-semibold text-accent">StepStitch</th>
                </tr>
              </thead>
              <tbody>
                {matrix.map((row) => (
                  <tr key={row.dimension} className="border-b border-line last:border-0 align-top">
                    <td className="px-5 py-4">
                      <p className="font-medium text-fg">{row.dimension}</p>
                      <p className="mt-1 text-[12.5px] text-muted">{row.note}</p>
                    </td>
                    <td className="px-3 py-4"><Cell value={row.replay} /></td>
                    <td className="px-3 py-4"><Cell value={row.errors} /></td>
                    <td className="px-3 py-4"><Cell value={row.stepstitch} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Reveal>

        <Reveal>
          <div className="mt-5 rounded-2xl border border-line bg-surface p-6">
            <p className="text-[15px] leading-relaxed text-muted">
              The strongest claim we will make is the true one:{" "}
              <span className="text-fg">
                StepStitch is privacy-minimized by design and produces a regression test, not a
                recording.
              </span>{" "}
              It never captures screens, input values, page text, raw URLs, request/response bodies,
              cookies, headers, screenshots, raw console logs, or raw stack traces — so there is no
              recording artifact to govern in the first place.
            </p>
          </div>
        </Reveal>

        <Reveal>
          <div className="mt-10 flex flex-wrap items-center gap-3">
            <Button href="/demo" trailingIcon={null}>
              See what it produces
            </Button>
            <Button href="/security" variant="secondary" trailingIcon={null}>
              Read the privacy boundary
            </Button>
          </div>
        </Reveal>
      </Section>
    </main>
  );
}
