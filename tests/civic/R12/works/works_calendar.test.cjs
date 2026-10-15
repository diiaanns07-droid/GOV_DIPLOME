/* R12 · раунд 15 · «Календарь работ» в НАСТОЯЩЕМ приложении: вход сотрудника → раздел → конфликт → карта.
 *
 *   NODE_PATH=$(npm root -g) node tests/civic/R12/works/works_calendar.test.cjs --url http://127.0.0.1:8655 \
 *     [--out research/round-15-results/R12/screens] [--user operator --password …] [--sizes 1366x768,1024x768,375x812]
 *
 * Сервер — app.py с маршрутами works-calendar / works-conflicts (patch R01 из INTEGRATION.txt R12) и CIVIC_DEMO=1
 * (фикстура R12, пока у R06 нет работ v2). Проверки: экран открылся из оболочки, 5 конфликтов, чип «копаем дважды»,
 * совет ru/kk, нет горизонтальной прокрутки страницы, нет ошибок в консоли, «Показать на карте» — раздел «Карта»,
 * слой «Конфликты работ» включён, карточка на карте, Esc закрывает карточку. Кадры — в --out (если задан).
 * Браузер — один, по очереди (COMMON: несколько браузеров на облачной машине дают ложные таймауты).
 */
"use strict";
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => {
  if (a.startsWith("--")) acc.push([a.slice(2), all[i + 1] && !all[i + 1].startsWith("--") ? all[i + 1] : "1"]);
  return acc;
}, []));
const URL = args.url || "http://127.0.0.1:8655";
const OUT = args.out || "";
const USER = args.user || "operator";
const PASSWORD = args.password || process.env.BIRGE_STAFF_PASSWORD || "Kokterek-Nura-71-Stand";
const SIZES = (args.sizes || "1366x768,1024x768,375x812").split(",").map((s) => s.split("x").map(Number));
const LANGS = (args.langs || "ru,kk").split(",");

const results = [];
function check(name, ok, detail) {
  results.push({ name, ok: !!ok, detail: detail || "" });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail ? " — " + detail : ""));
}

async function login(page) {
  return page.evaluate(async ({ user, password }) => {
    const r = await fetch("/api/civic/v1/session/login", { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: user, password }) });
    return r.status;
  }, { user: USER, password: PASSWORD });
}

async function openCalendar(page, lang) {
  await page.evaluate((l) => { if (window.BirgeI18n) window.BirgeI18n.setLang(l); }, lang);
  await page.waitForFunction(() => window.BirgeShell && window.BirgeWorksCalendar, null, { timeout: 20000 });
  await page.evaluate(() => { window.BirgeShell.setMode && window.BirgeShell.setMode("akimat"); window.BirgeShell.setSection("works-calendar"); });
  await page.waitForSelector(".wcal .wcal-tl .wcal-bar", { timeout: 20000 });
  await page.waitForTimeout(600);
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  const errors = [];
  try {
    for (const [w, h] of SIZES) {
      for (const lang of LANGS) {
        const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
        const page = await ctx.newPage();
        // Подложка OpenFreeMap и шрифты в облаке не грузятся (нет интернета, COMMON) — это не ошибка интерфейса.
        page.on("console", (m) => {
          const where = (m.location() && m.location().url) || "";
          if (m.type() === "error" && !(/ERR_(TUNNEL|NAME|INTERNET|CONNECTION)/.test(m.text()) && !/127\.0\.0\.1|localhost/.test(where))) {
            errors.push(`${w}/${lang}: ${m.text()} ${where}`);
          }
        });
        page.on("pageerror", (e) => errors.push(`${w}/${lang}: ${e.message}`));
        await page.goto(URL + "/", { waitUntil: "domcontentloaded" });
        const status = await login(page);
        check(`${w} ${lang}: вход сотрудника`, status === 200, "HTTP " + status);
        await page.reload({ waitUntil: "domcontentloaded" });
        await openCalendar(page, lang);
        // Демо-мир R02 (CIVIC_DEMO_WORLD=1): сцена 8 — его конфликт cf-w15-01 (ул. Баян Сулу), первым в списке может стоять
        // более срочный; без мира — фикстура R12, сцена 8 первая (ул. Сыганак).
        const world = await page.evaluate(() => !!document.querySelector('.wcal-cchip[data-conflict="cf-w15-01"]'));
        if (world) {
          // DEMO_SCRIPT R01, сцена 8, шаг 4: «Календарь работ» открывается сразу на конфликте сцены (scene_conflict).
          const first = await page.evaluate(() => document.querySelector(".wcal-focus")?.dataset.conflict || "");
          check(`${w} ${lang}: мир R02 — календарь открывается на сцене 8`, first === "cf-w15-01", first);
          await page.click('.wcal-cchip[data-conflict="cf-w15-01"]');
          await page.waitForSelector('.wcal-focus[data-conflict="cf-w15-01"]', { timeout: 5000 });
        }
        const info = await page.evaluate(() => ({
          title: document.querySelector(".wcal-title")?.textContent,
          chips: [...document.querySelectorAll(".wcal-cchip")].map((c) => c.textContent),
          bars: document.querySelectorAll(".wcal-bar").length,
          focusTitle: document.querySelector(".wcal-focus__title")?.textContent,
          advice: document.querySelector(".wcal-focus__advice")?.textContent || "",
          street: document.querySelector(".wcal-focus__street")?.textContent || "",
          pageScrollX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          keysShown: [...document.querySelectorAll(".wcal *")].some((el) => el.childElementCount === 0 && /^(wcal|common)\.[a-z_.]+$/.test(el.textContent.trim())),
        }));
        check(`${w} ${lang}: заголовок`, info.title && (lang === "kk" ? /күнтізбесі/.test(info.title) : /Календарь работ/.test(info.title)), info.title);
        check(`${w} ${lang}: 5 связей конфликтов`, info.chips.length === 5, info.chips.join(", "));
        check(`${w} ${lang}: чип «копаем дважды»`, info.chips.includes(lang === "kk" ? "екі рет қазу" : "копаем дважды"));
        const sceneStreet = world ? /Баян Сулу|Баян Сұлу/ : /Сыганак|Сығанақ/;
        check(`${w} ${lang}: сцена 8 — ${world ? "мир R02, ул. Баян Сулу" : "ул. Сыганак"}, совет`, sceneStreet.test(info.street) &&
          (lang === "kk" ? /Алдымен желілерді ауыстырыңыз/.test(info.advice) : /Сначала замените сети, потом кладите асфальт/.test(info.advice)), info.street);
        // Чип конфликта стоит в своей дорожке над полосами: не закрывает ни одной полосы (короткий асфальт, узкий промежуток).
        const covered = await page.evaluate(() => {
          const bars = [...document.querySelectorAll(".wcal-bar")].map((b) => b.getBoundingClientRect());
          const out = [];
          for (const c of document.querySelectorAll(".wcal-cchip")) {
            const r = c.getBoundingClientRect();
            if (bars.some((b) => r.left < b.right - 1 && r.right > b.left + 1 && r.top < b.bottom - 1 && r.bottom > b.top + 1)) out.push(c.dataset.conflict);
          }
          return out;
        });
        check(`${w} ${lang}: чипы конфликтов не закрывают полосы`, covered.length === 0, covered.join(", "));
        if (world) {
          // Асфальт уже уложен (пр. Кабанбай Батыра, cf-w15-02): совет беречь покрытие, а не «перенести асфальт».
          await page.click('.wcal-cchip[data-conflict="cf-w15-02"]');
          await page.waitForSelector('.wcal-focus[data-conflict="cf-w15-02"]', { timeout: 5000 });
          const done = await page.evaluate(() => ({
            stage: document.querySelector(".wcal-focus .wcal-chip--stage")?.textContent || "",
            advice: document.querySelector(".wcal-focus__advice")?.textContent || "",
          }));
          check(`${w} ${lang}: «асфальт уже уложен» — совет беречь покрытие`, (lang === "kk" ? /төселіп қойды/ : /уже уложен/).test(done.stage) &&
            !/Перенесите асфальт|Асфальт төсеуді қазудан кейінге/.test(done.advice) && (lang === "kk" ? /тесу әдісімен/ : /прокол/).test(done.advice), done.stage);
          await page.click('.wcal-cchip[data-conflict="cf-w15-01"]');
          await page.waitForSelector('.wcal-focus[data-conflict="cf-w15-01"]', { timeout: 5000 });
        }
        check(`${w} ${lang}: полосы работ`, info.bars >= 15, String(info.bars));
        check(`${w} ${lang}: нет горизонтальной прокрутки страницы`, info.pageScrollX <= 0, String(info.pageScrollX));
        check(`${w} ${lang}: нет ключей вместо текста`, !info.keysShown);
        if (OUT) {
          fs.mkdirSync(OUT, { recursive: true });
          await page.screenshot({ path: path.join(OUT, `calendar_${w}_${lang}.png`) });
        }
        // Нажатие на полосу — карточка работы, Esc закрывает и возвращает фокус.
        await page.click(".wcal-bar.is-sel");
        await page.waitForSelector(".wcal-pop", { timeout: 5000 });
        if (OUT && lang === "ru" && w === 1366) await page.screenshot({ path: path.join(OUT, `calendar_${w}_${lang}_work.png`) });
        await page.keyboard.press("Escape");
        const popGone = await page.evaluate(() => !document.querySelector(".wcal-pop") && document.activeElement?.classList.contains("wcal-bar"));
        check(`${w} ${lang}: карточка работы закрывается Esc, фокус на полосе`, popGone);
        // Переход к карте
        await page.click(".wcal-mapbtn");
        await page.waitForSelector(".wcal-mapcard", { timeout: 8000 });
        await page.waitForTimeout(1400);
        const mapInfo = await page.evaluate(() => ({
          section: document.body.dataset.birgeSection, layer: window.BirgeShell && window.BirgeShell.layer,
          card: document.querySelector(".wcal-mapcard__title")?.textContent,
          // eslint-disable-next-line no-undef
          hasLayer: (() => { try { return !!(typeof map !== "undefined" && map.getLayer && map.getLayer("birge-r12-wc-line")); } catch (e) { return false; } })(),
        }));
        check(`${w} ${lang}: «Показать на карте» → раздел «Карта»`, mapInfo.section === "map", mapInfo.section);
        check(`${w} ${lang}: слой «Конфликты работ» включён`, mapInfo.layer === "works-conflicts" && mapInfo.hasLayer, String(mapInfo.layer));
        check(`${w} ${lang}: карточка конфликта на карте`, !!mapInfo.card, mapInfo.card);
        if (OUT) await page.screenshot({ path: path.join(OUT, `map_${w}_${lang}.png`) });
        await page.keyboard.press("Escape");
        check(`${w} ${lang}: Esc закрывает карточку на карте`, await page.evaluate(() => !document.querySelector(".wcal-mapcard")));
        await ctx.close();
      }
    }
    // Вкладка «Календарь работ» в «Ведомствах» R17 (схема R11 §5.4, patch R17 из INTEGRATION R12) — если экран R17 есть.
    {
      const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
      const page = await ctx.newPage();
      page.on("pageerror", (e) => errors.push(`embedded: ${e.message}`));
      await page.goto(URL + "/", { waitUntil: "domcontentloaded" });
      await login(page);
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => window.BirgeShell && window.BirgeWorksCalendar, null, { timeout: 20000 });
      const hasTab = await page.evaluate(async () => {
        if (!window.BirgeAgencies) return false;
        window.BirgeShell.setSection("agencies");
        for (let i = 0; i < 40 && !document.querySelector('[role="tab"][data-tab="calendar"]'); i++) await new Promise((r) => setTimeout(r, 100));
        return !!document.querySelector('[role="tab"][data-tab="calendar"]');
      });
      if (!hasTab) {
        console.log("NOT_RUN вкладка в «Ведомствах» — в сборке нет экрана R17 или patch R17 ещё не применён");
      } else {
        await page.click('[role="tab"][data-tab="calendar"]');
        await page.waitForSelector(".ag-calendar .wcal-bar", { timeout: 15000 });
        // Главная кнопка вкладки — одна «Добавить работу» на весь экран «Ведомств» (у хозяина вкладки или у календаря).
        const emb = await page.evaluate(() => ({ h2: !!document.querySelector(".ag-calendar .wcal-title"),
          main: [...document.querySelectorAll("[data-agencies] .ag-body .bk-btn--primary")].filter((x) => x.offsetParent)
            .map((x) => x.textContent.trim()),
          chips: document.querySelectorAll(".ag-calendar .wcal-cchip").length }));
        check("вкладка «Календарь работ» в «Ведомствах»: без своего заголовка, главная — «Добавить работу»",
          !emb.h2 && emb.main.length === 1 && /Добавить работу|Жұмыс қосу/.test(emb.main[0]) && emb.chips >= 5, JSON.stringify(emb));
        if (OUT) await page.screenshot({ path: path.join(OUT, "embedded_r17_tab_1366_ru.png") });
        await page.click('[role="tab"][data-tab="board"]');
        await page.waitForTimeout(300);
        check("вкладка снимает календарь при уходе", await page.evaluate(() => !document.querySelector(".ag-calendar")));
      }
      await ctx.close();
    }
    // Все состояния экрана (подмена ответа шлюза): сотрудник не вошёл, модуль не подключён, нет связи, пусто, скелетон.
    if (!args["no-states"]) {
      const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
      const page = await ctx.newPage();
      page.on("pageerror", (e) => errors.push(`states: ${e.message}`));
      await page.goto(URL + "/", { waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => window.BirgeShell && window.BirgeWorksCalendar, null, { timeout: 20000 });
      const cases = [
        ["staff", { status: 401, body: { error: { code: "staff_required", message: "…" } } }, ".wcal-state--staff"],
        ["not_ready", { status: 503, body: { error: "module_not_ready", module: "engine.civic_geo.api", role: "R12" } }, ".wcal-state--not_ready"],
        ["network", "abort", ".wcal-state--network"],
        ["error", { status: 500, body: { error: "internal" } }, ".wcal-state--error"],
        ["empty", { status: 200, body: { period: { from: "2026-09-01", to: "2027-09-30", today: "2026-10-15" }, months: [], rows: [], works: [],
          conflicts: [], services: [], kinds: [], counts: { works: 0, conflicts: 0, high: 0 }, demo: false } }, ".wcal-state--empty"],
      ];
      for (const [name, reply, sel] of cases) {
        await page.unroute("**/api/civic/v2/works-calendar**").catch(() => {});
        await page.route("**/api/civic/v2/works-calendar**", (route) => (reply === "abort" ? route.abort("internetdisconnected")
          : route.fulfill({ status: reply.status, contentType: "application/json", body: JSON.stringify(reply.body) })));
        await page.evaluate(() => { window.BirgeShell.setSection("map"); window.BirgeShell.setSection("works-calendar"); });
        const ok = await page.waitForSelector(".wcal " + sel, { timeout: 8000 }).then(() => true, () => false);
        const text = ok ? await page.$eval(".wcal " + sel, (el) => el.textContent.trim().slice(0, 80)) : "";
        check(`состояние «${name}»`, ok, text);
        if (name === "staff") {
          const login = await page.$eval(".wcal .wcal-state--staff .bk-btn", (b) => b.textContent.trim()).catch(() => "");
          check("«для сотрудников» — кнопка «Войти»", /Войти|Кіру/.test(login), login);
        }
        if (OUT) await page.screenshot({ path: path.join(OUT, `state_${name}_1366_ru.png`) });
      }
      // Скелетон: ответ задерживается на 1,5 с — скелетон виден (не раньше 150 мс), потом экран.
      await page.unroute("**/api/civic/v2/works-calendar**").catch(() => {});
      await page.route("**/api/civic/v2/works-calendar**", async (route) => { await new Promise((r) => setTimeout(r, 1500)); route.continue(); });
      await page.evaluate(() => { window.BirgeShell.setSection("map"); window.BirgeShell.setSection("works-calendar"); });
      const early = await page.evaluate(() => !!document.querySelector(".wcal .wcal-skel__box"));
      await page.waitForTimeout(400);
      const skel = await page.evaluate(() => !!document.querySelector(".wcal .wcal-skel__box"));
      check("скелетон не раньше 150 мс, затем виден", !early && skel, `сразу ${early}, через 400 мс ${skel}`);
      if (OUT) await page.screenshot({ path: path.join(OUT, "state_loading_1366_ru.png") });
      await ctx.close();
    }
  } finally {
    await browser.close();
  }
  check("нет ошибок в консоли", errors.length === 0, errors.slice(0, 5).join(" | "));
  const failed = results.filter((r) => !r.ok).length;
  console.log(`ИТОГ: ${results.length - failed}/${failed} (PASS/FAIL)`);
  if (args.json) fs.writeFileSync(args.json, JSON.stringify({ url: URL, results }, null, 1));
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
