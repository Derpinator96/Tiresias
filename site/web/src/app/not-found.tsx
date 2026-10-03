import Link from "next/link";
import { Sidebar } from "@/components/site/sidebar";
import { H1, Lead, Page } from "@/components/site/prose";

export default function NotFound() {
  return (
    <>
      <Sidebar />
      <main className="min-w-0 flex-1 lg:pl-[15.5rem]">
        <Page>
          <H1>This page does not exist</H1>
          <Lead>
            <Link href="/" className="text-accent underline">Go to the overview</Link> or open the <Link href="/playground" className="text-accent underline">pipeline playground</Link>.
          </Lead>
        </Page>
      </main>
    </>
  );
}
