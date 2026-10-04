import type { Metadata } from "next";
import { AlertsPanel } from "@/components/alerts/alerts-panel";
import { H1, Page } from "@/components/site/prose";

export const metadata: Metadata = {
  title: "Slow-query alerts | Tiresias",
  description: "Slow queries from pg-prod's log, the fix for each, and the email sent to the DBA.",
};

export default function Alerts() {
  return (
    <Page>
      <H1>Slow-query alerts</H1>
      <AlertsPanel />
    </Page>
  );
}
