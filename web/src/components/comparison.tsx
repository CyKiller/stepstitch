import { Check, X, Minus } from "@phosphor-icons/react/dist/ssr";
import { Reveal } from "./reveal";
import { Section, SectionHeader } from "./section";

type Cell = { kind: "yes" | "no" | "partial"; text: string };
type Row = { axis: string; replay: Cell; apm: Cell; stitch: Cell };

const rows: Row[] = [
  {
    axis: "Captures screens, page text, input values",
    replay: { kind: "no", text: "By default" },
    apm: { kind: "partial", text: "Often" },
    stitch: { kind: "yes", text: "Never" },
  },
  {
    axis: "PII risk in a third-party tool",
    replay: { kind: "no", text: "High" },
    apm: { kind: "partial", text: "Medium" },
    stitch: { kind: "yes", text: "Nothing sensitive captured" },
  },
  {
    axis: "Proves the bug is reproducible",
    replay: { kind: "no", text: "No" },
    apm: { kind: "no", text: "No" },
    stitch: { kind: "yes", text: "0 to 1 score, A to F grade" },
  },
  {
    axis: "Output is a regression test",
    replay: { kind: "no", text: "A video" },
    apm: { kind: "no", text: "A stack trace" },
    stitch: { kind: "yes", text: "Playwright test" },
  },
  {
    axis: "Self-hosted and auditable",
    replay: { kind: "no", text: "SaaS only" },
    apm: { kind: "no", text: "SaaS only" },
    stitch: { kind: "yes", text: "Apache-2.0, self-host" },
  },
  {
    axis: "Native to agent networks",
    replay: { kind: "no", text: "No" },
    apm: { kind: "no", text: "No" },
    stitch: { kind: "yes", text: "MCP, 8 read-only tools" },
  },
];

function Mark({ cell, accent }: { cell: Cell; accent?: boolean }) {
  const Icon = cell.kind === "yes" ? Check : cell.kind === "partial" ? Minus : X;
  const color =
    cell.kind === "yes"
      ? accent
        ? "text-ok"
        : "text-muted"
      : cell.kind === "partial"
        ? "text-muted"
        : "text-muted";
  return (
    <div className="flex items-center gap-2">
      <Icon size={15} weight="bold" className={color} />
      <span className={accent ? "text-fg" : "text-muted"}>{cell.text}</span>
    </div>
  );
}

export function Comparison() {
  return (
    <Section id="compare" className="border-b border-line">
      <SectionHeader
        title="Not session replay, not error tracking"
        body="Those tools tell you something broke. StepStitch hands you a test that proves it, with nothing sensitive leaving your boundary."
      />

      <Reveal>
        <div className="mt-12 overflow-x-auto rounded-2xl border border-line">
          <table className="w-full min-w-[680px] border-collapse text-sm">
            <thead>
              <tr className="bg-surface-2/60">
                <th className="w-[28%] p-4 text-left font-medium text-muted">
                  Capability
                </th>
                <th className="p-4 text-left font-semibold text-fg">
                  Session replay
                  <span className="block text-xs font-normal text-muted">
                    e.g. FullStory, LogRocket
                  </span>
                </th>
                <th className="p-4 text-left font-semibold text-fg">
                  APM and error tracking
                  <span className="block text-xs font-normal text-muted">
                    e.g. Sentry, Datadog
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
