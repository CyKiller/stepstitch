import { Plugs, Lock } from "@phosphor-icons/react/dist/ssr";
import { Reveal } from "./reveal";
import { Section, SectionHeader } from "./section";
import { Marquee } from "./marquee";

const tools = [
  "list_recent_traces",
  "get_trace_summary",
  "get_replayability_score",
  "get_privacy_posture",
  "get_diagnostic_summary",
  "generate_playwright_repro",
  "match_verified_fixes",
  "get_attestation",
  "get_fragility_map",
  "generate_minimal_repro",
  "create_export_preview",
  "create_fs_export_preview",
];

const consumers = [
  "Microsoft Copilot Studio",
  "OpenAI",
  "Claude",
  "LangGraph",
  "AWS Bedrock",
  "Google Vertex",
];

function ConsumerChip({ name }: { name: string }) {
  return (
    <div className="flex shrink-0 items-center gap-2.5 rounded-xl border border-line bg-surface px-4 py-3">
      <span className="grid size-6 shrink-0 place-items-center rounded-md bg-surface-2 font-mono text-[11px] font-semibold text-accent">
        {name[0]}
      </span>
      <span className="whitespace-nowrap text-sm font-medium text-fg">
        {name}
      </span>
    </div>
  );
}

export function Agentic() {
  return (
    <Section id="agents" className="border-b border-line">
      <SectionHeader
        title="Bring your own agentic network"
        body="StepStitch is a capability provider, not an agent orchestrator. One MCP server surfaces twelve read-only and draft tools — including structural fix-memory, signed evidence attestation, and fragility prediction. Any agent network consumes them. The autonomy lives in your stack."
      />

      <div className="mt-12 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Reveal>
          <div className="h-full rounded-2xl border border-line bg-surface p-6">
            <div className="flex items-center gap-2.5">
              <Plugs size={18} weight="bold" className="text-accent" />
              <h3 className="text-base font-semibold text-fg">
                Twelve Copilot-safe tools
              </h3>
            </div>
            <div className="mt-5 grid grid-cols-1 gap-x-6 gap-y-2.5 sm:grid-cols-2">
              {tools.map((t) => (
                <code
                  key={t}
                  className="font-mono text-[12.5px] text-muted"
                >
                  {t}
                </code>
              ))}
            </div>
            <div className="mt-6 flex items-start gap-2 rounded-lg border border-line bg-surface-2/50 px-3.5 py-3 text-[13px] text-muted">
              <Lock
                size={15}
                weight="bold"
                className="mt-0.5 shrink-0 text-accent"
              />
              <span>
                Destructive operations stay off the agent surface. Delete,
                purge, kill switch, and direct writes are admin-only and
                human-gated.
              </span>
            </div>
          </div>
        </Reveal>

        <Reveal delay={0.08}>
          <div className="h-full rounded-2xl border border-line bg-surface p-6">
            <h3 className="text-base font-semibold text-fg">
              Works with any MCP client
            </h3>
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              The same contract is surfaced three ways: an MCP server, an
              OpenAPI connector for Copilot Studio, and function specs for
              tool-calling models.
            </p>
            <div className="mt-5">
              <Marquee>
                {consumers.map((c) => (
                  <ConsumerChip key={c} name={c} />
                ))}
              </Marquee>
            </div>
          </div>
        </Reveal>
      </div>
    </Section>
  );
}
