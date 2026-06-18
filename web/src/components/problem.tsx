import { Reveal } from "./reveal";
import { Section } from "./section";

export function Problem() {
  return (
    <Section id="why">
      <Reveal>
        <p className="max-w-4xl text-2xl font-medium leading-snug tracking-tight text-fg md:text-3xl">
          Most engineering teams do not need another recording to watch. They
          need a user-reported bug that can become a{" "}
          <span className="text-accent">regression test</span>.
        </p>
      </Reveal>

      <div className="mt-14 grid gap-px overflow-hidden rounded-2xl border border-line bg-line md:grid-cols-2">
        <Reveal className="bg-surface">
          <div className="h-full p-7 md:p-8">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">
              Session replay
            </h3>
            <p className="mt-4 text-lg font-medium text-fg">
              Captures the screen, then asks an engineer to watch it back.
            </p>
            <ul className="mt-5 space-y-2.5 text-[15px] text-muted">
              <li>Records pixels, text, and input values by default</li>
              <li>Carries PII into a third-party tool you do not control</li>
              <li>Often banned outright in regulated environments</li>
              <li>Leaves you with a video, not a fix</li>
            </ul>
          </div>
        </Reveal>

        <Reveal delay={0.08} className="bg-surface">
          <div className="h-full p-7 md:p-8">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-accent">
              StepStitch
            </h3>
            <p className="mt-4 text-lg font-medium text-fg">
              Captures the structure of what broke, then compiles a test.
            </p>
            <ul className="mt-5 space-y-2.5 text-[15px] text-muted">
              <li>Route templates, stable selectors, API status codes</li>
              <li>Scrubbed in the browser and again on the server</li>
              <li>Self-hosted, so the data never leaves your boundary</li>
              <li>Leaves you with a runnable Playwright reproduction</li>
            </ul>
          </div>
        </Reveal>
      </div>
    </Section>
  );
}
