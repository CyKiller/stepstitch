import { Nav } from "@/components/nav";
import { Hero } from "@/components/hero";
import { Problem } from "@/components/problem";
import { HowItWorks } from "@/components/how-it-works";
import { WorkflowSection } from "@/components/workflow-section";
import { DemoSection } from "@/components/demo-section";
import { Comparison } from "@/components/comparison";
import { Features } from "@/components/features";
import { Agentic } from "@/components/agentic";
import { Trust } from "@/components/trust";
import { Contact } from "@/components/contact";
import { Footer } from "@/components/footer";

export default function Home() {
  return (
    <>
      <Nav />
      <main className="flex-1">
        <Hero />
        <Problem />
        <HowItWorks />
        <WorkflowSection />
        <DemoSection />
        <Comparison />
        <Features />
        <Agentic />
        <Trust />
        <Contact />
      </main>
      <Footer />
    </>
  );
}
