import { Sidebar } from "@/components/site/sidebar";

export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Sidebar />
      <main className="min-w-0 flex-1 lg:pl-[5.5rem]">{children}</main>
    </>
  );
}
