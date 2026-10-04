"use client";
// Sign-in and sign-up for the local web app (src/lib/auth-server.ts). After success it goes to
// ?next= (same-site paths only) or /alerts.
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Source } from "@/components/playground/bits";
import { LOCAL } from "@/lib/context";

const nextPath = () => {
  const n = new URLSearchParams(window.location.search).get("next") ?? "";
  return n.startsWith("/") && !n.startsWith("//") ? n : "";
};

export function AuthForm({ mode }: { mode: "signin" | "signup" }) {
  const router = useRouter();
  const [f, setF] = useState({ name: "", email: "", password: "", role: "dba" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!LOCAL) return <p className="text-sm text-slate-700">Accounts exist only in the local web app; the public site has no sign-in.</p>;

  const submit = async () => {
    setBusy(true);
    setErr(null);
    const r = await fetch(`/api/auth/${mode}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(f) });
    const body = await r.json().catch(() => ({}));
    setBusy(false);
    if (!r.ok) return setErr(body.error ?? `HTTP ${r.status}`);
    router.replace(nextPath() || (f.role === "analyst" && mode === "signup" ? "/workbench" : "/alerts"));
  };
  const field = (k: "name" | "email" | "password", label: string, type = "text") => (
    <label className="block space-y-1">
      <span className="text-sm font-medium text-slate-900">{label}</span>
      <Input type={type} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} autoComplete={k === "password" ? (mode === "signup" ? "new-password" : "current-password") : k} />
    </label>
  );

  return (
    <form className="glass mt-6 max-w-md space-y-4 p-6" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
      {mode === "signup" && field("name", "Name")}
      {mode === "signup" && (
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium text-slate-900">Role</legend>
          <div className="glass-subtle inline-flex pill p-0.5">
            {([["dba", "DBA: alerts and analytics"], ["analyst", "Analyst: runs queries"]] as const).map(([r, text]) => (
              <button key={r} type="button" aria-pressed={f.role === r} onClick={() => setF({ ...f, role: r })}
                className={f.role === r ? "h-8 pill bg-ink px-3 text-sm text-white" : "h-8 pill px-3 text-sm text-slate-600 hover:bg-white/70"}>{text}</button>
            ))}
          </div>
          <p className="text-xs text-slate-600">demo: the role is chosen here; in production an administrator assigns it</p>
        </fieldset>
      )}
      {field("email", "Email (alerts are sent here)", "email")}
      {field("password", mode === "signup" ? "Password (at least 8 characters)" : "Password", "password")}
      {err && <p className="text-sm text-signal">{err}</p>}
      <button type="submit" disabled={busy} className="inline-flex h-9 w-full items-center justify-center gap-2 pill bg-ink text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40">
        {busy && <Loader2 className="size-4 animate-spin" />}{mode === "signup" ? "Create account" : "Sign in"}
      </button>
      <p className="text-sm text-slate-700">
        {mode === "signup" ? <>Already have an account? <Link href="/signin" className="font-medium text-ink underline">Sign in</Link></>
          : <>No account yet? <Link href="/signup" className="font-medium text-ink underline">Create one</Link></>}
      </p>
      <Source>stored on this machine only: email, name and a scrypt password hash in the private history folder</Source>
    </form>
  );
}
