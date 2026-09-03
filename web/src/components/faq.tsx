import { Plus } from "@phosphor-icons/react/dist/ssr";
import { Reveal } from "./reveal";
import { Section, SectionHeader } from "./section";

import { claim } from "@/lib/claims";

const faqs = [
  {
    q: "Is StepStitch session replay?",
    a: "No. It captures the structure of what broke (route templates, stable selectors, API status codes), never screens, input values, page text, or raw URLs. It is issue-to-repro infrastructure, not session replay.",
  },
  {
    q: "Is the generated test a real regression test?",
    a: "Yes. A captured API failure becomes an armed page.waitForResponse plus a status assertion; a captured client exception becomes a pageerror assertion. The test fails while the bug is present and passes once it is fixed, so it is safe to keep in CI as a regression guard.",
  },
  {
    q: "How long does self-hosting take?",
    a: "Minutes. The service ships as a Docker image with a one-command Railway deploy; the SDK is an npm install with zero runtime dependencies. See the Self-host guide.",
  },
  {
    q: "Is it compatible with HIPAA / SEC Reg S-P?",
    a: "You control where StepStitch runs and stores its evidence, and the SDK captures structure rather than content: no screens, input values, or page text. Free text a user types is the one place customer data can enter, and the server scrubs it. The healthcare-strict and financial-services-strict profiles disable it outright and refuse the request with a 422; the default profile redacts and drops forbidden keys. " + claim("controls-not-certification") + " See the Security page for the crosswalk.",
  },
  {
    q: "What frameworks does it work with?",
    a: "Any web frontend. The SDK is framework-agnostic TypeScript that records structural footsteps; the compiled reproduction is standard Playwright.",
  },
  {
    q: "Is StepStitch open source?",
    a: "Yes, Apache-2.0 across the SDK, service core, MCP connector, and adapters. You can read exactly what is captured and what is dropped before deploying.",
  },
];

export function Faq() {
  return (
    <Section id="faq" className="border-b border-line">
      <SectionHeader
        title="Questions, answered"
        body="The things technical and compliance reviewers ask first."
      />
      <Reveal>
        <div className="mt-10 divide-y divide-line border-y border-line">
          {faqs.map((f) => (
            <details key={f.q} className="group">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-5 text-left">
                <span className="text-base font-medium text-fg">{f.q}</span>
                <Plus
                  size={18}
                  weight="bold"
                  className="shrink-0 text-muted transition-transform duration-300 ease-[var(--ease-spring)] group-open:rotate-45"
                />
              </summary>
              <p className="max-w-3xl pb-5 text-[15px] leading-relaxed text-muted">
                {f.a}
              </p>
            </details>
          ))}
        </div>
      </Reveal>
    </Section>
  );
}
