import type { Metadata } from "next";
import { GnnLab } from "@/components/gnn/gnn-lab";
import { H1, Page } from "@/components/site/prose";

export const metadata: Metadata = {
  title: "GNN | Tiresias",
  description: "Explore the plan GNN: node features, message passing up the plan tree, and when it serves.",
};

export default function Gnn() {
  return (
    <Page>
      <H1>How the plan GNN reads a query plan</H1>
      <div className="mt-6"><GnnLab /></div>
    </Page>
  );
}
