import { ImageResponse } from "next/og";

export const runtime = "edge";
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
          <div
            style={{
              color: "#fafafa",
              fontSize: 76,
              fontWeight: 600,
              lineHeight: 1.05,
              letterSpacing: "-0.03em",
              maxWidth: 1000,
            }}
          >
            Turn a user-reported bug into a{" "}
            <span style={{ color: "#34d399" }}>regression test</span>.
          </div>
          <div style={{ color: "#a1a1aa", fontSize: 32 }}>
            Issue-to-repro infrastructure. No screens, no input values, no PII.
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
