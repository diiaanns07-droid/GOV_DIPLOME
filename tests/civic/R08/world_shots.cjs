/*
 * R08 · браузерная проверка и кадры на настоящей сборке R01 с демо-миром R02 (раунд 15, задачи 5–6).
 *
 *   CIVIC_DEMO=1 CIVIC_DEMO_WORLD=1 python3 app.py --port 8660        # сборка R01 + модули соседей + R08
 *   CIVIC_STAND_PASSWORD=… NODE_PATH=$(npm root -g) node tests/civic/R08/world_shots.cjs [base_url] [папка_кадров]
 *
 * Пароль сотрудника — только из переменной окружения (operator, как в RUN.txt R01). Проверяет и снимает:
 *   - Ситуационный центр без входа — «Войдите как сотрудник» и одна кнопка;
 *   - после входа: 1920×1080 и 1366×768, ru и kk — без прокрутки, 4 числа = ответ akim/board, все блоки по очереди;
 *     колонка R17 «Ответ просрочен» (правило R09, не срок исправления), «Двор недели» и «идёт сейчас» у начатого дела,
 *     карта районов (контуры OSM, числа = akim/board); подписи и числа плиток не под мини-графиком;
 *   - «Картина дня» в оболочке Birge: три карточки, «Поддержать» → дело сцены 7, «Открыть кризисный штаб» → идущий штаб;
 *   - «Картина недели»: ru и kk, печать — не больше 2 листов A4.
 * Итог — world_shots.json в папке кадров.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = (process.argv[2] || "http://127.0.0.1:8660").replace(/\/$/, "");
const OUT = process.argv[3] || path.join(__dirname, "../../../research/round-15-results/R08/screens/world");
const USER = process.env.CIVIC_STAND_USER || "operator";
const PASSWORD = process.env.CIVIC_STAND_PASSWORD || "";
fs.mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail) {
  results.push({ name, status: ok ? "PASS" : "FAIL", detail: detail == null ? undefined : detail });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail != null && !ok ? " — " + JSON.stringify(detail).slice(0, 300) : ""));
}
const TECH = /undefined|NaN|\bnull\b|\[object|osm-|c-w15|i-w15|inc-w15|\{[A-Za-z_]+\}/;   // {n} — незаполненная подстановка словаря
const shot = (page, name, full) => page.screenshot({ path: path.join(OUT, name), type: "jpeg", quality: 84, fullPage: !!full });
function pdfPages(file) {
  return (fs.readFileSync(file).toString("latin1").match(/\/Type\s*\/Page[^s]/g) || []).length;
}

(async () => {
  // Поле даты «Картины дня» (<input type=date>) Chromium рисует по LANG процесса, а не по языку страницы: без этого в облаке
  // кадр показывает «10/16/2026» вместо «16.10.2026» (как у R01 1940e4db).
  const browser = await chromium.launch({ env: { ...process.env, LANG: "ru_RU.UTF-8", LC_ALL: "ru_RU.UTF-8" } });
  // 1. без входа
  {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
    const page = await ctx.newPage();
    await page.goto(BASE + "/civic/board/index.html", { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".sc[data-state='forbidden']", { timeout: 20000 });
    const text = await page.textContent(".sc");
    const actions = await page.$$eval(".sc-state a, .sc-state button", (els) => els.map((e) => e.getAttribute("href") || e.textContent));
    check("без входа: «Войдите как сотрудник» и одна кнопка", /сотрудник/i.test(text) && actions.length === 1, { actions });
    await shot(page, "world-board-forbidden.jpg");
    await ctx.close();
  }
  if (!PASSWORD) {
    results.push({ name: "проверки после входа", status: "NOT_RUN", detail: "нет CIVIC_STAND_PASSWORD" });
    return finish(browser);
  }
  // 2. вход сотрудника (сессия R02 через шлюз R01)
  const login = await browser.newContext();
  const r = await login.request.post(BASE + "/api/civic/v1/session/login", { headers: { Origin: BASE }, data: { username: USER, password: PASSWORD } });
  check("вход сотрудника", r.status() === 200, r.status());
  const state = await login.storageState();
  const api = await (await login.request.get(BASE + "/api/civic/v2/akim/board")).json();
  const scenes = await (await login.request.get(BASE + "/api/civic/v2/demo/scenes")).json().catch(() => ({}));
  const scene7 = (((scenes && (scenes.data || scenes)) || {}).scenes || {}).scene7 || {};
  await login.close();

  const want = [api.kpi.new_day, api.kpi.in_progress, api.kpi.overdue, api.kpi.fixed_week].map((k) => String(k && k.value != null ? k.value : k));
  for (const [w, h, lang] of [[1920, 1080, "ru"], [1920, 1080, "kk"], [1366, 768, "ru"], [1366, 768, "kk"]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, storageState: state });
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); } catch (e) {} }, lang);
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.goto(BASE + "/civic/board/index.html", { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".sc[data-state='ready']", { timeout: 20000 });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(900);   // числа «доезжают» (600 мс)
    const tag = `${w}-${lang}`;
    const fits = await page.evaluate(() => document.scrollingElement.scrollHeight <= innerHeight + 1 && document.scrollingElement.scrollWidth <= innerWidth + 1);
    check(`${tag}: без прокрутки`, fits);
    const kpi = await page.$$eval(".sc-kpi__value", (els) => els.map((e) => e.textContent.replace(/\s/g, "")));
    check(`${tag}: 4 числа = akim/board`, JSON.stringify(kpi) === JSON.stringify(want), { kpi, want });
    // Длинная подпись (ҚАЗ «Мерзімінде түзетілмеген») не уходит под мини-график, число тоже (R10 аудит B0.9).
    const sparkHits = await page.evaluate(() => Array.from(document.querySelectorAll(".sc-kpi")).flatMap((t) => {
      const s = t.querySelector(".sc-spark");
      if (!s || getComputedStyle(s).display === "none") return [];
      const sr = s.getBoundingClientRect();
      return [".sc-kpi__label", ".sc-kpi__value"].filter((sel) => {
        const r = document.createRange(); r.selectNodeContents(t.querySelector(sel)); const b = r.getBoundingClientRect();
        return !(b.right <= sr.left || sr.right <= b.left || b.bottom <= sr.top || sr.bottom <= b.top);
      }).map((sel) => sel + ": " + t.querySelector(sel).textContent.trim());
    }));
    check(`${tag}: подписи и числа не под мини-графиком`, sparkHits.length === 0, sparkHits);
    const crisis = await page.textContent(".sc-crisis").catch(() => "");
    check(`${tag}: баннер кризиса из штаба R17`, lang === "ru" ? /Буран/.test(crisis) : /боран/i.test(crisis), crisis.slice(0, 120));
    await shot(page, `world-board-${tag}.jpg`);
    const ids = await page.$$eval(".sc-tab", (els) => els.map((e) => e.getAttribute("data-id")));
    check(`${tag}: блоки по очереди = slides akim/board`, JSON.stringify(ids) === JSON.stringify(api.slides), { ids, slides: api.slides });
    for (let i = 0; i < ids.length; i++) {
      await page.click(`.sc-tab[data-id='${ids[i]}']`);
      await page.waitForTimeout(450);
      const body = await page.textContent("#sc-slide-host");
      check(`${tag}: блок «${ids[i]}» без технических слов`, !TECH.test(body), (body.match(TECH) || [])[0]);
      if (ids[i] === "services") {
        check(`${tag}: колонка R17 — «ответ просрочен»`, lang === "ru" ? /Ответ просрочен/.test(body) : /Жауап мерзімі өткен/.test(body));
      }
      if (ids[i] === "together") {
        const yard = await page.textContent(".sc-yard").catch(() => "");
        check(`${tag}: «Двор недели» со страницы двора R16`, /BI City Tokyo/.test(yard) && /37/.test(yard), yard);
        check(`${tag}: начатое дело — «идёт сейчас»`, lang === "ru" ? /идёт сейчас/.test(body) : /қазір өтіп жатыр/.test(body));
      }
      if (ids[i] === "districts") {
        // Карта районов: контуры OSM из сборки, числа = районы akim/board (= карта R07), не больше 3 кружков мест.
        const map = await page.evaluate(() => {
          const m = document.querySelector(".sc-map");
          return m ? { labels: Array.from(m.querySelectorAll(".sc-map__label")).filter((l) => l.style.visibility !== "hidden")
            .map((l) => l.textContent.replace(/\s/g, "")), pins: m.querySelectorAll(".sc-map__pin").length,
            w: m.getBoundingClientRect().width } : null;
        });
        const want = (api.districts.items || []).map((r) => String(r.value));
        check(`${tag}: карта районов — числа = akim/board`, !!map && map.w > 150 && map.pins <= 3
          && map.labels.length >= 4 && map.labels.every((v) => want.includes(v)), { map, want });
      }
      if (w === 1920 || (w === 1366 && lang === "kk")) await shot(page, `world-board-${tag}-${String(i + 1).padStart(2, "0")}-${ids[i]}.jpg`);
    }
    check(`${tag}: без ошибок в консоли`, errors.length === 0, errors);
    await ctx.close();
  }

  // 3. «Картина дня» в оболочке Birge
  for (const lang of ["ru", "kk"]) {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, storageState: state });
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); } catch (e) {} }, lang);
    const page = await ctx.newPage();
    await page.goto(BASE + "/#day", { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".akim-trio .akim-mini", { timeout: 30000 });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(700);
    const cards = await page.$$eval(".akim-trio .akim-mini", (els) => els.map((e) => e.getAttribute("data-block")));
    check(`день ${lang}: три карточки соседей`, JSON.stringify(cards) === JSON.stringify(["agencies", "together", "meetings"]), cards);
    const support = await page.getAttribute(".akim-mini[data-block='together'] a", "href");
    if (scene7.initiative) {
      check(`день ${lang}: «Поддержать» → дело сцены 7`, support === "#together/" + scene7.initiative, { support, scene7: scene7.initiative });
    }
    const crisisBtn = await page.$$eval(".akim-pulse__crisis", (els) => els.map((e) => e.getAttribute("href")));
    check(`день ${lang}: одна кнопка «Открыть кризисный штаб» → идущий штаб`, crisisBtn.length === 1 && /#agencies\/crisis\/inc-/.test(crisisBtn[0]), crisisBtn);
    const text = await page.evaluate(() => (document.querySelector(".akim") || document.body).innerText);
    check(`день ${lang}: без технических слов`, !TECH.test(text), (text.match(TECH) || [])[0]);
    await shot(page, `world-day-1366-${lang}.jpg`, true);
    await ctx.close();
  }

  // 4. «Картина недели»
  for (const lang of ["ru", "kk"]) {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, storageState: state });
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); } catch (e) {} }, lang);
    const page = await ctx.newPage();
    await page.goto(BASE + "/civic/akim/week.html", { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".wk[data-state='ok']", { timeout: 20000 });
    await page.evaluate(() => document.fonts.ready);
    const text = await page.textContent(".wk-sheet");
    check(`неделя ${lang}: без технических слов`, !TECH.test(text), (text.match(TECH) || [])[0]);
    await shot(page, `world-week-1366-${lang}.jpg`, true);
    await page.emulateMedia({ media: "print" });
    const pdf = path.join(OUT, `world-week-${lang}.pdf`);
    await page.pdf({ path: pdf, format: "A4", printBackground: true });
    check(`неделя ${lang}: печать — не больше 2 листов A4`, pdfPages(pdf) <= 2, pdfPages(pdf));
    await ctx.close();
  }
  return finish(browser);
})().catch((e) => { console.error(e); process.exit(2); });

async function finish(browser) {
  await browser.close();
  const fails = results.filter((r) => r.status === "FAIL").length;
  const passed = results.filter((r) => r.status === "PASS").length;
  fs.writeFileSync(path.join(OUT, "world_shots.json"), JSON.stringify({ base: BASE, at: new Date().toISOString(),
    pass: passed, fail: fails, not_run: results.length - passed - fails, results }, null, 1));
  console.log(`\nИтог: ${passed} PASS, ${fails} FAIL`);
  process.exit(fails ? 1 : 0);
}
