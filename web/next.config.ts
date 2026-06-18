import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the workspace root: this app lives in web/ inside a larger repo that
  // has its own lockfile, which would otherwise confuse root inference.
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
