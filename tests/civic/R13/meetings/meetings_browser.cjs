// R13 · «Вопросы и встречи» (раунд 15) в оболочке Birge: раздел #meetings, житель и акимат, все состояния, кадры.
//
//   BIRGE_URL=http://127.0.0.1:8655 BIRGE_STAFF_USER=operator BIRGE_STAFF_PASS=… \
//     NODE_PATH=$(npm root -g) node tests/civic/R13/meetings/meetings_browser.cjs <папка_кадров> [--full]
//
// Сервер — сборка с маршрутами meetings.* (R01 или стенд с research/round-15-results/R13/patches/*.patch), CIVIC_DEMO=1,
// свежая база (демо-набор «Встреч» R13) и сотрудник. Без маршрутов — SKIP (а не PASS).
// Проверяет (IA_ROUND15 §5.3, VISUAL_BRIEF): одна главная кнопка; «Приду» — число +1 и держится после перезагрузки;
// голос за вопрос; форма вопроса (ошибка → «Вопрос отправлен»); прошедшая встреча — итоги, поручения со статусом
// словом, «просрочено», связь; Esc — на шаг назад; «На карте» → цель на карте; вкладка «Вопросы» — «Вопрос акиму»
// без второго заголовка; загрузка / пусто / ошибка с «Повторить»; без прокрутки вбок на 375; акимат — вход, новая
// встреча, поручение, статус из строки, связь, проверка вопроса, итог; нет ошибок JS. --full — кадры 1024 и всех состояний.
"use strict";
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path");

const BASE = (process.env.BIRGE_URL || "http://127.0.0.1:8655").replace(/\/$/, "");
const STAFF = { user: process.env.BIRGE_STAFF_USER || "operator", pass: process.env.BIRGE_STAFF_PASS || "parol-demo-12345" };
const args = process.argv.slice(2);
const OUT = path.resolve(args.find((a) => !a.startsWith("--")) || "r13-meetings-out");
const FULL = args.includes("--full");
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet|ERR_TUNNEL|net::ERR/i;
const checks = [];
const check = (name, ok, detail) => {
  checks.push({ name, status: ok ? "PASS" : "FAIL", detail: detail ?? null });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail != null ? " — " + JSON.stringify(detail).slice(0, 240) : ""));
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// R10 B-118 (VISUAL_BRIEF §4 п. 10, шкала 13/15/17): в разделе каждая кнопка, поле, вкладка — не меньше 44 × 44 px
// (ссылка-текст — 44 в высоту), каждый видимый текст — не меньше 13 px. Скрытое для глаза (bk-sr-only) не считаем.
async function sizeAudit(page, label) {
  const res = await page.evaluate(() => {
    const root = document.querySelector(".mt");
    if (!root) return { small: ["нет .mt"], tiny: [] };
    const seen = (el) => { const r = el.getBoundingClientRect(); return r.width > 2 && r.height > 2 && getComputedStyle(el).visibility !== "hidden"; };
    const name = (el) => (el.getAttribute("data-focus") || el.className || el.tagName).toString().split(" ")[0];
    const small = [];
    root.querySelectorAll("button, select, input:not([type=hidden]), textarea, a[href], [role=tab]").forEach((el) => {
      if (!seen(el)) return;
      const r = el.getBoundingClientRect();
      const textLink = el.classList.contains("mt-link");
      // зона нажатия шире видимой кнопки за счёт ::after (ui-kit .bk-vote: 32 px + inset -6px) — как считает R10 ux_lib
      const a = getComputedStyle(el, "::after");
      const zone = a.content !== "none" && a.position === "absolute";
      const out = (v) => (zone ? Math.max(0, -parseFloat(v) || 0) : 0);
      const zh = r.height + out(a.top) + out(a.bottom), zw = r.width + out(a.left) + out(a.right);
      if (zh < 43.5 || (!textLink && zw < 43.5)) small.push(name(el) + " " + Math.round(zw) + "×" + Math.round(zh));
    });
    const tiny = [];
    const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (walk.nextNode()) {
      const el = walk.currentNode.parentElement;
      if (!walk.currentNode.textContent.trim() || !el || !seen(el) || el.closest(".bk-sr-only, .sr-only")) continue;
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (fs < 12.5) tiny.push(name(el) + " " + fs + "px");
    }
    return { small: [...new Set(small)], tiny: [...new Set(tiny)] };
  });
  check(`${label}: зоны нажатия не меньше 44 px`, res.small.length === 0, res.small.slice(0, 6).join("; ") || null);
  check(`${label}: текст не меньше 13 px`, res.tiny.length === 0, res.tiny.slice(0, 6).join("; ") || null);
}
const shots = [];

async function context(browser, w, h, lang, mode, reduce) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, reducedMotion: reduce ? "reduce" : "no-preference" });
  await ctx.addInitScript(([l, m]) => { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); }, [lang, mode]);
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !NOISE.test(m.text())) page.errs.push(m.text()); });
  return { ctx, page };
}
const shot = async (page, name) => {
  const file = path.join(OUT, name + ".png");
  await page.screenshot({ path: file });
  shots.push(path.basename(file));
};
const openMeetings = async (page, hash) => {
  await page.goto(BASE + "/" + (hash || "#meetings"));
  await page.waitForSelector(".mt", { timeout: 60000 });
  await page.waitForSelector(".mt-hero, .mt-row, .mt-state, .mt-dhead, .mt-login", { timeout: 30000 });
  await sleep(400);
};
const noSideScroll = (page) => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1
  && [...document.querySelectorAll(".mt *")].every((e) => { const r = e.getBoundingClientRect(); return !r.width || r.right <= innerWidth + 1; }));
const primaryCount = (page) => page.evaluate(() => [...document.querySelectorAll(".mt-body .bk-btn--primary")]
  .filter((b) => b.getClientRects().length && !b.closest(".qa")).length);
const login = async (page) => {
  await page.evaluate(async (s) => {
    await fetch("/api/civic/v1/session/login", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: s.user, password: s.pass }) });
  }, STAFF);
  await page.reload();
  await page.waitForFunction(() => window.CivicShell?.csrfToken?.(), null, { timeout: 30000 }).catch(() => null);
};

async function residentFlow(browser, w, h, lang) {
  const tag = `${w}-${lang}`;
  const { ctx, page } = await context(browser, w, h, lang, "resident", true);
  await openMeetings(page);
  const kk = lang === "kk";
  const title = await page.textContent(".mt__title");
  check(`${tag} раздел #meetings открыт, заголовок на языке`, kk ? /Сұрақтар мен кездесулер/.test(title) : /Вопросы и встречи/.test(title), title);
  check(`${tag} две вкладки «Встречи · Вопросы»`, (await page.$$(".mt-seg [role=tab]")).length === 2);
  const hero = await page.$(".mt-hero");
  check(`${tag} ближайшая встреча крупно`, !!hero);
  const heroText = hero ? await hero.innerText() : "";
  // место — любое (свой набор R13: «Eco Park»; демо-мир R02: другой двор), важно, что подпись места есть
  const place = hero ? await hero.$eval(".mt-place__label", (el) => el.textContent.trim()).catch(() => "") : "";
  check(`${tag} в карточке: дата, место, «Пример», ведущий без имени`,
    /\d/.test(heroText) && place.length > 2
      && (kk ? /Үлгі/.test(heroText) && /Аудан әкімі/.test(heroText) : /Пример/.test(heroText) && /аким района/.test(heroText)), heroText.slice(0, 160));
  check(`${tag} одна главная кнопка — «Приду»`, (await primaryCount(page)) === 1 && /Приду|Барамын/.test(await page.textContent(".mt-going")));
  check(`${tag} без прокрутки вбок`, await noSideScroll(page));
  const btn = await page.$(".mt-going");
  const box = btn ? await btn.boundingBox() : null;
  check(`${tag} «Приду» не ниже 44 px`, !!box && box.height >= 44, box && Math.round(box.height));
  await sizeAudit(page, `${tag} список`);
  await shot(page, `${tag}-r-list`);

  if (w === 1366 && lang === "ru") {
    const before = Number((await page.textContent(".mt-count")).replace(/\D/g, ""));
    await page.click(".mt-going");
    await page.waitForFunction((n) => Number(document.querySelector(".mt-count").textContent.replace(/\D/g, "")) === n + 1, before, { timeout: 15000 }).catch(() => null);
    const after = Number((await page.textContent(".mt-count")).replace(/\D/g, ""));
    check("«Приду» → число +1, кнопка нажата", after === before + 1 && (await page.getAttribute(".mt-going", "aria-pressed")) === "true", { before, after });
    check("появилась «Не смогу прийти»", !!(await page.$(".mt-notgoing")));
    await shot(page, `${tag}-r-going`);
    await page.reload();
    await page.waitForSelector(".mt-hero .mt-going[aria-pressed=true]", { timeout: 30000 }).catch(() => null);
    check("«Приду» держится после перезагрузки (одно устройство — один раз)",
      (await page.getAttribute(".mt-going", "aria-pressed")) === "true" && Number((await page.textContent(".mt-count")).replace(/\D/g, "")) === after);
    await page.click(".mt-notgoing");
    await page.waitForFunction((n) => Number(document.querySelector(".mt-count").textContent.replace(/\D/g, "")) === n, before, { timeout: 15000 }).catch(() => null);
    check("«Не смогу прийти» → число вернулось", Number((await page.textContent(".mt-count")).replace(/\D/g, "")) === before);

    // Голос за вопрос (экран перерисовывается после ответа — только селекторы, не сохранённые элементы)
    await sleep(600);
    const VOTE = ".mt-qlist .mt-q:nth-child(2) .mt-vote";
    if (await page.$(VOTE)) {
      const n0 = Number((await page.innerText(VOTE)).replace(/\D/g, ""));
      await page.click(VOTE);
      await page.waitForFunction(([sel, n]) => Number(document.querySelector(sel)?.innerText.replace(/\D/g, "")) === n + 1, [VOTE, n0], { timeout: 15000 }).catch(() => null);
      const n1 = Number((await page.innerText(VOTE)).replace(/\D/g, ""));
      check("голос за вопрос: +1 и «Вы поддержали»", n1 === n0 + 1 && (await page.getAttribute(VOTE, "aria-pressed")) === "true", { n0, n1 });
    } else check("голос за вопрос", false, "нет вопросов");

    // Форма вопроса: ошибка на коротком, отправка
    await page.click(".mt-askbtn");
    await page.waitForSelector(".mt-ask textarea", { timeout: 10000 });
    await page.click(".mt-ask button[type=submit]");
    await sleep(300);
    check("форма: ошибка на пустом вопросе", !!(await page.$(".mt-ask .bk-field__error")));
    await shot(page, `${tag}-r-form-error`);
    await page.fill(".mt-ask textarea", "Когда во дворе Eco Park отремонтируют спортивную площадку?");
    await page.click(".mt-ask button[type=submit]");
    await page.waitForSelector(".mt-sent", { timeout: 15000 }).catch(() => null);
    check("вопрос отправлен — «опубликуют после проверки»", !!(await page.$(".mt-sent")));
    await shot(page, `${tag}-r-sent`);

    // Прошедшая встреча: итоги, поручения, «просрочено», связь, ответы (строка с фазой «прошла» — в демо-мире выше неё
    // может стоять другая предстоящая встреча)
    await page.click('.mt-rows .mt-row[data-phase="held"]');
    await page.waitForSelector(".mt-dhead", { timeout: 20000 });
    await sleep(400);
    const detail = await page.innerText(".mt-detail");
    check("встреча: «Итоги встречи» и «Поручения»", /Итоги встречи/.test(detail) && /Поручения/.test(detail));
    const orders = await page.$$(".mt-order");
    check("поручения со статусом словом и сроком", orders.length >= 4 && /Выполнено|В работе|Не начато/.test(detail) && /срок/.test(detail), orders.length);
    // «просрочено» — ровно у тех поручений, у которых сервис отдал overdue (в наборе R13 такое есть, в демо-мире — может не быть)
    const late = await page.evaluate(async () => {
      const id = decodeURIComponent((location.hash.split("/")[1] || ""));
      const r = await fetch("/api/civic/v2/meetings/" + encodeURIComponent(id), { credentials: "same-origin" });
      const b = await r.json(); const m = (b.data || b).meeting || {};
      return { api: (m.orders || []).filter((o) => o.overdue).length, ui: document.querySelectorAll(".mt-order.is-overdue").length };
    });
    check("просроченные поручения помечены (как в ответе сервиса)", late.api === late.ui && (late.api === 0 || /просрочено/.test(detail)), late);
    check("связь поручения с обращением видна", !!(await page.$(".mt-linkchip")));
    check("ответы на встрече — цитатой", !!(await page.$(".mt-answer")));
    await sizeAudit(page, `${tag} прошедшая встреча`);
    await shot(page, `${tag}-r-past`);
    await page.keyboard.press("Escape");
    await page.waitForSelector(".mt-hero", { timeout: 15000 }).catch(() => null);
    check("Esc — назад к списку встреч, раздел не закрыт", !!(await page.$(".mt-hero")) && (await page.evaluate(() => window.BirgeShell?.section)) === "meetings");

    // Вкладка «Вопросы» — «Вопрос акиму» внутри, без второго заголовка
    await page.click('.mt-seg [role=tab][value="questions"]');
    await page.waitForSelector(".mt-askhost .qa", { timeout: 20000 }).catch(() => null);
    await sleep(800);
    const embedded = await page.evaluate(() => {
      const t = document.querySelector(".mt-askhost .qa__title");
      return { has: !!document.querySelector(".mt-askhost .qa"), titleHidden: !!t && t.classList.contains("bk-sr-only"),
        close: !!document.querySelector(".mt-askhost .qa__close"), rule: !!document.querySelector(".mt-askhost .qa__rule") };
    });
    check("вкладка «Вопросы»: «Вопрос акиму» внутри, без второго заголовка и «×»", embedded.has && embedded.titleHidden && !embedded.close && embedded.rule, embedded);
    await sizeAudit(page, `${tag} вкладка «Вопросы»`);
    await shot(page, `${tag}-r-questions`);
    await page.click('.mt-seg [role=tab][value="meetings"]');
    await page.waitForSelector(".mt-hero", { timeout: 15000 }).catch(() => null);

    // «На карте» — раздел карты и цель встречи
    await page.click(".mt-hero .mt-link");
    await sleep(1200);
    const where = await page.evaluate(() => ({ section: window.BirgeShell?.section, hash: location.hash }));
    check("«На карте» → карта с целью встречи", where.section === "map" && /target=area:yard-/.test(decodeURIComponent(where.hash)), where);
  }
  check(`${tag} нет ошибок JS`, page.errs.length === 0, page.errs.slice(0, 3));
  await ctx.close();
}

async function statesFlow(browser, w, h, lang) {
  const tag = `${w}-${lang}`;
  // Загрузка: ответ задержан — скелетон (не раньше 150 мс)
  let { ctx, page } = await context(browser, w, h, lang, "resident", true);
  await page.route(/\/api\/civic\/v2\/meetings\?/, async (r) => { await sleep(4000); await r.continue().catch(() => null); });
  await page.goto(BASE + "/#meetings");
  await page.waitForSelector(".mt", { timeout: 60000 });
  await sleep(700);
  check(`${tag} загрузка — скелетон`, !!(await page.$(".mt-skel")));
  await shot(page, `${tag}-r-loading`);
  await ctx.close();
  // Пусто
  ({ ctx, page } = await context(browser, w, h, lang, "resident", true));
  await page.route(/\/api\/civic\/v2\/meetings\?/, (r) => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ items: [], next_id: null, counts: { upcoming: 0, past: 0 }, staff: false }) }));
  await openMeetings(page);
  const empty = await page.$(".mt-state .bk-empty");
  check(`${tag} пусто — подсказка и кнопка «Задать вопрос акиму»`, !!empty && !!(await page.$(".mt-state .bk-btn")));
  await shot(page, `${tag}-r-empty`);
  if (empty) {
    await page.click(".mt-state .bk-btn");
    await page.waitForSelector(".mt-askhost .qa", { timeout: 20000 }).catch(() => null);
    check(`${tag} кнопка пустого состояния ведёт на вкладку «Вопросы»`, !!(await page.$(".mt-askhost .qa")));
  }
  await ctx.close();
  // Ошибка сети → «Повторить» → список
  ({ ctx, page } = await context(browser, w, h, lang, "resident", true));
  let fail = true;
  await page.route(/\/api\/civic\/v2\/meetings\?/, (r) => (fail ? r.abort("failed") : r.continue()));
  await openMeetings(page);
  check(`${tag} ошибка — «что случилось» и «Повторить»`, !!(await page.$(".mt-state .bk-error")));
  await shot(page, `${tag}-r-error`);
  fail = false;
  await page.click(".mt-state .bk-btn").catch(() => null);
  await page.waitForSelector(".mt-hero", { timeout: 20000 }).catch(() => null);
  check(`${tag} «Повторить» загружает встречи`, !!(await page.$(".mt-hero")));
  check(`${tag} состояния без ошибок JS`, page.errs.length === 0, page.errs.slice(0, 3));
  await ctx.close();
}

async function staffFlow(browser, w, h, lang) {
  const tag = `${w}-${lang}`;
  const { ctx, page } = await context(browser, w, h, lang, "akimat", true);
  await openMeetings(page);
  const banner = await page.$(".mt-login");
  check(`${tag} акимат без входа — «войдите» и список встреч`, !!banner && (await page.$$(".mt-row")).length >= 3);
  if (w === 1366 && lang === "ru") await shot(page, `${tag}-a-login`);
  await login(page);
  await page.waitForSelector(".mt-lead .bk-btn--primary", { timeout: 30000 }).catch(() => null);
  check(`${tag} после входа — «Новая встреча»`, /Новая встреча|Жаңа кездесу/.test(await page.textContent(".mt-lead .bk-btn--primary").catch(() => "")));
  await shot(page, `${tag}-a-list`);
  if (w === 1366 && lang === "ru") {
    // Новая встреча
    await page.click(".mt-lead .bk-btn--primary");
    await page.waitForSelector('.mt-form [name="place"]', { timeout: 10000 });
    await sleep(1500);  // подсказки мест из поиска карты
    await page.fill('.mt-form [name="place"]', "Двор: Eco Park");
    await shot(page, `${tag}-a-new`);
    await page.click(".mt-form button[type=submit]");
    await page.waitForSelector(".mt-dhead", { timeout: 20000 }).catch(() => null);
    const created = await page.innerText(".mt-detail").catch(() => "");
    check("новая встреча создана и открыта (место из карты — «На карте»)", /Встреча акима района/.test(created) && !!(await page.$(".mt-dhead .mt-link")), created.slice(0, 120));
    await page.keyboard.press("Escape");
    await page.waitForSelector(".mt-row", { timeout: 15000 });
    // Прошедшая встреча Нуры: поручение, статус, связь
    const rows = await page.$$(".mt-row");
    let opened = false;
    for (const r of rows) { if (/Нура/.test(await r.innerText()) && /выполнено|Выполнено/.test(await r.innerText())) { await r.click(); opened = true; break; } }
    await page.waitForSelector(".mt-dhead", { timeout: 20000 }).catch(() => null);
    check("акимат: встреча с поручениями открыта", opened && !!(await page.$(".mt-order")));
    const n0 = (await page.$$(".mt-order")).length;
    check("во встрече одна главная кнопка — «Добавить поручение»", (await primaryCount(page)) === 1 && /Добавить поручение/.test(await page.textContent(".mt-lead .bk-btn--primary")));
    await page.click(".mt-lead .bk-btn--primary");
    await page.fill('.mt-form [name="text_ru"]', "Установить урны у детской площадки");
    await page.selectOption('.mt-form [name="service"]', "waste");
    // Связь — выбором из открытых обращений района (R09), без ввода номера
    await page.waitForSelector('.mt-form [name="link_pick"]', { timeout: 15000 }).catch(() => null);
    const pick = await page.$('.mt-form [name="link_pick"]');
    if (pick) {
      const value = await pick.evaluate((sel) => sel.options[1] && sel.options[1].value);
      await page.selectOption('.mt-form [name="link_pick"]', value);
      check("выбор обращения района подставил номер записи", (await page.inputValue('.mt-form [name="link_id"]')) === value, value);
    } else check("выбор обращения района", false, "нет списка");
    await shot(page, `${tag}-a-order-form`);
    await page.click(".mt-form button[type=submit]");
    await page.waitForFunction((n) => document.querySelectorAll(".mt-order").length === n + 1, n0, { timeout: 15000 }).catch(() => null);
    check("поручение добавлено", (await page.$$(".mt-order")).length === n0 + 1);
    await sleep(600);
    // место обращения — любое (первое по числу сообщивших в районе: в наборе R13 «Хан Шатыр», в демо-мире — своё)
    check("у нового поручения видно место обращения", /Обращение: [^·\n]{3,}/.test(await page.innerText(".mt-orders")));
    // Статус из строки: просроченное → «Выполнено» (снимается «просрочено»); нет просроченных (демо-мир) — любое невыполненное.
    const overdueBefore = (await page.$$(".mt-order.is-overdue")).length;
    const doneBefore = (await page.$$(".mt-order.is-done")).length;
    const sel = (await page.$(".mt-order.is-overdue .mt-select--sm")) || (await page.$(".mt-order:not(.is-done) .mt-select--sm"));
    if (sel) {
      const wasLate = overdueBefore > 0;
      await sel.selectOption("done");
      await page.waitForFunction((n) => document.querySelectorAll(".mt-order.is-done").length === n + 1, doneBefore, { timeout: 15000 }).catch(() => null);
      const overdueAfter = (await page.$$(".mt-order.is-overdue")).length, doneAfter = (await page.$$(".mt-order.is-done")).length;
      check(wasLate ? "статус из строки: «Выполнено», «просрочено» снято" : "статус из строки: «Выполнено»",
        doneAfter === doneBefore + 1 && overdueAfter === (wasLate ? overdueBefore - 1 : overdueBefore), { overdueBefore, overdueAfter, doneBefore, doneAfter });
    } else check("статус из строки", false, "нет невыполненного поручения");
    await sleep(1200);  // после смены статуса экран перерисовывается (список и карточка) — дальше только селекторы
    const LINK = ".mt-order:last-child .mt-order__tools .mt-link";
    if (await page.$(LINK)) {
      await page.click(LINK);
      await page.selectOption('.mt-linkform [name="order_link_kind"]', "project");
      // R11 R13-1: проект выбирают по названию (проекты и объекты района R06); номер на экране не пишется — он в подсказке
      await page.waitForSelector('.mt-linkform [name="order_link_pick"], .mt-linkform .mt-pick-empty', { timeout: 15000 }).catch(() => null);
      const ppick = await page.$('.mt-linkform [name="order_link_pick"]');
      const opt = ppick ? await ppick.evaluate((el) => el.options[1] && { value: el.options[1].value, text: el.options[1].text }) : null;
      if (opt) await page.selectOption('.mt-linkform [name="order_link_pick"]', opt.value);
      else await page.fill('.mt-linkform [name="order_link_id"]', "p-demo-123");
      const want = opt ? { id: opt.value, title: opt.text.split(" · ")[0] } : { id: "p-demo-123", title: null };
      await page.click(".mt-linkform button[type=submit]");
      await sleep(1200);
      const chip = await page.$(".mt-order:last-child .mt-linkchip");
      const chipText = chip ? await chip.innerText() : "";
      const chipTitle = (chip && (await chip.getAttribute("title"))) || "";
      check(want.title ? "связь с проектом: название из списка района" : "связь с проектом без названия: «Связано с проектом акимата»",
        want.title ? chipText.includes("Проект: " + want.title) : /Связано с проектом акимата/.test(chipText), chipText);
      check("номер записи — только в подсказке", !chipText.includes(want.id) && chipTitle.includes(want.id), chipTitle);
    } else check("связь с проектом", false, "нет кнопки «Связать»");
    await sizeAudit(page, `${tag} встреча (акимат)`);
    await shot(page, `${tag}-a-detail`);
    // Итог: изменить и сохранить
    await page.click('.mt-sec [data-focus="res-edit"]');
    await page.fill('.mt-form [name="result_ru"]', "Пришли 58 жителей, прозвучали 14 вопросов. Дано 6 поручений; ход работ — ниже.");
    await page.click('.mt-form button[type=submit]');
    await sleep(1200);
    check("итог встречи обновлён", /дано 6 поручений|Дано 6 поручений/i.test(await page.innerText(".mt-detail")));
    // Ближайшая встреча: вопрос на проверке → «Опубликовать»
    await page.keyboard.press("Escape");
    await page.waitForSelector(".mt-row", { timeout: 15000 });
    await page.click(".mt-rows .mt-row");  // первая строка — ближайшая встреча
    await page.waitForSelector(".mt-dhead", { timeout: 20000 }).catch(() => null);
    const pending = await page.$$(".mt-q--pending");
    if (pending.length) {
      await page.click(".mt-q--pending .bk-btn:not(.bk-btn--ghost)");
      await page.waitForFunction((n) => document.querySelectorAll(".mt-q--pending").length === n - 1, pending.length, { timeout: 15000 }).catch(() => null);
      check("акимат: вопрос к встрече опубликован из карточки встречи", (await page.$$(".mt-q--pending")).length === pending.length - 1);
    } else check("акимат: вопрос на проверке виден", false, "нет вопросов на проверке");
    await shot(page, `${tag}-a-next`);
  }
  check(`${tag} акимат без ошибок JS`, page.errs.length === 0, page.errs.slice(0, 3));
  await ctx.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  let modules = null;
  try { modules = (await (await fetch(BASE + "/api/civic/v2/modules")).json()).modules; } catch (e) { modules = null; }
  if (!modules || !modules["meetings.list"] || modules["meetings.list"].status !== "ready") {
    console.log("SKIP: в сборке нет маршрутов meetings.* (нужен патч R01 или сборка B1+)");
    process.exit(0);
  }
  const browser = await chromium.launch(fs.existsSync("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    ? { executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" } : {});
  const sizes = FULL ? [[1366, 768], [1024, 768], [375, 812]] : [[1366, 768], [375, 812]];
  try {
    for (const [w, h] of sizes) for (const lang of ["ru", "kk"]) {
      await residentFlow(browser, w, h, lang);
      if (FULL || (w === 1366 && lang === "ru")) await statesFlow(browser, w, h, lang);
      await staffFlow(browser, w, h, lang);
    }
  } catch (e) {
    check("исключение", false, String(e && e.stack || e).slice(0, 400));
  } finally {
    await browser.close();
    const fails = checks.filter((c) => c.status === "FAIL").length;
    fs.writeFileSync(path.join(OUT, "CHECKS.json"), JSON.stringify({ base: BASE, checks, shots }, null, 1));
    console.log(`R13 meetings_browser: ${checks.length - fails}/${checks.length} PASS, кадров ${shots.length}`);
    process.exit(fails ? 1 : 0);
  }
})();
