import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { HomeResults } from "@/components/viz/home-results";
import { PipelineMap } from "@/components/viz/pipeline-map";
import { H1, Page } from "@/components/site/prose";

export default function Home() {
  return (
    <Page>
      <H1>Tiresias tunes Postgres from hashed metadata</H1>
      <div className="mt-5 flex flex-wrap gap-2">
        <Link href="/playground" className="inline-flex h-9 items-center gap-1.5 rounded-full bg-ink px-4 text-sm font-medium text-white hover:bg-slate-800">
          Replay the pipeline <ArrowRight className="size-4" />
        </Link>
        <Link href="/hashing" className="inline-flex h-9 items-center rounded-full bg-white px-4 text-sm font-medium text-slate-900 shadow-(--glass-shadow) hover:bg-slate-50">Hash your own SQL</Link>
      </div>

      <div className="mt-8"><PipelineMap /></div>

      <HomeResults />
    </Page>
  );
}
