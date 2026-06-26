import { Section, SectionHeader } from "./section";
import { LiveDemo } from "./live-demo";
import { Bezel } from "./bezel";
import { Reveal } from "./reveal";
import { RedToGreen } from "./red-to-green";

export function DemoSection() {
  return (
    <Section id="demo" className="border-b border-line">
      <SectionHeader
        title="See exactly what your team gets"
        body="A real example, live from a running StepStitch service. Click through the tabs to follow what happened, how reproducible it is, what was kept private, and the test it wrote automatically."
      />

      {/* The outcome first — the compiled repro running red, then green —
          then the full evidence that produced it. */}
      <Reveal className="mx-auto mt-12 max-w-2xl">
        <RedToGreen />
      </Reveal>

      <div className="mt-8">
        <Bezel>
          <LiveDemo />
        </Bezel>
      </div>
    </Section>
  );
}
