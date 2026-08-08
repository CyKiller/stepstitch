import { GithubLogo } from "@phosphor-icons/react/dist/ssr";
import { Reveal } from "./reveal";
import { Aurora } from "./aurora";
import { Button } from "./button";
import { Tilt } from "./tilt";
import { Bezel } from "./bezel";
import { SAMPLE_TRACE } from "@/lib/stepstitch";

export function Hero() {
  return (
    <section
      id="top"
      className="relative isolate overflow-hidden border-b border-line"
    >
      <Aurora />
      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-12 px-4 pt-16 pb-20 sm:px-6 md:grid-cols-12 md:pt-24 md:pb-28">
        <div className="flex flex-col justify-center md:col-span-7">
          <Reveal>
            <span className="inline-flex w-fit items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-muted">
              <span className="size-1.5 rounded-full bg-ok" aria-hidden />
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
              The AI gets a policy-constrained, structural account of the
              failure — the shape of the bug, not the customer&apos;s screen,
              typing, or page content. Then StepStitch reruns the same frozen
              test and measures red-to-green itself. Self-hosted: you hold the
              evidence and the keys.
            </p>
          </Reveal>

          <Reveal delay={0.15}>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button href="#contact">Book a pilot</Button>
              <Button
                href="/self-host"
                variant="secondary"
                leadingIcon={GithubLogo}
                trailingIcon={null}
              >
                Self-host free
              </Button>
            </div>
          </Reveal>
        </div>

        {/* Real product output: the actual generated Playwright repro + grade. */}
        <div className="md:col-span-5">
          <Reveal delay={0.2}>
            <Tilt>
              <Bezel innerClassName="brand-gradient-border">
                <figure>
                  <div className="flex items-center justify-between border-b border-line px-4 py-3">
                    <span className="font-mono text-xs text-muted">
                      generate_playwright_repro
                    </span>
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-ok/12 px-2.5 py-1 text-xs font-semibold text-ok">
                      <span className="pulse-dot size-1.5 rounded-full bg-ok" />
                      Replayability {SAMPLE_TRACE.replayability.grade}
                    </span>
                  </div>
                  <pre className="overflow-x-auto px-4 py-4 font-mono text-[12.5px] leading-relaxed text-fg/90 [mask-image:linear-gradient(to_right,#000_calc(100%-2.5rem),transparent)]">
                    <code>{SAMPLE_TRACE.playwright_code}</code>
                  </pre>
                  <figcaption className="border-t border-line px-4 py-2.5 font-mono text-[11px] text-muted">
                    Generated from a scrubbed trace. Runs red, fix turns it
                    green.
                  </figcaption>
                </figure>
              </Bezel>
            </Tilt>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
