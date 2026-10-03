"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  NavigationMenu, NavigationMenuContent, NavigationMenuItem, NavigationMenuLink, NavigationMenuList, NavigationMenuTrigger,
} from "@/components/ui/navigation-menu";
import { STAGES, STAGE_SUMMARY } from "@/lib/stages";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/playground", label: "Playground" },
  { href: "/hashing", label: "Hashing" },
  { href: "/ask", label: "Ask" },
];

export function SiteHeader() {
  const path = usePathname();
  const item = (active: boolean) =>
    cn("inline-flex h-8 items-center rounded-md px-2.5 text-sm text-slate-700 hover:bg-white/80", active && "bg-white/90 font-medium text-slate-900");
  return (
    <header className="sticky top-3 z-40 mx-auto w-[min(1100px,calc(100%-24px))]">
      <div className="glass-bar flex flex-wrap items-center gap-2 px-3 py-2">
        <Link href="/" className="mr-2 text-sm font-semibold text-slate-900">Blind Tuner</Link>
        <NavigationMenu>
          <NavigationMenuList className="flex-wrap">
            <NavigationMenuItem>
              <NavigationMenuTrigger className={item(path.startsWith("/stages"))}>Stages</NavigationMenuTrigger>
              <NavigationMenuContent>
                <ul className="grid w-[min(520px,calc(100vw-48px))] gap-1 p-2 sm:grid-cols-2">
                  {STAGES.map((s, i) => (
                    <li key={s.id}>
                      <NavigationMenuLink
                        render={<Link href={`/stages/${s.id}`} />}
                        className="block rounded-md p-2 hover:bg-slate-900/5"
                      >
                        <span className="text-sm font-medium text-slate-900">{i + 1}. {s.title}</span>
                        <span className="mt-0.5 block text-xs leading-snug text-slate-600">{STAGE_SUMMARY[s.id]}</span>
                      </NavigationMenuLink>
                    </li>
                  ))}
                </ul>
              </NavigationMenuContent>
            </NavigationMenuItem>
            {LINKS.map((l) => (
              <NavigationMenuItem key={l.href}>
                <NavigationMenuLink render={<Link href={l.href} />} className={item(path === l.href)}>
                  {l.label}
                </NavigationMenuLink>
              </NavigationMenuItem>
            ))}
          </NavigationMenuList>
        </NavigationMenu>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="mx-auto mt-16 w-[min(1100px,calc(100%-24px))] pb-8">
      <div className="glass-subtle flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl px-4 py-3 text-xs text-slate-600">
        <span>Blind Tuner: a CodeUtsava X.0 entry for Problem Statement 4.</span>
        <a href="https://github.com/Derpinator96/Tiresias" className="hover:underline">Source on GitHub</a>
        <Link href="/privacy" className="hover:underline">Privacy</Link>
        <Link href="/terms" className="hover:underline">Terms</Link>
      </div>
    </footer>
  );
}
