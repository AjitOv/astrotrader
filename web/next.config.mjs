/** @type {import('next').NextConfig} */
const apiBase = process.env.ASTROTRADE_API_URL ?? "http://127.0.0.1:8000";

const nextConfig = {
  // Optional client-side proxy. Server components call the API directly via
  // lib/api.ts, but if any client component ever needs to reach the engine
  // (e.g. for streaming) it can hit /api/* and avoid CORS.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiBase}/:path*` }];
  },
};
export default nextConfig;
