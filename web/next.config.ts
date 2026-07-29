import type { NextConfig } from "next";

// The public demo console is the real operator UI, served by the StepStitch host over a
// read-only synthetic dataset (server/demo.py). Proxying it through this origin rather than
// linking out keeps the visitor here, and — because the console derives its API base from its
// own path — the same page works at the site, at the host, and self-hosted, with nothing to
// keep in sync.
//
// STEPSTITCH_DEMO_HOST (server-only) is the base URL where the demo app is MOUNTED:
//   https://your-host.example/demo   when the ingest host runs with STEPSTITCH_DEMO_MODE=1
//   http://127.0.0.1:8020            when running `server.demo_app` standalone
// Unset, /dashboard still renders and says the demo is offline; the build never fails.
const demoHost = process.env.STEPSTITCH_DEMO_HOST?.replace(/\/$/, "");

const nextConfig: NextConfig = {
  // Pin the workspace root: this app lives in web/ inside a larger repo that
  // has its own lockfile, which would otherwise confuse root inference.
  turbopack: {
    root: __dirname,
  },
  async rewrites() {
    if (!demoHost) return [];
    return [
      // The console itself.
      { source: "/dashboard/demo", destination: `${demoHost}/dashboard` },
      // Everything it fetches. The console asks for "<its own path>/api/…", which arrives
      // here as /dashboard/demo/api/… and maps straight onto the demo app's own routes.
      { source: "/dashboard/demo/api/:path*", destination: `${demoHost}/api/:path*` },
      { source: "/dashboard/demo/admin/:path*", destination: `${demoHost}/admin/:path*` },
    ];
  },
};

export default nextConfig;
