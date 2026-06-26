import { Hero } from "@/components/hero";
import { PlainExplainer } from "@/components/plain-explainer";
import { Problem } from "@/components/problem";
import { HowItWorks } from "@/components/how-it-works";
import { WorkflowSection } from "@/components/workflow-section";
import { DemoSection } from "@/components/demo-section";
import { Comparison } from "@/components/comparison";
import { Features } from "@/components/features";
import { Enterprise } from "@/components/enterprise";
import { Agentic } from "@/components/agentic";
import { Trust } from "@/components/trust";
import { OpenCore } from "@/components/open-core";
import { CaseStudies } from "@/components/case-studies";
import { Faq } from "@/components/faq";
import { Contact } from "@/components/contact";

export default function Home() {
  return (
    <main id="main" className="flex-1">
      <Hero />
      <PlainExplainer />
      <Problem />
      <HowItWorks />
      <WorkflowSection />
      <DemoSection />
      <Comparison />
      <Features />
      <Enterprise />
      <Agentic />
      <Trust />
      <OpenCore />
      <CaseStudies />
      <Faq />
      <Contact />
    </main>
  );
}
