// Accounts for the local web app (alerts go to the signed-in DBA). Password hashing and input
// checks only; storage and sessions are in auth-server.ts. node:crypto only, so
// tests/auth.test.mjs loads it with Node's type stripping.
import { randomBytes, scryptSync, timingSafeEqual } from "node:crypto";

export type Role = "dba" | "analyst";
export const ROLES: Role[] = ["dba", "analyst"];
export type User = { email: string; name: string; hash: string; created_at: string; role?: Role };   // no role: an account from before roles, a DBA

/** Who may do what (RBAC). DBA: alerts and analytics; both roles: the query workbench. */
export const CAN = {
  alerts: ["dba"] as Role[],
  analytics: ["dba"] as Role[],
  workbench: ["dba", "analyst"] as Role[],
};

const KEYLEN = 64;

/** "scrypt$<salt hex>$<hash hex>" with a random 16-byte salt. */
export function hashPassword(password: string): string {
  const salt = randomBytes(16);
  return `scrypt$${salt.toString("hex")}$${scryptSync(password, salt, KEYLEN).toString("hex")}`;
}

export function verifyPassword(password: string, stored: string): boolean {
  const [kind, salt, hash] = stored.split("$");
  if (kind !== "scrypt" || !salt || !hash) return false;
  const want = Buffer.from(hash, "hex");
  const got = scryptSync(password, Buffer.from(salt, "hex"), want.length);
  return got.length === want.length && timingSafeEqual(got, want);
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** The first problem with a sign-up form, or null. */
export function signupProblem(email: unknown, name: unknown, password: unknown, role: unknown = "dba"): string | null {
  if (!ROLES.includes(role as Role)) return "choose a role";
  if (typeof email !== "string" || !EMAIL.test(email) || email.length > 200) return "enter a valid email address";
  if (typeof name !== "string" || !name.trim() || name.length > 100) return "enter your name";
  if (typeof password !== "string" || password.length < 8 || password.length > 200) return "the password needs at least 8 characters";
  return null;
}
