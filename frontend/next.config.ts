import type { NextConfig } from "next";

// The app renders in the browser after login and fetches from the FastAPI backend,
// so cacheComponents / partial prefetching (server-rendered shells) aren't used.
const nextConfig: NextConfig = {
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
