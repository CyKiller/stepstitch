import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, Timer } from "@phosphor-icons/react/dist/ssr";
import { Section, SectionHeader } from "@/components/section";
import { Reveal } from "@/components/reveal";
import { Button } from "@/components/button";
import { CodeBlock } from "@/components/code-block";
import { NPM_URL } from "@/lib/links";
import {
  DOCKER_DOCTOR,
  DOCKER_SEED,
  DOCKER_UP,
  MANUAL_HOST_TERMINAL_1,
  MANUAL_HOST_TERMINAL_2,
  OFFLINE_DEMO,
  OFFLINE_DEMO_WINDOWS_ACTIVATE,
  SDK_INSTALL,
} from "@/lib/quickstart-commands";

export const metadata: Metadata = {
  title: "Quickstart: StepStitch",
  description:
    "Three ways in: add the zero-dependency SDK with npm alone, prove the whole loop offline with Node and Python, or run the full host with Docker and walk a trace to a verified red-to-green fix. Every command works in the order shown.",
};

// Each journey states its real prerequisites up front, and its commands are imported from
// one shared module so the README, this page, and the clean-install CI gate can never
// document three different sequences.
type Step = { title: string; body: string; code?: string; caption?: string };
type Journey = { name: string; prereqs: string; intro: string; steps: Step[] };

const journeys: Journey[] = [
  {
    name: "Add the SDK to your app",
    prereqs: "Needs Node and npm. Nothing else.",
    intro:
      "The zero-dependency tracker goes into the app whose bugs you want reproduced. Capture is off until a user consents.",
    steps: [
      {
        title: "Install the tracker",
        body: "One package, no transitive dependencies, works from both ESM and CommonJS. Consent is off by default: until your app calls grantConsent(), nothing is observed and nothing is sent.",
        code: SDK_INSTALL,
      },
    ],
  },
  {
    name: "Prove the loop offline",
    prereqs: "Needs Git, Node 20+, and Python 3.10+. Nothing leaves your machine.",
    intro:
      "The demo imports the real service modules for scrubbing, scoring, compiling, and verdicts. Python and the service package are therefore genuine prerequisites, and installing them is part of the sequence.",
    steps: [
      {
        title: "Clone, install the service, run the demo",
        body: "Runs the real pipeline end to end (report → scrub → score → Playwright → verdict) with no database, no network and no credentials, then asserts no forbidden field or value survived the scrub. The venv keeps the service install disposable.",
        code: OFFLINE_DEMO,
        caption: `Windows (PowerShell): activate with ${OFFLINE_DEMO_WINDOWS_ACTIVATE}. Deterministic: re-running writes an identical demo/evidence-bundle.json.`,
      },
    ],
  },
  {
    name: "Run the full host",
    prereqs:
      "Needs Docker. (Prefer no Docker? The manual path below needs Python 3.10+ and a Postgres you provide.)",
    intro:
      "One command brings up Postgres and the ingest host with throwaway dev tokens. From there you seed a trace, check the install, point reproductions at your app, and close the loop from CI.",
    steps: [
      {
        title: "Bring up Postgres and the host",
        body: "-d returns your terminal once the containers are up (follow logs with docker compose logs -f stepstitch). Then open http://localhost:8000/dashboard and paste dev-admin when the console asks for a token. These are throwaway development credentials and must never be used in production.",
        code: DOCKER_UP,
      },
      {
        title: "Seed a demo trace",
        body: "Submits one realistic, already-structural trace (transfer → 500). The script needs both variables: it refuses to guess where your host is or what its ingest token might be.",
        code: DOCKER_SEED,
      },
      {
        title: "Check the install where the configuration lives",
        body: "doctor walks the whole chain, including the environment, host, database, both tokens, capture policy, and reproduction settings, and names the fix for anything broken. It reads configuration from its own environment, so with Compose it must run inside the container; on your host shell it would truthfully report the variables missing. It never prints a secret value. (-T skips TTY allocation, so this exact line also works from scripts and CI.)",
        code: DOCKER_DOCTOR,
      },
      {
        title: "No Docker? Terminal 1: run the host",
        body: "macOS/Linux; on Windows use the Docker path above. Install the service and the host's requirements before uvicorn ever starts, and export the configuration first. STEPSTITCH_APP_BASE_URL is where generated reproductions will point: set it to your staging app now, or every repro targets localhost:3000 until you configure it. uvicorn runs in the foreground: leave this terminal open.",
        code: MANUAL_HOST_TERMINAL_1,
      },
      {
        title: "Terminal 2: check it with doctor",
        body: "A second terminal, because uvicorn owns the first. A fresh shell has neither the venv nor your exports, and doctor reads configuration only from its own environment, so activate and export again before running it.",
        code: MANUAL_HOST_TERMINAL_2,
      },
      {
        title: "Point reproductions at your app, then generate one",
        body: "A trace knows the route template, not your hostname, and never recorded what was typed. Supply the rest once and every generated test carries a READY / NEEDS-CONFIG checklist naming anything still missing. Configuration stores env var names, never credentials.",
        code: "curl -X PUT -H \"Authorization: Bearer $STEPSTITCH_ADMIN_TOKEN\" \\\n  -H 'Content-Type: application/json' \\\n  -d '{\"config\":{\"base_url\":\"https://staging.your-app.example\",\"route_params\":{\"id\":\"1001\"}}}' \\\n  http://localhost:8000/admin/config/repro\n\ncurl -H \"Authorization: Bearer $STEPSTITCH_ADMIN_TOKEN\" \\\n  http://localhost:8000/api/stepstitch/v1/session/<trace_id>/playwright",
      },
      {
        title: "Close the loop from CI",
        body: "Your CI runs the reproduction on the buggy commit and again on the fix, then posts both measured outcomes. confirmed_fixed means StepStitch actually observed the test fail and then pass: if either run does not complete, nothing is recorded. Issue CI a verify-scoped token from the console's Agents tab; it never needs your admin token.",
        code: "# the shipped workflow does this for you: .github/workflows/stepstitch-repro.yml\n# red  -> checkout the pre-fix ref, run the repro, expect FAIL\n# green -> checkout the fix,       run the repro, expect PASS\ncurl -X POST -H \"Authorization: Bearer $STEPSTITCH_VERIFY_TOKEN\" \\\n  -H 'Content-Type: application/json' \\\n  -d '{\"pre_passed\": false, \"post_passed\": true, \"fix_ref\": \"PR #482\"}' \\\n  http://localhost:8000/api/stepstitch/v1/session/<trace_id>/verify   # -> confirmed_fixed",
      },
    ],
  },
];

// Continuous step numbering across the three journeys, computed statically because the
// React compiler (rightly) refuses render-time mutation.
const stepOffsets = journeys.map((_, i) =>
  journeys.slice(0, i).reduce((acc, j) => acc + j.steps.length, 0),
);

export default function QuickstartPage() {
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
            eyebrow="Quickstart"
            title="Three ways in, smallest first"
            body="Add the SDK to your app with npm alone. Prove the whole loop offline with Node and Python. Or run the full host and watch a submitted trace become a Playwright repro and a confirmed fix. Each path states its real prerequisites, and every command works in the order shown."
          />
        </div>

        <Reveal>
          <div className="mt-8 inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-[13px] text-muted">
            <Timer size={15} weight="bold" className="text-accent" />
            No ServiceNow, Salesforce, GitHub, Copilot, or cloud credentials required.
          </div>
        </Reveal>

        <div className="mt-12 grid gap-14">
          {journeys.map((journey, journeyIndex) => (
            <div key={journey.name}>
              <Reveal>
                <h2 className="text-xl font-semibold tracking-tight text-fg">
                  {journey.name}
                </h2>
                <p className="mt-1 text-[13.5px] font-medium text-accent">
                  {journey.prereqs}
                </p>
                <p className="mt-3 max-w-2xl text-[14.5px] leading-relaxed text-muted">
                  {journey.intro}
                </p>
              </Reveal>
              <ol className="mt-6 grid gap-4">
                {journey.steps.map((s, stepIndex) => {
                  const n = stepOffsets[journeyIndex] + stepIndex + 1;
                  return (
                    <Reveal key={s.title}>
                      <li className="rounded-2xl border border-line bg-surface p-6">
                        <div className="flex items-center gap-3">
                          <span className="grid size-7 shrink-0 place-items-center rounded-full bg-accent-solid text-[13px] font-semibold text-accent-fg">
                            {n}
                          </span>
                          <h3 className="text-base font-semibold text-fg">{s.title}</h3>
                        </div>
                        <p className="mt-3 text-[14.5px] leading-relaxed text-muted">
                          {s.body}
                        </p>
                        {s.code ? (
                          <div className="mt-4">
                            <CodeBlock code={s.code} caption={s.caption} />
                          </div>
                        ) : null}
                      </li>
                    </Reveal>
                  );
                })}
              </ol>
            </div>
          ))}
        </div>

        <Reveal>
          <div className="mt-10 flex flex-wrap items-center gap-3">
            <Button href="/demo" trailingIcon={null}>
              See the finished demo
            </Button>
            <Button href={NPM_URL} variant="secondary" external trailingIcon={null}>
              @stepstitch/tracker on npm
            </Button>
          </div>
        </Reveal>
      </Section>
    </main>
  );
}
