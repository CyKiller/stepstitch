import { GithubLogo } from "@phosphor-icons/react/dist/ssr";
import { Reveal } from "./reveal";
import { Aurora } from "./aurora";
import { Button } from "./button";
import { Bezel } from "./bezel";
import { SAMPLE_TRACE } from "@/lib/stepstitch";

const heroCode = SAMPLE_TRACE.playwright_code.slice(
  SAMPLE_TRACE.playwright_code.indexOf("test('StepStitch"),
);

export function Hero() {
  return (
    <section
      id="top"
      className="relative isolate overflow-hidden border-b border-line"
    >
      <Aurora />
      <div className="mx-auto grid max-w-7xl grid-cols-1 items-center gap-10 px-4 pb-16 pt-12 sm:px-6 md:grid-cols-12 md:pb-20 md:pt-16">
        <div className="md:col-span-7">
          <Reveal>
            <span className="inline-flex w-fit items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-muted">
              Open source, Apache-2.0
            </span>
          </Reveal>

          <Reveal delay={0.05}>
            <h1 className="mt-5 text-balance text-4xl font-semibold leading-[1.05] tracking-tight text-fg md:text-5xl lg:text-6xl">
              Turn a user-reported bug into a{" "}
              <span className="brand-gradient-text animate-shimmer">
                regression test
              </span>
              .
            </h1>
          </Reveal>

          <Reveal delay={0.1}>
            <p className="mt-5 max-w-[58ch] text-lg leading-relaxed text-muted">
              Capture structural evidence, generate a Playwright reproduction,
              and verify the fix without recording screens, input values, or
              page text.
            </p>
          </Reveal>

          <Reveal delay={0.15}>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button href="/demo" event="hero_demo">
                See the demo
              </Button>
              <Button
                href="/self-host"
                variant="secondary"
                leadingIcon={GithubLogo}
                trailingIcon={null}
                event="hero_self_host"
              >
                Self-host
              </Button>
            </div>
          </Reveal>
        </div>

        {/* Real product output: the actual generated Playwright repro + grade. */}
        <div className="md:col-span-5">
          <Reveal delay={0.2}>
            <Bezel innerClassName="brand-gradient-border">
              <figure>
                <div className="flex items-center justify-between border-b border-line px-4 py-3">
                  <span className="font-mono text-xs text-muted">
                    generated-repro.spec.ts
                  </span>
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-ok/12 px-2.5 py-1 text-xs font-semibold text-ok">
                    Replayability {SAMPLE_TRACE.replayability.grade}
                  </span>
                </div>
                <pre className="max-h-[22rem] overflow-auto px-4 py-4 font-mono text-[12px] leading-relaxed text-fg/90 [mask-image:linear-gradient(to_right,#000_calc(100%-2.5rem),transparent)]">
                  <code>{heroCode}</code>
                </pre>
                <figcaption className="border-t border-line px-4 py-2.5 font-mono text-[11px] text-muted">
                  Real output from the committed synthetic trace.
                </figcaption>
              </figure>
            </Bezel>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
