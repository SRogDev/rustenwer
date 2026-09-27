import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The web app imports shared TypeScript contracts from the repo root
  // (`../shared/types`). Next 16 builds with Turbopack, which confines
  // module resolution to its project root — point it at the repo root so
  // those cross-directory imports resolve (webpack allowed this in Next 15).
  turbopack: {
    root: path.resolve(__dirname, ".."),
  },
};

export default nextConfig;
