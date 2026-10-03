"use client";
// Shared by the local-only pages: the public-build notice and one JSON fetch with a one-line error.
import { useEffect, useState } from "react";

export const LocalOnly = () => (
  <p className="glass-subtle mt-6 rounded-lg px-4 py-3 text-sm text-slate-700">
    Local web app only (make up): this page reads the private gateway.
  </p>
);

export function ErrorLine({ text }: { text?: string }) {
  return text ? <p className="rounded-md bg-signal-soft px-3 py-2 font-mono text-xs font-medium text-signal [overflow-wrap:anywhere]">{text}</p> : null;
}

/** GET `url` (refetched when it changes). `error` is the API's one-line message or the HTTP status;
 *  `data` keeps the last answer while a new url loads. */
export function useJson<T>(url: string | null) {
  const [state, setState] = useState<{ url: string; data?: T; error?: string } | null>(null);
  useEffect(() => {
    if (!url) return;
    let live = true;
    fetch(url, { cache: "no-store" })
      .then(async (r) => {
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(body.error ?? `HTTP ${r.status}`);
        return body as T;
      })
      .then((data) => { if (live) setState({ url, data }); }, (e: unknown) => { if (live) setState({ url, error: e instanceof Error ? e.message : String(e) }); });
    return () => { live = false; };
  }, [url]);
  const done = state?.url === url;
  return { data: state?.data ?? null, error: done ? state?.error : undefined, loading: !!url && !done };
}

export const ms = (v: number | null | undefined, digits = 1) => (v === null || v === undefined ? "n/a" : `${v.toFixed(digits)} ms`);
