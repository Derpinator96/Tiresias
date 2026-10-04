import { caller, guard, webConfig } from "@/lib/ask-server";
import { runData } from "@/lib/data-shared";

// Data questions for the local web container (src/lib/data-shared.ts). 404 everywhere else.
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
  const s = webConfig().ask_timeout_s;
  const r = await runData(question.trim(), caller(process.env.GATEWAY_URL, s), caller(process.env.AI_URL, s));
  return Response.json(r, { status: "error" in r ? 502 : 200 });
}
