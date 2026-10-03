import type { Metadata } from "next";
import Link from "next/link";
import { AskReplay } from "@/components/ask/replay";
import { LiveAsk } from "bt-live-ask";
import { H1, H2, Lead, P } from "@/components/site/prose";

export const metadata: Metadata = {
  title: "Ask why a query is slow | Blind Tuner",
  description: "A DBA asks why a query is slow; the AI answers from hashed metadata, the fix is measured on the twin, and the SQL comes with a rollback.",
};

export default function Ask() {
  return (
    <>
      <H1>A DBA asks why a query is slow and gets a measured fix with its rollback</H1>
      <Lead>
        The question never leaves the private network. The AI side gets template codes, calls its tools, and writes an answer in codes; a checker blocks any number that no tool produced. The fix is measured on the twin, and the DBA gets migration.sql and rollback.sql to run by hand.
      </Lead>
      <P>
        On a machine running Blind Tuner&apos;s Docker stack, this page also has a live question box. The public site only replays a recorded session. Steps in detail: <Link href="/stages/llm" className="text-blue-700 underline">LLM agent</Link>, <Link href="/stages/twin" className="text-blue-700 underline">twin</Link>, <Link href="/stages/dba" className="text-blue-700 underline">DBA console</Link>.
      </P>
      {LiveAsk && <div className="mt-6"><LiveAsk /></div>}
      <H2>Recorded session</H2>
      <AskReplay />
    </>
  );
}
