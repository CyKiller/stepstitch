import { Hero } from "@/components/hero";
import { PlainExplainer } from "@/components/plain-explainer";
import { Pillars } from "@/components/pillars";
import { HowItWorks } from "@/components/how-it-works";
import { DemoSection } from "@/components/demo-section";
import { Comparison } from "@/components/comparison";
import { Contact } from "@/components/contact";

export default function Home() {
  return (
    <main id="main" className="flex-1">
      <Hero />
      <PlainExplainer />
      <DemoSection />
      <HowItWorks />
      <Comparison />
      <Pillars />
      <Contact />
    </main>
  );
}
