import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle,
  Clock,
  FileCode,
  ShieldCheck,
  Warning,
  XCircle,
} from "@phosphor-icons/react/dist/ssr";
import { Button } from "@/components/button";
import { ConsoleBoard } from "@/components/console-board";
import { ConsoleOverview } from "@/components/console-overview";
import { Reveal } from "@/components/reveal";
import { Section, SectionHeader } from "@/components/section";

// Whether the proxy is wired (see web/next.config.ts). Server-only: never shipped to the
// browser, and its absence changes the page rather than breaking the build.
const demoOnline = Boolean(process.env.STEPSTITCH_DEMO_HOST);

export const metadata: Metadata = {
  title: "StepStitch console preview - synthetic data, no signup",
  description:
    "Explore the shipping StepStitch overview and failure board over a committed synthetic dataset. The data is invented; the interface and pipeline are real.",
};

const DEMO_URL = "/dashboard/demo";

// The six states a failure moves through. This is the actual lifecycle in shapes.py, not a
// marketing simplification, which is the point: the demo shows one failure sitting in each.
const stages = [
  {
    icon: CheckCircle,
    name: "Fixed and proven",
    body: "The reproduction failed on the buggy commit and passed on the fix. Both runs happened. That pair is the only thing StepStitch accepts as proof, and it is what fills the memory the console matches new reports against.",
    featured: true,
  },
  {
    icon: Clock,
    name: "Waiting for a test run",
    body: "Reported, scrubbed and scored. Nobody has run the generated test yet.",
  },
  {
    icon: ShieldCheck,
    name: "Seen before",
    body: "Structurally close to something already fixed, so the console says where to start.",
  },
  {
    icon: FileCode,
    name: "Confirmed broken",
    body: "The reproduction failed as expected. The bug is real and reproducible on demand.",
  },
  {
    icon: XCircle,
    name: "Still broken",
    body: "A fix was tried. The same test still fails, so the verdict says so.",
  },
  {
    icon: Warning,
    name: "Test needs fixing",
    body: "The reproduction passed on the broken build, so it never reproduced anything.",
  },
];

export default function DashboardPage() {
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
            eyebrow="Console preview"
            title="See the shipping console before you install anything"
            body="Explore the overview and failure board over a committed synthetic dataset, with no signup or credentials. The data is invented; the interface and pipeline are real."
          />
        </div>

        <Reveal className="mt-10">
          <div className="flex flex-wrap items-center gap-3">
            <Button href="#console-preview" event="dashboard_preview">
              Explore the preview
            </Button>
            <Button
              href={demoOnline ? DEMO_URL : "/self-host"}
              variant="secondary"
              event={demoOnline ? "dashboard_live" : "dashboard_self_host"}
            >
              {demoOnline ? "Open the live console" : "Run it on your data"}
            </Button>
          </div>
        </Reveal>

        <Reveal className="mt-12">
          <div id="console-preview" className="scroll-mt-28">
            <ConsoleOverview />
          </div>
        </Reveal>
      </Section>

      <Section className="border-t border-line pt-0">
        <SectionHeader
          title="Six failures, one in every state"
          body="A bug does not go straight from reported to fixed, and a console that only shows those two ends is hiding the part you actually work in. The demo puts one failure in each state so the whole path is visible at once."
        />

        <div className="mt-12 grid gap-4 md:grid-cols-2">
          {stages.map(({ icon: Icon, name, body, featured }) => (
            <Reveal key={name} className={featured ? "md:col-span-2" : undefined}>
              <div
                className={`flex h-full flex-col gap-3 rounded-2xl border p-6 ${
                  featured
                    ? "border-accent/30 bg-[color-mix(in_oklab,var(--accent)_7%,var(--surface))]"
                    : "border-line bg-surface"
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <Icon
                    size={18}
                    weight="duotone"
                    className={featured ? "text-accent" : "text-muted"}
                  />
                  <h3 className="text-base font-semibold text-fg">{name}</h3>
                </div>
                <p
                  className={`text-pretty text-[15px] leading-relaxed text-muted ${
                    featured ? "max-w-3xl" : ""
                  }`}
                >
                  {body}
                </p>
              </div>
            </Reveal>
          ))}
        </div>

        <Reveal className="mt-16">
          <ConsoleBoard />
        </Reveal>
      </Section>

      <Section className="border-t border-line">
        <SectionHeader
          title="What is synthetic, and what is not"
          body="The failures are invented. Everything done to them is the shipping code."
        />

        <div className="mt-10 grid gap-x-12 gap-y-8 md:grid-cols-2">
          <Reveal>
            <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-accent">
              Made up
            </h3>
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              A fictional bank, six invented failures, and fake customer details written into
              the reports on purpose. There is no real person behind any of it, and the
              account numbers and emails you will see redacted were never real.
            </p>
          </Reveal>
          <Reveal>
            <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-accent">
              Real
            </h3>
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              The scrubber that removed those details, the replayability score, the generated
              Playwright test, the red-to-green verdict and the hashed attestation are all
              produced by the same code a self-hosted install runs. The dataset is regenerated
              from that pipeline and a test fails if it drifts.
            </p>
          </Reveal>
        </div>

        <Reveal className="mt-12">
          <div className="flex flex-wrap items-center gap-3">
            <Button href="/quickstart">Point it at your own app</Button>
            <Button href="/security" variant="secondary">
              What it never captures
            </Button>
          </div>
        </Reveal>
      </Section>
    </main>
  );
}
