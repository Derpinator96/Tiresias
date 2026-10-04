// Run: npm test. Local accounts (src/lib/auth-shared.ts).
import { test } from "node:test";
import assert from "node:assert/strict";
import { hashPassword, signupProblem, verifyPassword } from "../src/lib/auth-shared.ts";

test("scrypt hashes verify, are salted, and reject a wrong password", () => {
  const a = hashPassword("correct horse"), b = hashPassword("correct horse");
  assert.notEqual(a, b);
  assert.ok(a.startsWith("scrypt$") && !a.includes("correct horse"));
  assert.ok(verifyPassword("correct horse", a));
  assert.ok(!verifyPassword("wrong horse", a));
  assert.ok(!verifyPassword("correct horse", "plain"));
});

test("sign-up checks email, name and password length", () => {
  assert.equal(signupProblem("dba@example.com", "Asha", "longenough"), null);
  assert.match(signupProblem("not-an-email", "Asha", "longenough"), /email/);
  assert.match(signupProblem("dba@example.com", " ", "longenough"), /name/);
  assert.match(signupProblem("dba@example.com", "Asha", "short"), /8 characters/);
});
