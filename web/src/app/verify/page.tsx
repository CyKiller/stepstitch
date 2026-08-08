import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowLeft,
  Terminal,
  Certificate,
  Detective,
  Monitor,
} from "@phosphor-icons/react/dist/ssr";
import { Section, SectionHeader } from "@/components/section";
import { Reveal } from "@/components/reveal";
import { Button } from "@/components/button";
import { GITHUB_URL } from "@/lib/links";
import { claim } from "@/lib/claims";

export const metadata: Metadata = {
  title: "Verify it yourself — StepStitch",
  description:
    "The checks behind every StepStitch claim, as commands you can run: replay hostile fixtures through the live scrub boundary, recompute an attestation hash, confirm the fixing agent holds no verdict credential.",
  alternates: { canonical: "/verify" },
  openGraph: {
    title: "Verify it yourself — StepStitch",
    description:
      "Don't take the vendor's word. Run the privacy and verification checks against your own deployment.",
    url: "/verify",
  },
};

const checks = [
  {
    icon: Terminal,
    title: "Replay hostile fixtures through the live scrub boundary",
    claimIds: ["tenant-fixtures-verifiable"],
    body:
      "Write the payloads you are worried about — card-number shapes, raw URLs, response bodies — and let the verifier tell you what the live policy does with each one before anything goes live.",
    code: `stepstitch policy verify examples/policy/financial-fixtures.json
# per fixture: rejected (422, nothing stored) | dropped | redacted | accepted
# plus a must_not_persist literal scan over everything that would be stored`,
    source: "service/stepstitch_service/policy_verify.py",
  },
  {
    icon: Certificate,
    title: "Recompute an attestation, or verify its signature",
    claimIds: ["attestation-self-verifiable"],
    body:
      "Every verified fix carries a canonical, hashed evidence bundle — scrub report, replayability, verdict, evidence grade. The hash covers the grade, so nothing can be upgraded after issue.",
    code: `# 1. the hash is reproducible from the bundle alone
python -c "import json,hashlib,sys; b=json.load(open('attestation.json')); \\
print(hashlib.sha256(json.dumps(b,sort_keys=True,separators=(',',':')).encode()).hexdigest())"

# 2. the signature is your tenant's, not ours
cosign verify-blob --key tenant.pub --signature attestation.sig attestation.json`,
    source: "service/stepstitch_service/attestation.py",
  },
  {
    icon: Detective,
    title: "Confirm the fixing agent cannot grade its own work",
    claimIds: ["agent-cannot-self-verify", "evidence-grade-uncounterfeitable"],
    body:
      "Read the scope table: writing a verdict requires the verify scope, which sits outside the ladder any connected agent is issued from. Then read the test that proves a caller-supplied grade is demoted.",
    code: `# the credential 'stepstitch connect' issues can read repros — never verify
POST /session/{id}/verify  ->  requires scope: verify (agents get: repros)

# and the grade cannot be asserted into existence
pytest service/tests/test_evidence.py server/tests/test_agents.py`,
    source: "service/stepstitch_service/host/agents.py",
  },
];

export default function VerifyPage() {
  return (
    <main id="main" className="flex-1">
      <Section className="pt-12">
        <Reveal>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-muted transition-colors hover:text-fg"
          >
            <ArrowLeft size={14} weight="bold" />
            Back home
          </Link>
        </Reveal>

        <div className="mt-6">
          <SectionHeader
            eyebrow="Trust"
            title="Don't trust us. Run the checks."
            body="Every material claim on this site maps to a file and a named test in the open repository. This page turns the three that matter most into commands you can run against your own deployment."
          />
        </div>

        <div className="mt-12 flex flex-col gap-5">
          {checks.map((c, i) => (
            <Reveal key={c.title} delay={i * 0.06}>
              <div className="rounded-2xl border border-line bg-surface p-6">
                <div className="flex items-center gap-2.5">
                  <c.icon size={20} weight="bold" className="text-accent" />
                  <h3 className="text-base font-semibold text-fg">{c.title}</h3>
                </div>
                <p className="mt-3 max-w-[75ch] text-[15px] leading-relaxed text-muted">
                  {c.body}
                </p>
                <pre className="mt-4 overflow-x-auto rounded-xl border border-line bg-surface-2/50 p-4 font-mono text-[12.5px] leading-relaxed text-fg/90">
                  <code>{c.code}</code>
                </pre>
                <ul className="mt-4 flex flex-col gap-2">
                  {c.claimIds.map((id) => (
                    <li
                      key={id}
                      className="text-sm leading-relaxed text-muted"
                    >
                      {claim(id)}
                    </li>
                  ))}
                </ul>
                <a
                  href={`${GITHUB_URL}/blob/main/${c.source}`}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-4 inline-block font-mono text-xs text-accent hover:underline"
                >
                  {c.source}
                </a>
              </div>
            </Reveal>
          ))}

          <Reveal delay={0.2}>
            <div className="rounded-2xl border border-line bg-surface p-6">
              <div className="flex items-center gap-2.5">
                <Monitor size={20} weight="bold" className="text-accent" />
                <h3 className="text-base font-semibold text-fg">
                  Or just watch it work
                </h3>
              </div>
              <p className="mt-3 max-w-[75ch] text-[15px] leading-relaxed text-muted">
                The public demo console is the real product surface over a
                synthetic dataset — traces, privacy posture, replayability,
                the frozen reproduction, and the measured red-to-green verdict.
              </p>
              <div className="mt-5 flex flex-wrap items-center gap-3">
                <Button href="/demo">Open the live demo</Button>
                <Button
                  href={GITHUB_URL}
                  variant="secondary"
                  trailingIcon={null}
                >
                  Read the source
                </Button>
              </div>
            </div>
          </Reveal>
        </div>
      </Section>
    </main>
  );
}
