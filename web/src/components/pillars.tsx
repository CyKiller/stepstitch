import { EyeSlash, Scales, ArrowRight } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";
import { Reveal } from "./reveal";
import { Section, SectionHeader } from "./section";
import { claim } from "@/lib/claims";

// The two pillars everything else supports. Each card quotes registered claims
// (lib/claims.ts) so the copy here can never drift from evidence-backed wording.
const pillars = [
  {
    icon: EyeSlash,
    title: "Provable minimization",
    lead:
      "The evidence pipeline is deny-by-default: a strict allowlist of structural fields, forbidden keys treated as leak signals, and a strict mode that refuses a payload outright rather than storing it.",
    claims: ["hostile-post-cannot-persist", "tenant-fixtures-verifiable"],
    href: "/verify",
    linkLabel: "Run the checks yourself",
  },
  {
    icon: Scales,
    title: "Independent verification",
    lead:
      "The test bytes and execution envelope are frozen, the red run is measured before any fix exists, and the rerun is measured by StepStitch. The proposing agent holds no credential that could record a verdict.",
    claims: ["red-to-green-measured", "agent-cannot-self-verify"],
    href: "/verify",
    linkLabel: "Verify an attestation",
  },
];

export function Pillars() {
  return (
    <Section id="pillars" className="border-b border-line">
      <SectionHeader
        title="Private evidence, independently verified"
        body="The AI receives the structure of the failure without screens, input values, or page text. A fix is confirmed only after the same frozen test fails and then passes."
      />
      <div className="mt-12 grid gap-5 md:grid-cols-2">
        {pillars.map((p, i) => (
          <Reveal key={p.title} delay={i * 0.08}>
            <div className="flex h-full flex-col rounded-2xl border border-line bg-surface p-6">
              <div className="flex items-center gap-2.5">
                <p.icon size={20} weight="bold" className="text-accent" />
                <h3 className="text-base font-semibold text-fg">{p.title}</h3>
              </div>
              <p className="mt-3 text-[15px] leading-relaxed text-muted">
                {p.lead}
              </p>
              <ul className="mt-4 flex flex-col gap-3">
                {p.claims.map((id) => (
                  <li
                    key={id}
                    className="rounded-xl border border-line bg-surface-2/50 p-4 text-sm leading-relaxed text-muted"
                  >
                    {claim(id)}
                  </li>
                ))}
              </ul>
              <Link
                href={p.href}
                className="mt-auto inline-flex items-center gap-1.5 pt-5 text-sm font-semibold text-accent hover:underline"
              >
                {p.linkLabel}
                <ArrowRight size={14} weight="bold" />
              </Link>
            </div>
          </Reveal>
        ))}
      </div>
    </Section>
  );
}
