import type { NextConfig } from "next";

// The web container's image builds with NEXT_PUBLIC_BT_LOCAL=1; the public build does not. In a
// public build "bt-live-ask" resolves to a stub, so no live Ask code reaches any chunk
// (scripts/tests checks the client chunks for "/api/ask").
const local = process.env.NEXT_PUBLIC_BT_LOCAL === "1";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // The indicator covered the replay log; compile and runtime errors still show.
  devIndicators: false,
  turbopack: {
    resolveAlias: {
      "bt-live-ask": local ? "./src/components/ask/live-ask.tsx" : "./src/components/ask/live-off.ts",
    },
  },
};

export default nextConfig;
