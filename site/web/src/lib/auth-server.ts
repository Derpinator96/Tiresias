import "server-only";
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { load } from "js-yaml";
import { jwtVerify, SignJWT } from "jose";
import { cookies } from "next/headers";
import { hashPassword, signupProblem, verifyPassword, type Role, type User } from "@/lib/auth-shared";

// Local web app only. Users live in users.json in the private history directory (the web-history
// volume in the container); passwords as scrypt hashes. The session is an HS256 token in an
// httpOnly cookie. Its secret is BT_SESSION_SECRET from .env when set; otherwise a random one per
// server process, so a restart signs everyone out (simplified for the demo).

const COOKIE = "bt_session";
const dir = () => process.env.BT_HISTORY_DIR || "./.bt-history";
const file = () => join(dir(), "users.json");
const g = globalThis as unknown as { __btSecret?: Uint8Array };
const secret = () => (g.__btSecret ??= process.env.BT_SESSION_SECRET
  ? new TextEncoder().encode(process.env.BT_SESSION_SECRET)
  : new Uint8Array(randomBytes(32)));

export function alertsConfig(): { from: string; inbox_url: string; session_days: number } {
  const doc = load(readFileSync(process.env.BT_CONFIG ?? "../../config.yaml", "utf8")) as { alerts: ReturnType<typeof alertsConfig> };
  return doc.alerts;
}

function users(): User[] {
  try { return JSON.parse(readFileSync(file(), "utf8")); } catch { return []; }
}

function save(list: User[]) {
  if (!existsSync(dir())) mkdirSync(dir(), { recursive: true });
  writeFileSync(file(), JSON.stringify(list, null, 1), { mode: 0o600 });
}

export type Session = { email: string; name: string; role: Role };

async function startSession(u: User) {
  const days = alertsConfig().session_days;
  const token = await new SignJWT({ email: u.email, name: u.name, role: u.role ?? "dba" }).setProtectedHeader({ alg: "HS256" })
    .setIssuedAt().setExpirationTime(`${days}d`).sign(secret());
  (await cookies()).set(COOKIE, token, { httpOnly: true, sameSite: "lax", path: "/", maxAge: days * 86400 });
}

export async function signup(email: unknown, name: unknown, password: unknown, role: unknown): Promise<string | null> {
  const bad = signupProblem(email, name, password, role);
  if (bad) return bad;
  const e = (email as string).trim().toLowerCase();
  const list = users();
  if (list.some((u) => u.email === e)) return "an account with this email already exists; sign in instead";
  const u: User = { email: e, name: (name as string).trim(), hash: hashPassword(password as string), created_at: new Date().toISOString(), role: role as Role };
  save([...list, u]);
  await startSession(u);
  return null;
}

export async function signin(email: unknown, password: unknown): Promise<string | null> {
  const u = typeof email === "string" ? users().find((x) => x.email === email.trim().toLowerCase()) : undefined;
  if (!u || typeof password !== "string" || !verifyPassword(password, u.hash)) return "wrong email or password";
  await startSession(u);
  return null;
}

export async function signout() {
  (await cookies()).delete(COOKIE);
}

/** The session if its role may use `what`, else the Response to send (401 signed out, 403 wrong role). */
export async function requireRole(allowed: Role[]): Promise<Session | Response> {
  const s = await session();
  if (!s) return Response.json({ error: "not signed in" }, { status: 401 });
  if (!allowed.includes(s.role)) return Response.json({ error: `your role (${s.role}) cannot use this; it needs ${allowed.join(" or ")}` }, { status: 403 });
  return s;
}

export async function session(): Promise<Session | null> {
  const token = (await cookies()).get(COOKIE)?.value;
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, secret());
    return { email: String(payload.email), name: String(payload.name), role: payload.role === "analyst" ? "analyst" : "dba" };
  } catch {
    return null;
  }
}
