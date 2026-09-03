import { Fingerprint, ShieldCheck, MagnifyingGlass } from "@phosphor-icons/react/dist/ssr";
import type { Icon } from "@phosphor-icons/react";
import { Reveal } from "./reveal";
import { Section, SectionHeader } from "./section";
import { GITHUB_URL } from "@/lib/links";

type Item = { icon: Icon; title: string; desc: string; proof: string; href: string };

// The version this section describes. Deliberately PINNED, not tracked to the current
// release: these three moats landed in 0.6, and auto-bumping the label would claim they
// are new in whatever ships next. When a later release earns its own section, change this
// literal and the items together: never one without the other.
const SHIPPED_IN = "0.6";

// Three moats shipped in 0.6: each a first-class API + MCP tool, structural only.
const items: Item[] = [
  {
    icon: Fingerprint,
    title: "Fix Memory",
    desc: "Every confirmed red→green fix becomes a structural fingerprint. A new bug is matched against the corpus with the prior fix: “you've fixed this shape before,” without an agent ever seeing raw data.",
    proof: "GET /similar-fixes",
    href: "/agents",
  },
  {
    icon: ShieldCheck,
    title: "Evidence Attestation",
    desc: "A canonical, tamper-evident evidence bundle covers the scrub report, replayability, verdict, and build, signed with your own key. Anyone can verify it independently by recomputing the hash or running cosign verify-blob. We hold no key.",
    proof: "GET /attestation · cosign verify-blob",
    href: "/security",
  },
  {
    icon: MagnifyingGlass,
    title: "Fragility Radar",
    desc: "The deterministic replayability signal turned predictive: which steps are most likely to break (selector brittleness, templated routes), plus a minimal repro reduced to the failing path.",
    proof: "GET /fragility · GET /minimal-repro",
    href: "/agents",
  },
];

export function WhatsNew() {
  return (
    <Section id="whats-new" className="border-b border-line">
      <SectionHeader
        eyebrow={`New in ${SHIPPED_IN}`}
        title="Three moats nobody else has"
        body="Built on the primitives only StepStitch holds: a deterministic compiler, a provable scrubber, a verified-fix corpus, and supply-chain signing. Each is an open-source API and an MCP tool."
      />

      <div className="mt-12 grid gap-4 lg:grid-cols-3">
        {items.map((it, i) => {
          const Glyph = it.icon;
          return (
            <Reveal key={it.title} delay={i * 0.06}>
              <a
                href={it.href}
                className="flex h-full flex-col rounded-2xl border border-line bg-surface p-6 md:p-7 transition-colors hover:border-accent/40"
              >
                <div className="flex items-center gap-2.5">
                  <Glyph size={18} weight="bold" className="text-accent" />
                  <h3 className="text-base font-semibold text-fg">{it.title}</h3>
                </div>
                <p className="mt-3 flex-1 text-[15px] leading-relaxed text-muted">
                  {it.desc}
                </p>
                <p className="mt-4 font-mono text-[12px] text-accent/90">{it.proof}</p>
              </a>
            </Reveal>
          );
        })}
      </div>

      <Reveal className="mt-6">
        <a
          href={`${GITHUB_URL}/releases/tag/v${SHIPPED_IN}.0`}
          target="_blank"
          rel="noreferrer"
          className="text-sm font-semibold text-accent hover:underline"
        >
          See the {SHIPPED_IN}.0 release →
        </a>
      </Reveal>
    </Section>
  );
}
