import { Eye, ShieldCheck, Package } from "@phosphor-icons/react/dist/ssr";
import type { Icon } from "@phosphor-icons/react";
import { Reveal } from "./reveal";
import { Section, SectionHeader } from "./section";
import { GITHUB_URL, NPM_URL } from "@/lib/links";

type Study = {
  name: string;
  role: string;
  lede: string;
  points: string[];
  icon: Icon;
};

// Real production deployments. Both repositories are private, so we name the
// integration and its proof points rather than linking into closed source.
const studies: Study[] = [
  {
    name: "Marvox",
    role: "Reference (dogfood) deployment",
    icon: ShieldCheck,
    lede: "StepStitch is a required subsystem — Marvox refuses to boot in production if the vendored evidence service cannot mount. It is load-bearing, not a plugin.",
    points: [
      "Server-side scrub boundary on every ingest — screens, input values and page text never reach storage, and free text is scrubbed",
      "Pinned and vendored, gated by ~20 tests covering drift, the privacy boundary, and a production boot check",
      "Bug reports compile into privacy-safe Playwright regressions — proposal-only, never run against production",
      "An operator-triggered fix loop confirms the repro is red, then opt-in opens a human-review PR that adds it as a skip-marked test — it never edits product code or auto-merges",
    ],
  },
  {
    name: "aGentSyS",
    role: "Agentic connector showcase",
    icon: Eye,
    lede: "StepStitch docks into the swarm as a capability cartridge — a secure modal that turns “a copilot tells you things” into a network that can safely act on what actually broke.",
    points: [
      "A named “Diagnostics & Repro” agent, powered by StepStitch, joins the core roster",
      "Consumed over a frozen OpenAPI surface, re-exposed to every agent as MCP tools",
      "Evidence is governance-gated — policy clears the write before any agent acts on a draft",
    ],
  },
];

export function CaseStudies() {
  return (
    <Section id="production" className="border-b border-line">
      <SectionHeader
        title="Running in production — starting with our own"
        body="StepStitch isn't a demo. We run it as a required, boot-blocking subsystem in our own products — the evidence layer one refuses to start without, and the source of truth an agent swarm acts on. Your team's deployment is next."
      />

      <div className="mt-12 grid gap-5 lg:grid-cols-2">
        {studies.map((s, i) => {
          const Glyph = s.icon;
          return (
            <Reveal key={s.name} delay={i * 0.08}>
              <div className="flex h-full flex-col rounded-2xl border border-line bg-surface p-7 md:p-8">
                <div className="flex items-center gap-2.5">
                  <span className="grid size-9 place-items-center rounded-xl border border-line bg-surface-2/50 text-accent">
                    <Glyph size={18} weight="bold" />
                  </span>
                  <div>
                    <h3 className="text-base font-semibold text-fg">
                      {s.name}
                    </h3>
                    <p className="font-mono text-[11.5px] uppercase tracking-wide text-muted">
                      {s.role}
                    </p>
                  </div>
                </div>
                <p className="mt-5 text-[15px] leading-relaxed text-fg">
                  {s.lede}
                </p>
                <ul className="mt-5 space-y-2.5 text-[14px] text-muted">
                  {s.points.map((p) => (
                    <li key={p} className="flex gap-2.5">
                      <span
                        aria-hidden
                        className="mt-2 size-1.5 shrink-0 rounded-full bg-accent"
                      />
                      <span>{p}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </Reveal>
          );
        })}
      </div>

      <Reveal className="mt-8">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted">
          <span>Want to be the next one?</span>
          <a
            href={NPM_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 font-semibold text-accent hover:underline"
          >
            <Package size={15} weight="bold" />
            Install @stepstitch/tracker
          </a>
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noreferrer"
            className="font-semibold text-accent hover:underline"
          >
            Star it on GitHub
          </a>
        </div>
      </Reveal>
    </Section>
  );
}
