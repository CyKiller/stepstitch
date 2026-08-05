import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Analytics } from "@vercel/analytics/next";
import { SpeedInsights } from "@vercel/speed-insights/next";
import { JsonLd } from "@/components/json-ld";
import { Nav } from "@/components/nav";
import { Footer } from "@/components/footer";
import { SITE_URL } from "@/lib/links";
import "./globals.css";

export const metadata: Metadata = {
  title: "StepStitch: issue-to-repro infrastructure, not session replay",
  description:
    "Turn a user-reported bug into a regression test. A replayability score and a Playwright repro, with no screens, input values or page text captured; free text is policy-scrubbed. Open source, self-hosted.",
  metadataBase: new URL(SITE_URL),
  robots: { index: true, follow: true },
  openGraph: {
    title: "StepStitch: issue-to-repro infrastructure",
    description:
      "Turn a user-reported bug into a regression test. Privacy-safe by default. Open source. Self-hosted.",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "StepStitch: issue-to-repro infrastructure",
    description:
      "Turn a user-reported bug into a regression test. Privacy-safe by default. Open source. Self-hosted.",
  },
};

// Resolve theme before paint: stored choice wins, else system preference.
const themeScript = `(function(){try{var t=localStorage.getItem('ss-theme');if(!t){t=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}document.documentElement.setAttribute('data-theme',t);}catch(e){document.documentElement.setAttribute('data-theme','dark');}})();`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${GeistSans.variable} ${GeistMono.variable} h-full`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        {/* Without JS, reveal wrappers would stay at opacity 0. Force them
            visible so crawlers and no-JS visitors see all content. */}
        <noscript>
          <style>{`.ss-reveal{opacity:1!important;transform:none!important}`}</style>
        </noscript>
      </head>
      <body className="min-h-full flex flex-col bg-bg text-fg font-sans">
        <JsonLd />
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-accent-solid focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-accent-fg"
        >
          Skip to content
        </a>
        <div className="grain-overlay" aria-hidden />
        <Nav />
        {children}
        <Footer />
        <Analytics />
        <SpeedInsights />
      </body>
    </html>
  );
}
