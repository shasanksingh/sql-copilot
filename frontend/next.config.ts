import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  distDir: process.env.NODE_ENV === "production" ? ".next-build" : ".next",
  outputFileTracingRoot: path.resolve(__dirname),
  typedRoutes: true,
};

export default nextConfig;
