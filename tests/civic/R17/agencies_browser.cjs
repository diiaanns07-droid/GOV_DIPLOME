// R17 · «Штаб ведомств» и кризисный штаб в оболочке Birge R01: 1366 / 1024 / 375 × ru / kk, сцены 8 (табло) и 9 (кризис).
// Запускает свой сервер (CIVIC_DEMO=1, временная база), создаёт сотрудника, проходит пути и делает кадры.
//
//   BIRGE_REPO=<сборка с patch R01_agencies_routes_assets.patch> NODE_PATH=$(npm root -g) \
//     node tests/civic/R17/agencies_browser.cjs <папка_кадров>
//   BASE=http://127.0.0.1:8655 … — проверить уже запущенный стенд (сотрудник operator / пароль из STAFF_PASS).
//
// Проверяет: 20 служб на одном экране 1366 × 768 без прокрутки; KPI = числа API; вкладки Табло · Совместные ·
// Передачи · Кризис; раскрытие строки службы; нет прокрутки вбок; нет непереведённых ключей; кризис: задача → прогресс,
// обновление ҚАЗ+РУС → лента, новый кризис из шаблона → закрыть с итогом; житель зоны: баннер и карточка ҚАЗ/РУС без
// внутренних задач; без входа — просьба войти; слой «Кризис» на карте; prefers-reduced-motion — без пульса; нет ошибок JS.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(process.env.BIRGE_REPO || path.join(__dirname, "../../.."));
const OUT = path.resolve(process.argv[2] || "r17-out");
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet|ERR_TUNNEL|net::ERR/i;
const STAFF = { user: process.env.STAFF_USER || "r17.check", pass: process.env.STAFF_PASS || "r17-check-pass-2026" };
const DEVICE = "d-r17browsercheck0001";
const checks = [];
const check = (name, ok, detail) => {
  checks.push({ name, status: ok ? "PASS" : "FAIL", detail: detail ?? null });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail != null ? " — " + JSON.stringify(detail).slice(0, 300) : ""));
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  delete env.CIVIC_DEMO_WORLD;
  const run = (args, input) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: REPO, env, input, stdio: [input ? "pipe" : "ignore", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  run(`create-editor ${STAFF.user} --password-stdin`, STAFF.pass + "\n");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

async function newPage(ctx) {
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !NOISE.test(m.text())) page.errs.push(m.text()); });
  return page;
}
async function login(page, base) {
  await page.goto(base + "/");
  await page.evaluate(async (s) => {
    await fetch("/api/civic/v1/session/login", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: s.user, password: s.pass }) });
  }, STAFF);
}
// Язык — через ключ хранилища i18n R11 (setLang до готовности словарей перезаписывался при старте страницы).
async function setup(page, { lang, mode, tab }) {
  await page.evaluate(async ({ lang, mode, tab }) => {
    localStorage.setItem("birge.mode", mode);
    sessionStorage.setItem("birge.agencies", JSON.stringify({ tab: tab || "board", days: 30, district: "" }));
    const I = window.BirgeI18n;
    if (I && I.STORAGE_KEY) localStorage.setItem(I.STORAGE_KEY, lang);
    if (I && I.ready) await I.ready;
    if (I) I.setLang(lang);
  }, { lang, mode, tab });
}
// Прокрутки вбок нет: страница не шире окна, и в экране R17 ничто не вылезает за край — кроме содержимого блоков
// с собственной прокруткой (вкладки, список дворов, шкала «Календаря работ» R12 .wcal-tl с overflow-x: auto).
const noSideScroll = (page) => page.evaluate(() => {
  const clipped = (e) => { for (let n = e.parentElement; n && !n.classList.contains("ag"); n = n.parentElement) {
    if (/^(auto|scroll)$/.test(getComputedStyle(n).overflowX)) return true; } return false; };   // hidden — не прощаем
  return document.documentElement.scrollWidth <= innerWidth + 1
    && [...document.querySelectorAll(".ag *")].every((e) => e.getBoundingClientRect().right <= innerWidth + 1
      || e.closest(".bk-tabs, .ag-yards, .ag-scroll") || clipped(e));
});
// Как проверка R10 (tests/e2e/ux_lib.cjs uiScreen): текст мельче 13 px и зоны нажатия < 40 px — внутри экрана R17.
// Строки табло — role="row" (не кнопки): 26 px на компьютере по замыслу (R10 B-110: «строки не трогать»).
const uxProbe = (page) => page.evaluate(() => {
  // Текст только для диктора (.bk-sr-only R11: 1×1 px, clip) человек не видит — не оцениваем (как R10).
  const srOnly = (e) => { const r = e.getBoundingClientRect(); if (r.width <= 1 || r.height <= 1) return true;
    for (let n = e; n && n.nodeType === 1; n = n.parentElement) {
      if (n.classList && (n.classList.contains("bk-sr-only") || n.classList.contains("sr-only"))) return true;
      const cs = getComputedStyle(n);
      if (cs.clip === "rect(0px, 0px, 0px, 0px)" || /inset\(50%\)/.test(cs.clipPath || "")) return true;
    }
    return false; };
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0"
      && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth && !srOnly(e); };
  const roots = [...document.querySelectorAll(".ag, .ag-banner, .ag-public")];
  const inside = (e) => roots.some((r) => r.contains(e)) && !e.closest(".wcal, [data-calendar]");
  const tiny = [];
  for (const el of document.querySelectorAll(".ag *, .ag-banner *, .ag-public *")) {
    if (!inside(el) || !vis(el) || el.children.length || !el.textContent.trim() || el.closest("svg")) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (fs && fs < 13) tiny.push(`${fs}px «${el.textContent.trim().slice(0, 24)}»`);
  }
  const small = [...document.querySelectorAll("button, a[href], [role=button], input, select, summary, textarea")]
    .filter((e) => inside(e) && vis(e))
    .map((e) => { const box = (/^(checkbox|radio)$/.test(e.type) && e.closest("label")) || e; const r = box.getBoundingClientRect();
      return { h: Math.round(r.height), w: Math.round(r.width), t: (box.innerText || e.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 24) }; })
    .filter((t) => t.h < 40 || t.w < 40);
  // Контраст ≥ 4,5:1 (крупный ≥ 24 px или ≥ 18,66 px полужирный — 3:1), фон — первый непрозрачный слой вверх (как R10).
  const rgba = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const v = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);
    return [v[0], v[1], v[2], v.length > 3 ? v[3] : 1]; };
  const lum = (c) => { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const over = (top, bot) => { const a = top[3]; return [0, 1, 2].map((i) => top[i] * a + bot[i] * (1 - a)).concat(1); };
  const bgOf = (e) => {
    const layers = [];
    for (let n = e; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (Number(cs.opacity) < 0.99 || (cs.backgroundImage && cs.backgroundImage !== "none")) return null;
      const c = rgba(cs.backgroundColor);
      if (c && c[3] > 0) { layers.push(c); if (c[3] >= 0.99) break; }
      if (n === document.documentElement && (!c || c[3] < 0.99)) layers.push([255, 255, 255, 1]);
    }
    if (!layers.length) return null;
    let col = layers[layers.length - 1]; if (col[3] < 0.99) col = over(col, [255, 255, 255, 1]);
    for (let i = layers.length - 2; i >= 0; i--) col = over(layers[i], col);
    return col;
  };
  const low = [];
  for (const el of document.querySelectorAll(".ag *, .ag-banner *, .ag-public *")) {
    const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").trim();
    if (own.length < 2 || !inside(el) || !vis(el) || el.closest("svg, [disabled], [aria-disabled=true]")) continue;
    const cs = getComputedStyle(el), fg = rgba(cs.color), bg = bgOf(el);
    if (!fg || !bg) continue;
    const f = fg[3] < 0.99 ? over(fg, bg) : fg;
    const L1 = lum(f), L2 = lum(bg), ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const fs = parseFloat(cs.fontSize), need = fs >= 24 || (Number(cs.fontWeight) >= 700 && fs >= 18.66) ? 3 : 4.5;
    if (ratio < need) low.push(`${ratio.toFixed(2)}:1 «${own.slice(0, 24)}»`);
  }
  return { tiny: tiny.slice(0, 6), tinyN: tiny.length, small: small.slice(0, 6), smallN: small.length, low: low.slice(0, 6), lowN: low.length };
});
const rawKeys = (page) => page.evaluate(() => [...document.querySelectorAll(".ag, .ag-banner, .ag-public")]
  .map((e) => e.innerText).join("\n").match(/\b(agencies|crisis|common|shell)\.[a-z_.]+/g) || []);
const openAgencies = async (page, base, tab) => {
  await page.goto(base + "/#agencies");
  await page.waitForSelector(".ag", { timeout: 40000 });
  if (tab === "crisis") await page.waitForSelector(".ag-crisis, .ag-empty", { timeout: 20000 });
  else if (tab === "board") await page.waitForSelector(".ag-row", { timeout: 20000 });
  else await page.waitForSelector(".ag-list, .ag-empty", { timeout: 20000 });
  await page.waitForTimeout(500);
};

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  let srv = null, base = process.env.BASE;
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r17-"));
  if (!base) {
    const port = await freePort();
    srv = await startServer(port, path.join(tmp, "civic.sqlite3"));
    base = `http://127.0.0.1:${port}`;
  }
  const browser = await chromium.launch();
  try {
    const modules = await (await fetch(base + "/api/civic/v2/modules")).json();
    const r17 = Object.entries(modules.modules || {}).filter(([k]) => /^(agencies|incidents)\./.test(k));
    check("шлюз: 11 маршрутов R17 подключены", r17.length === 11 && r17.every(([, v]) => v.status === "ready"), r17.map(([k, v]) => k + ":" + v.status));

    // ---------------------------------------------------------------- без входа
    {
      const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
      const page = await newPage(ctx);
      await page.goto(base + "/");
      await setup(page, { lang: "ru", mode: "akimat", tab: "board" });
      await page.goto(base + "/#agencies");
      await page.waitForSelector(".ag", { timeout: 40000 });
      await page.waitForTimeout(1200);
      const txt = await page.evaluate(() => document.querySelector(".ag").innerText);
      check("без входа: просьба войти, табло не показано", !(await page.$(".ag-row")) && /Войти|сотрудник/i.test(txt), txt.slice(0, 120));
      await page.screenshot({ path: `${OUT}/login-1366-ru.png` });
      check("без входа: нет ошибок JS", page.errs.length === 0, page.errs);
      await ctx.close();
    }

    // ---------------------------------------------------------------- табло: 3 ширины × 2 языка
    const apiBoard = await (async () => {
      const ctx = await browser.newContext();
      const page = await newPage(ctx);
      await login(page, base);
      // Шлюз R01 раунда 15: «сотрудник» = сессия + CSRF и для чтения — токен из GET /api/civic/v1/session.
      // R16 в сборке: сотрудник «Поддержал» дело жителей вывозом мусора (тот же маршрут, что кнопка R16) →
      // задача оператору вывоза на табло R17.
      const r16 = (modules.modules || {})["together.initiatives.support"];
      const body = await page.evaluate(async (withR16) => {
        const sess = await (await fetch("/api/civic/v1/session", { credentials: "same-origin" })).json();
        const d = sess && sess.data ? sess.data : sess;
        const headers = { "X-CSRF-Token": d.csrf_token || "" };
        if (withR16) {
          const list = await (await fetch("/api/civic/v2/together/initiatives?status=published", { credentials: "same-origin", headers })).json();
          const item = ((list && list.items) || []).filter((x) => !(x.support && x.support.by_akimat))[0];
          if (item) await fetch(`/api/civic/v2/together/initiatives/${encodeURIComponent(item.id)}/support`, { method: "POST",
            credentials: "same-origin", headers: { ...headers, "Content-Type": "application/json" },
            body: JSON.stringify({ inventory: true, pickup_service: "waste", note: "Мешки и вывоз к 14:00" }) });
        }
        return (await fetch("/api/civic/v2/agencies/board?days=30", { credentials: "same-origin", headers })).json();
      }, !!(r16 && r16.status === "ready"));
      await ctx.close();
      return body;
    })();
    for (const [w, h] of [[1366, 768], [1024, 768], [375, 812]]) {
      for (const lang of ["ru", "kk"]) {
        const tag = `${w}-${lang}`;
        const ctx = await browser.newContext({ viewport: { width: w, height: h } });
        const page = await newPage(ctx);
        await login(page, base);
        await setup(page, { lang, mode: "akimat", tab: "board" });
        await openAgencies(page, base, "board");
        const info = await page.evaluate(() => {
          const rows = [...document.querySelectorAll(".ag-row")];
          const last = rows[rows.length - 1];
          const kpi = document.querySelector(".ag-kpi__value");
          // Видимая часть — до края прокручиваемой панели оболочки (а не окна): строка под краем листа не видна.
          let sc = last; while (sc && sc !== document.body) { const o = getComputedStyle(sc).overflowY; if (o === "auto" || o === "scroll") break; sc = sc.parentElement; }
          const edge = sc && sc !== document.body ? Math.min(innerHeight, sc.getBoundingClientRect().top + sc.clientHeight) : innerHeight;
          return { rows: rows.length, lastBottom: last ? last.getBoundingClientRect().bottom : 0, inner: Math.round(edge),
            kpiOpen: kpi ? kpi.textContent.replace(/\s/g, "") : null };
        });
        check(`${tag}: 20 служб в табло`, info.rows === 20, info.rows);
        if (w === 1366) check(`${tag}: все 20 служб на одном экране без прокрутки`, info.lastBottom <= info.inner, info);
        check(`${tag}: KPI «открыто» = API`, info.kpiOpen === String(apiBoard.totals.open), [info.kpiOpen, apiBoard.totals.open]);
        if (w !== 375) {
          // R11 R17-3: на 1366 название службы целиком в строку, на 1024 — не больше двух строк, без обрезки.
          const cutNames = await page.evaluate(() => [...document.querySelectorAll(".ag-row .ag-svc__name")]
            .filter((e) => e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1).map((e) => e.textContent));
          check(`${tag}: названия служб не обрезаны`, cutNames.length === 0, cutNames);
        }
        // Аудит R10 (visual_audit, «вкладки целиком»): вкладка не уходит за край полосы — на телефоне вкладки в две строки.
        const tabsCut = await page.evaluate(() => [...document.querySelectorAll(".ag [role=tab]")].filter((t) => {
          const r = t.getBoundingClientRect(); let edge = { left: 0, right: innerWidth };
          for (let n = t.parentElement; n && n !== document.body; n = n.parentElement) {
            if (/(auto|scroll|hidden|clip)/.test(getComputedStyle(n).overflowX)) { const pr = n.getBoundingClientRect(); edge = { left: pr.left, right: pr.right }; break; }
          }
          return r.width > 0 && (r.right > edge.right + 1 || r.left < edge.left - 1);
        }).map((t) => t.innerText.trim()));
        check(`${tag}: вкладки штаба видны целиком`, tabsCut.length === 0, tabsCut);
        // Цель п. 10 — 44 px: вкладки и период «7 · 30 · 90» (рамка кнопки, как меряет аудит R10).
        const under44 = await page.evaluate(() => [...document.querySelectorAll(".ag [role=tab], .ag-seg > button")]
          .map((e) => e.getBoundingClientRect()).filter((r) => r.width > 0 && (r.width < 44 || r.height < 44)).map((r) => Math.round(r.width) + "×" + Math.round(r.height)));
        check(`${tag}: вкладки и период — зона нажатия 44 px`, under44.length === 0, under44);
        check(`${tag}: нет прокрутки вбок`, await noSideScroll(page));
        check(`${tag}: нет непереведённых ключей`, (await rawKeys(page)).length === 0, await rawKeys(page));
        const ux = await uxProbe(page);
        check(`${tag}: шрифт ≥ 13 px`, ux.tinyN === 0, ux.tiny);
        check(`${tag}: зоны нажатия ≥ 40 px`, ux.smallN === 0, ux.small);
        check(`${tag}: контраст текста ≥ 4,5:1`, ux.lowN === 0, ux.low);
        if (apiBoard.totals && apiBoard.totals.overdue_fix != null) {
          const two = await page.evaluate(() => [...document.querySelectorAll(".ag-kpi__label")].map((e) => e.textContent));
          check(`${tag}: два «просрочено» — разные подписи (ответ R09 и исправление R08)`, two.length === 4 && new Set(two).size === 4, two);
          const cutKpi = await page.evaluate(() => [...document.querySelectorAll(".ag-kpi__label")]
            .filter((e) => e.scrollHeight > e.clientHeight + 1 || e.scrollWidth > e.clientWidth + 1).map((e) => e.textContent));
          check(`${tag}: подписи плиток не обрезаны`, cutKpi.length === 0, cutKpi);
        }
        await page.screenshot({ path: `${OUT}/board-${tag}.png` });
        // раскрыть самую загруженную службу
        await page.click(".ag-row");
        await page.waitForSelector(".ag-detail .ag-item, .ag-detail .ag-note", { timeout: 15000 });
        check(`${tag}: строка службы раскрывается списком обращений`, !!(await page.$(".ag-detail")));
        if (w !== 1024) await page.screenshot({ path: `${OUT}/board-open-${tag}.png` });
        // Вывоз после дел жителей (R16 pickups): отметка в строке службы и список в раскрытой строке.
        const pick = Object.entries(apiBoard.pickups || {}).filter(([, n]) => n > 0)[0];
        if (!pick) {
          if (w === 1366 && lang === "ru") checks.push({ name: "вывоз после дел жителей (R16)", status: "NOT_RUN", detail: "R16 нет в сборке — pickups пусто" });
        } else if (w !== 1024) {
          const mark = await page.$(`.ag-row[data-service="${pick[0]}"] .ag-svc__extra`);
          check(`${tag}: у службы ${pick[0]} отметка вывоза (${pick[1]})`, !!mark && (await mark.innerText()).trim() === String(pick[1]));
          await page.click(`.ag-row[data-service="${pick[0]}"]`);
          await page.waitForSelector('[data-list="pickups"] .ag-item', { timeout: 15000 });
          check(`${tag}: раскрытая строка — «Вывоз после дел жителей»`, (await page.$$('[data-list="pickups"] .ag-item')).length === pick[1]);
          check(`${tag}: вывоз без прокрутки вбок`, await noSideScroll(page));
          await page.screenshot({ path: `${OUT}/board-pickups-${tag}.png` });
        }
        for (const tab of ["joint", "handoffs", "crisis"]) {
          await page.click(`[data-tab=${tab}]`);
          await page.waitForSelector(tab === "crisis" ? ".ag-crisis, .ag-empty" : ".ag-list, .ag-empty", { timeout: 20000 });
          await page.waitForTimeout(500);
          check(`${tag}: вкладка ${tab} без прокрутки вбок`, await noSideScroll(page));
          check(`${tag}: вкладка ${tab} без непереведённых ключей`, (await rawKeys(page)).length === 0, await rawKeys(page));
          if (w === 375 && tab !== "crisis") {
            // R11 круг 12 (R17-6): на телефоне заголовок строки и причина передачи — целиком (2–3 строки), не многоточием.
            const cutRows = await page.evaluate(() => [...document.querySelectorAll(".ag-lrow__title, .ag-quote")]
              .filter((e) => e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1).map((e) => e.textContent.slice(0, 60)));
            check(`${tag}: вкладка ${tab}: заголовки строк и причины передач не обрезаны`, cutRows.length === 0, cutRows);
          }
          const uxTab = await uxProbe(page);
          check(`${tag}: вкладка ${tab}: шрифт ≥ 13 px, зоны нажатия ≥ 40 px, контраст ≥ 4,5:1`, uxTab.tinyN === 0 && uxTab.smallN === 0 && uxTab.lowN === 0, uxTab);
          await page.screenshot({ path: `${OUT}/${tab}-${tag}.png` });
        }
        // «Календарь работ» (R12 embedded, IA_ROUND15 §5.4) — если модуль R12 в сборке: открылся и не просит войти.
        if (await page.$("[data-tab=calendar]")) {
          await page.click("[data-tab=calendar]");
          await page.waitForSelector("[data-calendar] *, .ag-empty", { timeout: 20000 }).catch(() => null);
          await page.waitForTimeout(2500);
          const cal = await page.evaluate(() => {
            const box = document.querySelector("[data-calendar]");
            const text = box ? box.innerText : "";
            return { mounted: !!box, chars: text.length, login: /Войдите|Кіріңіз|staff_required/i.test(text),
              mains: [...document.querySelectorAll(".ag .bk-btn--primary")].filter((b) => b.offsetParent).map((b) => b.innerText.trim()) };
          });
          check(`${tag}: вкладка «Календарь работ» открылась без просьбы войти`, cal.mounted && !cal.login, cal);
          check(`${tag}: в календаре одна главная кнопка (R10 B-115)`, cal.mains.length <= 1, cal.mains);
          check(`${tag}: вкладка calendar без прокрутки вбок`, await noSideScroll(page));
          if (w !== 1024) await page.screenshot({ path: `${OUT}/calendar-${tag}.png` });
        }
        // Сцена 8: строка обращения в раскрытой службе → «Обращения» R09 с этой жалобой (#inbox/<id> или фильтр «одна»).
        if (w === 1366) {
          await page.click("[data-tab=board]");
          await page.waitForSelector(".ag-row", { timeout: 15000 });
          await page.click(".ag-row");
          await page.waitForSelector(".ag-detail .ag-item__btn, .ag-detail .ag-note", { timeout: 15000 });
          const one = await page.$(".ag-detail .ag-item__btn");
          if (one) {
            const id = await one.getAttribute("data-complaint");
            await one.click();
            await page.waitForTimeout(1500);
            const where = await page.evaluate(() => ({ hash: location.hash, section: window.BirgeShell && window.BirgeShell.section,
              filter: (() => { try { return JSON.parse(sessionStorage.getItem("birge.inbox.filter") || "null"); } catch (e) { return null; } })() }));
            check(`${tag}: строка табло → «Обращения» с этой жалобой`, where.section === "inbox"
              && (where.hash === "#inbox/" + id || !!(where.filter && where.filter.ids && where.filter.ids[0] === id)), { id, ...where });
          }
        }
        check(`${tag}: нет ошибок JS`, page.errs.length === 0, page.errs);
        await ctx.close();
      }
    }

    // ---------------------------------------------------------------- сцена 9: кризисный штаб (1366, ru)
    {
      const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
      const page = await newPage(ctx);
      await login(page, base);
      await setup(page, { lang: "ru", mode: "akimat", tab: "crisis" });
      await openAgencies(page, base, "crisis");
      check("кризис: идёт пример «Буран в Нуре»", /Буран в Нуре/.test(await page.innerText(".ag-crisis")));
      const progressBefore = await page.evaluate(() => document.querySelector(".ag-svcchip__count").textContent);
      const todo = await page.$('.ag-task[data-status="todo"] .ag-task__st, .ag-task[data-status="doing"] .ag-task__st');
      await todo.click();
      await page.waitForTimeout(800);
      const states = await page.$$eval(".ag-task", (els) => els.map((e) => e.dataset.status));
      check("кризис: задача сменила статус (оптимистично и на сервере)", states.length === 4, states);
      await page.fill('[data-form=update] textarea[data-lang=ru]', "Дороги к школам расчищены, автобусы ходят.");
      await page.fill('[data-form=update] textarea[data-lang=kk]', "Мектепке баратын жолдар тазартылды, автобустар жүріп тұр.");
      await page.click("[data-action=send-update]");
      await page.waitForFunction(() => /Дороги к школам расчищены/.test(document.querySelector(".ag-feed").innerText), null, { timeout: 15000 });
      check("кризис: обновление ҚАЗ+РУС появилось в ленте", true);
      await page.screenshot({ path: `${OUT}/crisis-1366-ru.png` });
      // только один язык — понятная ошибка у поля
      await page.fill('[data-form=update] textarea[data-lang=ru]', "Только по-русски");
      await page.click("[data-action=send-update]");
      await page.waitForSelector(".bk-field--error", { timeout: 10000 });
      check("кризис: без казахского текста — ошибка у поля, не отправлено", true);
      // новый кризис из шаблона и закрытие с итогом
      await page.fill('[data-form=update] textarea[data-lang=ru]', "");
      await page.click("[data-action=new-crisis]");
      await page.waitForSelector("[data-form=create]");
      await page.click("[data-kind=water_outage]");
      await page.selectOption('[data-form=create] .ag-select', "esil");
      await page.screenshot({ path: `${OUT}/crisis-form-1366-ru.png` });
      await page.click("[data-action=create-crisis]");
      await page.waitForFunction(() => /Прорыв водопровода/.test((document.querySelector(".ag-crisis") || {}).innerText || ""), null, { timeout: 15000 });
      check("кризис: создан из шаблона «Прорыв водопровода» с задачами служб", (await page.$$(".ag-task")).length === 4);
      await page.click("[data-action=close-crisis]");
      await page.fill('[data-form=close] textarea[lang=ru]', "Трубу заменили, воду дали во все дома.");
      await page.fill('[data-form=close] textarea[lang=kk]', "Құбыр ауыстырылды, барлық үйге су берілді.");
      await page.click("[data-action=confirm-close]");
      await page.waitForFunction(() => /Трубу заменили/.test((document.querySelector(".ag-history") || {}).innerText || ""), null, { timeout: 15000 });
      check("кризис: закрыт с итогом, в списке «Прошедшие»", true);
      // слой «Кризис» на карте
      await page.click("[data-tab=crisis]");
      await page.waitForSelector("[data-action=show-map]");
      await page.click("[data-action=show-map]");
      await page.waitForTimeout(3000);
      const layer = await page.evaluate(() => {
        // eslint-disable-next-line no-undef
        const m = typeof map !== "undefined" ? map : null;
        const ids = m && m.getStyle && m.getStyle() ? m.getStyle().layers.map((l) => l.id) : [];
        const heat = ids.findIndex((id) => /^r07-/.test(id)), fill = ids.indexOf("r17-crisis-fill");
        return { layer: window.BirgeShell && window.BirgeShell.layer, drawn: fill >= 0, fill, firstR07: heat,
          underHeat: heat < 0 || (fill >= 0 && fill < heat) };
      });
      check("карта: слой «Кризис» включён и нарисован", layer.layer === "crisis" && layer.drawn, layer);
      check("карта: зона кризиса под слоями тепловой карты R07 (цвета мест не тонут)", layer.underHeat, layer);
      await page.screenshot({ path: `${OUT}/crisis-map-1366-ru.png` });
      // Прежний вид ссылки (R08 «Картина дня»): #agencies/crisis=<id> — тот же кризис, а не табло.
      await page.evaluate(() => { location.hash = "#agencies/crisis=inc-demo-blizzard-nura"; });
      await page.waitForFunction(() => /Буран в Нуре/.test((document.querySelector(".ag-crisis") || {}).innerText || ""), null, { timeout: 15000 })
        .catch(() => null);
      check("ссылка вида R08 #agencies/crisis=<id> открывает кризис", /Буран в Нуре/.test(await page.evaluate(() =>
        (document.querySelector(".ag-crisis") || {}).innerText || "")));
      check("кризис: нет ошибок JS", page.errs.length === 0, page.errs);
      await ctx.close();
    }

    // ---------------------------------------------------------------- житель зоны: баннер и карточка
    for (const [w, h, lang] of [[375, 812, "kk"], [375, 812, "ru"], [1366, 768, "ru"], [1366, 768, "kk"]]) {
      const tag = `${w}-${lang}`;
      const ctx = await browser.newContext({ viewport: { width: w, height: h } });
      const page = await newPage(ctx);
      await page.goto(base + "/");
      await page.evaluate(async (dev) => {
        localStorage.setItem("birge.device", dev);
        await fetch("/api/civic/v2/nearby/subscriptions", { method: "POST", headers: { "Content-Type": "application/json", "X-Birge-Device": dev },
          body: JSON.stringify({ device_id: dev, scope: "district", id: "nura", on: true }) });
      }, DEVICE);
      await setup(page, { lang, mode: "resident" });
      await page.goto(base + "/");
      await page.waitForSelector(".ag-banner:not([hidden])", { timeout: 30000 });
      await page.waitForTimeout(600);
      await page.screenshot({ path: `${OUT}/resident-banner-${tag}.png` });
      await page.click(".ag-banner__open");
      // Оболочка R01 раунда 15 открывает раздел #crisis/<id> (публичная карточка BirgeAgencies, section "crisis");
      // оболочка без такого раздела — запасная карточка R17 поверх карты (.ag-public).
      const CARD = ".ag-public:not([hidden]), [data-agencies-public] .ag-card--public";
      await page.waitForSelector(CARD, { timeout: 20000 });
      await page.waitForTimeout(500);
      const inShell = !!(await page.$("[data-agencies-public] .ag-card--public"));
      const card = await page.innerText(inShell ? "[data-agencies-public]" : ".ag-public");
      check(`${tag}: «Подробнее» → ${inShell ? "раздел #crisis/<id> оболочки" : "карточка поверх карты"}`, true,
        inShell ? await page.evaluate(() => location.hash) : null);
      const updates = (await page.$$((inShell ? "[data-agencies-public]" : ".ag-public") + " .ag-upd")).length;
      check(`${tag}: житель зоны видит кризис и обновления`, /(Буран|боран)/i.test(card) && updates >= 2, { updates, card: card.slice(0, 80) });
      check(`${tag}: жителю не видны внутренние задачи и заметки штаба`, !/Расчистить главные|Негізгі көшелерді|бригады переведены|бригадасы/.test(card));
      if (lang === "kk") check(`${tag}: карточка на казахском`, /Аймақ|бастап/.test(card), card.slice(0, 80));
      await page.screenshot({ path: `${OUT}/resident-card-${tag}.png` });
      if (!inShell) {
        await page.keyboard.press("Escape");
        check(`${tag}: Esc закрывает карточку`, !!(await page.$(".ag-public[hidden]")));
      }
      check(`${tag}: житель — нет ошибок JS`, page.errs.length === 0, page.errs);
      await ctx.close();
    }

    // ---------------------------------------------------------------- prefers-reduced-motion
    {
      const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 }, reducedMotion: "reduce" });
      const page = await newPage(ctx);
      await login(page, base);
      await setup(page, { lang: "ru", mode: "akimat", tab: "crisis" });
      await openAgencies(page, base, "crisis");
      const anim = await page.evaluate(() => getComputedStyle(document.querySelector(".ag-card__badge"), "::after").animationName);
      check("reduced motion: значок кризиса без пульса", anim === "none", anim);
      await ctx.close();
    }
  } catch (err) {
    check("сценарий без исключений", false, String(err && err.stack || err).slice(0, 600));
  } finally {
    await browser.close();
    if (srv) srv.kill();
    const failed = checks.filter((c) => c.status === "FAIL").length;
    const notRun = checks.filter((c) => c.status === "NOT_RUN").length;
    fs.writeFileSync(path.join(OUT, "browser_checks.json"), JSON.stringify({ base: base, total: checks.length, failed, not_run: notRun, checks }, null, 1));
    console.log(`\n${checks.length - failed - notRun}/${checks.length - notRun} PASS` + (notRun ? ` · NOT_RUN ${notRun}` : ""));
    process.exit(failed ? 1 : 0);
  }
})();
