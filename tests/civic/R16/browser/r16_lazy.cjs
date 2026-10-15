// R16 · ленивое подключение модуля (R10 B-113: первый значок карты > 3 с, когда все модули раунда 15 грузятся сразу).
// Страница открывается БЕЗ together-text.js и together.js (запросы к ним обрываются), через 3 с оба скрипта вставляются
// так, как это сделала бы оболочка при первом открытии раздела. Модуль должен сам зарегистрировать разделы и слой
// и открыть отложенный адрес оболочки: дело, двор, список. Ошибок страницы быть не должно.
// Оболочка раунда 15 (R01, пути разделов) держит адрес до загрузки модуля — он должен остаться тем же. Оболочка без путей
// (FINAL-4) уводит такой адрес на карту до модуля: там достаточно, что модуль сам открыл раздел (пометка в строке).
//   NODE_PATH=$(npm root -g) node tests/civic/R16/browser/r16_lazy.cjs http://127.0.0.1:8655 [двор] [дело]
// Двор и дело по умолчанию — фикстура стенда; на демо-мире R02: yard-1454082640 i-w15-01.
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:8655";
const YARD = process.argv[3] || process.env.R16_SCENE_YARD || "yard-1454082638";
const ITEM = process.argv[4] || process.env.R16_SCENE_ITEM || "i-demo-scene7";
const CASES = [
  ["дело #together/" + ITEM, "together/" + ITEM, ".tg-detail .tg-actionbar", "together"],
  ["двор #yard/" + YARD, "yard/" + YARD, ".tg-yardhead .tg-kpis", "yard"],
  ["список #together", "together", ".tg .tg-card", "together"],
];

(async () => {
  const browser = await chromium.launch();
  let fails = 0;
  for (const [name, hash, selector, section] of CASES) {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
    await ctx.addInitScript(() => { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", "ru"); });
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    let block = true;
    await page.route("**/civic/together/together*.js", (route) => (block ? route.abort() : route.continue()));
    await page.goto(BASE + "/?n=lazy#" + hash, { waitUntil: "load" });
    await page.waitForTimeout(3000);
    const before = await page.evaluate(() => ({ module: !!window.BirgeTogether, section: window.BirgeShell && window.BirgeShell.section }));
    block = false;
    const t0 = Date.now();
    await page.evaluate(() => new Promise((resolve, reject) => {
      const text = document.createElement("script");
      text.src = "/civic/together/together-text.js";
      text.onerror = reject;
      text.onload = () => {
        const main = document.createElement("script");
        main.src = "/civic/together/together.js";
        main.onload = resolve;
        main.onerror = reject;
        document.body.appendChild(main);
      };
      document.body.appendChild(text);
    }));
    const opened = await page.waitForSelector(selector, { timeout: 15000 }).then(() => true, () => false);
    const ms = Date.now() - t0;
    const after = await page.evaluate(() => ({ hash: location.hash, section: window.BirgeShell && window.BirgeShell.section }));
    const paths = before.section === section;   // оболочка держала раздел до модуля (раунд 15)
    const ok = opened && !before.module && errors.length === 0 && after.section === section && (!paths || after.hash === "#" + hash);
    if (!ok) fails++;
    const note = paths ? "" : " (оболочка без путей: адрес раздела ведёт модуль)";
    console.log(`${ok ? "PASS" : "FAIL"} ленивый вход: ${name} · ${ms} мс${note}${ok ? "" : "  " + JSON.stringify({ before, opened, after, errors: errors.slice(0, 3) })}`);
    await ctx.close();
  }
  await browser.close();
  console.log(`\nИТОГ: PASS ${CASES.length - fails} · FAIL ${fails}`);
  process.exit(fails ? 1 : 0);
})();
