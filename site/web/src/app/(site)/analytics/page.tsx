import type { Metadata } from "next";
import { AnalyticsPanel } from "@/components/alerts/analytics-panel";
import { H1, Page } from "@/components/site/prose";

export const metadata: Metadata = { title: "Query analytics | Tiresias", description: "Live query times from every workbench run, with spikes over the slow threshold marked." };

export default function Analytics() {
  return (
    <Page>
      <H1>Query analytics</H1>
      <AnalyticsPanel />
    </Page>
  );
}
