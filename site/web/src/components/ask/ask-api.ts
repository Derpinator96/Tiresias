// The live Ask HTTP calls, local web container only. In a public build "bt-ask-api" resolves to
// ask-api-off.ts (next.config.ts), so the live Ask path never reaches a client chunk
// (scripts/tests test_web_client_chunks_have_no_names_canaries_or_live_ask_path).
type Reply = { ok: boolean; status: number; body: Record<string, unknown> };

const call = async (url: string, init?: RequestInit): Promise<Reply> => {
  const r = await fetch(url, { cache: "no-store", ...init });
  return { ok: r.ok, status: r.status, body: await r.json() };
};

export const askApi = {
  post: (question: string) => call("/api/ask", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question }) }),
  get: (qid: string) => call(`/api/ask?qid=${encodeURIComponent(qid)}`),
};
