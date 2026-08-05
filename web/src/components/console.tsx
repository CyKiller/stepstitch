import {
  Plugs,
  Lock,
  Eye,
  ShieldCheck,
  MagnifyingGlass,
  UserGear,
} from "@phosphor-icons/react/dist/ssr";
import type { Icon } from "@phosphor-icons/react";
import { Reveal } from "./reveal";
import { Section, SectionHeader } from "./section";
import { Button } from "./button";
import { ConsoleBoard } from "./console-board";

type Panel = {
  icon: Icon;
  title: string;
  desc: string;
  proof: string;
};

// The governed operator console that ships in 0.5.0. Every panel maps to a real,
// named place in the open-source code — same proof-over-promises stance as the rest
// of the page. Verified against server/agents.py, server/host.py, server/dashboard.py.
const panels: Panel[] = [
  {
    icon: Plugs,
    title: "Connect any agent, scoped",
    desc: "Register each AI agent and issue it a named token scoped to what it actually needs — none, summaries, repros or drafts for assistants, and a separate verify scope for CI that may fetch a reproduction and post a verdict and nothing else. The host enforces the scope; an out-of-scope call is refused, not silently allowed.",
    proof: "server/agents.py · POST /admin/agents",
  },
  {
    icon: Lock,
    title: "Tokens you can revoke",
    desc: "Each agent gets its own bearer token, stored only as a hash and shown once. Registering one hands you a ready-to-paste MCP client config — connect Claude, Copilot, or your own agent with no bespoke wiring.",
    proof: "secrets.token_urlsafe · copilot/MCP-SETUP.md",
  },
  {
    icon: Eye,
    title: "See exactly what the model sees",
    desc: "For any trace, preview the literal MCP payload an agent receives — alongside the never-captured list — before you approve a connection. It is self-hosted, so nothing leaves your boundary at all.",
    proof: "GET /session/{id}/privacy-posture",
  },
  {
    icon: ShieldCheck,
    title: "Edit the scrub policy live",
    desc: "Add custom redaction patterns and dropped fields from the dashboard, with a live preview. Edits can only tighten the boundary — never loosen the built-in PII rules — proven by test.",
    proof: "/admin/config/scrub · scrubber.py",
  },
  {
    icon: MagnifyingGlass,
    title: "Audit + per-agent activity",
    desc: "Every operator read and config change is recorded. See each agent's reads, scopes exercised, denials, and last-seen — governance proof your reviewers can read.",
    proof: "GET /audit",
  },
  {
    icon: UserGear,
    title: "Self-hosted operator console",
    desc: "All of the above is a single read-only-by-default page served by the host at /dashboard — admin-gated, audited, with no destructive action exposed. It is the cockpit, not a SaaS you ship your data to.",
    proof: "server/dashboard.py · GET /dashboard",
  },
];

export function Console() {
  return (
    <Section id="console" className="border-b border-line">
      <SectionHeader
        eyebrow="The operator console"
        title="One bug, however many people reported it"
        body="The self-hosted console groups traces by what actually broke — same route, same failure, same structure — so forty reports of one bug are one card and one decision. It moves through the pipeline as your CI reports back, and it governs the part nobody else does: which agent gets which evidence. Each panel points at the open-source code that implements it."
      />

      <Reveal className="mt-12">
        <ConsoleBoard />
      </Reveal>

      <Reveal className="mt-6">
        <Button href="/dashboard">Try the console</Button>
      </Reveal>

      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {panels.map((p, i) => {
          const Glyph = p.icon;
          return (
            <Reveal key={p.title} delay={i * 0.06}>
              <div className="flex h-full flex-col rounded-2xl border border-line bg-surface p-6 md:p-7">
                <div className="flex items-center gap-2.5">
                  <Glyph size={18} weight="bold" className="text-accent" />
                  <h3 className="text-base font-semibold text-fg">{p.title}</h3>
                </div>
                <p className="mt-3 flex-1 text-[15px] leading-relaxed text-muted">
                  {p.desc}
                </p>
                <p className="mt-4 font-mono text-[12px] text-accent/90">
                  {p.proof}
                </p>
              </div>
            </Reveal>
          );
        })}
      </div>
    </Section>
  );
}
