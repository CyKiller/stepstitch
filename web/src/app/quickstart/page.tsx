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
    body: "One command brings up Postgres and the ingest host with throwaway dev tokens. Prefer to run it yourself? The uvicorn line below does the same thing against your own database.",
    code: "docker compose up --build      # Postgres + host, dev tokens, http://localhost:8000\n\n# or, against your own database:\nexport DATABASE_URL=postgres://localhost/stepstitch\nexport STEPSTITCH_INGEST_TOKEN=dev-ingest STEPSTITCH_ADMIN_TOKEN=dev-admin\nexport STEPSTITCH_APP_BASE_URL=https://staging.your-app.example   # where repros should point\nuvicorn server.app:app --port 8000",
  },
  {
    title: "Check the install before going further",
    body: "doctor walks the whole chain — environment, host, database, both tokens, capture policy and reproduction settings — and names the fix for anything broken. It never prints a secret value, so its output is safe to paste into an issue.",
    code: "pip install ./service && stepstitch doctor",
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
    title: "Point reproductions at your app, then generate one",
    body: "A trace knows the route template, not your hostname, and never recorded what was typed. Supply the rest once and every generated test carries a READY / NEEDS-CONFIG checklist naming anything still missing. Configuration stores env var names, never credentials.",
    code: "curl -X PUT -H \"Authorization: Bearer $STEPSTITCH_ADMIN_TOKEN\" \\\n  -H 'Content-Type: application/json' \\\n  -d '{\"config\":{\"base_url\":\"https://staging.your-app.example\",\"route_params\":{\"id\":\"1001\"}}}' \\\n  http://localhost:8000/admin/config/repro\n\ncurl -H \"Authorization: Bearer $STEPSTITCH_ADMIN_TOKEN\" \\\n  http://localhost:8000/api/stepstitch/v1/session/<trace_id>/playwright",
  },
  {
    title: "Close the loop from CI",
    body: "Your CI runs the reproduction on the buggy commit and again on the fix, then posts both measured outcomes. confirmed_fixed means StepStitch actually observed the test fail and then pass — if either run does not complete, nothing is recorded. Issue CI a verify-scoped token from the console's Agents tab; it never needs your admin token.",
    code: "# the shipped workflow does this for you: .github/workflows/stepstitch-repro.yml\n# red  -> checkout the pre-fix ref, run the repro, expect FAIL\n# green -> checkout the fix,       run the repro, expect PASS\ncurl -X POST -H \"Authorization: Bearer $STEPSTITCH_VERIFY_TOKEN\" \\\n  -H 'Content-Type: application/json' \\\n  -d '{\"pre_passed\": false, \"post_passed\": true, \"fix_ref\": \"PR #482\"}' \\\n  http://localhost:8000/api/stepstitch/v1/session/<trace_id>/verify   # -> confirmed_fixed",
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
