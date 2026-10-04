import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { HomeResults } from "@/components/viz/home-results";
import { PipelineMap } from "@/components/viz/pipeline-map";
import { Page } from "@/components/site/prose";

export default function Home() {
  return (
    <Page>
      <HomeResults hero={<>
        <div>
          <h1 className="text-3xl font-light md:text-4xl tracking-tight text-ink">Tiresias tunes Postgres<br /><span className="text-slate-400">from hashed metadata</span></h1>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link href="/playground" className="pill inline-flex h-9 items-center gap-1.5 bg-ink px-4 text-sm font-medium text-white hover:bg-slate-800">
              Replay the pipeline <ArrowRight className="size-4" />
            </Link>
            <Link href="/hashing" className="pill inline-flex h-9 items-center bg-white px-4 text-sm font-medium text-ink shadow-(--glass-shadow) hover:bg-lime">Hash your own SQL</Link>
          </div>
        </div>
        <PipelineMap />
      </>} />
    </Page>
  );
}
