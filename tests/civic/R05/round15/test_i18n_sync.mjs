// R05 · раунд 15 · запасные строки модуля 3D = словарь R11. Модуль берёт строку из BirgeI18n, если ключ там есть; без
// словаря (демо, старая сборка) работают запасные строки build3d.js STRINGS — они не должны расходиться с вычитанным R11
// (R11 в раунде 15 поправила kk у build3d.ba.label / ba.value: «жүгірткі», не «шторка»).
// Сверяются ключи, которые уже есть в словаре рабочей копии (web/civic/i18n/ru.json, kk.json); новых ключей модуля в
// словаре может ещё не быть — их список печатается, это не ошибка.
// Запуск: node --test tests/civic/R05/round15/test_i18n_sync.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import vm from "node:vm";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const ctx = { self: { document: null, CivicBuild3DCore: {}, CivicBuild3DModels: {} } };
vm.createContext(ctx);
vm.runInContext(readFileSync(path.join(ROOT, "web/civic/build3d/build3d.js"), "utf8"), ctx);
const STRINGS = JSON.parse(JSON.stringify(ctx.self.CivicBuild3D.STRINGS));
const dict = (lang) => JSON.parse(readFileSync(path.join(ROOT, "web/civic/i18n", lang + ".json"), "utf8"));
const norm = (v) => (typeof v === "string" ? v.replace(/ /g, " ") : JSON.stringify(v));

for (const lang of ["ru", "kk"]) {
  test(`build3d.* ${lang}: запасная строка модуля = словарь R11 (где ключ уже в словаре)`, () => {
    const d = dict(lang);
    const keys = Object.keys(STRINGS[lang]);
    const inDict = keys.filter((k) => k in d), notYet = keys.filter((k) => !(k in d));
    const diffs = inDict.filter((k) => norm(d[k]) !== norm(STRINGS[lang][k])).map((k) => ({ key: k, module: STRINGS[lang][k], dict: d[k] }));
    if (notYet.length) console.log(`# ${lang}: ключей модуля нет в словаре этой копии (${notYet.length}): ${notYet.join(", ")}`);
    assert.ok(inDict.length > 0, "словарь без ключей build3d.* — не та копия?");
    assert.deepEqual(diffs, [], "строки модуля расходятся со словарём");
  });
}
