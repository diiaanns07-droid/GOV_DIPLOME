// R16 · сцена 7 демо v2 «Двор вместе» (IDEA §3) от начала до конца, на ЧИСТОЙ базе стенда (сцена меняет данные):
//   «Мой двор» (Нура) → проблемы и соседи → «Субботник во дворе» → «Я приду» (14 → 15) → акимат «Поддержать:
//   мешки и вывоз» → «Отметить сделанным» → житель видит «Сделано вместе: 15 соседей» → лента двора → слой карты.
//   NODE_PATH=$(npm root -g) node tests/civic/R16/browser/r16_scene7.cjs http://127.0.0.1:8655 <папка кадров> [ru|kk] [1366x768]
// Фото «после» здесь не загружаем: в облаке нет настоящего фото (поправка П1) — на показе его добавляют с телефона.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.argv[2] || "http://127.0.0.1:8655";
const OUT = process.argv[3] || "research/round-15-results/R16/screens";
const LANG = process.argv[4] || "ru";
const [W, H] = (process.argv[5] || "1366x768").split("x").map(Number);
const STAFF = { user: process.env.R16_STAFF_USER || "operator", pass: process.env.R16_STAFF_PASS || "demo-stand-pass-2026" };
const YARD = "yard-1454082638";
const ITEM = "i-demo-scene7";
const tag = `scene7_${W}-${LANG}`;
fs.mkdirSync(OUT, { recursive: true });
const steps = [];
let fails = 0;
function step(name, ok, ms, info) {
  steps.push({ name, ok: !!ok, ms, info: ok ? undefined : info });
  if (!ok) fails++;
  console.log(`${ok ? "PASS" : "FAIL"} ${name} · ${ms} мс${ok ? "" : "  " + String(JSON.stringify(info)).slice(0, 200)}`);
}
async function timed(fn) { const t0 = Date.now(); const r = await fn(); return [r, Date.now() - t0]; }

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: W < 500 ? 2 : 1 });
  await ctx.addInitScript(([l]) => { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l); }, [LANG]);
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(e.message));
  await page.goto(BASE + "/?scene=7#yard/" + YARD, { waitUntil: "load" });
  let [, ms] = await timed(() => page.waitForSelector(".tg-yardhead", { timeout: 20000 }));
  await page.waitForTimeout(500);
  const yard = await page.evaluate(() => ({ kpis: [...document.querySelectorAll(".tg-kpi .bk-kpi__value")].map((n) => n.textContent),
    problems: document.querySelectorAll(".tg-overview .tg-row").length, next: document.querySelector(".tg-overview .tg-card__title")?.textContent }));
  step("1. «Мой двор»: 3 числа, проблемы двора, ближайшее дело", yard.kpis.length === 3 && yard.problems >= 1 && !!yard.next, ms, yard);
  await page.screenshot({ path: path.join(OUT, `${tag}_1_yard.png`) });

  [, ms] = await timed(async () => { await page.click(`[data-focus="open-${ITEM}"]`); await page.waitForSelector(".tg-actionbar"); });
  const before = await page.$eval(".tg-actionbar .tg-count", (n) => n.dataset.n);
  step("2. дело «Субботник во дворе»: 14 соседей придут", before === "14", ms, before);
  await page.screenshot({ path: path.join(OUT, `${tag}_2_initiative.png`) });

  [, ms] = await timed(async () => {
    await page.click(".tg-actionbar .tg-join");
    await page.waitForFunction(() => document.querySelector(".tg-actionbar .tg-count")?.dataset.n === "15");
  });
  await page.waitForTimeout(450);
  step("3. «Я приду»: 14 → 15", true, ms);
  await page.screenshot({ path: path.join(OUT, `${tag}_3_joined.png`) });

  // Акимат: вход, «Поддержать: мешки и вывоз», «Отметить сделанным».
  const sctx = await browser.newContext({ viewport: { width: W, height: H } });
  await sctx.addInitScript(([l]) => { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); }, [LANG]);
  const sp = await sctx.newPage();
  sp.on("pageerror", (e) => errs.push("staff: " + e.message));
  await sp.goto(BASE + "/", { waitUntil: "load" });
  await sp.evaluate(async (s) => {
    await fetch("/api/civic/v1/session/login", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: s.user, password: s.pass }) });
  }, STAFF);
  await sp.goto(BASE + "/?n=2#together/" + ITEM, { waitUntil: "load" });
  await sp.waitForFunction(() => window.CivicShell && window.CivicShell.csrfToken && window.CivicShell.csrfToken(), null, { timeout: 20000 });
  await sp.waitForSelector(".tg-detail .tg-staffactions", { timeout: 20000 });
  [, ms] = await timed(async () => {
    await sp.click(`[data-focus="support-${ITEM}"]`);
    await sp.waitForSelector(".tg-form input[type=text]");
    await sp.fill(".tg-form input[type=text]", LANG === "kk" ? "Қаптар және шығару 14:00-де" : "Мешки и вывоз в 14:00");
    await sp.click(".tg-form button[type=submit]");
    await sp.waitForSelector(".tg-detail .tg-supportbox", { timeout: 10000 });
  });
  await sp.waitForTimeout(400);
  step("4. акимат «Поддержать: мешки и вывоз» → «Поддержано акиматом»", true, ms);
  await sp.screenshot({ path: path.join(OUT, `${tag}_4_supported.png`) });
  [, ms] = await timed(async () => {
    await sp.click(`[data-focus="done-${ITEM}"]`);
    await sp.waitForSelector(".tg-form textarea");
    await sp.fill(".tg-form textarea", LANG === "kk" ? "Аула тазаланды, 20 қап шығарылды." : "Убрали двор и вывезли 20 мешков.");
    await sp.click(".tg-form button[type=submit]");
    await sp.waitForSelector(".tg-detail .tg-report__big", { timeout: 10000 });
  });
  const doneText = await sp.$eval(".tg-detail .tg-report__big", (n) => n.textContent);
  step("5. акимат «Отметить сделанным» → «Сделано вместе: 15»", /15/.test(doneText), ms, doneText);
  await sp.screenshot({ path: path.join(OUT, `${tag}_5_done_staff.png`) });
  await sctx.close();

  // Житель: «Сделано вместе», лента двора, слой карты.
  await page.goto(BASE + "/?n=3#together/" + ITEM, { waitUntil: "load" });
  [, ms] = await timed(() => page.waitForSelector(".tg-detail .tg-report__big", { timeout: 20000 }));
  const resident = await page.evaluate(() => ({ done: document.querySelector(".tg-report__big")?.textContent,
    support: !!document.querySelector(".tg-supportbox"), bar: !!document.querySelector(".tg-actionbar") }));
  step("6. житель: «Сделано вместе: 15 соседей», плашка акимата, запись закрыта", /15/.test(resident.done || "") &&
    resident.support && !resident.bar, ms, resident);
  await page.screenshot({ path: path.join(OUT, `${tag}_6_done_resident.png`) });
  await page.goto(BASE + "/?n=4#yard/" + YARD, { waitUntil: "load" });
  await page.waitForSelector(".tg-feed", { timeout: 20000 });
  await page.waitForTimeout(400);
  const feed = await page.$$eval(".tg-feed__text", (n) => n.map((x) => x.textContent));
  step("7. лента двора: «Сделано вместе» и «Акимат поддержал»", feed.some((t) => /15/.test(t)) && feed.length >= 2, 0, feed.slice(0, 3));
  await page.screenshot({ path: path.join(OUT, `${tag}_7_yard_feed.png`) });
  await page.evaluate(() => { window.BirgeShell.setSection("map"); });
  await page.waitForTimeout(800);
  [, ms] = await timed(async () => {
    await page.evaluate(() => window.BirgeShell.setLayer("initiatives"));
    await page.waitForSelector(".tg-pin", { timeout: 15000 });
  });
  const pins = await page.$$eval(".tg-pin", (n) => n.map((x) => x.getAttribute("aria-label")));
  step("8. слой карты «Инициативы» (выключен по умолчанию, включается переключателем): дело двора — «сделано»",
    pins.some((l) => /15/.test(l)), ms, pins.slice(0, 3));
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(OUT, `${tag}_8_map_layer.png`) });
  step("нет ошибок JS", errs.length === 0, 0, errs.slice(0, 3));
  await browser.close();
  fs.writeFileSync(path.join(OUT, `${tag}.json`), JSON.stringify({ base: BASE, lang: LANG, size: `${W}x${H}`,
    at: new Date().toISOString(), fails, steps }, null, 1));
  console.log(`\nСЦЕНА 7 ${tag}: ${fails ? "FAIL " + fails : "PASS"} · всего ${steps.reduce((s, x) => s + x.ms, 0)} мс на действия`);
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
