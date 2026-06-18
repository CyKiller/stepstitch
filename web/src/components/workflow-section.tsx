import { Section, SectionHeader } from "./section";
import { WorkflowShowcase } from "./workflow-showcase";

export function WorkflowSection() {
  return (
    <Section id="workflow" className="border-b border-line">
      <SectionHeader
        eyebrow="One report, two views"
        title="The same moment, from both sides"
        body="Your user keeps their screen, their inputs, and their data. Your engineers get structure, a score, and a runnable test. Step through the whole workflow."
      />
      <WorkflowShowcase />
    </Section>
  );
}
