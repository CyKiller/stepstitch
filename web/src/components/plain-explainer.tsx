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
    body: "It captures what they clicked and what failed. Never their screen, their typing, or any personal data.",
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
      <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 md:py-20">
        <Reveal>
          <p className="text-center text-sm font-medium uppercase tracking-[0.16em] text-accent">
            In plain words
          </p>
        </Reveal>
        <div className="mt-10 grid gap-6 md:grid-cols-3">
          {steps.map((s, i) => {
            const Glyph = s.icon;
            return (
              <Reveal key={s.title} delay={i * 0.08}>
                <div className="relative h-full">
                  <div className="flex items-center gap-3">
                    <span className="grid size-11 shrink-0 place-items-center rounded-2xl border border-line bg-surface text-accent">
                      <Glyph size={22} weight="bold" />
                    </span>
                    <span className="font-mono text-sm text-muted">
                      {i + 1}
                    </span>
                  </div>
                  <h3 className="mt-4 text-lg font-semibold tracking-tight text-fg">
                    {s.title}
                  </h3>
                  <p className="mt-2 text-[15px] leading-relaxed text-muted">
                    {s.body}
                  </p>
                </div>
              </Reveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}
