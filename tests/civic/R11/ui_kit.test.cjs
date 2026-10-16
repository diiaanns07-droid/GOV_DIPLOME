/* R11 · ui-kit.js в node без браузера: сезонный порядок категорий (POLISH_WAVE п. 11).
 *   node tests/civic/R11/ui_kit.test.cjs */
"use strict";
const assert = require("assert");
const fs = require("fs"), path = require("path"), vm = require("vm");
const ROOT = path.resolve(__dirname, "../../..");
const sandbox = { self: {} };
vm.runInNewContext(fs.readFileSync(path.join(ROOT, "web/civic/ui-kit/ui-kit.js"), "utf8"), sandbox);
const UI = sandbox.self.BirgeUI;
const cats = JSON.parse(fs.readFileSync(path.join(ROOT, "web/civic/ui-kit/categories_v2.json"), "utf8")).categories;
const ids = cats.map((c) => c.id);
assert.deepStrictEqual(ids.slice(0, 2), ["roads", "snow_ice"], "в файле «Дороги» первые, «Снег» вторые");
for (const [m, first] of [[1, "snow_ice"], [3, "snow_ice"], [4, "roads"], [10, "roads"], [11, "snow_ice"], [12, "snow_ice"]]) {
  const d = new Date(2026, m - 1, 15);
  const byId = UI.seasonOrder(ids, d), byObj = UI.seasonOrder(cats, d).map((c) => c.id);
  assert.strictEqual(byId[0], first, "месяц " + m);
  assert.deepStrictEqual(byObj, byId, "объекты и id — одинаково");
  assert.strictEqual(byId.length, ids.length);
  assert.deepStrictEqual(byId.filter((x) => x !== first), ids.filter((x) => x !== first), "остальные — в порядке файла");
}
assert.deepStrictEqual(ids, cats.map((c) => c.id), "исходный список не меняется");
assert.deepStrictEqual(UI.seasonOrder([], new Date(2026, 0, 1)), []);
// П3: метка «ИИ» — подпись и подсказка экранируются (угроза R15 T-R11-01: помощники ui-kit со строками HTML)
{
  const fakeDoc = { createElement: () => ({ className: "", title: "", innerHTML: "" }), addEventListener() {}, readyState: "complete",
    body: null, documentElement: { dataset: {} }, querySelector: () => null, querySelectorAll: () => [] };
  const box = { self: { document: fakeDoc } };
  vm.runInNewContext(fs.readFileSync(path.join(ROOT, "web/civic/ui-kit/ui-kit.js"), "utf8"), box);
  const tag = box.self.BirgeUI.aiTag({ label: "<img src=x onerror=alert(1)>" });
  assert.strictEqual(tag.className, "bk-ai");
  assert.ok(!/<img/.test(tag.innerHTML) && /&lt;img/.test(tag.innerHTML), "подпись метки экранирована");
  assert.ok(/#i-ai"/.test(tag.innerHTML), "значок i-ai из набора");
  const plain = box.self.BirgeUI.aiTag();
  assert.ok(/common\.ai\.badge/.test(plain.innerHTML) && plain.title === "common.ai.hint", "без словаря — ключи, без падения");
}
console.log("PASS ui_kit.test.cjs");
