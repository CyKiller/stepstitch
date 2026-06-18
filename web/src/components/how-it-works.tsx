import {
  Eye,
  Gauge,
  Code,
  CheckCircle,
  GitPullRequest,
} from "@phosphor-icons/react/dist/ssr";
import type { Icon } from "@phosphor-icons/react";
import { Reveal } from "./reveal";
import { Section, SectionHeader } from "./section";

type Step = {
  icon: Icon;
  title: string;
  desc: string;
  tool: string;
};

const steps: Step[] = [
  {
    icon: Eye,
    title: "Perceive",
    desc: "A user reports a bug. StepStitch stores a scrubbed, structural trace.",
    tool: "list_recent_traces",
  },
  {
    icon: Gauge,
    title: "Score",
    desc: "A deterministic 0 to 1 score and an A to F grade say if it reproduces.",
    tool: "get_replayability_score",
  },
  {
    icon: Code,
    title: "Reproduce",
    desc: "Fetch a deterministic Playwright test built from the trace. Text only.",
    tool: "generate_playwright_repro",
  },
  {
    icon: CheckCircle,
    title: "Verify",
    desc: "Run it in your CI or sandbox. Red turns green once the fix lands.",
    tool: "get_verifications",
  },
  {
    icon: GitPullRequest,
    title: "Fix, human-gated",
    desc: "Open a pull request with the regression test. A reviewer merges, never the agent.",
    tool: "github_bridge",
  },
];

export function HowItWorks() {
  return (
    <Section id="how" className="border-y border-line">
      <SectionHeader
        title="From one report to a merged fix"
        body="StepStitch perceives, scores, compiles, and drafts. It never plans or acts on its own. The autonomy stays in your stack."
      />

      <div className="relative mt-14 grid gap-y-8 md:grid-cols-5 md:gap-x-5">
        {/* Connector line behind the step nodes (desktop). The surface-filled
            icon circles sit on top, reading as connected pipeline stages. */}
        <div
          aria-hidden
          className="animate-shimmer absolute left-[10%] right-[10%] top-5 hidden h-px md:block"
          style={{
            backgroundImage:
              "linear-gradient(100deg, var(--color-accent), var(--color-accent-2), var(--color-accent))",
            backgroundSize: "220% auto",
            opacity: 0.6,
          }}
        />
        {steps.map((s, i) => {
          const Glyph = s.icon;
          return (
            <Reveal key={s.title} delay={i * 0.06}>
              <div className="relative h-full">
                <div className="flex items-center gap-3 md:block">
                  <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-line bg-surface text-accent shadow-[0_0_0_4px_var(--color-bg)]">
                    <Glyph size={20} weight="bold" />
                  </span>
                  <h3 className="text-base font-semibold text-fg md:mt-4">
                    {s.title}
                  </h3>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-muted">
                  {s.desc}
                </p>
                <p className="mt-3 font-mono text-[11.5px] text-accent/90">
                  {s.tool}
                </p>
              </div>
            </Reveal>
          );
        })}
      </div>
    </Section>
  );
}
