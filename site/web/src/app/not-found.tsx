import Link from "next/link";
import { SiteFooter, SiteHeader } from "@/components/site/header";
import { H1, Lead } from "@/components/site/prose";

export default function NotFound() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto mt-8 w-[min(1100px,calc(100%-32px))] flex-1">
        <H1>This page does not exist</H1>
        <Lead>
          <Link href="/" className="text-blue-700 underline">Go to the home page</Link> or open the <Link href="/playground" className="text-blue-700 underline">pipeline playground</Link>.
        </Lead>
      </main>
      <SiteFooter />
    </>
  );
}
