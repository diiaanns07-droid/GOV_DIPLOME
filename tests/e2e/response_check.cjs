#!/usr/bin/env node
// R10 · раунд 14 · эталон A, правило качества Linear 4 «Мгновенный отклик» (research/round-14/design/README.md):
// «действие отражается сразу (оптимистичное обновление), скелетон не дольше 150 мс, никакой мигающей перезагрузки списков».
// Владелец правила — каждый владелец своего экрана, R10 замеряет. Для каждого действия — два прогона:
//   «быстро»   — сервер сборки как есть (ответ за единицы мс);
//   «медленно» — каждый запрос /api/civic/ задержан на --delay мс (по умолчанию 900) — как телефон в плохой сети.
// Замер в странице, от pointerdown/keydown действия (performance.now()):
//   отклик   — первое изменение DOM в области экрана (MutationObserver: узлы, текст, class/aria-*; карта и значки не считаются);
//   готово   — экран в нужном состоянии (условие сценария);
//   загрузка — когда виден и когда пропал скелетон/«загрузка» ([class*=skel], [class*=shimmer], [aria-busy=true]);
//   запросы  — начало и конец запросов /api/ после действия (Resource Timing);
//   строки   — сколько строк списка видно во время перехода (мигание = падение до 0 между непустыми состояниями).
// Итоги (порог правила 150 мс):
//   «быстро»:   скелетон ≤ 150 мс (лучше — ни разу); загрузка, мелькнувшая < 100 мс, — СМОТРЕТЬ (мигание);
//   «медленно»: отклик (изменение или скелетон) ≤ 150 мс — иначе «нажал — ничего не происходит» (FAIL);
//   оптимистичные действия: результат виден раньше ответа сервера (FAIL, если только после);
//   списки: строки не исчезают все разом при обновлении (FAIL).
// Облако: программный WebGL занимает главный поток (3–9 к/с) — абсолютные мс завышены; сравнивать сборки на одной машине
// (--label, две папки) или повторить на ноутбуке. DOM-время (MutationObserver) от кадров не зависит.
//   NODE_PATH="$(npm root -g)" node tests/e2e/response_check.cjs --root <сборка> --out <папка> [--delay 900] [--only card,day] [--label имя]
// Итог: <out>/RESPONSE.json, RESPONSE.md; код 0 (отчёт; FAIL — в таблице).
"use strict";
const fs = require("fs"), path = require("path"), os = require("os");
const { chromium } = require("playwright");
const L = require("./r10_lib.cjs");
const args = L.parseArgs(process.argv.slice(2));
const ROOT = path.resolve(String(args.root || path.join(__dirname, "../..")));
const OUT = path.resolve(String(args.out || path.join(os.tmpdir(), "r10-response")));
const DELAY = Number(args.delay || 900);
const ONLY = args.only ? new Set(String(args.only).split(",")) : null;
const LABEL = String(args.label || "");
const KHAN = [71.406553, 51.131155];
const LOADING = '[class*="skel"], [class*="shimmer"], [aria-busy="true"], [class*="--loading"]';

// Запись в странице: ставится до загрузки, включается arm(), t0 — следующее нажатие/клавиша.
const RECORDER = (LOADING) => {
  const R = (window.__R = { armed: false, t0: null, cfg: null });
  try { performance.setResourceTimingBufferSize(2000); } catch (e) { /* пусто */ }
  const vis = (e) => { const r = e.getBoundingClientRect(); if (r.width < 2 || r.height < 2) return false; for (let p = e; p && p.nodeType === 1; p = p.parentElement) { const s = getComputedStyle(p); if (s.display === "none" || s.visibility === "hidden" || Number(s.opacity) < 0.05) return false; } return r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth; };
  const inMap = (n) => { const e = n && (n.nodeType === 1 ? n : n.parentElement); return !!(e && e.closest && e.closest(".maplibregl-canvas-container, .maplibregl-marker, .maplibregl-control-container, canvas")); };
  const region = () => (R.cfg && R.cfg.region ? [...document.querySelectorAll(R.cfg.region)] : null);
  const inRegion = (n) => { const e = n && (n.nodeType === 1 ? n : n.parentElement); if (!e) return false; const rs = region(); if (!rs) return true; return rs.some((r) => r.contains(e) || e.contains(r)); };
  const check = (why) => {
    if (R.t0 === null || R.done) return;
    const t = performance.now() - R.t0;
    // загрузка: видимые скелетоны в области (кнопка с aria-busy — тоже отклик «идёт»)
    const loads = [...document.querySelectorAll(LOADING)].filter((e) => !inMap(e) && inRegion(e) && vis(e));
    if (loads.length) { if (R.loadOn === null) { R.loadOn = t; R.loadWhat = loads.slice(0, 3).map((e) => (e.className && e.className.baseVal === undefined ? String(e.className) : e.tagName).split(" ").slice(0, 2).join(".")); R.loadIntervals.push([t, null]); } }
    else if (R.loadOn !== null) { R.loadIntervals[R.loadIntervals.length - 1][1] = t; R.loadOn = null; }
    if (R.cfg.rows) { const n = [...document.querySelectorAll(R.cfg.rows)].filter(vis).length; if (R.target === null) R.rowsMin = Math.min(R.rowsMin, n); R.rowsLast = n; }
    if (R.target === null) { let ok = false; try { ok = !!R.pred(); } catch (e) { ok = false; } if (ok) { R.target = t; R.targetWhy = why; } }
  };
  // Для условий «готово»: видна ли загрузка внутри элемента; закончился ли запрос /api/…re… после действия.
  R.busy = (root) => !!root && [...root.querySelectorAll(LOADING)].some(vis);
  R.apiDone = (re) => R.t0 !== null && performance.getEntriesByType("resource").some((x) => re.test(x.name) && x.startTime >= R.t0 - 5 && x.responseEnd > 0);
  // Экран раздела — самый большой видимый из «#birge-screen, .birge-screen, .birge-day».
  R.screen = () => [...document.querySelectorAll("#birge-screen, .birge-screen, .birge-day")].filter(vis).sort((a, b) => b.getBoundingClientRect().width * b.getBoundingClientRect().height - a.getBoundingClientRect().width * a.getBoundingClientRect().height)[0] || null;
  R.arm = (cfg) => { R.cfg = cfg; if (cfg.init) { try { eval("(" + cfg.init + ")")(); } catch (e) { /* пусто */ } } R.pred = eval("(" + cfg.target + ")"); R.armed = true;
    try { R.preTrue = !!R.pred(); } catch (e) { R.preTrue = false; } R.t0 = null; R.done = false; R.dom = null; R.domWhat = null; R.target = null; R.loadOn = null; R.loadIntervals = []; R.loadWhat = null;
    R.rowsBefore = cfg.rows ? [...document.querySelectorAll(cfg.rows)].filter(vis).length : null; R.rowsMin = Infinity; R.rowsLast = null; };
  const start = (e) => { if (!R.armed) return; R.armed = false; R.t0 = performance.now(); R.ev = e.type; check("t0"); };
  // Ввод не латиницей Playwright шлёт как insertText — без keydown: старт и по beforeinput.
  addEventListener("pointerdown", start, true); addEventListener("keydown", start, true); addEventListener("beforeinput", start, true);
  const mo = new MutationObserver((list) => {
    if (R.t0 === null || R.done) return;
    if (R.dom === null) for (const m of list) { const n = m.target; if (inMap(n)) continue; if (!inRegion(n) && ![...m.addedNodes].some((a) => inRegion(a))) continue;
      R.dom = performance.now() - R.t0; R.domWhat = `${m.type}${m.attributeName ? ":" + m.attributeName : ""} ${(n.nodeType === 1 ? n : n.parentElement || {}).className || ""}`.slice(0, 80); break; }
    check("dom");
  });
  const go = () => mo.observe(document, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["class", "aria-busy", "aria-pressed", "aria-selected", "aria-checked", "aria-expanded", "hidden", "disabled"] });
  go();
  setInterval(() => check("poll"), 16);
  R.collect = () => { check("end"); R.done = true; const api = performance.getEntriesByType("resource").filter((x) => /\/api\//.test(x.name) && x.startTime >= R.t0 - 5)
      .map((x) => ({ path: x.name.replace(location.origin, "").split("?")[0].slice(0, 60), start: Math.round(x.startTime - R.t0), end: Math.round(x.responseEnd - R.t0) }));
    return { ev: R.ev || null, t0: R.t0 !== null, preTrue: !!R.preTrue, dom: R.dom === null ? null : Math.round(R.dom), domWhat: R.domWhat, target: R.target === null ? null : Math.round(R.target), targetWhy: R.targetWhy || null,
      loading: R.loadIntervals.map(([a, b]) => [Math.round(a), b === null ? null : Math.round(b)]), loadWhat: R.loadWhat, rows: R.cfg.rows ? { before: R.rowsBefore, min: R.rowsMin === Infinity ? null : R.rowsMin, after: R.rowsLast } : null, api }; };
};

// ------------------------------------------------------------------------------------------------ сценарии
const vis = (page, sel) => L.firstVisible(page.locator(sel));
const openCard = async (page) => { const p = await L.showPoint(page, KHAN, 17); if (!p) return false; await L.tap(page, p.x, p.y); await L.sleep(2500); return !!(await vis(page, ".r07-card")); };
const cardAt = async (page) => { const p = await L.showPoint(page, KHAN, 17); return p ? { act: () => L.tap(page, p.x, p.y) } : null; };
const btn = async (page, re, scope) => L.firstVisible((scope || page).getByRole("button", { name: re }));
const clickOf = (b) => (b ? { act: () => b.click() } : null);
const navBtn = async (page, re) => { const b = await L.firstVisible(page.locator(".birge-nav__item, .birge-header button, header button").filter({ hasText: re })); return b; };
// Сценарий: id, роль, имя, режим, вход сотрудника, область, условие «готово», строки, оптимистичное?, prep → {act}.
const SC = [
  { id: "card", owner: "R07", name: "Карточка места по нажатию на значок", mode: "resident", region: "#civic-panel, .r07-card, [class*=r07-place]",
    target: "() => { const c = document.querySelector('.r07-card'); return !!c && c.getBoundingClientRect().width > 0 && /Хан Шатыр/.test(c.innerText) && !window.__R.busy(c); }",
    prep: cardAt },
  { id: "period", owner: "R07", name: "«Горячие места»: период 30 → 90 дней", mode: "akimat", region: "#civic-panel", rows: ".r07-list > li",
    target: "() => { const b = [...document.querySelectorAll('button')].find((x) => /^90 дней$/.test(x.innerText.trim())); const on = b && (b.getAttribute('aria-pressed') === 'true' || b.getAttribute('aria-checked') === 'true' || b.getAttribute('aria-selected') === 'true' || /(^|\\s)(on|is-on|active|is-active|bk-seg__btn--on|r07-seg__btn--on)(\\s|$)/.test(b.className)); const l = document.querySelector('.r07-list'); return !!on && !!l && window.__R.apiDone(/\\/heat/) && !window.__R.busy(document.querySelector('#civic-panel')); }",
    prep: async (page) => { const b = await btn(page, /^90 дней$/); if (!b) return null; await page.evaluate(() => { const l = document.querySelector(".r07-list"); window.__R.before = l ? l.innerText : ""; }); return clickOf(b); } },
  { id: "day", owner: "R08", name: "«Картина дня» из шапки", mode: "akimat", staff: true, region: "#birge-screen, .birge-screen, .akim",
    target: "() => { const s = window.__R.screen(); return !!s && s.getBoundingClientRect().width > 0 && /Картина дня/.test(s.innerText) && /\\d/.test(s.innerText) && !window.__R.busy(s); }",
    prep: async (page) => clickOf(await navBtn(page, /^\s*Картина дня\s*$/)) },
  { id: "complaints", owner: "R09", name: "«Обращения» сотрудника из шапки", mode: "akimat", staff: true, region: "#birge-screen, .birge-screen", rows: "#birge-screen li, #birge-screen [role=row], #birge-screen .bc-row, #birge-screen [class*=row]",
    target: "() => { const s = window.__R.screen(); if (!s || s.getBoundingClientRect().width < 10 || !/Обращения/.test(s.innerText)) return false; const rows = [...s.querySelectorAll('li, [role=row], [class*=row], article')].filter((e) => e.getBoundingClientRect().height >= 36 && /\\d/.test(e.innerText)); return rows.length >= 2 && !window.__R.busy(s); }",
    prep: async (page) => clickOf(await navBtn(page, /^\s*Обращения\s*$/)) },
  { id: "take", fresh: true, owner: "R07+R09", name: "«Взять в работу» в карточке места (сотрудник)", mode: "akimat", staff: true, optimistic: true, region: "#civic-panel, .r07-card",
    target: "() => { const c = document.querySelector('.r07-card'); return !!c && /В работе/.test(c.innerText); }",
    prep: async (page) => { if (!(await openCard(page))) return null; return clickOf(await btn(page, /^\s*Взять в работу\s*$/, page.locator(".r07-card"))); } },
  { id: "metoo", fresh: true, owner: "R07", name: "«Я тоже» в карточке места (житель)", mode: "resident", optimistic: true, region: "#civic-panel, .r07-card",
    target: "() => { const c = document.querySelector('.r07-card'); if (!c) return false; const b = [...c.querySelectorAll('button')].find((x) => /Я тоже|Вы с нами|Вы уже/.test(x.innerText)); const toast = [...document.querySelectorAll('[role=status], [class*=toast]')].some((e) => /учтён|с нами/.test(e.textContent)); return toast || /Вы с нами|Вы уже отметились/.test(c.innerText) || (!!b && b.getAttribute('aria-pressed') === 'true'); }",
    prep: async (page) => { if (!(await openCard(page))) return null; return clickOf(await btn(page, /^\s*Я тоже\s*$/, page.locator(".r07-card"))); } },
  { id: "projects", owner: "R06", name: "«Проекты и идеи» сотрудника из шапки", mode: "akimat", staff: true, region: "#birge-screen, .birge-screen", rows: "#birge-screen article",
    target: "() => { const s = window.__R.screen(); return !!s && [...s.querySelectorAll('article')].filter((e) => e.getBoundingClientRect().height > 40).length >= 1 && !window.__R.busy(s); }",
    prep: async (page) => clickOf(await navBtn(page, /^\s*Проекты( и идеи)?\s*$/)) },
  { id: "vote", fresh: true, owner: "R06", name: "«Поддержать» идею (житель)", mode: "resident", optimistic: true, region: "#birge-screen, .birge-screen, .ri-card",
    target: "() => { const b = window.__R.voteBtn; if (!b) return false; const card = b.closest('article') || b.parentElement; return b.getAttribute('aria-pressed') === 'true' || (card && card.innerText.replace(/\\s+/g, ' ') !== window.__R.before.replace(/\\s+/g, ' ')); }",
    prep: async (page) => {
      let ok = !!(await navBtn(page, /^\s*Идеи\s*$/));
      if (ok) await (await navBtn(page, /^\s*Идеи\s*$/)).click();
      else { const more = await btn(page, /^\s*Ещё\s*$/); if (!more) return null; await more.click(); await L.sleep(700); const it = await L.firstVisible(page.getByRole("menuitem", { name: /^\s*Идеи\s*$/ }).or(page.getByRole("button", { name: /^\s*Идеи\s*$/ }))); if (!it) return null; await it.click(); }
      await L.sleep(3000);
      const v = await btn(page, /^\s*Поддержать\s*$/); if (!v) return null;
      await v.evaluate((b) => { window.__R.voteBtn = b; const c = b.closest("article") || b.parentElement; window.__R.before = c ? c.innerText : ""; });
      return clickOf(v);
    } },
  { id: "mine", owner: "R09", name: "«Мои обращения» — повторное открытие", mode: "resident", region: "#birge-complaint-root, .bc-panel, #birge-screen",
    target: "() => { const s = [...document.querySelectorAll('.bc-panel, #birge-screen')].find((e) => e.getBoundingClientRect().width > 0 && /Мои обращения/.test(e.innerText)); return !!s && !window.__R.busy(s) && !/Загружаем|Жүктеп/.test(s.innerText); }",
    prep: async (page) => { const a = await navBtn(page, /^\s*Мои обращения\s*$/); if (!a) return null; await a.click(); await L.sleep(2500); await page.keyboard.press("Escape"); await L.sleep(800);
      const m = await navBtn(page, /^\s*Карта\s*$/); if (m) { await m.click(); await L.sleep(1200); } return clickOf(await navBtn(page, /^\s*Мои обращения\s*$/)); } },
  { id: "search", owner: "R01", name: "Поиск: подсказки с первой буквы («Х»)", mode: "akimat", region: "body",
    init: "() => { window.__R.opts = () => [...document.querySelectorAll('[role=listbox] [role=option], [class*=suggest] li, [class*=suggest] button, .civic-explore-row, .civic-explore-list li')].filter((e) => e.getBoundingClientRect().height > 10).length; window.__R.n0 = window.__R.opts(); }",
    target: "() => window.__R.opts() > window.__R.n0",
    prep: async (page) => { const i = await L.firstVisible(page.locator("input[placeholder*='Улица'], input[placeholder*='Поиск'], input[placeholder*='Найти']")); if (!i) return null; await i.click(); await L.sleep(500);
      return { act: () => page.keyboard.type("Х") }; } },
];

async function run(browser, server, sc, slow) {
  const size = sc.size || [1366, 768], mobile = size[0] < 761;
  const ctx = await browser.newContext({ viewport: { width: size[0], height: size[1] }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1, locale: "ru-RU" });
  await ctx.addInitScript((m) => { try { if (!sessionStorage.getItem("r10")) { localStorage.setItem("birge.lang", "ru"); localStorage.setItem("birge.mode", m); sessionStorage.setItem("r10", "1"); } } catch (e) { /* пусто */ } }, sc.mode);
  await ctx.addInitScript(RECORDER, LOADING);
  await L.glassMode(ctx, "keep");
  const state = { delay: 0 };
  await ctx.route("**/api/civic/**", async (route) => { const d = state.delay; if (d) await L.sleep(d); await route.continue().catch(() => null); });
  if (sc.staff && server.staff && server.staff.user) await ctx.request.post(server.base + "api/civic/v1/session/login", { data: { username: server.staff.user, password: server.staff.pass } }).catch(() => null);
  const page = await ctx.newPage();
  try {
    await page.goto(server.base); await page.waitForFunction(() => document.readyState === "complete" && document.body.innerText.length > 40, null, { timeout: 40000 }).catch(() => null);
    await L.sleep(4500);
    const p = await sc.prep(page);
    if (!p) return { reached: false };
    await L.sleep(400);
    await page.evaluate((cfg) => window.__R.arm(cfg), { region: sc.region || null, target: sc.target, rows: sc.rows || null, init: sc.init || null });
    state.delay = slow ? DELAY : 0;
    await p.act();
    const until = Date.now() + (slow ? DELAY : 0) + 6000;
    while (Date.now() < until) { const done = await page.evaluate(() => window.__R.target !== null).catch(() => false); if (done) break; await L.sleep(100); }
    await L.sleep(slow ? DELAY + 600 : 700);
    const r = await page.evaluate(() => window.__R.collect());
    state.delay = 0;
    return { reached: true, ...r };
  } catch (e) { return { reached: false, error: String(e).slice(0, 200) }; }
  finally { await ctx.close(); }
}

function verdicts(sc, fast, slow) {
  const v = [];
  const add = (name, status, detail) => v.push({ name, status, detail });
  if (!fast.reached || !slow.reached) { add("сценарий открылся", "NOT_RUN", fast.error || slow.error || "нет кнопки/состояния"); return v; }
  if (!fast.t0) { add("сценарий открылся", "NOT_RUN", "действие не дошло до страницы (нет pointerdown/keydown)"); return v; }
  if (fast.preTrue || slow.preTrue) { add("сценарий открылся", "NOT_RUN", "условие «готово» выполнялось ещё до действия — замер не годен"); return v; }
  // быстро: готово и скелетон
  const fl = fast.loading.map(([a, b]) => (b === null ? Infinity : b - a));
  add("быстро: готово", fast.target === null ? "FAIL" : fast.target <= 150 ? "PASS" : fast.target <= 400 ? "СМОТРЕТЬ" : "FAIL", fast.target === null ? "состояние не наступило" : `${fast.target} мс`);
  if (fl.length) {
    const longest = Math.max(...fl);
    // «Идёт» на самой кнопке (aria-busy, спиннер) — не скелетон экрана: до 300 мс — СМОТРЕТЬ, дольше — FAIL.
    const onButton = (fast.loadWhat || []).length && fast.loadWhat.every((w) => /btn|button|support/i.test(w));
    add("быстро: скелетон ≤ 150 мс", longest <= 150 ? (longest < 100 && !onButton ? "СМОТРЕТЬ" : "PASS") : onButton && longest <= 300 ? "СМОТРЕТЬ" : "FAIL",
      `${fast.loading.map(([a, b]) => `${a}–${b === null ? "…" : b}`).join(", ")} мс${longest < 100 && !onButton ? " — мелькнул (мигание)" : onButton ? " — «идёт» на кнопке" : ""} · ${(fast.loadWhat || []).join(" ")}`);
  } else add("быстро: скелетон ≤ 150 мс", "PASS", "скелетона нет — сразу содержимое");
  // медленно: отклик
  const firstSlow = [slow.dom, slow.loading.length ? slow.loading[0][0] : null].filter((x) => x !== null);
  const fb = firstSlow.length ? Math.min(...firstSlow) : null;
  add(`медленно (+${DELAY} мс): отклик ≤ 150 мс`, fb === null ? "FAIL" : fb <= 150 ? "PASS" : fb <= 300 ? "СМОТРЕТЬ" : "FAIL",
    fb === null ? "ничего не изменилось" : `первое изменение ${slow.dom ?? "—"} мс${slow.loading.length ? `, скелетон с ${slow.loading[0][0]} мс` : ", скелетона нет"}${slow.target !== null ? `, готово ${slow.target} мс` : ", не готово"}`);
  if (sc.optimistic) {
    const ends = slow.api.map((x) => x.end).filter((x) => x > 0), firstEnd = ends.length ? Math.min(...ends) : null;
    add("оптимистично: результат раньше ответа сервера", slow.target === null ? "FAIL" : firstEnd === null || slow.target < firstEnd ? "PASS" : "FAIL",
      `результат ${slow.target ?? "—"} мс, первый ответ ${firstEnd ?? "нет запроса"} мс${slow.api.length ? " · " + slow.api.slice(0, 3).map((x) => `${x.path} ${x.start}–${x.end}`).join("; ") : ""}`);
  }
  for (const [k, r] of [["быстро", fast], ["медленно", slow]]) if (r.rows && r.rows.before !== null) {
    const flick = r.rows.before > 0 && r.rows.min === 0 && (r.rows.after || 0) > 0;
    add(`${k}: список не мигает`, flick ? "FAIL" : "PASS", `строк до ${r.rows.before}, минимум ${r.rows.min}, после ${r.rows.after}`);
  }
  return v;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const server = await L.startServer(ROOT);
  const browser = await chromium.launch();
  const rows = [];
  try {
    for (const sc of SC) {
      if (ONLY && !ONLY.has(sc.id)) continue;
      // Действие меняет данные («Взять в работу», «Я тоже», «Поддержать») — каждому прогону свой сервер (своя база).
      const own = async (slowRun) => { if (!sc.fresh) return run(browser, server, sc, slowRun); const sv = await L.startServer(ROOT); try { return await run(browser, sv, sc, slowRun); } finally { await sv.stop(); } };
      const fast = await own(false), slow = await own(true);
      const v = verdicts(sc, fast, slow);
      rows.push({ id: sc.id, owner: sc.owner, name: sc.name, fast, slow, verdicts: v });
      console.log(`${sc.id.padEnd(10)} ${sc.owner.padEnd(8)} ` + v.map((x) => `${x.status}:${x.name}`).join(" | "));
    }
  } finally { await browser.close(); await server.stop(); }
  const counts = {}; rows.forEach((r) => r.verdicts.forEach((x) => (counts[x.status] = (counts[x.status] || 0) + 1)));
  const sha = L.buildSha(ROOT);
  fs.writeFileSync(path.join(OUT, "RESPONSE.json"), JSON.stringify({ sha, label: LABEL, delay: DELAY, when: new Date().toISOString(), counts, rows }, null, 1));
  const md = [`# R10 · правило 4 «мгновенный отклик» · ${LABEL || sha}`, "", `Сборка \`${sha}\`; «медленно» — каждый запрос /api/civic/ задержан на ${DELAY} мс. Итого: ${Object.entries(counts).map(([k, n]) => `${k} ${n}`).join(" · ")}.`,
    "Время — от нажатия (pointerdown/keydown), мс; облако с программным WebGL — абсолютные числа завышены, сравнивать сборки на одной машине.", "",
    "| Действие | Роль | Быстро: готово | Быстро: скелетон | Медленно: отклик / готово | Итоги |", "|---|---|---:|---|---|---|"];
  for (const r of rows) {
    const f = r.fast, s = r.slow;
    md.push(`| ${r.name} | ${r.owner} | ${f.reached ? f.target ?? "—" : "не открылось"} | ${f.reached ? (f.loading.length ? f.loading.map(([a, b]) => `${a}–${b ?? "…"}`).join(", ") : "нет") : ""} | ${s.reached ? `${s.dom ?? "—"} / ${s.target ?? "—"}` : ""} | ${r.verdicts.map((x) => `**${x.status}** ${x.name}${x.detail ? ` (${String(x.detail).replace(/\|/g, "/")})` : ""}`).join("<br>")} |`);
  }
  md.push("", "Правило: «быстро» — скелетон не дольше 150 мс (лучше — вовсе нет), «медленно» — отклик в пределах 150 мс (изменение или скелетон),",
    "оптимистичные действия («Взять в работу», «Я тоже», «Поддержать») показывают результат до ответа сервера, списки не пустеют при обновлении.");
  fs.writeFileSync(path.join(OUT, "RESPONSE.md"), md.join("\n") + "\n");
  console.log("ИТОГ:", counts, "→", OUT);
})().catch((e) => { console.error(e); process.exit(2); });
