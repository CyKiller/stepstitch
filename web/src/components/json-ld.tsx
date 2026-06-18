import { SITE_URL, GITHUB_URL } from "@/lib/links";

// Structured data for richer SERP eligibility: Organization, the product as a
// SoftwareApplication, and an FAQ matching likely "is this session replay?"
// style queries. Rendered as a single JSON-LD graph.
const graph = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${SITE_URL}/#org`,
      name: "StepStitch",
      url: SITE_URL,
      logo: `${SITE_URL}/icon`,
      sameAs: [GITHUB_URL],
    },
    {
      "@type": "SoftwareApplication",
      name: "StepStitch",
      applicationCategory: "DeveloperApplication",
      operatingSystem: "Self-hosted",
      url: SITE_URL,
      description:
        "Issue-to-repro infrastructure. Turns a user-reported bug into a scrubbed event timeline, a replayability score, and a copyable Playwright reproduction, without capturing screens, input values, or PII.",
      license: "https://www.apache.org/licenses/LICENSE-2.0",
      offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
      publisher: { "@id": `${SITE_URL}/#org` },
    },
    {
      "@type": "FAQPage",
      mainEntity: [
        {
          "@type": "Question",
          name: "Is StepStitch session replay?",
          acceptedAnswer: {
            "@type": "Answer",
            text: "No. StepStitch captures the structure of what broke (route templates, stable selectors, API status codes), never screens, input values, page text, or raw URLs. It is issue-to-repro infrastructure, not session replay.",
          },
        },
        {
          "@type": "Question",
          name: "What is a replayability score?",
          acceptedAnswer: {
            "@type": "Answer",
            text: "A deterministic 0 to 1 score with an A to F grade and warnings that tells you whether a user-reported bug is reproducible, before anyone opens an editor.",
          },
        },
        {
          "@type": "Question",
          name: "Is StepStitch open source?",
          acceptedAnswer: {
            "@type": "Answer",
            text: "Yes. The SDK, service core, MCP connector, and adapters are all Apache-2.0 and self-hostable, so your reviewers can audit exactly what is captured and what is dropped.",
          },
        },
        {
          "@type": "Question",
          name: "How does StepStitch protect PII?",
          acceptedAnswer: {
            "@type": "Answer",
            text: "The SDK redacts in the browser and the server scrubs every trace again before storage. It never stores screenshots, input values, page text, request bodies, cookies, or identifiers like SSNs and card numbers.",
          },
        },
      ],
    },
  ],
};

export function JsonLd() {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(graph) }}
    />
  );
}
