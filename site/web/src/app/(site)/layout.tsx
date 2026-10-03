import { SiteFooter, SiteHeader } from "@/components/site/header";

export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto mt-8 w-[min(1100px,calc(100%-32px))] flex-1">{children}</main>
      <SiteFooter />
    </>
  );
}
