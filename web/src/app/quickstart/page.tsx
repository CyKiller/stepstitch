import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, Timer } from "@phosphor-icons/react/dist/ssr";
import { Section, SectionHeader } from "@/components/section";
import { Reveal } from "@/components/reveal";
import { Button } from "@/components/button";
import { CodeBlock } from "@/components/code-block";
import { NPM_URL } from "@/lib/links";

export const metadata: Metadata = {
  title: "Quickstart — StepStitch",
  description:
    "Go from clone to a verified red-to-green reproduction in about ten minutes. Install the SDK, run the credential-free demo, view the operator cockpit, generate a Playwright repro, and walk the verification flow — no ServiceNow, Salesforce, GitHub, or cloud credentials required.",
};

const steps: { title: string; body: string; code?: string; caption?: string }[] = [
  {
    title: "Install the SDK",
    body: "Add the zero-dependency tracker to the app whose bugs you want to reproduce.",
    code: "npm install @stepstitch/tracker",
  },
  {
    title: "Run the credential-free demo",
    body: "The fastest way to see the whole moat. It imports the real service modules and writes a labeled evidence bundle — no database, no credentials, nothing sent.",
    code: "npm run demo      # writes demo/evidence-bundle.json\nnpm run smoke     # asserts no forbidden field or value survived the scrub",
    caption: "Deterministic — re-running produces an identical bundle.",
  },
  {
    title: "Mount the service (or use the reference host)",
    body: "For the live path, run the ingest service against a local Postgres. The server scrubber is the trust boundary — it strips NPI again on ingest, independent of the SDK.",
    code: "export DATABASE_URL=postgres://localhost/stepstitch\nexport STEPSTITCH_INGEST_TOKEN=dev-ingest STEPSTITCH_ADMIN_TOKEN=dev-admin\nuvicorn server.app:app --port 8000",
    caption: "Copy .env.example to .env and fill in the placeholders.",
  },
  {
    title: "Submit a demo trace",
    body: "Seed one realistic, already-structural trace (transfer → 500) into the running service.",
    code: "STEPSTITCH_BASE_URL=http://localhost:8000 STEPSTITCH_INGEST_TOKEN=dev-ingest \\\n  node scripts/seed-demo-trace.mjs",
  },
  {
    title: "View the operator cockpit",
    body: "Open the read-only cockpit, paste your admin token, and inspect the sanitized evidence: summary, replayability, privacy posture, and verification history.",
    code: "open http://localhost:8000/dashboard",
  },
  {
    title: "Generate a Playwright repro",
    body: "Compile the trace into a deterministic Playwright test. It fails while the bug exists and passes once it is fixed. No credentials are embedded.",
    code: "curl -H \"Authorization: Bearer $STEPSTITCH_ADMIN_TOKEN\" \\\n  http://localhost:8000/api/stepstitch/v1/session/<trace_id>/playwright",
  },
  {
    title: "Walk the verification / corpus flow",
    body: "Report a pre-fix run (red) then a post-fix run (green). Only red→green is recorded as confirmed_fixed in the regression corpus.",
    code: "# POST /session/<trace_id>/verify  { \"pre_passed\": false }      -> reproduced_unfixed\n# POST /session/<trace_id>/verify  { \"pre_passed\": false, \"post_passed\": true } -> confirmed_fixed",
    caption: "See demo/README.md for the full live walk-through.",
  },
];

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
            eyebrow="Quickstart"
            title="From clone to a verified reproduction in ~10 minutes"
            body="The first two steps need nothing but Node and the repo — the credential-free demo proves the whole loop offline. The rest wires up the live service so you can submit a trace and watch it become a Playwright repro and a confirmed fix."
          />
        </div>

        <Reveal>
          <div className="mt-8 inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-[13px] text-muted">
            <Timer size={15} weight="bold" className="text-accent" />
            No ServiceNow, Salesforce, GitHub, Copilot, or cloud credentials required.
          </div>
        </Reveal>

        <ol className="mt-10 grid gap-4">
          {steps.map((s, i) => (
            <Reveal key={s.title} delay={Math.min(i * 0.04, 0.2)}>
              <li className="rounded-2xl border border-line bg-surface p-6">
                <div className="flex items-center gap-3">
                  <span className="grid size-7 shrink-0 place-items-center rounded-full bg-accent-solid text-[13px] font-semibold text-accent-fg">
                    {i + 1}
                  </span>
                  <h3 className="text-base font-semibold text-fg">{s.title}</h3>
                </div>
                <p className="mt-3 text-[14.5px] leading-relaxed text-muted">{s.body}</p>
                {s.code ? (
                  <div className="mt-4">
                    <CodeBlock code={s.code} caption={s.caption} />
                  </div>
                ) : null}
              </li>
            </Reveal>
          ))}
        </ol>

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
