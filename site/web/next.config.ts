import type { NextConfig } from "next";

// The web container's image builds with NEXT_PUBLIC_BT_LOCAL=1; the public build does not. In a
// public build "bt-live-ask" and "bt-ask-api" resolve to stubs, so no live Ask code reaches any chunk
// (scripts/tests checks the client chunks for "/api/ask").
const local = process.env.NEXT_PUBLIC_BT_LOCAL === "1";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // The indicator covered the replay log; compile and runtime errors still show.
  devIndicators: false,
  // Dev server only: let 127.0.0.1 load dev assets too, so a second user can sign in there (its own
  // cookies) beside one at localhost. Production builds ignore this.
  allowedDevOrigins: ["127.0.0.1"],
  turbopack: {
    resolveAlias: {
      "bt-live-ask": local ? "./src/components/ask/live-ask.tsx" : "./src/components/ask/live-off.ts",
      "bt-ask-api": local ? "./src/components/ask/ask-api.ts" : "./src/components/ask/ask-api-off.ts",
    },
  },
};

export default nextConfig;
