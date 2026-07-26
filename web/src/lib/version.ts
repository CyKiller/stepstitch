// The currently released version, kept in step with the rest of the repo by
// release-please. The literal below is rewritten on every release cut — the marker
// comment is what release-please matches on, so do not reflow this line or move the
// comment. See the `extra-files` list in release-please-config.json.
//
// Anything on the site that names the shipped version must read from here. Hardcoding
// it in a component means it silently goes stale the moment a release lands, which is
// exactly what happened to the footer and the "what's new" link at 0.6.0.
export const RELEASE_VERSION = "0.6.0"; // x-release-please-version

/** The release tag, e.g. `v0.7.0`. */
export const RELEASE_TAG = `v${RELEASE_VERSION}`;
