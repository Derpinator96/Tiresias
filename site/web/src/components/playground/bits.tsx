"use client";
import { useState, type ReactNode } from "react";
import { Check, Copy, Download } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

export function Pip({ tone }: { tone: "ok" | "busy" | "idle" | "bad" }) {
  const c = { ok: "bg-accent", busy: "bg-signal", idle: "bg-slate-400", bad: "bg-signal" }[tone];
  return <span className={cn("inline-block size-2 shrink-0 rounded-full", c)} aria-hidden />;
}

/** Where a figure comes from or what it assumes: one line "Source", opens on click. */
export function Source({ children }: { children: ReactNode }) {
  return (
    <details className="group mt-1 text-xs leading-snug text-slate-600">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-slate-500 hover:text-slate-800 [&::-webkit-details-marker]:hidden">
        <span className="font-mono text-xs">i</span> source and assumptions
      </summary>
      <p className="mt-1 [overflow-wrap:anywhere]">{children}</p>
    </details>
  );
}

export function save(name: string, data: BlobPart, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000); // revoking at once can cancel the download
  toast.success(`Saved ${name}`);
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className="inline-flex h-7 items-center gap-1.5 rounded-md glass-subtle px-2 text-xs text-ink hover:bg-white/80"
      onClick={async () => {
        let ok = false;
        try {
          await navigator.clipboard.writeText(text);
          ok = true;
        } catch {
          // Clipboard API blocked (permissions, non-secure origin): fall back to a hidden textarea.
          const ta = Object.assign(document.createElement("textarea"), { value: text });
          document.body.append(ta);
          ta.select();
          ok = document.execCommand("copy");
          ta.remove();
        }
        if (!ok) return void toast.error("Clipboard blocked by the browser");
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      }}
    >
      {done ? <Check className="size-3.5 text-accent" /> : <Copy className="size-3.5" />}
      {done ? "Copied" : label}
    </button>
  );
}

const KW = /\b(SELECT|FROM|WHERE|AND|OR|IN|SUM|CREATE|INDEX|CONCURRENTLY|ON|DROP|IF|EXISTS)\b/g;

/** Keywords in ink, comments in slate, strings in accent. Line-level only, no parser. */
function Highlight({ line }: { line: string }) {
  if (line.trimStart().startsWith("--")) return <span className="text-slate-400">{line}</span>;
  const parts = line.split(/('[^']*')/);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith("'") ? (
          <span key={i} className="text-accent">{p}</span>
        ) : (
          p.split(KW).map((w, j) => (j % 2 ? <span key={`${i}-${j}`} className="font-semibold text-ink">{w}</span> : w))
        ),
      )}
    </>
  );
}

export function SqlBlock({ text, file, tone }: { text: string; file?: string; tone?: "add" | "del" }) {
  return (
    <div className="inset-field overflow-hidden">
      {file && (
        <div className="flex items-center justify-between gap-2 border-b border-slate-200/80 px-3 py-1.5">
          <span className="font-mono text-xs text-slate-600">{file}</span>
          <div className="flex gap-1.5">
            <CopyButton text={text} />
            <button
              type="button"
              className="inline-flex h-7 items-center gap-1.5 rounded-md glass-subtle px-2 text-xs text-ink hover:bg-white/80"
              onClick={() => save(file.endsWith(".sql") ? file : `${file}.sql`, text, "application/sql")}
            >
              <Download className="size-3.5" /> .sql
            </button>
          </div>
        </div>
      )}
      <pre className="overflow-x-auto p-3 font-mono text-xs leading-relaxed tracking-tight text-slate-800">
        {text.split("\n").map((l, i) => (
          <div key={i} className={cn(tone === "add" && "bg-accent-soft/60", tone === "del" && "bg-signal-soft/60")}>
            {tone && <span className="mr-2 select-none text-slate-400">{tone === "add" ? "+" : "-"}</span>}
            <Highlight line={l} />
          </div>
        ))}
      </pre>
    </div>
  );
}

export function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="inset-field min-w-0 px-3 py-2 transition-[transform,border-color,box-shadow] duration-150 hover:-translate-y-px hover:border-slate-300 hover:shadow-sm motion-reduce:transition-none motion-reduce:hover:translate-y-0 [overflow-wrap:anywhere]">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="font-mono text-lg font-semibold tracking-tight text-slate-900">{value}</div>
      {note && <Source>{note}</Source>}
    </div>
  );
}
