import type { Metadata } from "next";
import { HashingLab } from "@/components/hashing/gateway-view";
import { H1, Page } from "@/components/site/prose";

export const metadata: Metadata = {
  title: "Hashing visualizer | Tiresias",
  description: "Type SQL and watch the gateway's steps in your browser: HMAC-SHA256 codes, values as ?, role flags.",
};

export default function Hashing() {
  return (
    <Page>
      <H1>Hash your own SQL</H1>
      <div className="mt-6"><HashingLab /></div>
    </Page>
  );
}
