// R05 · строки модуля = словарь R11. Словарь главнее (модуль берёт ключ из BirgeI18n, если он там есть), но без словаря
// (демо, старая сборка) работают запасные строки модуля — они не должны расходиться с вычитанными R11.
//   mkdir /tmp/r11kit && git archive origin/claude/r14-R11 web/civic/i18n | tar -x -C /tmp/r11kit
//   node tests/civic/R05/build3d/i18n_sync_check.mjs /tmp/r11kit [метка R11]
// Сверяет: ключи build3d.* модуля (STRINGS) и research/round-14-results/R05/i18n_build3d.json — со словарём;
// запасные общие ключи модуля (COMMON_FALLBACK) — со словарём. Отчёт: runs/i18n_sync_r11.json.
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import vm from "node:vm";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const OUT = path.join(ROOT, "research/round-14-results/R05");
const KIT = process.argv[2];
if (!KIT) {
  console.error("usage: node i18n_sync_check.mjs <выгрузка R11 с web/civic/i18n> [метка]");
  process.exit(2);
}
const LABEL = process.argv[3] || KIT;
const dict = {};
for (const l of ["ru", "kk"]) dict[l] = JSON.parse(await readFile(path.join(KIT, "web/civic/i18n", l + ".json"), "utf8"));

// Модуль — в песочнице без карты: нужны только STRINGS и COMMON_FALLBACK (оба отдаёт CivicBuild3D / исходник).
const src = await readFile(path.join(ROOT, "web/civic/build3d/build3d.js"), "utf8");
const sandbox = { window: {}, document: { addEventListener() {}, querySelector() { return null; } }, console };
sandbox.window.window = sandbox.window;
sandbox.self = sandbox.window;
vm.createContext(sandbox);
vm.runInContext(src, sandbox);
const mod = sandbox.window.CivicBuild3D;
const STRINGS = mod && mod.STRINGS;
const i = src.indexOf("var COMMON_FALLBACK");
const COMMON = vm.runInNewContext("(" + src.slice(src.indexOf("{", i), src.indexOf("\n  };", i) + 4).replace(/;\s*$/, "") + ")");
const file = JSON.parse(await readFile(path.join(OUT, "i18n_build3d.json"), "utf8"));

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const diffs = [];
let n = 0;
for (const l of ["ru", "kk"]) {
  for (const [k, v] of Object.entries(STRINGS[l])) {
    n++;
    if (dict[l][k] === undefined) diffs.push({ where: "module", lang: l, key: k, module: v, r11: null });
    else if (!same(v, dict[l][k])) diffs.push({ where: "module", lang: l, key: k, module: v, r11: dict[l][k] });
  }
  for (const [k, v] of Object.entries(COMMON[l])) {
    n++;
    if (dict[l][k] !== undefined && !same(v, dict[l][k])) diffs.push({ where: "common_fallback", lang: l, key: k, module: v, r11: dict[l][k] });
  }
  for (const [k, v] of Object.entries(file)) {
    n++;
    if (!same(v[l], STRINGS[l][k])) diffs.push({ where: "i18n_build3d.json", lang: l, key: k, file: v[l], module: STRINGS[l][k] });
  }
}
for (const d of diffs) console.log("DIFF " + JSON.stringify(d));
const report = {
  generated_at: new Date().toISOString(),
  r11: LABEL,
  build3d_keys: Object.keys(STRINGS.ru).length,
  common_fallback_keys: Object.keys(COMMON.ru).length,
  compared: n,
  diffs,
  status: diffs.length ? "FAIL" : "PASS",
};
await writeFile(path.join(OUT, "runs", "i18n_sync_r11.json"), JSON.stringify(report, null, 1) + "\n");
console.log(`${report.status} — ключей build3d ${report.build3d_keys}, общих запасных ${report.common_fallback_keys}, сравнений ${n}, расхождений ${diffs.length}`);
process.exit(diffs.length ? 1 : 0);
