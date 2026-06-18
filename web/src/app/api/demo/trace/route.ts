import { NextResponse } from "next/server";
import { fetchDemoTrace } from "@/lib/stepstitch";

// Read-only. The browser hits this route; the route holds the admin token and
// talks to the StepStitch service. Only GET is exposed here, and the handler
// only ever issues read (GET) calls plus the sanitized read-side responses.
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const trace = await fetchDemoTrace();
    return NextResponse.json(trace, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      { error: "demo_unavailable" },
      { status: 502 },
    );
  }
}
