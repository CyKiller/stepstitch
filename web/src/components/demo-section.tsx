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
        body="Follow a generated trace from structural timeline to replayability score, privacy posture, and runnable Playwright test. The panel always states its source."
      />

      {/* Show the measured outcome before the evidence that produced it. */}
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
