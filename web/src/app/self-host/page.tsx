import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "@phosphor-icons/react/dist/ssr";
import { Section, SectionHeader } from "@/components/section";
import { Reveal } from "@/components/reveal";
import { CodeBlock } from "@/components/code-block";
import { Button } from "@/components/button";
import { GITHUB_URL } from "@/lib/links";

export const metadata: Metadata = {
  title: "Self-host StepStitch — open source, Apache-2.0",
  description:
    "Run StepStitch inside your own boundary in minutes. Install the SDK, deploy the service with Docker or one Railway command, pick a privacy profile. No data leaves your infrastructure.",
};

const profiles = [
  ["financial-services-enterprise", "Default. Free text scrubbed (280 chars), forbidden keys dropped and reported."],
  ["healthcare-strict", "HIPAA posture. Free text disabled; forbidden keys rejected with 422."],
  ["internal-enterprise", "Internal tools. Longer notes scrubbed, forbidden keys dropped."],
  ["open-source-default", "Open-source projects. Scrub + drop, relaxed retention."],
];

export default function SelfHostPage() {
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
            eyebrow="Self-host"
            title="Run it inside your boundary in minutes"
            body="StepStitch is Apache-2.0 and self-hosted by default. The SDK has zero runtime dependencies; the service is one container. Your traces never leave your infrastructure."
          />
        </div>

        <div className="mt-12 grid gap-5 lg:grid-cols-2">
          <Reveal>
            <div className="flex h-full flex-col gap-4 rounded-2xl border border-line bg-surface p-6">
              <h3 className="text-base font-semibold text-fg">
                1. Install the browser SDK
              </h3>
              <p className="text-[15px] text-muted">
                Capture structural footsteps, redacted in the page.
              </p>
              <CodeBlock code={`npm install @stepstitch/tracker`} />
              <CodeBlock
                code={`import { createTracker } from '@stepstitch/tracker';

const tracker = createTracker({
  ingestEndpoint: '/api/stepstitch/v1/session',
  profile: 'financial-services-enterprise',
});
tracker.start(); // OFF until consent; honors GPC/DNT`}
              />
            </div>
          </Reveal>

          <Reveal delay={0.06}>
            <div className="flex h-full flex-col gap-4 rounded-2xl border border-line bg-surface p-6">
              <h3 className="text-base font-semibold text-fg">
                2. Deploy the service
              </h3>
              <p className="text-[15px] text-muted">
                One container with a Postgres database. Railway, Docker, or your
                own Kubernetes.
              </p>
              <CodeBlock
                code={`# Railway: deploys the Dockerfile + Postgres
railway up`}
              />
              <CodeBlock
                code={`# Or pull the published multi-arch image
docker pull ghcr.io/cykiller/stepstitch-api:latest
docker run -p 8000:8000 \\
  -e DATABASE_URL=... \\
  -e STEPSTITCH_ADMIN_TOKEN=... \\
  -e STEPSTITCH_INGEST_TOKEN=... \\
  -e STEPSTITCH_PROFILE=financial-services-enterprise \\
  ghcr.io/cykiller/stepstitch-api:latest`}
              />
            </div>
          </Reveal>
        </div>

        <Reveal>
          <div className="mt-5 rounded-2xl border border-line bg-surface p-6">
            <h3 className="text-base font-semibold text-fg">
              3. Pick a privacy profile
            </h3>
            <p className="mt-2 max-w-2xl text-[15px] text-muted">
              A profile can only <span className="text-fg">tighten</span> the
              privacy boundary, never loosen it. Drift is guarded by a named test.
            </p>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              {profiles.map(([name, desc]) => (
                <div
                  key={name}
                  className="rounded-xl border border-line bg-surface-2/40 p-4"
                >
                  <p className="font-mono text-[13px] text-accent">{name}</p>
                  <p className="mt-1 text-[13px] text-muted">{desc}</p>
                </div>
              ))}
            </div>
          </div>
        </Reveal>

        <Reveal>
          <div className="mt-5 rounded-2xl border border-line bg-surface p-6">
            <h3 className="text-base font-semibold text-fg">
              Optional: the MCP connector
            </h3>
            <p className="mt-2 max-w-2xl text-[15px] text-muted">
              Expose the eight read-only and draft tools to any agent network.
            </p>
            <div className="mt-4">
              <CodeBlock
                code={`pip install 'stepstitch-service[mcp]'
export STEPSTITCH_BASE_URL="https://stepstitch.internal/api/stepstitch/v1"
export STEPSTITCH_TOKEN="<admin-bearer>"
python -m stepstitch_service.mcp_cli`}
              />
            </div>
          </div>
        </Reveal>

        <Reveal>
          <div className="mt-10 flex flex-wrap items-center gap-3">
            <Button href={`${GITHUB_URL}#readme`} external trailingIcon={null}>
              Read the full docs
            </Button>
            <Button href="/#contact" variant="secondary" trailingIcon={null}>
              Talk to us about a managed pilot
            </Button>
          </div>
        </Reveal>
      </Section>
    </main>
  );
}
