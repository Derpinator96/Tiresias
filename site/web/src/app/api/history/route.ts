import { guard, listBundles } from "@/lib/ask-server";

// The administrator's asked questions, newest first. Local web container only (guard: 404 elsewhere).
export async function GET(req: Request) {
  return guard(req) ?? Response.json(listBundles());
}
