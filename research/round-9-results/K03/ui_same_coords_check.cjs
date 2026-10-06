// K03 r9: браузерная проверка подсказки «в тех же координатах ещё N» в таблице записей случая устойчивости (resilience-ui.js).
//   NODE_PATH="$(npm root -g)" node ui_same_coords_check.cjs <app_root> <out.json>
// Ожидание по построению из data.js: у каждой записи категории — число и имена ДРУГИХ записей той же категории в точно тех же
// координатах. На сборке без подсказки проверка даёт FAIL (это фиксирует пробел), на копии с патчем P1 — PASS.
// Страница открывается через file://, сеть не используется; исходные файлы не меняются.
"use strict";
const { chromium } = require("playwright");
const path = require("path"), fs = require("fs");
const { pathToFileURL } = require("url");
const app = path.resolve(process.argv[2]), outFile = process.argv[3];
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail: ok ? undefined : detail }); console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? " — " + String(detail).slice(0, 300) : "")); };

(async () => {
  const browser = await chromium.launch(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {});
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [], requests = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("request", (r) => { if (!/^(file|blob|data):/.test(r.url())) requests.push(r.url()); });
  await page.goto(pathToFileURL(path.join(app, "web", "index.html")).href);
  await page.click('#toolSeg button[data-tool="v2"]');
  for (const city of ["shymkent", "astana"]) {
    if (city !== "shymkent") { await page.click(`#citySeg button[data-city="${city}"]`); await page.waitForTimeout(80); }
    for (const cat of ["school", "outpatient_clinic"]) {
      await page.selectOption("#plCat", cat); await page.waitForTimeout(60);
      await page.click("#plDemo"); await page.click("#rsAdd"); await page.waitForTimeout(80);
      const got = await page.evaluate(() => {
        const rows = [...document.querySelectorAll(`#resBody table.rs-recs tbody tr`)];
        return rows.map((tr) => ({ id: tr.querySelector("input[data-rs-rec]").getAttribute("data-rs-rec"), text: tr.querySelectorAll("td")[1].textContent }));
      });
      const want = await page.evaluate(([c, g]) => {
        const ps = CITY_EVIDENCE.cities[c].places.filter((p) => p.group === g);
        return Object.fromEntries(ps.map((p) => [p.id, ps.filter((o) => o.id !== p.id && o.lon === p.lon && o.lat === p.lat).map((o) => o.name || "Без названия")]));
      }, [city, cat]);
      const bad = [];
      for (const r of got) {
        const w = want[r.id], m = r.text.match(/в тех же координатах ещё (\d+): ([^(]*) \(/);
        if (w.length === 0 && m) bad.push(`${r.id}: лишняя подсказка`);
        if (w.length > 0 && (!m || Number(m[1]) !== w.length || w.some((n) => !m[2].includes(n)))) bad.push(`${r.id}: ожидалось ещё ${w.length} (${w.join(", ")}), в строке: ${m ? m[0] : "нет подсказки"}`);
      }
      const nShared = Object.values(want).filter((w) => w.length).length;
      check(`${city}/${cat}: подсказка общих координат у ${nShared} из ${got.length} записей = data.js`, got.length === Object.keys(want).length && bad.length === 0, bad.slice(0, 4).join(" | "));
      await page.click(`#rsDel_${(await page.evaluate(() => CITY_RESILIENCE_UI.state.cases[0].id))}`); await page.waitForTimeout(40);
    }
  }
  check("нет ошибок страницы", errors.length === 0, errors.join(" | "));
  check("нет сетевых запросов", requests.length === 0, requests.join(" "));
  await browser.close();
  if (outFile) fs.writeFileSync(outFile, JSON.stringify({ app_root: app, results }, null, 1) + "\n");
  process.exit(results.every((r) => r.ok) ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
