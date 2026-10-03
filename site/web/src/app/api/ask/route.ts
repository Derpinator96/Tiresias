import { askState, guard, startAsk } from "@/lib/ask-server";

// Live Ask for the local web container. 404 everywhere else (BT_LOCAL unset), so the public
// deploy has no live path. Read at request time: route handlers are not cached.

export async function POST(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  let question: unknown;
  try {
    question = (await req.json()).question;
  } catch {
    return Response.json({ error: "body must be JSON" }, { status: 400 });
  }
  if (typeof question !== "string" || !question.trim() || question.length > 500) {
    return Response.json({ error: "question must be 1 to 500 characters" }, { status: 400 });
  }
  const r = await startAsk(question.trim());
  return "error" in r ? Response.json({ error: r.error }, { status: r.status }) : Response.json(r);
}

export async function GET(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  const qid = new URL(req.url).searchParams.get("qid") ?? "";
  const state = await askState(qid);
  return state ? Response.json(state) : Response.json({ error: "unknown question; the server may have restarted" }, { status: 404 });
}
