import { ImageResponse } from "next/og";

// No `runtime` export: the Edge Runtime is deprecated in this Next version and the
// default Node.js runtime renders ImageResponse fine — it also re-enables static
// generation for this route, which `runtime = "edge"` was silently disabling.
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "StepStitch: issue-to-repro infrastructure";

export default function OgImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#09090b",
          padding: "80px",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "18px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <div style={{ width: 120, height: 16, borderRadius: 8, background: "#34d399" }} />
            <div style={{ width: 120, height: 16, borderRadius: 8, background: "#34d399", opacity: 0.5, marginLeft: 40 }} />
            <div style={{ width: 120, height: 16, borderRadius: 8, background: "#34d399" }} />
          </div>
          <div style={{ color: "#fafafa", fontSize: 40, fontWeight: 600 }}>
            StepStitch
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          {/* Satori (the OG renderer) requires an explicit display on any element
              with more than one child — mixed text + span was fine on the deprecated
              edge runtime only because the route never rendered at build time. A
              wrapping flex row of word spans keeps the two-tone headline. */}
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              columnGap: 18,
              color: "#fafafa",
              fontSize: 76,
              fontWeight: 600,
              lineHeight: 1.05,
              letterSpacing: "-0.03em",
              maxWidth: 1000,
            }}
          >
            {"Turn a user-reported bug into a".split(" ").map((word, i) => (
              <span key={`${word}-${i}`}>{word}</span>
            ))}
            <span style={{ color: "#34d399" }}>regression</span>
            <span style={{ display: "flex" }}>
              <span style={{ color: "#34d399" }}>test</span>
              <span>.</span>
            </span>
          </div>
          <div style={{ color: "#a1a1aa", fontSize: 32 }}>
            Issue-to-repro infrastructure. No screens, no input values, no page text.
          </div>
        </div>

        <div style={{ color: "#71717a", fontSize: 26 }}>
          Open source. Self-hosted. Built for regulated teams.
        </div>
      </div>
    ),
    { ...size },
  );
}
