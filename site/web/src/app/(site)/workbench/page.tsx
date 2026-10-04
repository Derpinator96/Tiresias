import type { Metadata } from "next";
import { WorkbenchPanel } from "@/components/alerts/workbench-panel";
import { H1, Page } from "@/components/site/prose";

export const metadata: Metadata = { title: "Query workbench | Tiresias", description: "Run suggested slow-log and normal queries against pg-prod, read-only." };

export default function Workbench() {
  return (
    <Page>
      <H1>Query workbench</H1>
      <WorkbenchPanel />
    </Page>
  );
}
