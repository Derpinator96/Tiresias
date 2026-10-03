import type { Metadata } from "next";
import { AskReplay } from "@/components/ask/replay";
import { LiveAsk } from "bt-live-ask";
import { H1, H2, Page } from "@/components/site/prose";

export const metadata: Metadata = {
  title: "Ask why a query is slow | Tiresias",
  description: "A DBA asks why a query is slow; the AI answers from hashed metadata, the fix is measured on the twin, and the SQL comes with a rollback.",
};

export default function Ask() {
  return (
    <Page>
      <H1>Ask why a query is slow</H1>
      {LiveAsk && <div className="mt-6"><LiveAsk /></div>}
      <H2>Recorded session</H2>
      <AskReplay />
    </Page>
  );
}
