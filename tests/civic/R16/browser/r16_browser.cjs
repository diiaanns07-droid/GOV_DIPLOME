// R16 · браузерная проверка «Мой двор» и «Сделаем вместе» на стенде (tests/civic/R16/stand.py).
//   NODE_PATH=$(npm root -g) node tests/civic/R16/browser/r16_browser.cjs http://127.0.0.1:8655 research/round-15-results/R16/screens
// Размеры 1366×768, 1024×768, 375×812 × ҚАЗ / РУС; житель и акимат; состояния: загрузка, пусто, ошибка, успех.
// Демо-дело сцены 7 не меняется: «Я приду» → «Не смогу прийти» (полный проход сцены — r16_scene7.cjs на чистой базе).
// Итог — JSON рядом с кадрами (browser_r16.json): PASS/FAIL каждой проверки.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.argv[2] || "http://127.0.0.1:8655";
const OUT = process.argv[3] || "research/round-15-results/R16/screens";
const ONLY = process.env.R16_ONLY || "";          // «1366-ru» — один размер и язык (быстрый круг)
const STAFF = { user: process.env.R16_STAFF_USER || "operator", pass: process.env.R16_STAFF_PASS || "demo-stand-pass-2026" };
// Сцена 7: по умолчанию — запасные демо R16; с демо-миром R02 (CIVIC_DEMO_WORLD=1) — R16_SCENE_YARD=yard-1454082640
// R16_SCENE_ITEM=i-w15-01 (scenes.scene7 в world_v1.json).
const SCENE = { yard: process.env.R16_SCENE_YARD || "yard-1454082638", initiative: process.env.R16_SCENE_ITEM || "i-demo-scene7",
  emptyYard: "yard-1104998691" };
const SIZES = [[1366, 768], [1024, 768], [375, 812]];
const LANGS = ["ru", "kk"];
fs.mkdirSync(OUT, { recursive: true });

const results = [];
function check(name, ok, info) {
  results.push({ name, ok: !!ok, info: ok ? undefined : info });
  console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : "  " + String(JSON.stringify(info)).slice(0, 300)));
}
async function newPage(ctx) {
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push(e.message));
  page.on("console", (m) => {
    // Подложка OpenFreeMap в облаке не грузится (нет интернета) — это не ошибка модуля.
    if (m.type() === "error" && !/ERR_TUNNEL|ERR_NAME|Failed to load resource|openfreemap|tiles/i.test(m.text())) page.errs.push(m.text());
  });
  return page;
}
async function waitTg(page, selector) {
  await page.waitForFunction(() => !!(window.BirgeTogether && document.querySelector(".tg")), null, { timeout: 20000 });
  if (selector) await page.waitForSelector(selector, { timeout: 15000 });
  await page.waitForTimeout(350);
}
let loads = 0;
async function go(page, hash, selector) {
  // Новый адрес страницы (?n=…) — полная загрузка: смена только «#…» на тот же раздел страницу не перезагружает.
  await page.goto(BASE + "/?n=" + (++loads) + hash, { waitUntil: "load" });
  await waitTg(page, selector);
}
async function noSideScroll(page) {
  return page.evaluate(() => {
    const root = document.querySelector("#birge-screen");
    const docOk = document.documentElement.scrollWidth <= innerWidth + 1;
    const sheetOk = !root || root.scrollWidth <= root.clientWidth + 1;
    return docOk && sheetOk;
  });
}
// Видимый текст без «сырых» ключей и обрезанных строк (казахский длиннее русского).
async function textHealth(page) {
  return page.evaluate(() => {
    const host = document.querySelector(".tg");
    if (!host) return { raw: ["нет .tg"], clipped: [] };
    const raw = (host.innerText.match(/\btogether\.[a-z_.]+/g) || []).slice(0, 5);
    const clipped = [];
    host.querySelectorAll("button, .tg-card__title, .tg-row__title, .tg-kpi__label, .tg-status, .tg-support, .bk-chip, .tg-title").forEach((el) => {
      if (!el.offsetParent) return;
      const style = getComputedStyle(el);
      if (style.overflow === "hidden" && el.scrollWidth > el.clientWidth + 2) clipped.push(el.textContent.trim().slice(0, 40));
      const rect = el.getBoundingClientRect();
      // Вкладки — строка с прокруткой вбок (ui-kit .bk-tabs): дальняя вкладка за краем — это нормально.
      if (rect.right > innerWidth + 1 && !el.closest(".bk-tabs, .bk-scroll-x")) clipped.push("за краем: " + el.textContent.trim().slice(0, 40));
    });
    return { raw, clipped: clipped.slice(0, 5) };
  });
}
// Поправка П1: в модуле нет иллюстраций — svg крупнее 48 px только схема двора (форма OSM для точки сбора),
// img — только настоящие фото «после» (data URL).
async function slopFree(page) {
  return page.evaluate(() => {
    const bad = [];
    document.querySelectorAll(".tg svg").forEach((el) => {
      const r = el.getBoundingClientRect();
      if ((r.width > 48 || r.height > 48) && !el.classList.contains("tg-yardmap")) bad.push("svg " + Math.round(r.width) + "×" + Math.round(r.height));
    });
    document.querySelectorAll(".tg img").forEach((el) => { if (!/^data:image\//.test(el.getAttribute("src") || "")) bad.push("img " + el.getAttribute("src")); });
    return bad;
  });
}
async function primaries(page) {
  return page.evaluate(() => [...document.querySelectorAll(".tg .bk-btn--primary")].filter((b) => b.offsetParent &&
    !b.closest(".tg-card") && !b.closest(".tg-similar")).map((b) => b.textContent.trim()));
}
async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, name + ".png") });
}
async function jpegBuffer(page, w, h) {
  // «Фото после» для формы: рисуем картинку в браузере (как камера телефона, 1600×1066) и отдаём JPEG.
  const b64 = await page.evaluate(([w, h]) => {
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    const g = c.getContext("2d");
    const grad = g.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, "#e8f0fb"); grad.addColorStop(0.6, "#f3f1ec"); grad.addColorStop(1, "#e1ecd6");
    g.fillStyle = grad; g.fillRect(0, 0, w, h);
    g.fillStyle = "#b9734a"; for (let i = 0; i < 4; i++) g.fillRect(200 + i * 300, h * 0.62, 220, 24);
    g.fillStyle = "#8a6a4a"; for (let i = 0; i < 6; i++) g.fillRect(120 + i * 250, h * 0.4, 14, 160);
    g.fillStyle = "#cfe0bf"; for (let i = 0; i < 6; i++) { g.beginPath(); g.arc(127 + i * 250, h * 0.38, 70, 0, 7); g.fill(); }
    return c.toDataURL("image/jpeg", 0.92).split(",")[1];
  }, [w, h]);
  return Buffer.from(b64, "base64");
}

(async () => {
  const browser = await chromium.launch();
  for (const [w, hgt] of SIZES) {
    for (const lang of LANGS) {
      const tag = `${w}-${lang}`;
      if (ONLY && ONLY !== tag) continue;
      const phone = w < 500;
      // ---------------- житель
      const ctx = await browser.newContext({ viewport: { width: w, height: hgt }, deviceScaleFactor: phone ? 2 : 1 });
      await ctx.addInitScript(([l]) => {
        localStorage.setItem("birge.mode", "resident");
        localStorage.setItem("birge.lang", l);
        localStorage.removeItem("birge.together.yard");
      }, [lang]);
      const page = await newPage(ctx);

      // Выбор двора
      await go(page, "#yard", ".tg-yardrow");
      const rows = await page.$$eval(".tg-yardrow", (n) => n.length);
      check(`${tag} выбор двора: список дворов с соседями`, rows >= 5, rows);
      check(`${tag} выбор двора: одна главная кнопка`, (await primaries(page)).length === 1, await primaries(page));
      await shot(page, `${tag}_yard_picker`);

      // Выбор двора на карте (IA R11 §5.1): главная кнопка — «Выбрать на карте»; Esc — выход; нажатие во дворе — двор.
      const pickMain = await page.$('.tg-picker .bk-btn--primary[data-focus="pick-map"]');
      check(`${tag} выбор двора: главная — «Выбрать на карте», «Определить по месту» — тише`,
        !!pickMain && !!(await page.$('.tg-picker [data-focus="locate"]:not(.bk-btn--primary)')));
      if (pickMain) {
        await page.click('.tg-picker [data-focus="pick-map"]');   // экран мог перерисоваться — по селектору
        await page.waitForSelector(".tg-pickbar", { timeout: 5000 });
        check(`${tag} выбор на карте: строка-подсказка над картой`, await page.$eval(".tg-pickbar", (n) => n.getBoundingClientRect().width > 0));
        if (w === 1366 || phone) await shot(page, `${tag}_yard_pick_map`);
        await page.keyboard.press("Escape");
        await page.waitForFunction(() => !document.querySelector(".tg-pickbar"), null, { timeout: 5000 });
        check(`${tag} выбор на карте: Esc — выход`, true);
        await go(page, "#yard", ".tg-yardrow");
        await page.click('[data-focus="pick-map"]');
        await page.waitForSelector(".tg-pickbar", { timeout: 5000 });
        const spot = await page.evaluate(async (id) => {
          const res = await fetch("/api/civic/v2/together/yards/" + encodeURIComponent(id), { headers: { Accept: "application/json" } });
          const j = await res.json();
          const pt = (j.yard || {}).point;
          if (!pt || typeof map === "undefined" || !map) return null;   // eslint-disable-line no-undef
          map.jumpTo({ center: pt, zoom: 17 });                         // eslint-disable-line no-undef
          await new Promise((r) => setTimeout(r, 400));
          const xy = map.project(pt);                                   // eslint-disable-line no-undef
          const box = map.getCanvas().getBoundingClientRect();          // eslint-disable-line no-undef
          // Точка двора, не закрытая значками тепловой карты: ищем рядом свободное место на холсте.
          for (const [dx, dy] of [[0, 0], [14, 0], [-14, 0], [0, 14], [0, -14], [20, 20], [-20, -20]]) {
            const x = box.left + xy.x + dx, y = box.top + xy.y + dy;
            if (document.elementFromPoint(x, y) === map.getCanvas()) return { x, y }; // eslint-disable-line no-undef
          }
          return null;
        }, SCENE.yard);
        if (spot) {
          await page.mouse.click(spot.x, spot.y);
          const opened = await page.waitForSelector(`.tg-yardhead`, { timeout: 15000 }).then(() => true, () => false);
          check(`${tag} выбор на карте: нажатие во дворе открывает «Мой двор»`, opened && !(await page.$(".tg-pickbar")));
        } else {
          check(`${tag} выбор на карте: двор сцены 7 виден на карте`, false, "нет точки двора или она закрыта");
        }
        await go(page, "#yard", ".tg-yardrow");
      }

      // Страница двора (сцена 7)
      await page.click(`[data-focus="yard-${SCENE.yard}"]`);
      await page.waitForSelector(".tg-yardhead", { timeout: 15000 });
      await page.waitForTimeout(400);
      const head = await page.evaluate(() => ({
        title: document.querySelector(".tg-yardhead .tg-title")?.textContent,
        kpis: [...document.querySelectorAll(".tg-kpi .tg-kpi__value")].map((n) => n.textContent),
        tabs: document.querySelectorAll(".tg-tabs [role=tab]").length,
        demo: !!document.querySelector(".tg-yardhead .tg-demo"),
        feed: document.querySelectorAll(".tg-feed li").length,
      }));
      check(`${tag} двор: шапка, 3 числа, 4 вкладки, «Пример»`, /GreenLine/.test(head.title || "") && head.kpis.length === 3 &&
        head.kpis.every((k) => /^\d+$/.test(k.replace(/\s/g, ""))) && head.tabs === 4 && head.demo, head);
      check(`${tag} двор: лента двора не пустая`, head.feed >= 1, head.feed);
      check(`${tag} двор: одна главная кнопка`, (await primaries(page)).length === 1, await primaries(page));
      check(`${tag} двор: нет прокрутки вбок`, await noSideScroll(page));
      check(`${tag} двор: без рисунков (П1)`, !(await slopFree(page)).length, await slopFree(page));
      const health = await textHealth(page);
      check(`${tag} двор: нет ключей и обрезанного текста`, !health.raw.length && !health.clipped.length, health);
      await shot(page, `${tag}_yard_overview`);

      // «Я живу здесь»
      const membersBefore = Number(head.kpis[0].replace(/\s/g, ""));
      await page.click('[data-focus="join-yard"]');
      await page.waitForSelector(".tg-member", { timeout: 10000 });
      const members = Number(await page.$eval(".tg-kpi .tg-kpi__value", (n) => n.textContent.replace(/\s/g, "")));
      check(`${tag} двор: «Я живу здесь» → число соседей +1, кнопка «Предложить дело»`, members === membersBefore + 1 &&
        !!(await page.$('[data-focus="propose"]')), { membersBefore, members });
      if (w === 1366 || phone) await shot(page, `${tag}_yard_member`);

      // Вкладки
      await page.click('[data-focus="tab-problems"]');
      await page.waitForTimeout(250);
      check(`${tag} двор: вкладка «Проблемы» — места с карты`, (await page.$$(".tg-panel .tg-row")).length >= 1);
      if (w === 1366) await shot(page, `${tag}_yard_problems`);
      await page.click('[data-focus="tab-initiatives"]');
      await page.waitForTimeout(250);
      check(`${tag} двор: вкладка «Инициативы» — карточки`, (await page.$$(".tg-panel .tg-card")).length >= 2);
      if (w === 1366) await shot(page, `${tag}_yard_initiatives`);
      await page.click('[data-focus="tab-works"]');
      await page.waitForTimeout(250);
      check(`${tag} двор: вкладка «Работы» — список или понятная строка`,
        !!(await page.$(".tg-panel .tg-calm, .tg-panel .tg-nodata, .tg-panel .tg-row")));
      if (w === 1366) await shot(page, `${tag}_yard_works`);

      // Мастер: 3 шага и «Это увидят все»
      await page.click('[data-focus="tab-overview"]');
      await page.click('[data-focus="propose"]');
      await page.waitForSelector(".tg-wizard", { timeout: 10000 });
      await page.click('[data-focus="wnext"]');
      check(`${tag} мастер: без вида дела — понятная подсказка`, !!(await page.$(".tg-werror")));
      await page.click('[data-focus="kind-cleanup"]');
      await page.fill("#tg-wname", lang === "kk" ? "Аулада сенбілік" : "Субботник у площадки");
      await page.fill("#tg-wtext", lang === "kk" ? "Балалар алаңы жанында жиналамыз." : "Соберёмся у детской площадки.");
      if (w === 1366 || phone) await shot(page, `${tag}_wizard_1_what`);
      await page.click('[data-focus="wnext"]');
      await page.waitForSelector(".tg-yardmap", { timeout: 10000 });
      const box = await page.$eval(".tg-yardmap .tg-yardmap__area", (p) => { const r = p.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });
      await page.mouse.click(box[0], box[1]);
      await page.waitForTimeout(200);
      check(`${tag} мастер: точка сбора — во дворе по форме OSM`, !!(await page.$(".tg-yardmap__pin")));
      if (w === 1366 || phone) await shot(page, `${tag}_wizard_2_where`);
      await page.click('[data-focus="wnext"]');
      await page.waitForSelector(".tg-bringadd", { timeout: 10000 });
      if (w === 1366 || phone) await shot(page, `${tag}_wizard_3_bring`);
      await page.click('[data-focus="wnext"]');
      await page.waitForSelector(".tg-card--preview", { timeout: 10000 });
      await page.waitForTimeout(900);   // похожие рядом (запрос) — после него баннер
      const similar = !!(await page.$(".tg-similar"));
      check(`${tag} мастер: «Рядом уже есть похожее дело» (тот же вид, ближе 600 м)`, similar);
      await shot(page, `${tag}_wizard_4_review`);
      if (similar) await page.click(".tg-similar .tg-wnav .bk-btn:not(.bk-btn--primary)");
      await page.waitForSelector('[data-focus="wsend"]', { timeout: 5000 });
      if (w === 1366 || phone) await shot(page, `${tag}_wizard_4_review_privacy`);
      await page.click('[data-focus="wsend"]');
      await page.waitForSelector(".tg-sent", { timeout: 10000 });
      check(`${tag} мастер: отправлено — «на проверке»`, !!(await page.$(".tg-sent")));
      if (w === 1366 || phone) await shot(page, `${tag}_wizard_5_sent`);

      // «Сделаем вместе»: список и карточка дела
      await go(page, "#together", ".tg-card");
      const list = await page.evaluate(() => ({ cards: document.querySelectorAll(".tg-card").length,
        mine: document.querySelectorAll(".tg-mine .tg-row").length }));
      check(`${tag} список: карточки дел и «Мои инициативы» (на проверке)`, list.cards >= 5 && list.mine >= 1, list);
      check(`${tag} список: одна главная кнопка вне карточек`, (await primaries(page)).length === 1, await primaries(page));
      check(`${tag} список: нет прокрутки вбок`, await noSideScroll(page));
      check(`${tag} список: без рисунков (П1)`, !(await slopFree(page)).length, await slopFree(page));
      const lh = await textHealth(page);
      check(`${tag} список: нет ключей и обрезанного текста`, !lh.raw.length && !lh.clipped.length, lh);
      await shot(page, `${tag}_list`);
      await page.click(`[data-focus="open-${SCENE.initiative}"]`);
      await page.waitForSelector(".tg-detail .tg-actionbar", { timeout: 10000 });
      await page.waitForTimeout(300);
      const before = await page.$eval(".tg-actionbar .tg-count", (n) => n.dataset.n);
      // «Что взять» — на языке интерфейса (R11 R16-1): слова из подсказок и демо-мира другого языка переведены.
      const bring = await page.evaluate((l) => {
        const T = window.BirgeTogetherText || {}, other = l === "kk" ? "ru" : "kk";
        const words = (x) => new Set(Object.keys(T[x] || {}).filter((k) => k.startsWith("together.bring.")).flatMap((k) => T[x][k]));
        const mine = words(l), theirs = words(other);
        const tags = [...document.querySelectorAll(".tg-detail .tg-bring .bk-tag")].map((n) => n.textContent.trim());
        return { tags, foreign: tags.filter((w) => theirs.has(w) && !mine.has(w)) };
      }, lang);
      check(`${tag} карточка дела: «что взять» на языке интерфейса`, bring.tags.length > 0 && !bring.foreign.length, bring);
      await shot(page, `${tag}_detail`);
      await page.click(".tg-actionbar .tg-join");
      await page.waitForFunction(() => document.querySelector(".tg-actionbar .tg-join")?.getAttribute("aria-pressed") === "true" &&
        !document.querySelector(".tg-actionbar .tg-join")?.getAttribute("aria-busy"), null, { timeout: 10000 });
      await page.waitForTimeout(400);
      const after = await page.$eval(".tg-actionbar .tg-count", (n) => n.dataset.n);
      check(`${tag} «Я приду»: ${before} → ${after} (+1, один раз)`, Number(after) === Number(before) + 1, { before, after });
      await shot(page, `${tag}_detail_joined`);
      await page.reload({ waitUntil: "load" });
      // Оболочка с путями (R01 раунд 15) хранит адрес дела (#together/i-…) — после перезагрузки сразу карточка дела;
      // оболочка FINAL-4 — список.
      await waitTg(page, ".tg-card, .tg-detail .tg-actionbar");
      if (!(await page.$(".tg-detail .tg-actionbar"))) await page.click(`[data-focus="open-${SCENE.initiative}"]`);
      await page.waitForSelector(".tg-actionbar", { timeout: 10000 });
      const kept = await page.evaluate(() => ({ n: document.querySelector(".tg-actionbar .tg-count")?.dataset.n,
        pressed: document.querySelector(".tg-actionbar .tg-join")?.getAttribute("aria-pressed") }));
      check(`${tag} «Я приду»: после перезагрузки — то же число и «Вы придёте»`, kept.n === after && kept.pressed === "true", kept);
      await page.click(".tg-unjoin");
      await page.waitForFunction((b) => document.querySelector(".tg-actionbar .tg-count")?.dataset.n === String(b), Number(before), { timeout: 10000 });
      check(`${tag} «Не смогу прийти» → снова ${before}`, true);
      // Ошибка сети при «Я приду»: число возвращается, тост «Не получилось».
      await page.route("**/api/civic/v2/together/initiatives/*/join", (route) => route.abort());
      await page.click(".tg-actionbar .tg-join");
      await page.waitForTimeout(900);
      const reverted = await page.evaluate(() => ({ n: document.querySelector(".tg-actionbar .tg-count")?.dataset.n,
        toast: document.querySelector(".bk-toast--error")?.textContent || "" }));
      check(`${tag} «Я приду» без связи: число вернулось, тост ошибки`, reverted.n === before && reverted.toast.length > 0, reverted);
      if (w === 1366 || phone) await shot(page, `${tag}_detail_offline_toast`);
      await page.unroute("**/api/civic/v2/together/initiatives/*/join");
      // «На карте» в карточке дела: оболочка с setLayer (R01 раунда 15) — слой «Инициативы» и выделенная капсула дела
      // (лист слева остаётся открытым); без setLayer (FINAL-4) — цель «двор» на карте.
      await go(page, "#together/" + SCENE.initiative, '.tg-detail [data-focus="show-map"]');
      await page.click('[data-focus="show-map"]');
      const shown = await page.waitForFunction((id) => {
        if (document.body.dataset.birgeLayer === "initiatives") return document.querySelector(`.tg-pin--focus[data-id="${id}"]`) ? "layer" : false;
        return /#target=/.test(location.hash) ? "target" : false;
      }, SCENE.initiative, { timeout: 15000 }).then((x) => x.jsonValue(), () => null);
      check(`${tag} «На карте» в карточке дела: ${shown === "layer" ? "слой «Инициативы», капсула дела выделена" : "цель на карте"}`, !!shown, shown);
      if (shown === "layer") {
        // Перелёт к делу (программная отрисовка WebGL в облаке медленная — ждём, пока камера встанет).
        const flown = await page.waitForFunction(() => typeof map !== "undefined" && map && !map.isMoving() && map.getZoom() >= 15, // eslint-disable-line no-undef
          null, { timeout: 10000 }).then(() => true, () => false);
        const cam = await page.evaluate(() => ({ zoom: typeof map !== "undefined" && map ? Math.round(map.getZoom() * 10) / 10 : null, // eslint-disable-line no-undef
          moving: typeof map !== "undefined" && map ? map.isMoving() : null, section: window.BirgeShell && window.BirgeShell.section, // eslint-disable-line no-undef
          sheet: !!document.querySelector("#birge-screen:not([hidden])") }));
        check(`${tag} «На карте»: карта у дела (масштаб двора), лист остаётся`, flown && (phone || cam.sheet), cam);
        if (w === 1366 || phone) await shot(page, `${tag}_detail_on_map`);
      }
      // Сделано вместе: карточка с фото «после» (демо-иллюстрация)
      await go(page, "#together", ".tg-card");
      await page.click('[data-focus="when-done"]');   // чипы «Скоро · Сделано» (IA §5.2)
      await page.click('[data-focus="open-i-demo-benches"]');
      await page.waitForSelector(".tg-report__big", { timeout: 10000 });
      // П1: у демо-дела нет фото — строка «Фото появится после дела», а не нарисованная картинка.
      check(`${tag} «Сделано вместе»: число соседей и строка вместо фото (П1)`, !!(await page.$(".tg-report .tg-afterline")) &&
        !(await page.$(".tg-report img")) && /\d/.test(await page.$eval(".tg-report__big", (n) => n.textContent)));
      await shot(page, `${tag}_detail_done`);
      // Состояния: загрузка (скелетон не раньше 150 мс), ошибка с «Повторить», пустой двор
      await page.route("**/api/civic/v2/together/yards/" + SCENE.emptyYard, async (route) => { await new Promise((r) => setTimeout(r, 1500)); route.continue(); });
      // Ссылка ленты уведомлений «#yard/yard-…» (CONTRACT §5.8) открывает двор сразу.
      await page.goto(BASE + "/?n=" + (++loads) + "#yard/" + SCENE.emptyYard, { waitUntil: "load" });
      await page.waitForFunction(() => !!document.querySelector(".tg"), null, { timeout: 20000 });
      await page.waitForTimeout(500);
      const skel = !!(await page.$(".tg-skel"));
      check(`${tag} загрузка: скелетон`, skel);
      if (w === 1366 || phone) await shot(page, `${tag}_state_loading`);
      await page.waitForSelector(".tg-yardhead", { timeout: 15000 });
      await page.unroute("**/api/civic/v2/together/yards/" + SCENE.emptyYard);
      await page.waitForTimeout(300);
      check(`${tag} пусто: двор без дел — иллюстрация и подсказка`, !!(await page.$(".tg-overview .tg-empty")));
      await shot(page, `${tag}_state_empty_yard`);
      await page.route("**/api/civic/v2/together/initiatives*", (route) => route.fulfill({ status: 503, contentType: "application/json",
        body: JSON.stringify({ error: "module_not_ready", message: "Эта часть ещё не подключена в сборке." }) }));
      await go(page, "#together", ".tg-error");
      check(`${tag} ошибка: «что случилось + Повторить»`, !!(await page.$(".tg-error .bk-btn")));
      await shot(page, `${tag}_state_error`);
      await page.unroute("**/api/civic/v2/together/initiatives*");
      await page.click(".tg-error .bk-btn");
      await page.waitForSelector(".tg-card", { timeout: 10000 });
      check(`${tag} ошибка → «Повторить» → список`, true);
      // Двор сцены — снова без этого устройства (стенд остаётся тем же для следующего прогона).
      await page.evaluate(async (yard) => {
        await fetch("/api/civic/v2/together/yards/" + yard + "/leave", { method: "POST", headers: { "Content-Type": "application/json",
          "X-Birge-Device": localStorage.getItem("birge.device") }, body: "{}" });
      }, SCENE.yard);
      check(`${tag} житель: нет ошибок JS`, page.errs.length === 0, page.errs.slice(0, 3));
      await ctx.close();

      // ---------------- акимат
      const sctx = await browser.newContext({ viewport: { width: w, height: hgt }, deviceScaleFactor: phone ? 2 : 1 });
      await sctx.addInitScript(([l]) => { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); }, [lang]);
      const sp = await newPage(sctx);
      await go(sp, "#together", ".tg-staff");
      await sp.waitForSelector(".tg-staff .tg-empty, .tg-staff .tg-staffrow", { timeout: 15000 });
      check(`${tag} акимат без входа: просьба войти`, !!(await sp.$(".tg-staff .tg-empty .bk-btn--primary")));
      if (w === 1366 || phone) await shot(sp, `${tag}_staff_login`);
      await sp.evaluate(async (s) => {
        await fetch("/api/civic/v1/session/login", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: s.user, password: s.pass }) });
      }, STAFF);
      await sp.reload({ waitUntil: "load" });
      await sp.waitForFunction(() => window.CivicShell && typeof window.CivicShell.csrfToken === "function" && window.CivicShell.csrfToken(), null, { timeout: 20000 });
      await go(sp, "#together", ".tg-staffrow");
      const queue = await sp.evaluate(() => ({ rows: document.querySelectorAll(".tg-staffrow").length,
        flags: [...document.querySelectorAll(".tg-flags")].map((n) => n.textContent) }));
      check(`${tag} акимат: очередь на проверке и пометка о телефоне`, queue.rows >= 1 && queue.flags.length >= 1, queue);
      check(`${tag} акимат: нет прокрутки вбок`, await noSideScroll(sp));
      const sh = await textHealth(sp);
      check(`${tag} акимат: нет ключей и обрезанного текста`, !sh.raw.length && !sh.clipped.length, sh);
      await shot(sp, `${tag}_staff_queue`);
      await sp.click('.tg-tabs [data-focus="stab-waiting"]');
      await sp.waitForSelector(`.tg-staffrow[data-id="${SCENE.initiative}"]`, { timeout: 10000 });
      await sp.click(`[data-focus="support-${SCENE.initiative}"]`);
      await sp.waitForSelector(".tg-form", { timeout: 5000 });
      await sp.$eval(`.tg-staffrow[data-id="${SCENE.initiative}"]`, (n) => n.scrollIntoView({ block: "center" }));
      await shot(sp, `${tag}_staff_support_form`);
      await sp.click(`[data-focus="done-${SCENE.initiative}"]`);
      await sp.waitForSelector(".tg-form textarea", { timeout: 5000 });
      const chooser = sp.waitForEvent("filechooser");
      await sp.click(".tg-photoadd label.bk-btn");
      const fc = await chooser;
      await fc.setFiles({ name: "after.jpg", mimeType: "image/jpeg", buffer: await jpegBuffer(sp, 1600, 1066) });
      await sp.waitForSelector(".tg-photoadd__thumb", { timeout: 10000 });
      check(`${tag} акимат: фото «после» сжато в браузере (миниатюра готова)`, true);
      await sp.$eval(`.tg-staffrow[data-id="${SCENE.initiative}"] .tg-form`, (n) => n.scrollIntoView({ block: "center" }));
      await shot(sp, `${tag}_staff_report_form`);
      check(`${tag} акимат: нет ошибок JS`, sp.errs.length === 0, sp.errs.slice(0, 3));
      await sctx.close();
    }
  }
  await browser.close();
  const summary = { base: BASE, at: new Date().toISOString(), pass: results.filter((r) => r.ok).length,
    fail: results.filter((r) => !r.ok).length, results };
  fs.writeFileSync(path.join(OUT, "browser_r16.json"), JSON.stringify(summary, null, 1));
  console.log(`\nИТОГ: PASS ${summary.pass} · FAIL ${summary.fail}`);
  process.exit(summary.fail ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
