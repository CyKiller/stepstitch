import { Check, X, Minus } from "@phosphor-icons/react/dist/ssr";
import { Reveal } from "./reveal";
import { Section, SectionHeader } from "./section";
import { MCP_TOOL_COUNT } from "@/lib/mcp-tools";

type Cell = { kind: "yes" | "no" | "partial"; text: string };
type Row = {
  axis: string;
  replay: Cell;
  openreplay: Cell;
  apm: Cell;
  stitch: Cell;
};

const rows: Row[] = [
  {
    axis: "Captures screens, page text, input values",
    replay: { kind: "no", text: "By default" },
    openreplay: { kind: "no", text: "Records DOM" },
    apm: { kind: "partial", text: "Often" },
    stitch: { kind: "yes", text: "Never" },
  },
  {
    axis: "PII risk in the tool",
    replay: { kind: "no", text: "High" },
    openreplay: { kind: "partial", text: "Medium" },
    apm: { kind: "partial", text: "Medium" },
    stitch: { kind: "yes", text: "No screens, values or PII captured" },
  },
  {
    axis: "Proves the bug is reproducible",
    replay: { kind: "no", text: "No" },
    openreplay: { kind: "no", text: "No" },
    apm: { kind: "no", text: "No" },
    stitch: { kind: "yes", text: "0 to 1 score, A to F grade" },
  },
  {
    axis: "Output is a regression test",
    replay: { kind: "no", text: "A video" },
    openreplay: { kind: "partial", text: "Exports a script" },
    apm: { kind: "no", text: "A stack trace" },
    stitch: { kind: "yes", text: "Asserting Playwright test" },
  },
  {
    axis: "Self-hosted and auditable",
    replay: { kind: "no", text: "SaaS only" },
    openreplay: { kind: "yes", text: "Open source" },
    apm: { kind: "no", text: "SaaS only" },
    stitch: { kind: "yes", text: "Apache-2.0, self-host" },
  },
  {
    axis: "Native to agent networks",
    replay: { kind: "no", text: "No" },
    openreplay: { kind: "no", text: "No" },
    apm: { kind: "no", text: "No" },
    stitch: { kind: "yes", text: `MCP, ${MCP_TOOL_COUNT} scoped tools` },
  },
];

function Mark({ cell, accent }: { cell: Cell; accent?: boolean }) {
  const Icon = cell.kind === "yes" ? Check : cell.kind === "partial" ? Minus : X;
  return (
    <div className="flex items-center gap-2">
      <Icon
        size={15}
        weight="bold"
        className={cell.kind === "yes" && accent ? "text-ok" : "text-muted"}
      />
      <span className={accent ? "text-fg" : "text-muted"}>{cell.text}</span>
    </div>
  );
}

export function Comparison() {
  return (
    <Section id="compare" className="border-b border-line">
      <SectionHeader
        title="Not session replay, not error tracking"
        body="Those tools tell you something broke. StepStitch hands you a test that proves it, with nothing sensitive leaving your boundary. Even the open-source replay tools still record the screen."
      />

      <Reveal>
        <div className="mt-12 overflow-x-auto rounded-2xl border border-line">
          <table className="w-full min-w-[860px] border-collapse text-sm">
            <thead>
              <tr className="bg-surface-2/60">
                <th className="w-[24%] p-4 text-left font-medium text-muted">
                  Capability
                </th>
                <th className="p-4 text-left font-semibold text-fg">
                  Session replay
                  <span className="block text-xs font-normal text-muted">
                    FullStory, LogRocket
                  </span>
                </th>
                <th className="p-4 text-left font-semibold text-fg">
                  OpenReplay
                  <span className="block text-xs font-normal text-muted">
                    Open-source replay
                  </span>
                </th>
                <th className="p-4 text-left font-semibold text-fg">
                  APM and errors
                  <span className="block text-xs font-normal text-muted">
                    Sentry, Datadog
                  </span>
                </th>
                <th className="p-4 text-left font-semibold text-accent ring-1 ring-inset ring-accent-solid/30">
                  StepStitch
                  <span className="block text-xs font-normal text-muted">
                    Issue-to-repro
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.axis} className="border-t border-line bg-surface">
                  <td className="p-4 align-top font-medium text-fg">{r.axis}</td>
                  <td className="p-4 align-top">
                    <Mark cell={r.replay} />
                  </td>
                  <td className="p-4 align-top">
                    <Mark cell={r.openreplay} />
                  </td>
                  <td className="p-4 align-top">
                    <Mark cell={r.apm} />
                  </td>
                  <td className="bg-accent-solid/[0.04] p-4 align-top ring-1 ring-inset ring-accent-solid/20">
                    <Mark cell={r.stitch} accent />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Reveal>
    </Section>
  );
}
