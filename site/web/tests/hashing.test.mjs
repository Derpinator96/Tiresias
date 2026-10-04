// Run: npm test. Checks the browser hashing visualizer against the gateway's rules.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { bitsDiffer, code, hashSql, hmacHex, newKey, Unparsed } from "../src/lib/hashing.ts";

const KEY = Uint8Array.from({ length: 32 }, (_, i) => i);

test("Web Crypto HMAC matches Python's hmac (gateway/hashing.py)", async () => {
  // python3 -c "import hmac,hashlib; print(hmac.new(bytes(range(32)), b'invoices.branch', hashlib.sha256).hexdigest())"
  assert.equal(await hmacHex(KEY, "invoices.branch"), "810def903f1ee0e87396b31e1067bf358fa33090ca931ec0a855d121281a8295");
  assert.equal(await code("t", "invoices", KEY), "t_2680af88");
  assert.equal(await code("c", "invoices.branch", KEY), "c_810def90");
});

test("Web Crypto HMAC matches node:crypto for a random key", async () => {
  const k = newKey();
  assert.equal(k.length, 32);
  assert.equal(await hmacHex(k, "x.y"), createHmac("sha256", k).update("x.y").digest("hex"));
});

test("values, parameters and comments become ?, names become codes, roles as the gateway", async () => {
  const sql = "SELECT SUM(total) FROM invoices i WHERE i.branch = 7 AND issued_on >= '2026-09-26' -- note\n AND code = $1";
  const r = await hashSql(sql, KEY);
  const c = (n) => r.columns.find((x) => x.column === n);
  assert.equal(r.sql, `SELECT SUM(${c("total").code}) FROM t_2680af88 WHERE ${c("branch").code} = ? AND ${c("issued_on").code} >= ? AND ${c("code").code} = ?`);
  assert.equal(c("branch").code, "c_810def90");
  assert.deepEqual(c("total").roles, ["SELECT"]);
  assert.deepEqual(c("branch").roles, ["EQ"]);
  assert.deepEqual(c("issued_on").roles, ["RANGE"]);
  assert.ok(!/2026|note|\b7\b|\$1/.test(r.sql));
});

test("join, IN, group, order, function-wrapped and quoted strings", async () => {
  const sql = "SELECT a.city, COUNT(*) FROM shops a JOIN visits v ON a.id = v.shop WHERE v.kind IN ('x', 'it''s') AND date_trunc('month', v.day) = $2 GROUP BY a.city ORDER BY a.city";
  const r = await hashSql(sql, KEY);
  const roles = Object.fromEntries(r.columns.map((x) => [`${x.table}.${x.column}`, x.roles]));
  assert.deepEqual(roles["shops.id"], ["JOIN"]);
  assert.deepEqual(roles["visits.shop"], ["JOIN"]);
  assert.deepEqual(roles["visits.kind"], ["EQ"]);
  assert.deepEqual(roles["visits.day"], []);
  assert.deepEqual(roles["shops.city"], ["SELECT", "GROUP", "ORDER"]);
  assert.ok(r.sql.includes("IN (?, ?)") && r.sql.includes("DATE_TRUNC(?,"), r.sql);
  assert.ok(!/shops|visits|\bcity\b|month|it's/.test(r.sql), r.sql);
});

test("fails closed on an unqualified column with two tables in scope", async () => {
  await assert.rejects(hashSql("SELECT x FROM a, b", KEY), Unparsed);
  await assert.rejects(hashSql("SELECT 1", KEY), Unparsed);
});

test("changing one letter changes about half of the 256 digest bits", async () => {
  const d = bitsDiffer(await hmacHex(KEY, "branch"), await hmacHex(KEY, "brunch"));
  assert.ok(d > 80 && d < 176, String(d));
});

test("glitch frames run from the plain SQL to the hashed SQL", async () => {
  const { glitchFrame } = await import("../src/lib/glitch.ts");
  const from = "SELECT SUM(total) FROM invoices\nWHERE branch = 7";
  const to = (await hashSql(from, KEY)).sql;
  assert.equal(glitchFrame(from, to, 0, Math.random), from);
  assert.equal(glitchFrame(from, to, 1, Math.random), to);
  const mid = glitchFrame(from, to, 0.5, () => 0);
  assert.ok(mid.length >= Math.min(from.length, to.length) && mid.length <= Math.max(from.length, to.length), mid);
  assert.notEqual(mid, from);
  assert.notEqual(mid, to);
});

test("hashSql counts the values it strips", async () => {
  assert.equal((await hashSql("SELECT x FROM t WHERE a = 7 AND b IN ('p', $1)", KEY)).values, 3);
});
