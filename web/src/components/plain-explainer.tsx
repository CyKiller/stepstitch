import { Warning, ShieldCheck, CheckCircle } from "@phosphor-icons/react/dist/ssr";
import { Reveal } from "./reveal";

const steps = [
  {
    icon: Warning,
    title: "A customer hits a problem",
    body: "Something breaks while they are using your app, like a payment that will not go through.",
  },
  {
    icon: ShieldCheck,
    title: "StepStitch records the steps, not the screen",
    body: "It records which control was used and what failed. It never captures screens, input values, or page text; free text is scrubbed server-side.",
  },
  {
    icon: CheckCircle,
    title: "Your team reproduces it and proves the fix",
    body: "In one click it becomes a test that fails on the bug and passes once it is fixed, so it stays fixed.",
  },
];

export function PlainExplainer() {
  return (
    <section className="border-b border-line bg-surface/40">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-16 sm:px-6 md:grid-cols-12 md:gap-12 md:py-20">
        <Reveal className="md:col-span-4">
          <h2 className="text-2xl font-semibold tracking-tight text-fg md:text-3xl">
            In plain words
          </h2>
          <p className="mt-4 text-[15px] leading-relaxed text-muted">
            No jargon. Three steps from a customer&rsquo;s bad moment to a fix
            that stays fixed.
          </p>
        </Reveal>

        {/* A divided list keeps the sequence easy to scan on every viewport. */}
        <div className="divide-y divide-line border-y border-line md:col-span-8">
          {steps.map((s, i) => {
            const Glyph = s.icon;
            return (
              <Reveal key={s.title} delay={i * 0.08}>
                <div className="flex gap-5 py-6">
                  <span className="grid size-11 shrink-0 place-items-center rounded-2xl border border-line bg-surface text-accent">
                    <Glyph size={22} weight="bold" />
                  </span>
                  <div>
                    <div className="flex items-baseline gap-2.5">
                      <span className="font-mono text-sm text-muted">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <h3 className="text-lg font-semibold tracking-tight text-fg">
                        {s.title}
                      </h3>
                    </div>
                    <p className="mt-2 text-[15px] leading-relaxed text-muted">
                      {s.body}
                    </p>
                  </div>
                </div>
              </Reveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}
