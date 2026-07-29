import { Section, SectionHeader } from "./section";
import { LiveDemo } from "./live-demo";
import { Bezel } from "./bezel";
import { Reveal } from "./reveal";
import { RedToGreen } from "./red-to-green";

export function DemoSection() {
  return (
    <Section id="demo" className="border-b border-line">
      {/* The panel below fetches its trace at runtime and may fall back to the bundled
          sample, so this copy stays source-neutral — the badge and the disclosure line
          inside the panel say where the trace actually came from. */}
      <SectionHeader
        title="See exactly what your team gets"
        body="A worked example straight from the StepStitch pipeline — the badge on the panel says whether it was fetched moments ago from a live service or is the bundled synthetic sample. Click through the tabs to follow what happened, how reproducible it is, what was kept private, and the test it wrote automatically."
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
