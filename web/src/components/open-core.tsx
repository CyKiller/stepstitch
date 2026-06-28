import { Check } from "@phosphor-icons/react/dist/ssr";
import { Reveal } from "./reveal";
import { Section, SectionHeader } from "./section";
import { Button } from "./button";
import { GITHUB_URL } from "@/lib/links";

const openSource = [
  "The @stepstitch/tracker SDK and the privacy / repro engine",
  "The universal MCP connector and OpenAPI surface",
  "The operator console: agent scoping, scrub-policy editor, and audit",
  "The ServiceNow, Salesforce, and Genesys draft adapters",
  "OIDC SSO, RBAC, deployment profiles, and the compliance evidence",
];

const commercial = [
  "A hosted / managed offering you do not run yourself",
  "Additional supported enterprise adapters",
  "A compliance pack with formal regulatory attestations",
  "Direct partnership and priority support",
];

export function OpenCore() {
  return (
    <Section id="pricing" className="border-b border-line">
      <SectionHeader
        title="Open core. Self-host free, today."
        body="Everything in the repository is Apache-2.0 right now — there is no crippled free tier and no closed core. A managed edition may come later; it will be additive, and nothing open today will be retroactively closed."
      />

      <div className="mt-12 grid gap-5 lg:grid-cols-2">
        {/* Free / open — the emphasized, accented column. */}
        <Reveal>
          <div className="flex h-full flex-col rounded-2xl border border-accent/30 bg-accent/[0.04] p-7 md:p-8">
            <div className="flex items-baseline justify-between gap-3">
              <h3 className="text-lg font-semibold text-fg">
                Open source
              </h3>
              <span className="rounded-md border border-accent/30 bg-surface px-2 py-1 font-mono text-[11.5px] text-accent">
                Apache-2.0
              </span>
            </div>
            <p className="mt-2 text-2xl font-semibold tracking-tight text-fg">
              Free, self-hosted
            </p>
            <ul className="mt-6 space-y-3 text-[15px] text-muted">
              {openSource.map((f) => (
                <li key={f} className="flex gap-2.5">
                  <Check
                    size={16}
                    weight="bold"
                    className="mt-1 shrink-0 text-accent"
                  />
                  <span>{f}</span>
                </li>
              ))}
            </ul>
            <div className="mt-7">
              <Button href="/self-host" variant="secondary">
                Self-host free
              </Button>
            </div>
          </div>
        </Reveal>

        {/* Commercial — honest "later / talk to us", never invented pricing. */}
        <Reveal delay={0.08}>
          <div className="flex h-full flex-col rounded-2xl border border-line bg-surface p-7 md:p-8">
            <div className="flex items-baseline justify-between gap-3">
              <h3 className="text-lg font-semibold text-fg">
                Managed &amp; commercial
              </h3>
              <span className="rounded-md border border-line bg-surface-2/50 px-2 py-1 font-mono text-[11.5px] text-muted">
                On the roadmap
              </span>
            </div>
            <p className="mt-2 text-2xl font-semibold tracking-tight text-fg">
              Talk to us
            </p>
            <ul className="mt-6 space-y-3 text-[15px] text-muted">
              {commercial.map((f) => (
                <li key={f} className="flex gap-2.5">
                  <Check
                    size={16}
                    weight="bold"
                    className="mt-1 shrink-0 text-muted"
                  />
                  <span>{f}</span>
                </li>
              ))}
            </ul>
            <div className="mt-7">
              <Button href="/#contact">Book a pilot</Button>
            </div>
          </div>
        </Reveal>
      </div>

      <Reveal className="mt-6">
        <p className="text-sm text-muted">
          Read the full licensing stance in{" "}
          <a
            href={`${GITHUB_URL}/blob/main/COMMERCIAL.md`}
            target="_blank"
            rel="noreferrer"
            className="font-semibold text-accent hover:underline"
          >
            COMMERCIAL.md
          </a>
          .
        </p>
      </Reveal>
    </Section>
  );
}
