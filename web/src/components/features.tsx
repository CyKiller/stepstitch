import {
  ShieldCheck,
  Gauge,
  Code,
  SlidersHorizontal,
  GitPullRequest,
  ChartLine,
} from "@phosphor-icons/react/dist/ssr";
import { Reveal } from "./reveal";
import { Section, SectionHeader } from "./section";
import { SpotlightCard } from "./spotlight-card";

const profiles = [
  "financial-services-enterprise",
  "healthcare-strict",
  "internal-enterprise",
  "open-source-default",
];

const adapters = [
  "ServiceNow",
  "Salesforce",
  "Genesys",
  "Jira",
  "Zendesk",
];

function Tile({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <SpotlightCard
      className={`rounded-2xl border border-line bg-surface p-6 ${className ?? ""}`}
    >
      {children}
    </SpotlightCard>
  );
}

function Head({
  icon: Icon,
  title,
}: {
  icon: React.ComponentType<{ size?: number; weight?: "bold"; className?: string }>;
  title: string;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <Icon size={18} weight="bold" className="text-accent" />
      <h3 className="text-base font-semibold text-fg">{title}</h3>
    </div>
  );
}

export function Features() {
  return (
    <Section id="features" className="border-b border-line">
      <SectionHeader
        eyebrow="What ships today"
        title="A capability surface, not a roadmap"
        body="Every piece below is in the open-source repository, backed by a named test. Nothing here is a promise."
      />

      <div className="mt-12 grid auto-rows-fr gap-4 md:grid-cols-3">
        {/* Privacy: wide, tinted, with the never-captured chips */}
        <Reveal className="md:col-span-2">
          <Tile className="h-full [background:linear-gradient(135deg,color-mix(in_oklab,var(--accent-solid)_7%,var(--surface)),var(--surface))]">
            <Head icon={ShieldCheck} title="Two-layer privacy boundary" />
            <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-muted">
              The SDK redacts in the page, but the backend never trusts the
              client. Every trace is scrubbed again on the server before it is
              stored. Defense in depth, proven by a named test.
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              {[
                "screenshots",
                "input values",
                "page text",
                "raw URLs",
                "request bodies",
                "cookies & headers",
                "SSNs & card numbers",
              ].map((c) => (
                <span
                  key={c}
                  className="rounded-md border border-line bg-surface px-2 py-1 font-mono text-[11.5px] text-muted line-through decoration-bad/50"
                >
                  {c}
                </span>
              ))}
            </div>
          </Tile>
        </Reveal>

        {/* Replayability */}
        <Reveal delay={0.05}>
          <Tile className="h-full">
            <Head icon={Gauge} title="Replayability score" />
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              A deterministic 0 to 1 score with an A to F grade and warnings.
              Decide if a bug reproduces before anyone opens an editor.
            </p>
          </Tile>
        </Reveal>

        {/* Profiles */}
        <Reveal delay={0.05}>
          <Tile className="h-full">
            <Head icon={SlidersHorizontal} title="Deployment profiles" />
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              A profile can only tighten the privacy boundary, never loosen it.
            </p>
            <ul className="mt-4 space-y-1.5 font-mono text-[12px] text-muted">
              {profiles.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </Tile>
        </Reveal>

        {/* Adapters with real logos */}
        <Reveal delay={0.1}>
          <Tile className="h-full">
            <h3 className="text-base font-semibold text-fg">
              Drafts into your system of record
            </h3>
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              Flat, sanitized drafts. Draft-only, never an autonomous write.
            </p>
            <div className="mt-5 flex flex-wrap items-center gap-2">
              {adapters.map((a) => (
                <span
                  key={a}
                  className="rounded-md border border-line bg-surface-2/50 px-2.5 py-1 text-[13px] font-medium text-fg"
                >
                  {a}
                </span>
              ))}
              <span className="font-mono text-[12px] text-muted">
                + DraftAdapter SDK
              </span>
            </div>
          </Tile>
        </Reveal>

        {/* Playwright compiler */}
        <Reveal delay={0.1}>
          <Tile className="h-full">
            <Head icon={Code} title="Deterministic compiler" />
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              The same trace always compiles the same Playwright test. Text
              only, never run against production.
            </p>
          </Tile>
        </Reveal>

        {/* Repair loop + verified fix: wide */}
        <Reveal delay={0.05} className="md:col-span-2">
          <Tile className="h-full">
            <Head icon={GitPullRequest} title="Repair loop and verified-fix corpus" />
            <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-muted">
              A trace becomes a labeled GitHub issue and a regression-test pull
              request. A reviewer merges, never the agent. Only a pre-fail to
              post-pass transition is recorded as confirmed fixed.
            </p>
            <div className="mt-5 inline-flex items-center gap-3 rounded-lg border border-line bg-surface-2/50 px-4 py-2.5 font-mono text-[12.5px]">
              <span className="text-bad">pre: fail</span>
              <span className="text-muted">to</span>
              <span className="text-ok">post: pass</span>
              <span className="text-muted">=</span>
              <span className="text-fg">confirmed_fixed</span>
            </div>
          </Tile>
        </Reveal>

        {/* Observability */}
        <Reveal delay={0.1}>
          <Tile className="h-full">
            <Head icon={ChartLine} title="Observability and kill switch" />
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              A zero-dependency Prometheus endpoint, audited reads, and an
              org-wide kill switch that fails safe on error.
            </p>
          </Tile>
        </Reveal>
      </div>
    </Section>
  );
}
