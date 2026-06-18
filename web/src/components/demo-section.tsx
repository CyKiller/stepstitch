import { Section, SectionHeader } from "./section";
import { LiveDemo } from "./live-demo";
import { Bezel } from "./bezel";

export function DemoSection() {
  return (
    <Section id="demo" className="border-b border-line">
      <SectionHeader
        eyebrow="Live demo"
        title="See a real scrubbed trace"
        body="This pulls a sanitized trace straight from a running StepStitch service. The same evidence an engineer or an agent would read: timeline, replayability score, privacy posture, and the generated Playwright test."
      />
      <div className="mt-12">
        <Bezel>
          <LiveDemo />
        </Bezel>
      </div>
    </Section>
  );
}
