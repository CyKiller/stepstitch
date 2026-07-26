import { RELEASE_TAG } from "./version";

// Canonical site origin. Defaults to the live Vercel host; set
// NEXT_PUBLIC_SITE_URL to the custom domain once it is wired up.
export const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://stepstitch.vercel.app";

export const GITHUB_URL = "https://github.com/CyKiller/stepstitch";
export const NPM_URL = "https://www.npmjs.com/package/@stepstitch/tracker";
export const DOCS_URL = `${GITHUB_URL}#readme`;
// Release links are derived, never written out by hand — see lib/version.ts.
export const RELEASES_URL = `${GITHUB_URL}/releases`;
export const LATEST_RELEASE_URL = `${RELEASES_URL}/tag/${RELEASE_TAG}`;
// Single contact intent across the whole page: "Book a pilot".
export const CONTACT_ANCHOR = "#contact";
