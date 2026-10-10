// R05 → R11: новые ключи перевода модуля 3D-превью в формате `i18n_tools.py add` R11
// ({ключ: {ru, kk, where}}). Строки берутся из самого модуля (build3d.js, STRINGS), без ручного копирования.
//   node tests/civic/R05/build3d/export_i18n.mjs  → research/round-14-results/R05/i18n_build3d.json
import { readFileSync, writeFileSync } from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const ctx = { self: { document: null, CivicBuild3DCore: {}, CivicBuild3DModels: {} } };
vm.createContext(ctx);
vm.runInContext(readFileSync(path.join(ROOT, "web/civic/build3d/build3d.js"), "utf8"), ctx);
const S = ctx.self.CivicBuild3D.STRINGS;
const WHERE = [
  [/^build3d\.loading$/, "R05 · нижняя панель 3D, пока грузится объёмный вид"],
  [/^build3d\.unsupported/, "R05 · панель 3D, браузер без WebGL2"],
  [/^build3d\.load_failed$/, "R05 · панель 3D и тост: 3D или проекты не загрузились (+ «Повторить»)"],
  [/^build3d\.hint\./, "R05 · панель 3D при размещении: подсказка под названием объекта"],
  [/^build3d\.poles$/, "R05 · подсказка освещения: «… · 7 фонарей» (формы числа)"],
  [/^build3d\.err\./, "R05 · панель 3D при размещении: красная подсказка, «Поставить» неактивна"],
  [/^build3d\.placed/, "R05 · тост после «Поставить» (с «Отменить»)"],
  [/^build3d\.deleted$/, "R05 · тост после «Удалить» (с «Отменить»)"],
  [/^build3d\.save_failed$/, "R05 · тост-ошибка «Поставить»/«Удалить» (с «Повторить»)"],
  [/^build3d\.vote_failed$/, "R05 · тост-ошибка голоса (с «Повторить»)"],
  [/^build3d\.card\.your_vote/, "R05 · карточка проекта под кнопками «За/Против»"],
  [/^build3d\.card\.open$/, "R05 · aria-label таблички «Проект · 2027» над объектом"],
  [/^build3d\.card\./, "R05 · карточка проекта: строка места (улица, участок, двор)"],
  [/^build3d\.catalog\.place$/, "R05 · aria-label карточки каталога «Что построить?»"],
  [/^build3d\.local_note$/, "R05 · под каталогом, пока нет сервера предложений R06"],
  [/^build3d\.near\.source$/, "R05 · после синей подсказки «рядом уже есть …»"],
  [/^build3d\.near\./, "R05 · синяя подсказка при размещении: такой объект OSM уже есть рядом"],
  [/^build3d\.resident\./, "R05 · панель 3D у жителя (каталога нет)"],
  [/^build3d\.demo\.title$/, "R05 · шапка demo.html рядом с Birge (в сборке шапку даёт R01)"],
];
const out = {};
for (const key of Object.keys(S.ru)) {
  const where = (WHERE.find(([re]) => re.test(key)) || [null, "R05 · 3D-превью"])[1];
  out[key] = { ru: S.ru[key], kk: S.kk[key], where };
}
const missingKk = Object.keys(out).filter((k) => !out[k].kk);
if (missingKk.length) throw new Error("нет kk: " + missingKk.join(", "));
const file = path.join(ROOT, "research/round-14-results/R05/i18n_build3d.json");
writeFileSync(file, JSON.stringify(out, null, 1) + "\n");
console.log(Object.keys(out).length + " ключей → " + path.relative(ROOT, file));
