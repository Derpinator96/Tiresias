"use client";
// The current query context: which asked question every page renders from. Local web app only:
// in a public build LOCAL is false, nothing is fetched and useBundle() is always null, so every
// page falls back to its recorded figures. The chosen bundle id lives in localStorage.
import { useEffect } from "react";
import { create } from "zustand";
import { dehashWith, type Bundle, type BundleSummary } from "@/lib/bundle";

export const LOCAL = process.env.NEXT_PUBLIC_BT_LOCAL === "1";
const KEY = "bt.current";

const stored = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
const store = (id: string | null) => { try { if (id) localStorage.setItem(KEY, id); else localStorage.removeItem(KEY); } catch { /* private window */ } };

type S = {
  list: BundleSummary[];
  current: Bundle | null;
  loaded: boolean;    // the list was fetched at least once
  loading: boolean;   // a bundle is being fetched
  refresh: () => Promise<void>;
  select: (id: string | null) => Promise<void>;
};

export const useContextStore = create<S>()((set, get) => ({
  list: [], current: null, loaded: false, loading: false,
  refresh: async () => {
    if (!LOCAL) return;
    try {
      const r = await fetch("/api/history", { cache: "no-store" });
      if (!r.ok) return;
      const list: BundleSummary[] = await r.json();
      set({ list, loaded: true });
      const want = stored() && list.some((b) => b.id === stored()) ? stored() : list[0]?.id ?? null;
      if (want !== (get().current?.id ?? null)) await get().select(want);
    } catch {
      set({ loaded: true });
    }
  },
  select: async (id) => {
    if (!id) { store(null); set({ current: null }); return; }
    set({ loading: true });
    try {
      const r = await fetch(`/api/history/${encodeURIComponent(id)}`, { cache: "no-store" });
      if (r.ok) { store(id); set({ current: await r.json(), loading: false }); return; }
    } catch { /* fall through */ }
    set({ loading: false });
  },
}));

/** The selected bundle, or null (public build, nothing asked yet, or still loading). Fetches the
 *  history once per page load. */
export function useBundle(): Bundle | null {
  const { current, loaded, refresh } = useContextStore();
  useEffect(() => { if (LOCAL && !loaded) void refresh(); }, [loaded, refresh]);
  return LOCAL ? current : null;
}

/** Real name for one code (t_, c_ or q_), or the code itself when the bundle does not know it. */
export const name = (b: Bundle | null, code: string) => b?.names[code] ?? code;

/** Real names for every code in a text. */
export const dehash = (b: Bundle | null, text: string) => dehashWith(b?.names, text);
