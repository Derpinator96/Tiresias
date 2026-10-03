import type { Metadata } from "next";
import Link from "next/link";
import { HashingVisualizer } from "@/components/hashing/visualizer";
import { H1, Lead, P } from "@/components/site/prose";

export const metadata: Metadata = {
  title: "Hashing visualizer | Blind Tuner",
  description: "Type SQL and watch the gateway's steps in your browser: HMAC-SHA256 codes, values as ?, role flags.",
};

export default function Hashing() {
  return (
    <>
      <H1>The gateway hashes names and strips values; try it on your own SQL</H1>
      <Lead>
        This runs the gateway&apos;s algorithm in your browser with a demo key made in this tab. Nothing you type leaves the page. The codes differ from the real gateway&apos;s because the real key never leaves its private network.
      </Lead>
      <P>
        It hashes, it does not encrypt: a code cannot be turned back into a name, even with the key. Only the gateway, which keeps a table of the names it hashed, can translate an answer back for the DBA. <Link href="/stages/gateway" className="text-blue-700 underline">Read the gateway deep dive</Link>.
      </P>
      <div className="mt-6"><HashingVisualizer /></div>
    </>
  );
}
