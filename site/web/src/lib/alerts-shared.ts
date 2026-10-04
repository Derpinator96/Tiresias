// Slow-query alerts: the record saved per alert and the email sent to the DBA. Pure, type
// imports only (tests/alerts.test.mjs).

export type Alert = {
  id: string; created_at: string; to: string;
  template_id: string; sql: string; example: string | null;
  calls: number; mean_ms: number; total_ms: number; threshold_ms: number;
  fixes: string[]; migration: string; rollback: string;
  twin: { before_ms: number; after_ms: number } | null; twin_mode: string;
  emailed: boolean; email_error: string | null;
};

const n = (v: number) => v.toLocaleString("en-US", { maximumFractionDigits: 1 });
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
const noComments = (sql: string) => sql.replace(/\/\*[\s\S]*?\*\/|--[^\n]*/g, "").trim();

/** The facts of one alert in plain sentences; the email and the Alerts page both use them. */
export function alertLines(a: Alert): string[] {
  const lines = [
    `Slow query: ${n(a.mean_ms)} ms on average over ${a.calls.toLocaleString("en-US")} calls (${n(a.total_ms / 1000)} s in total); slow means ${n(a.threshold_ms)} ms or more.`,
  ];
  if (a.fixes.length) lines.push(`How to fix it: ${a.fixes.join(", and ")}.`);
  if (a.twin) {
    const pct = a.twin.before_ms ? Math.round((100 * (a.twin.before_ms - a.twin.after_ms)) / a.twin.before_ms) : 0;
    lines.push(`Expected effect on the twin: ${n(a.twin.before_ms)} ms to ${n(a.twin.after_ms)} ms, ${pct}% faster${a.twin_mode === "live" ? " (measured)" : " (recorded mode: replayed or a HypoPG estimate)"}.`);
  }
  return lines;
}

export function alertEmail(a: Alert, link: string): { subject: string; text: string; html: string } {
  const sql = noComments(a.sql);
  const subject = `Slow query on pg-prod: ${n(a.mean_ms)} ms average, ${sql.slice(0, 60)}${sql.length > 60 ? "..." : ""}`;
  const lines = alertLines(a);
  const text = [
    "Blind Tuner found a slow query on pg-prod.", "", "Query:", sql, "", ...lines, "",
    "SQL to apply, the full recommended change set (run with psql; nothing has been changed):", a.migration || "(none)", "",
    "Rollback:", a.rollback || "(none)", "", `Full stats: ${link}`,
  ].join("\n");
  const pre = (s: string) => `<pre style="background:#f6f7f9;padding:12px;border-radius:8px;white-space:pre-wrap;font-size:13px">${esc(s)}</pre>`;
  const html = `<div style="font-family:system-ui,sans-serif;color:#262726;max-width:640px">
<h2 style="margin:0 0 8px">Slow query on pg-prod</h2>
${pre(sql)}
${lines.map((l) => `<p style="margin:8px 0">${esc(l)}</p>`).join("\n")}
<h3 style="margin:16px 0 4px">SQL to apply</h3><p style="margin:0;font-size:13px">The full recommended change set. Run with psql; nothing has been changed.</p>
${pre(a.migration || "(none)")}
<h3 style="margin:16px 0 4px">Rollback</h3>
${pre(a.rollback || "(none)")}
<p style="margin:16px 0"><a href="${esc(link)}" style="background:#262726;color:#fff;padding:10px 16px;border-radius:999px;text-decoration:none">Open the full stats page</a></p>
<p style="font-size:12px;color:#64748b">Sent by the Blind Tuner local web app to ${esc(a.to)}.</p>
</div>`;
  return { subject, text, html };
}
