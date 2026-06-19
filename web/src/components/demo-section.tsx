import { Section, SectionHeader } from "./section";
import { LiveDemo } from "./live-demo";
import { Bezel } from "./bezel";

export function DemoSection() {
  return (
    <Section id="demo" className="border-b border-line">
      <SectionHeader
        eyebrow="Live demo"
        title="See exactly what your team gets"
        body="A real example, live from a running StepStitch service. Click through the tabs to follow what happened, how reproducible it is, what was kept private, and the test it wrote automatically."
      />
      <div className="mt-12">
        <Bezel>
          <LiveDemo />
        </Bezel>
      </div>
    </Section>
  );
}
