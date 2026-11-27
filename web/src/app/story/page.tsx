import type { Metadata } from "next";
import { Section, SectionHeader } from "@/components/section";
import { StorySurface } from "@/components/story/story-surface";

// Preview of the homepage scroll story. Not linked, not in the sitemap, and not indexed until
// it is approved. Brief: docs/superpowers/specs/2026-10-23-scroll-story-BRIEF.md
export const metadata: Metadata = {
  title: "Follow one request (preview): StepStitch",
  description: "Follow one customer's report from the moment it fails to a proven fix.",
  robots: { index: false, follow: false },
};

export default function StoryPage() {
  return (
    <>
      <Section>
        <SectionHeader
          as="h1"
          eyebrow="Preview"
          title="Follow one request"
          body="One customer's report, from the moment it fails to a proven fix. Every number on this page comes from one real, committed demo run."
        />
      </Section>
      <StorySurface />
    </>
  );
}
