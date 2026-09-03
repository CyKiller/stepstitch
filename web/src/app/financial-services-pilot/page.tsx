import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle,
  Package,
  CalendarCheck,
  ShieldCheck,
  Robot,
  GitPullRequest,
} from "@phosphor-icons/react/dist/ssr";
import { Section, SectionHeader } from "@/components/section";
import { Reveal } from "@/components/reveal";
import { Button } from "@/components/button";
import { GITHUB_URL } from "@/lib/links";
import { claim } from "@/lib/claims";

export const metadata: Metadata = {
  title: "Financial-services pilot: StepStitch",
  description:
    "A 30-day, self-hosted pilot that turns regulated support tickets into privacy-safe, reproducible engineering evidence: scrubbed trace, replayability score, Playwright repro, and ServiceNow/Salesforce/GitHub drafts. Free text, unapproved selectors and undeclared routes are refused with HTTP 422 under the strict profile; nothing is sent without human approval.",
};

const whoFor = [
  "Regulated financial-services teams where support escalations to engineering must carry no customer data the team cannot account for.",
  "Microsoft tenants standardizing on Copilot Studio / Power Platform for agent workflows.",
  "Risk, compliance, and model-risk reviewers who need evidence they can read, not certificates to trust.",
];

const installed = [
  ["Ingest API", "Self-hosted on Railway (or any OCI host) with the financial-services-enterprise scrub profile. You hold the keys; StepStitch holds no system-of-record credentials."],
  ["Tracker SDK", "@stepstitch/tracker mounted behind a consent gate in the app the support team supports."],
  ["MCP connector", "Read-only / draft-only tools for Copilot Studio, Claude, or any agent network."],
  ["Compliance packet", "COMPLIANCE-EVIDENCE.md generated from the live scrub policy, plus the named tests that back each control."],
];

const day30 = [
  "A working report → scrub → score → repro → draft → verified-fix loop on a real support flow.",
  "A folder of scrubbed traces, each with the server's own report of exactly what it stripped at ingestion.",
  "Deterministic Playwright reproductions your engineers can run in CI as regression tests.",
  "ServiceNow incident + Salesforce case + GitHub issue drafts, created but never auto-sent.",
  "A confirmed-fixed regression corpus: bugs that went red in CI before the fix and green after.",
];

const modes = [
  {
    icon: Robot,
    title: "Mode A: Power Platform native connectors",
    tag: "default for Microsoft tenants",
    body: "Copilot Studio calls the read-only export-preview endpoint, gets a flat draft, and maps it onto Microsoft's native ServiceNow/Salesforce connectors as a human-approved step. StepStitch never holds system-of-record credentials.",
  },
  {
    icon: GitPullRequest,
    title: "Mode B: governed direct-write",
    tag: "for paths not on Power Platform",
    body: "StepStitch can post the sanitized draft itself. This mode is off by default, admin-only, dry-run by default, requires a named human approver and idempotency key, is fully audited, and is never exposed on the agent surface.",
  },
];

const success = [
  // Sourced from the claim registry, not retyped here: the sentence and the test that
  // proves it are one object, so a stronger claim cannot be written into this page
  // without moving the evidence with it.
  claim("strict-schema-passed"),
  claim("reproduction-not-certified"),
  "Median time from support ticket to a runnable engineering repro measurably reduced.",
  "Every escalation carries a replayability grade so engineering knows what is reproducible.",
  "At least one bug taken from report to confirmed_fixed regression evidence.",
];

export default function FinancialServicesPilotPage() {
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
            as="h1"
            eyebrow="30-day pilot"
            title="A regulated support-to-engineering pilot, with the boundary in the code"
            body="In 30 days, turn user-reported bugs from a regulated app into privacy-safe, reproducible engineering evidence: a scrubbed trace, a replayability score, sanitized diagnostics, a Playwright repro, and ticket/PR drafts. StepStitch does this without capturing screens, input values, or page text. Self-hosted and open source, so your reviewers can verify every line."
          />
        </div>

        {/* Who it's for */}
        <Reveal>
          <div className="mt-12 rounded-2xl border border-line bg-surface p-6">
            <p className="text-xs font-medium uppercase tracking-wide text-muted">
              Who it is for
            </p>
            <ul className="mt-4 grid gap-3">
              {whoFor.map((w) => (
                <li key={w} className="flex items-start gap-2.5 text-[15px] text-muted">
                  <CheckCircle size={17} weight="bold" className="mt-0.5 shrink-0 text-accent" />
                  {w}
                </li>
              ))}
            </ul>
          </div>
        </Reveal>

        {/* What gets installed */}
        <Reveal>
          <div className="mt-5">
            <div className="flex items-center gap-2.5">
              <Package size={18} weight="bold" className="text-accent" />
              <h3 className="text-base font-semibold text-fg">What gets installed</h3>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {installed.map(([name, desc]) => (
                <div key={name} className="rounded-2xl border border-line bg-surface p-5">
                  <p className="text-sm font-semibold text-fg">{name}</p>
                  <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted">{desc}</p>
                </div>
              ))}
            </div>
          </div>
        </Reveal>

        {/* What you get by day 30 */}
        <Reveal>
          <div className="mt-5 rounded-2xl border border-line bg-surface p-6">
            <div className="flex items-center gap-2.5">
              <CalendarCheck size={18} weight="bold" className="text-accent" />
              <h3 className="text-base font-semibold text-fg">What you get by day 30</h3>
            </div>
            <ul className="mt-4 grid gap-3">
              {day30.map((d) => (
                <li key={d} className="flex items-start gap-2.5 text-[15px] text-muted">
                  <CheckCircle size={17} weight="bold" className="mt-0.5 shrink-0 text-ok" />
                  {d}
                </li>
              ))}
            </ul>
          </div>
        </Reveal>

        {/* Two delivery modes */}
        <Reveal>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {modes.map((m) => (
              <div key={m.title} className="flex h-full flex-col rounded-2xl border border-line bg-surface p-6">
                <div className="flex items-center gap-2.5">
                  <m.icon size={18} weight="bold" className="text-accent" />
                  <h3 className="text-[15px] font-semibold text-fg">{m.title}</h3>
                </div>
                <span className="mt-2 inline-flex w-fit rounded-full border border-line bg-surface-2/50 px-2 py-0.5 text-[11px] text-muted">
                  {m.tag}
                </span>
                <p className="mt-3 text-[13.5px] leading-relaxed text-muted">{m.body}</p>
              </div>
            ))}
          </div>
        </Reveal>

        {/* Compliance packet */}
        <Reveal>
          <div className="mt-5 rounded-2xl border border-line bg-surface p-6">
            <div className="flex items-center gap-2.5">
              <ShieldCheck size={18} weight="bold" className="text-accent" />
              <h3 className="text-base font-semibold text-fg">The compliance evidence packet</h3>
            </div>
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              Hand your reviewer the packet generated from the live scrub policy: it cannot drift
              from what the server actually enforces. It crosswalks the controls to SEC Reg S-P
              (2024) and NIST AI RMF, and names the test that backs each one.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {["COMPLIANCE-EVIDENCE.md", "RELEASE.md", "INCIDENT-RESPONSE.md", "THREAT-MODEL.md"].map((g) => (
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

        {/* Success criteria */}
        <Reveal>
          <div className="mt-5 rounded-2xl border border-line bg-surface p-6">
            <h3 className="text-base font-semibold text-fg">Success criteria</h3>
            <ul className="mt-4 grid gap-3">
              {success.map((s) => (
                <li key={s} className="flex items-start gap-2.5 text-[15px] text-muted">
                  <CheckCircle size={17} weight="bold" className="mt-0.5 shrink-0 text-accent" />
                  {s}
                </li>
              ))}
            </ul>
          </div>
        </Reveal>

        <Reveal>
          <div className="mt-10 flex flex-wrap items-center gap-3">
            <Button href="/#contact" trailingIcon={null}>
              Book the pilot
            </Button>
            <Button href="/demo" variant="secondary" trailingIcon={null}>
              See the red-to-green demo
            </Button>
          </div>
        </Reveal>
      </Section>
    </main>
  );
}
