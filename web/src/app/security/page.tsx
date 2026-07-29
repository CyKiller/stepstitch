import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowLeft,
  ShieldCheck,
  FileText,
} from "@phosphor-icons/react/dist/ssr";
import { Section, SectionHeader } from "@/components/section";
import { Reveal } from "@/components/reveal";
import { Button } from "@/components/button";
import { GITHUB_URL } from "@/lib/links";

export const metadata: Metadata = {
  title: "Security & compliance — StepStitch",
  description:
    "How StepStitch stays audit-ready: a two-layer privacy boundary, a never-captured list, deployment profiles, and a crosswalk to SEC Reg S-P, 2026 MRM guidance, and NIST AI RMF. Open source, so you can verify it.",
};

const neverCaptured = [
  "Screenshots / video",
  "Input values",
  "Page text / DOM content",
  "Raw URLs",
  "Request / response bodies",
  "Cookies / headers",
  "SSNs, account & card numbers",
  "Raw logs / stack traces",
];

const crosswalk = [
  ["SEC Reg S-P (2024)", "Safeguards and recordkeeping. Incident records retained five years."],
  ["2026 interagency MRM guidance", "Auditability, ongoing monitoring, and human oversight of model use (supersedes SR 11-7)."],
  ["NIST AI RMF", "Data governance, documentation, accountability, incident response."],
];

const gates = [
  "test_scrubber.py",
  "test_profiles.py",
  "test_golden_path.py",
  "test_repro_eval.py",
  "service/pyproject.toml (import-linter contract)",
  "test_compliance.py",
];

const docs = [
  ["COMPLIANCE-EVIDENCE.md", "The regulation crosswalk and the named tests that back each control."],
  ["docs/THREAT-MODEL.md", "Assets, trust boundaries, and the threats the design addresses."],
  ["SECURITY.md", "Disclosure policy and supported versions."],
  ["INCIDENT-RESPONSE.md", "The org-wide kill switch and containment procedure."],
];

export default function SecurityPage() {
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
            eyebrow="Security & compliance"
            title="Audit-ready, because you can read the code"
            body="The privacy boundary is open source. Your reviewers can confirm exactly what is captured and what is dropped, line by line, before anything is deployed. No certificate to take on faith."
          />
        </div>

        {/* Two-layer boundary + never captured */}
        <div className="mt-12 grid gap-5 lg:grid-cols-5">
          <Reveal className="lg:col-span-2">
            <div className="flex h-full flex-col rounded-2xl border border-line bg-surface p-6">
              <div className="flex items-center gap-2.5">
                <ShieldCheck size={18} weight="bold" className="text-accent" />
                <h3 className="text-base font-semibold text-fg">
                  Two-layer boundary
                </h3>
              </div>
              <p className="mt-3 text-[15px] leading-relaxed text-muted">
                The SDK redacts in the page, but the backend never trusts the
                client. Every trace is scrubbed again on the server before it is
                stored. Defense in depth, proven by a named test.
              </p>
            </div>
          </Reveal>
          <Reveal delay={0.06} className="lg:col-span-3">
            <div className="h-full rounded-2xl border border-line bg-surface p-6">
              <p className="text-xs font-medium uppercase tracking-wide text-muted">
                Never captured
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {neverCaptured.map((n) => (
                  <span
                    key={n}
                    className="rounded-md border border-line bg-surface-2/50 px-2.5 py-1 text-[13px] text-muted line-through decoration-bad/40"
                  >
                    {n}
                  </span>
                ))}
              </div>
            </div>
          </Reveal>
        </div>

        {/* Crosswalk */}
        <Reveal>
          <div className="mt-5 rounded-2xl border border-line bg-surface p-6">
            <h3 className="text-base font-semibold text-fg">
              Mapped to the regulations your reviewers cite
            </h3>
            <div className="mt-5 divide-y divide-line">
              {crosswalk.map(([name, note]) => (
                <div
                  key={name}
                  className="grid gap-1 py-4 first:pt-0 last:pb-0 sm:grid-cols-[minmax(0,38%)_1fr] sm:gap-4"
                >
                  <p className="text-sm font-semibold text-fg">{name}</p>
                  <p className="text-sm text-muted">{note}</p>
                </div>
              ))}
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              {gates.map((g) => (
                <span
                  key={g}
                  className="rounded-md border border-line bg-surface-2/50 px-2 py-1 font-mono text-[11.5px] text-muted"
                >
                  {g}
                </span>
              ))}
            </div>
          </div>
        </Reveal>

        {/* Doc links */}
        <Reveal>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {docs.map(([name, desc]) => (
              <a
                key={name}
                href={`${GITHUB_URL}/blob/main/${name}`}
                target="_blank"
                rel="noreferrer"
                className="group flex items-start gap-3 rounded-2xl border border-line bg-surface p-5 transition-colors hover:border-accent/40"
              >
                <FileText
                  size={18}
                  weight="bold"
                  className="mt-0.5 shrink-0 text-accent"
                />
                <span>
                  <span className="font-mono text-[13px] text-fg group-hover:text-accent">
                    {name}
                  </span>
                  <span className="mt-1 block text-[13px] text-muted">
                    {desc}
                  </span>
                </span>
              </a>
            ))}
          </div>
        </Reveal>

        <Reveal>
          <div className="mt-10 flex flex-wrap items-center gap-3">
            <Button href="/#contact" trailingIcon={null}>
              Request the compliance packet
            </Button>
            <Button href="/self-host" variant="secondary" trailingIcon={null}>
              Self-host it yourself
            </Button>
          </div>
        </Reveal>
      </Section>
    </main>
  );
}
