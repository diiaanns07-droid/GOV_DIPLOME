/* R11 · выбор языка при запуске (волна 2, обязательная мелочь «не переключать язык после ссылки или QR»).
 *   node tests/civic/R11/i18n_lang_order.test.cjs
 * Каждый случай — свежий экземпляр i18n.js в песочнице с поддельными localStorage, адресом и языком браузера. */
"use strict";
const assert = require("assert");
const fs = require("fs"), path = require("path"), vm = require("vm");
const ROOT = path.resolve(__dirname, "../../..");
const SRC = fs.readFileSync(path.join(ROOT, "web/civic/i18n/i18n.js"), "utf8");
const dicts = { ru: require(path.join(ROOT, "web/civic/i18n/ru.json")), kk: require(path.join(ROOT, "web/civic/i18n/kk.json")) };

async function start({ saved = null, search = "", languages = [], lang } = {}) {
  const store = saved ? { "birge.lang": saved } : {};
  const self = {
    localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
    location: { search },
    navigator: { languages, language: languages[0] },
  };
  const sb = { self, console };
  vm.runInNewContext(SRC, sb);
  const I = self.BirgeI18n;
  await I.init({ dicts, lang });
  return { lang: I.getLang(), saved: store["birge.lang"] || null, I, store };
}

(async () => {
  // Человек выбрал ҚАЗ — ссылка с ?lang=ru язык не переключает и выбор не трогает.
  let r = await start({ saved: "kk", search: "?report=object:osm-node-1&lang=ru" });
  assert.deepStrictEqual([r.lang, r.saved], ["kk", "kk"]);
  // Выбора нет — ?lang= показывает язык, но не запоминает.
  r = await start({ search: "?lang=kk" });
  assert.deepStrictEqual([r.lang, r.saved], ["kk", null]);
  // Выбора и параметра нет — язык браузера (kk-KZ), без запоминания.
  r = await start({ languages: ["kk-KZ", "ru-RU"] });
  assert.deepStrictEqual([r.lang, r.saved], ["kk", null]);
  r = await start({ languages: ["en-US", "ru-RU"] });
  assert.deepStrictEqual([r.lang, r.saved], ["ru", null]);
  // Ничего нет — ru.
  r = await start({ languages: ["en-US"] });
  assert.deepStrictEqual([r.lang, r.saved], ["ru", null]);
  // Явный язык хоста главнее, но не запоминается при запуске.
  r = await start({ saved: "ru", lang: "kk" });
  assert.deepStrictEqual([r.lang, r.saved], ["kk", "ru"]);
  // Нажатие ҚАЗ / РУС — запоминается.
  const s2 = await start({ saved: "ru", search: "?lang=kk" });
  assert.strictEqual(s2.lang, "ru");
  await s2.I.setLang("kk");
  assert.deepStrictEqual([s2.I.getLang(), s2.store["birge.lang"]], ["kk", "kk"]);
  console.log("PASS i18n_lang_order.test.cjs");
})().catch((e) => { console.error(e); process.exit(1); });
