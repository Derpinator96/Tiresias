import type { Metadata } from "next";
import { HashingVisualizer } from "@/components/hashing/visualizer";
import { H1, Page } from "@/components/site/prose";

export const metadata: Metadata = {
  title: "Hashing visualizer | Tiresias",
  description: "One query, hashed step by step in your browser: comments removed, values as ?, names as HMAC-SHA256 codes.",
};

export default function Hashing() {
  return (
    <Page>
      <H1>What the gateway does to a query</H1>
      <div className="mt-6"><HashingVisualizer /></div>
    </Page>
  );
}
