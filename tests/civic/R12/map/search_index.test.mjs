// R12 · подсказки поиска по индексу R12 (web/civic/map/search_index.js) — правило Linear 1 эталона A, данные для R01.
//   node --test tests/civic/R12/map/search_index.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const require = createRequire(import.meta.url);
const S = require(path.join(ROOT, "web/civic/map/search_index.js"));
const data = JSON.parse(fs.readFileSync(path.join(ROOT, "web/civic/map/search_index.json"), "utf8"));
const ix = S.makeIndex(data);

test("first letters find streets and stops, from the start of any word", () => {
  const r = ix.query("тур", { lang: "ru", limit: 10 });
  assert.ok(r.some((x) => x.kind === "street" && x.label === "проспект Туран"), JSON.stringify(r.map((x) => x.label)));
  const khan = ix.query("хан ша", { lang: "ru" });
  assert.equal(khan[0].label, "Остановка «Хан Шатыр»");
  assert.ok(Array.isArray(khan[0].point) && khan[0].point.length === 2);
  assert.ok(ix.query("т", { lang: "ru" }).length > 0, "с первой буквы");
});

test("Kazakh letters fold both ways and Kazakh labels come in ҚАЗ", () => {
  const a = ix.query("қабанбай", { lang: "kk" }), b = ix.query("кабанбай", { lang: "kk" });
  assert.ok(a.length && b.length);
  assert.deepEqual(a.map((x) => x.id), b.map((x) => x.id));
  const t = ix.query("тұран", { lang: "kk", limit: 10 });
  assert.ok(t.some((x) => x.label === "Тұран даңғылы"), JSON.stringify(t.map((x) => x.label)));
  // по-русски в ҚАЗ тоже находит (житель набрал как на табличке)
  assert.ok(ix.query("туран", { lang: "kk" }).length > 0);
});

test("exclude hides places already shown (id or the other side of the stop)", () => {
  const r = ix.query("хан шатыр", { lang: "ru" });
  assert.equal(r[0].label, "Остановка «Хан Шатыр»");
  const hidden = ix.query("хан шатыр", { lang: "ru", exclude: ["osm-node-4109037549"] });
  assert.ok(!hidden.some((x) => x.label === "Остановка «Хан Шатыр»"), "та же остановка (другая сторона) — уже в горячих местах");
});

test("the place itself before places named after it; the other language ranks one step lower", () => {
  const r = ix.query("парк", { lang: "ru", limit: 6 });
  assert.equal(r[0].kind, "park", JSON.stringify(r.map((x) => x.kind + ":" + x.label)));
  const k = ix.query("саябақ", { lang: "kk", limit: 3 });
  assert.equal(k[0].kind, "park", JSON.stringify(k.map((x) => x.label)));
  const y = ix.query("двор", { lang: "ru", limit: 3 });
  assert.ok(y.every((x) => x.kind === "yard"), "«двор» — дворы, а не «Остановка «Дворец…»»: " + JSON.stringify(y.map((x) => x.label)));
});

test("same-name streets in different districts stay apart, no duplicates otherwise", () => {
  const r = ix.query("улица абая", { lang: "ru", limit: 20 });
  const keys = r.map((x) => x.label + "|" + (x.district || ""));
  assert.equal(new Set(keys).size, keys.length);
  assert.ok(ix.query("", { lang: "ru" }).length === 0);
});

test("load() caches, rejects a wrong file and retries after an error", async () => {
  let calls = 0;
  const ok = () => { calls++; return Promise.resolve({ ok: true, json: () => Promise.resolve(data) }); };
  const a = await S.load("/x.json", ok), b = await S.load("/x.json", ok);
  assert.equal(calls, 1); assert.equal(a, b); assert.ok(a.size > 2000);
  await assert.rejects(S.load("/bad.json", () => Promise.resolve({ ok: true, json: () => Promise.resolve({ schema: "other" }) })));
  await assert.rejects(S.load("/down.json", () => Promise.resolve({ ok: false, status: 503 })));
  const again = await S.load("/down.json", ok);
  assert.ok(again.size > 2000, "после ошибки — новая попытка");
});
