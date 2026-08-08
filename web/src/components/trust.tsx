import { Reveal } from "./reveal";
import { Section, SectionHeader } from "./section";
import { GITHUB_URL } from "@/lib/links";

const crosswalk = [
  {
    name: "SEC Reg S-P (2024)",
    note: "Safeguards and recordkeeping. Incident records retained five years.",
  },
  {
    name: "Internal model-risk principles",
    note: "Named, runnable gates for auditability, monitoring, and human oversight. The 2026 interagency MRM guidance excludes generative and agentic AI from its scope, so StepStitch does not claim it applies.",
  },
  {
    name: "NIST AI RMF",
    note: "Data governance, documentation, accountability, incident response.",
  },
];

const gates = [
  "test_scrubber.py",
  "test_profiles.py",
  "test_golden_path.py",
  "test_repro_eval.py",
  ".importlinter",
  "test_compliance.py",
];

export function Trust() {
  return (
    <Section id="trust" className="border-b border-line">
      <SectionHeader
        title="Built to be audited, not just trusted"
        body="The privacy boundary is open source. Your reviewers can read exactly what is captured and what is dropped, line by line, before anything is deployed."
      />

      <div className="mt-12 grid gap-5 lg:grid-cols-5">
        <Reveal className="lg:col-span-2">
          <div className="flex h-full flex-col rounded-2xl border border-line bg-surface p-6">
            <h3 className="text-base font-semibold text-fg">
              The trust boundary is the code
            </h3>
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              Every component is Apache-2.0: the SDK, the service core, the MCP
              connector, and the adapters. Built for regulated and
              quality-focused teams that self-host.
            </p>
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
            <a
              href={`${GITHUB_URL}/blob/main/COMPLIANCE-EVIDENCE.md`}
              target="_blank"
              rel="noreferrer"
              className="mt-6 text-sm font-semibold text-accent hover:underline"
            >
              Read the compliance evidence
            </a>
          </div>
        </Reveal>

        <Reveal delay={0.08} className="lg:col-span-3">
          <div className="h-full rounded-2xl border border-line bg-surface p-6">
            <h3 className="text-base font-semibold text-fg">
              Mapped to the regulations your reviewers cite
            </h3>
            <div className="mt-5 divide-y divide-line">
              {crosswalk.map((c) => (
                <div
                  key={c.name}
                  className="grid gap-1 py-4 first:pt-0 last:pb-0 sm:grid-cols-[minmax(0,40%)_1fr] sm:gap-4"
                >
                  <p className="text-sm font-semibold text-fg">{c.name}</p>
                  <p className="text-sm text-muted">{c.note}</p>
                </div>
              ))}
            </div>
          </div>
        </Reveal>
      </div>
    </Section>
  );
}
