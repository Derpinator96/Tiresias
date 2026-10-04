import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { HomeResults } from "@/components/viz/home-results";
import { Page } from "@/components/site/prose";

export default function Home() {
  return (
    <Page>
      <HomeResults hero={
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-light tracking-tight text-ink">Tiresias tunes Postgres <span className="text-slate-400">from hashed metadata</span></h1>
          <div className="flex flex-wrap gap-2">
            <Link href="/playground" className="pill inline-flex h-8 items-center gap-1.5 bg-ink px-3.5 text-xs font-medium text-white hover:bg-slate-800">
              Replay the pipeline <ArrowRight className="size-3.5" />
            </Link>
            <Link href="/hashing" className="pill inline-flex h-8 items-center bg-white px-3.5 text-xs font-medium text-ink shadow-(--glass-shadow) hover:bg-lime">Hash your own SQL</Link>
          </div>
        </div>
      } />
    </Page>
  );
}
