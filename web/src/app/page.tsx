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
      {/* Progressive depth: every audience gets the plain outcome first, then
          self-selects into proof → build → compliance. Order matters more than
          copy here — see the "Stays Fixed" campaign plan. */}

      {/* Tier 1 — Outcome (everyone) */}
      <Hero />
      <PlainExplainer />
      <Problem />

      {/* Tier 2 — Proof (engineering leader): proof lands while a skimmer is
          still reading, so CaseStudies sits high, not buried at the bottom. */}
      <HowItWorks />
      <Comparison />
      <CaseStudies />
      <WorkflowSection />

      {/* Tier 3 — Build (developer) */}
      <DemoSection />
      <Features />
      <Agentic />
      <OpenCore />

      {/* Tier 4 — Trust (regulated enterprise) */}
      <Enterprise />
      <Trust />

      {/* Close (everyone) */}
      <Faq />
      <Contact />
    </main>
  );
}
