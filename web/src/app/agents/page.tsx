import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowLeft,
  Check,
  Prohibit,
  UserCheck,
  Plugs,
} from "@phosphor-icons/react/dist/ssr";
import { Section, SectionHeader } from "@/components/section";
import { Reveal } from "@/components/reveal";
import { Button } from "@/components/button";
import { GITHUB_URL } from "@/lib/links";

export const metadata: Metadata = {
  title: "Agents & MCP — StepStitch",
  description:
    "StepStitch exposes a read-only / draft-only surface to agents over MCP, OpenAPI, and function-calling. Agents can read safe summaries and create drafts; they cannot delete, purge, change retention, read raw traces, write records, or merge. Human approval is the control point.",
};

const surfaces = [
  ["MCP server", "A universal connector for Copilot Studio, Claude, OpenAI, Bedrock, LangGraph, and any MCP client — the same safe operations everywhere."],
  ["OpenAPI spec", "openapi-v2.json describes the read-only / draft tools for connector platforms that consume OpenAPI."],
  ["Function specs", "The identical capability list, exposed as function-calling tool definitions."],
];

const canDo = [
  "Read sanitized trace summaries (structure only, never raw footsteps)",
  "Read the replayability score and grade",
  "Read sanitized diagnostics and the recommended next step",
  "Read the privacy posture and scrub report",
  "Generate a deterministic Playwright reproduction",
  "Match a bug against the verified-fix corpus — “you’ve fixed this shape before”",
  "Get a signed, independently-verifiable evidence attestation",
  "Get a fragility map and a minimal repro for the failing path",
  "Create export-preview drafts (ServiceNow / Salesforce / Genesys / GitHub)",
];

const cannotDo = [
  "Delete or purge traces",
  "Change retention windows",
  "Trigger the kill switch",
  "Read raw traces, free-text explanations, or user identity",
  "Write to any system of record",
  "Open, approve, or merge a pull request",
];

export default function AgentsPage() {
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
            eyebrow="Agents & MCP"
            title="A safe surface for agents — read summaries, draft tickets, nothing destructive"
            body="StepStitch plugs into any agent network over MCP, OpenAPI, or function-calling. The capability list is a single source of truth shared across all three surfaces, and it is deliberately read-only and draft-only. Agents help an operator move faster; they never take an irreversible action."
          />
        </div>

        {/* Surfaces */}
        <Reveal>
          <div className="mt-12">
            <div className="flex items-center gap-2.5">
              <Plugs size={18} weight="bold" className="text-accent" />
              <h3 className="text-base font-semibold text-fg">Three ways to connect, one capability list</h3>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              {surfaces.map(([name, desc]) => (
                <div key={name} className="rounded-2xl border border-line bg-surface p-5">
                  <p className="text-sm font-semibold text-fg">{name}</p>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{desc}</p>
                </div>
              ))}
            </div>
          </div>
        </Reveal>

        {/* Per-agent scoping (0.5.0) */}
        <Reveal>
          <div className="mt-5 rounded-2xl border border-line bg-surface p-6">
            <div className="flex items-center gap-2.5">
              <UserCheck size={18} weight="bold" className="text-accent" />
              <h3 className="text-base font-semibold text-fg">
                Scope each agent — not just the surface
              </h3>
            </div>
            <p className="mt-3 max-w-3xl text-[15px] leading-relaxed text-muted">
              The list above is the ceiling for <span className="text-fg">any</span> agent. From
              the operator console you register each agent individually and issue it a named,
              revocable token scoped to a tier — so one connection gets summaries only while another
              can pull a repro. The host enforces the scope: an out-of-scope call is refused, not
              silently allowed, and every read and denial lands on the audit trail.
            </p>
            <div className="mt-4 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
              {([
                ["none", "registered, no access"],
                ["summaries", "summaries · score · privacy posture"],
                ["repros", "+ the Playwright reproduction"],
                ["drafts", "+ sanitized ticket drafts"],
              ] as const).map(([tier, what]) => (
                <div
                  key={tier}
                  className="rounded-xl border border-line bg-surface-2/50 p-3.5"
                >
                  <p className="font-mono text-[12.5px] font-semibold text-accent">
                    {tier}
                  </p>
                  <p className="mt-1 text-[12.5px] leading-relaxed text-muted">
                    {what}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </Reveal>

        {/* Can / cannot */}
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          <Reveal>
            <div className="h-full rounded-2xl border border-line bg-surface p-6">
              <div className="flex items-center gap-2.5">
                <Check size={18} weight="bold" className="text-ok" />
                <h3 className="text-base font-semibold text-fg">Agents can</h3>
              </div>
              <ul className="mt-4 grid gap-2.5">
                {canDo.map((c) => (
                  <li key={c} className="flex items-start gap-2.5 text-[14px] text-muted">
                    <Check size={16} weight="bold" className="mt-0.5 shrink-0 text-ok" />
                    {c}
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
          <Reveal delay={0.06}>
            <div className="h-full rounded-2xl border border-line bg-surface p-6">
              <div className="flex items-center gap-2.5">
                <Prohibit size={18} weight="bold" className="text-bad" />
                <h3 className="text-base font-semibold text-fg">Agents cannot</h3>
              </div>
              <ul className="mt-4 grid gap-2.5">
                {cannotDo.map((c) => (
                  <li key={c} className="flex items-start gap-2.5 text-[14px] text-muted">
                    <Prohibit size={16} weight="bold" className="mt-0.5 shrink-0 text-bad/80" />
                    {c}
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
        </div>

        {/* Human in the loop */}
        <Reveal>
          <div className="mt-5 rounded-2xl border border-line bg-surface p-6">
            <div className="flex items-center gap-2.5">
              <UserCheck size={18} weight="bold" className="text-accent" />
              <h3 className="text-base font-semibold text-fg">Human approval is the control point</h3>
            </div>
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              An agent can assemble the evidence and hand a human a ready-to-review draft. The final
              action — filing the ticket, opening the PR, merging the fix — always belongs to a named
              person or your own CI. StepStitch supplies evidence, repros, drafts, and verification
              records; your systems and your people perform the final action.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {["docs/AGENTS.md", "copilot/MCP-SETUP.md", "copilot/openapi-v2.json"].map((g) => (
                <a
                  key={g}
                  href={`${GITHUB_URL}/blob/main/${g}`}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-md border border-line bg-surface-2/50 px-2 py-1 font-mono text-[11.5px] text-muted transition-colors hover:border-accent/40 hover:text-fg"
                >
                  {g}
                </a>
              ))}
            </div>
          </div>
        </Reveal>

        <Reveal>
          <div className="mt-10 flex flex-wrap items-center gap-3">
            <Button href="/quickstart" trailingIcon={null}>
              Wire up the connector
            </Button>
            <Button href="/demo" variant="secondary" trailingIcon={null}>
              See the evidence it returns
            </Button>
          </div>
        </Reveal>
      </Section>
    </main>
  );
}
