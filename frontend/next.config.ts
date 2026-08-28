import type { NextConfig } from "next";

// Resolved at BUILD time: Next serializes rewrites into the routes manifest,
// so setting this in the container environment has no effect. That is fine
// here because the value is an internal address, identical in every
// deployment (compose service `api`), never a public hostname. `next dev`
// re-evaluates this file on start, so the localhost default covers local work.
const BACKEND_URL = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Emit .next/standalone with a self-contained server.js so the runtime image
  // needs neither node_modules nor the Next CLI. Required by frontend/Dockerfile.
  output: "standalone",

  // The admin UI calls /api/* and /v2/* on its own origin and this proxies them
  // to the backend. Two consequences worth knowing: no *public* hostname is compiled
  // into the client bundle, and admin traffic is same-origin so CORS never
  // applies to it. The app defines no /api or /v2 routes of its own, so nothing
  // collides. Deliberately not done in proxy.ts, which buffers request bodies
  // (10MB cap) and would throttle document uploads; rewrites stream.
  async rewrites() {
    return [
      // V2 API (current)
      { source: "/v2/:path*", destination: `${BACKEND_URL}/v2/:path*` },
      // V1 API (legacy, kept for compatibility but not used in admin UI v2)
      { source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` },
    ];
  },
};

export default nextConfig;
