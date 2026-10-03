import type { Metadata } from "next";
import { DatabaseSample } from "@/components/db/database-sample";
import { H1, Page } from "@/components/site/prose";

export const metadata: Metadata = {
  title: "Database sample | Tiresias",
  description: "Every table of the demo database with its gateway code, row count, size and the first rows.",
};

export default function Database() {
  return (
    <Page>
      <H1>Database sample</H1>
      <DatabaseSample />
    </Page>
  );
}
