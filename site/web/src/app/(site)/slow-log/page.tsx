import type { Metadata } from "next";
import { SlowLog } from "@/components/db/slow-log";
import { H1, Page } from "@/components/site/prose";

export const metadata: Metadata = {
  title: "Slow log | Tiresias",
  description: "The slow query templates the gateway found in pg-prod's log, and the plan-generation workload beside them.",
};

export default function SlowLogPage() {
  return (
    <Page>
      <H1>Slow query log</H1>
      <SlowLog />
    </Page>
  );
}
