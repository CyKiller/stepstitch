import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

// Favicon: the stitch mark (two offset bars + one) on the brand surface.
export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          justifyContent: "center",
          gap: 3,
          background: "#09090b",
          padding: 6,
        }}
      >
        <div style={{ width: 18, height: 4, borderRadius: 2, background: "#34d399" }} />
        <div style={{ width: 18, height: 4, borderRadius: 2, background: "#34d399", opacity: 0.55, marginLeft: 6 }} />
        <div style={{ width: 18, height: 4, borderRadius: 2, background: "#34d399" }} />
      </div>
    ),
    { ...size },
  );
}
