// R11: поведение web/civic/i18n/i18n.js в Node (node tests/civic/R11/i18n.test.cjs).
"use strict";
const assert = require("assert");
const path = require("path");
const ROOT = path.resolve(__dirname, "../../..");
const I = require(path.join(ROOT, "web/civic/i18n/i18n.js"));
const ru = require(path.join(ROOT, "web/civic/i18n/ru.json"));
const kk = require(path.join(ROOT, "web/civic/i18n/kk.json"));

const warnings = [];
console.warn = (m) => warnings.push(String(m));
const NB = " ";

(async () => {
  await I.init({ dicts: { ru, kk }, lang: "ru" });
  assert.strictEqual(I.getLang(), "ru");
  // Склонения ru
  const forms = [1, 2, 4, 5, 11, 12, 14, 21, 22, 25, 101, 111].map((n) => I.t("common.people", { n }));
  assert.deepStrictEqual(forms, ["1 человек", "2 человека", "4 человека", "5 человек", "11 человек", "12 человек",
    "14 человек", "21 человек", "22 человека", "25 человек", "101 человек", "111 человек"]);
  assert.strictEqual(I.t("common.period.last_days", { n: 21 }), "за 21 день");
  assert.strictEqual(I.t("object.late", { n: 23 }), "Отстаёт на 23 дня");
  // Числа и даты
  assert.strictEqual(I.formatNumber(1666), "1" + NB + "666");
  assert.strictEqual(I.formatNumber(1234567), "1" + NB + "234" + NB + "567");
  assert.strictEqual(I.formatNumber(2.5), "2,5");
  assert.strictEqual(I.formatNumber(NaN), "—");
  assert.strictEqual(I.t("common.people", { n: 1666 }), "1" + NB + "666 человек");
  const now = "2026-10-11";
  assert.strictEqual(I.formatDate("2026-10-11T10:00:00+05:00", { now }), "11" + NB + "окт");
  // 19:30 UTC 10 октября = 00:30 11 октября в Астане (UTC+5)
  assert.strictEqual(I.formatDate("2026-10-10T19:30:00Z", { now }), "11" + NB + "окт");
  assert.strictEqual(I.formatDate("2025-05-09", { now }), "9" + NB + "мая" + NB + "2025");
  assert.strictEqual(I.formatTime("2026-10-10T19:30:00Z"), "00:30");
  assert.strictEqual(I.formatRelative("2026-10-08T12:00:00+05:00", { now: "2026-10-11T09:00:00+05:00" }), "3 дня назад");
  assert.strictEqual(I.formatRelative("2026-10-10T23:00:00+05:00", { now: "2026-10-11T09:00:00+05:00" }), "вчера");
  assert.strictEqual(I.formatDate("не дата"), "—");
  // Параметры и категории
  assert.strictEqual(I.t("target.kind.stop", { name: "Нура" }), "Остановка «Нура»");
  assert.strictEqual(I.cat("snow_ice"), "Снег и гололёд");
  assert.strictEqual(warnings.length, 0, warnings.join("\n"));

  // Казахский
  await I.setLang("kk");
  assert.strictEqual(I.getLang(), "kk");
  assert.strictEqual(I.t("common.people", { n: 12 }), "12 адам");
  assert.strictEqual(I.t("common.people", { n: 1 }), "1 адам");
  assert.strictEqual(I.t("target.kind.stop", { name: "Нұра" }), "«Нұра» аялдамасы");
  assert.strictEqual(I.formatDate("2026-10-11", { now }), "11" + NB + "қазан");
  assert.strictEqual(I.cat("snow_ice"), "Қар және көктайғақ");
  assert.strictEqual(warnings.length, 0, warnings.join("\n"));

  // Явный язык третьим аргументом (так зовёт R07 через Birge.i18n.t)
  assert.strictEqual(I.t("target.metoo", null, "ru"), "Я тоже");
  assert.strictEqual(I.t("target.metoo", null, "kk"), "Мен де");
  assert.strictEqual(I.t("heat.reported", { count: 3 }, "ru"), "Сообщили 3 человека");
  assert.strictEqual(I.has("heat.title", "kk"), true);

  // Запасной ru с одним предупреждением
  const ruOnly = Object.assign({}, ru, { "test.only_ru": "Только по-русски" });
  await I.init({ dicts: { ru: ruOnly, kk }, lang: "kk" });
  assert.strictEqual(I.t("test.only_ru"), "Только по-русски");
  I.t("test.only_ru");
  assert.strictEqual(warnings.filter((w) => w.includes("test.only_ru")).length, 1);
  // Неизвестный ключ возвращается как есть и попадает в отчёт
  assert.strictEqual(I.t("nope.missing"), "nope.missing");
  assert.ok(I.report().kk.includes("nope.missing"));
  // Неизвестный язык не ломает текущий
  await I.setLang("en");
  assert.strictEqual(I.getLang(), "kk");
  // kz → kk
  await I.setLang("ru");
  await I.setLang("kz");
  assert.strictEqual(I.getLang(), "kk");
  // onChange
  let seen = null;
  const off = I.onChange((l) => (seen = l));
  await I.setLang("ru");
  assert.strictEqual(seen, "ru");
  off();
  await I.setLang("kk");
  assert.strictEqual(seen, "ru");
  console.log("PASS i18n.test.cjs");
})().catch((e) => {
  console.error("FAIL", e.message);
  process.exit(1);
});
