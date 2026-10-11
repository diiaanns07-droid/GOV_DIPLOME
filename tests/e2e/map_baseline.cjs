// R10 · раунд 14 · эталон «карта не стала хуже» (POLISH_WAVE_2.md, правила 1, 2, 5, 7).
//
//   node tests/e2e/map_baseline.cjs --root <папка сборки> --out <папка> [--repeat 3]
//        [--sizes 1366x768,375x812] [--langs ru,kk] [--modes resident,akimat] [--url http://…/]
//        [--inject-js <файл>]  — добавить скрипт на каждую загрузку (проверка самого сравнения, не приёмка)
//
// Что снимает для каждого варианта «размер × язык × вид» на ВРЕМЕННОЙ базе (как run-city.bat, CIVIC_DEMO=1):
//   1. Загрузка (повтор --repeat раз, каждый раз новое окно без кэша; медиана): DOMContentLoaded, load, карта создана,
//      стиль загружен, первый значок с числом на карте, главная кнопка видна, карта успокоилась (тайлы загружены,
//      сеть молчит 1.5 с); запросы при загрузке (сколько, байты, какие пути API) — правило 5 «новые слои грузятся,
//      только когда включены»; длинные задачи JS; узлы DOM; память JS.
//   2. Вид по умолчанию (первый повтор): кадр PNG; видимые слои стиля и сколько на них нарисовано; значки на карте;
//      кнопки и ссылки вне карты по зонам экрана (шапка, панели, плавающие); пункты меню (на телефоне — «Меню»);
//      легенда; центр, масштаб, наклон карты — правило 1 «по умолчанию только тепловая карта и работы города».
//   3. Плавность: сдвиг карты 2 с и полёт 12 → 15 (кадры requestAnimationFrame: кадр/с, p95, кадры > 50 мс).
//      В облаке WebGL программный — сравнивать только с прогоном на той же машине.
//   4. Время отклика интерфейса (мс от нажатия до результата): «Сообщить о проблеме» → форма; «Мои обращения»;
//      «Житель → Акимат» → «Что построить?»; «Картина дня» → 4 числа; место из «Горячих мест» → значок выбран;
//      ҚАЗ ↔ РУС.
//   5. Карточка места «Хан Шатыр» (правила 3–4): высота содержимого, кнопки, главные кнопки, главная видна без прокрутки.
//   6. API: медиана 5 запросов /heat (город z12, Нура z16), /akim/summary, /classify, /similar, /targets, /proposals.
// Итог: <out>/BASELINE.json, BASELINE.md, кадры default-<w>x<h>-<lang>-<mode>.png. Сравнение — compare_baseline.cjs.
"use strict";
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path"), os = require("os");
const L = require("./r10_lib.cjs");

const args = L.parseArgs(process.argv.slice(2));
const ROOT = path.resolve(args.root || path.join(__dirname, "../.."));
const OUT = path.resolve(args.out || path.join(os.tmpdir(), "r10-map-baseline"));
const SIZES = String(args.sizes || "1366x768,375x812").split(",").map((s) => s.split("x").map(Number));
const LANGS = String(args.langs || "ru,kk").split(",");
const MODES = String(args.modes || "resident,akimat").split(",");
const REPEAT = Number(args.repeat || 3);
const INJECT_JS = args["inject-js"] ? fs.readFileSync(path.resolve(String(args["inject-js"])), "utf8") : null;
const STOP = [71.406553, 51.131155];                       // «Хан Шатыр», остановка DEMO_SCRIPT
const NURA_BBOX = "71.375,51.115,71.420,51.140";
const DEMO_TEXT = "Аялдамада жарық жоқ, вечером на остановке темно";
const T = L.T;

// Счётчики в странице с начала навигации: первые моменты событий (performance.now()) и длинные задачи.
const PROBE = () => {
  const r = (window.__r10 = { t: {}, longtask_ms: 0, longtasks: 0 });
  try { new PerformanceObserver((l) => { for (const e of l.getEntries()) { r.longtasks++; r.longtask_ms += e.duration; } }).observe({ type: "longtask", buffered: true }); } catch (e) { /* нет API */ }
  const first = (k, ok) => { if (r.t[k] === undefined && ok) r.t[k] = Math.round(performance.now()); };
  const vis = (e) => { const b = e.getBoundingClientRect(); return b.width > 0 && b.height > 0 && b.bottom > 0 && b.top < innerHeight && b.right > 0 && b.left < innerWidth; };
  const tick = () => {
    try {
      // eslint-disable-next-line no-undef
      const m = typeof map !== "undefined" && map && map.getStyle ? map : null;
      first("map_created", !!m);
      if (m) { first("style_loaded", m.isStyleLoaded && m.isStyleLoaded()); first("map_loaded", m.loaded && m.loaded()); }
      first("first_badge", [...document.querySelectorAll(".maplibregl-marker")].some((e) => vis(e) && /\d/.test(e.innerText)));
      const re = window.__r10_primary ? new RegExp(window.__r10_primary, "i") : null;
      if (re) first("primary_visible", [...document.querySelectorAll("button, a[href], [role=button], h1, h2, h3, [role=heading]")].some((e) => vis(e) && re.test((e.innerText || e.getAttribute("aria-label") || "").trim())));
    } catch (e) { /* страница ещё строится */ }
    if (!r.stop && Object.keys(r.t).length < 5 && performance.now() < 30000) setTimeout(tick, 40);
  };
  tick();
};

// Вид по умолчанию: что видно на карте и вокруг неё.
const FINGERPRINT = () => {
  // eslint-disable-next-line no-undef
  const m = typeof map !== "undefined" && map && map.getStyle ? map : null;
  const vis = (e) => { const b = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return b.width > 0 && b.height > 0 && s.visibility !== "hidden" && s.display !== "none" && Number(s.opacity) > 0.05 && b.bottom > 0 && b.top < innerHeight && b.right > 0 && b.left < innerWidth; };
  const onTop = (e) => { const b = e.getBoundingClientRect();
    const x = Math.min(Math.max(b.left + b.width / 2, 0), innerWidth - 1), y = Math.min(Math.max(b.top + b.height / 2, 0), innerHeight - 1);
    const h = document.elementFromPoint(x, y); return !h || h === e || e.contains(h) || h.contains(e); };
  const name = (e) => (e.getAttribute("aria-label") || e.innerText || e.getAttribute("title") || e.value || "").replace(/\s+/g, " ").trim().slice(0, 60);
  const zone = (b) => { const cx = b.left + b.width / 2, cy = b.top + b.height / 2, wide = innerWidth >= 1024;
    if (cy < 72) return "шапка"; if (cy > innerHeight - 140) return "низ";
    if (wide && cx < 440) return "панель слева"; if (wide && cx > innerWidth - 440) return "панель справа"; return "поверх карты"; };
  const onMap = (e) => !!e.closest(".maplibregl-marker, .b3d-labels, .maplibregl-popup");
  const controls = [...document.querySelectorAll("button, a[href], [role=button], [role=tab], select, input, summary")]
    .filter((e) => vis(e) && onTop(e) && !onMap(e) && !e.closest(".maplibregl-ctrl-attrib"))
    .map((e) => ({ name: name(e), zone: zone(e.getBoundingClientRect()), pressed: e.getAttribute("aria-pressed") || e.getAttribute("aria-selected") || undefined }));
  const markers = [...document.querySelectorAll(".maplibregl-marker")].filter(vis);
  const markerKinds = {};
  for (const e of markers) { const k = [...e.classList].find((c) => !/^maplibregl/.test(c)) || "marker"; markerKinds[k] = (markerKinds[k] || 0) + 1; }
  const labels3d = [...document.querySelectorAll(".b3d-labels button, .b3d-labels [role=button]")].filter(vis).length;
  const headings = [...document.querySelectorAll("h1, h2, h3, [role=heading]")].filter((e) => vis(e) && onTop(e)).map(name).filter(Boolean);
  const legend = [...document.querySelectorAll("[class*=legend]")].filter((e) => vis(e) && !e.closest("[class*=legend] [class*=legend]"))
    .map((e) => e.innerText.replace(/\s+/g, " ").trim()).filter(Boolean).slice(0, 4);
  const panels = [...document.querySelectorAll("[role=dialog], [role=region], aside, section[aria-label], .bk-panel, .bk-sheet")]
    .filter((e) => vis(e) && onTop(e)).map((e) => (e.getAttribute("aria-label") || (e.querySelector("h1,h2,h3") || {}).innerText || e.className || e.tagName).toString().replace(/\s+/g, " ").trim().slice(0, 50));
  let style = null;
  if (m) {
    const layers = (m.getStyle().layers || []).map((l) => ({ id: l.id, type: l.type, source: l.source, visible: !(l.layout && l.layout.visibility === "none") }));
    const shown = layers.filter((l) => l.visible);
    const rendered = {};
    for (const l of shown) { try { rendered[l.id] = m.queryRenderedFeatures({ layers: [l.id] }).length; } catch (e) { rendered[l.id] = null; } }
    const c = m.getCenter();
    style = { center: [Number(c.lng.toFixed(4)), Number(c.lat.toFixed(4))], zoom: Number(m.getZoom().toFixed(2)), pitch: Math.round(m.getPitch()), bearing: Math.round(m.getBearing()),
      layers_total: layers.length, layers_visible: shown.map((l) => l.id), layers_hidden: layers.filter((l) => !l.visible).map((l) => l.id),
      rendered, sources: Object.keys(m.getStyle().sources || {}) };
  }
  return { lang: document.documentElement.lang, style, markers: markers.length, marker_kinds: markerKinds,
    markers_with_number: markers.filter((e) => /\d/.test(e.innerText)).length, labels3d, controls, headings, legend, panels,
    dom_nodes: document.getElementsByTagName("*").length,
    js_heap_mb: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 2 ** 20) : null };
};

// Плавность анимации карты: кадры requestAnimationFrame во время сдвига и полёта.
const SMOOTH = async (stop) => {
  // eslint-disable-next-line no-undef
  const m = typeof map !== "undefined" && map && map.getStyle ? map : null;
  if (!m) return null;
  const wait = (ms) => new Promise((ok) => setTimeout(ok, ms));
  const frames = async (start, ms) => { const d = []; let last = performance.now(); const t0 = last; let run = true;
    const loop = (t) => { d.push(t - last); last = t; if (run) requestAnimationFrame(loop); };
    requestAnimationFrame(loop); start(); await wait(ms); run = false; await wait(50);
    const v = d.slice(1).sort((a, b) => a - b);
    return { frames: v.length, fps: Math.round((v.length * 1000) / (performance.now() - t0)), p50_ms: Math.round(v[v.length >> 1] || 0),
      p95_ms: Math.round(v[Math.floor(v.length * 0.95)] || 0), max_ms: Math.round(v[v.length - 1] || 0), over50: v.filter((x) => x > 50).length }; };
  m.jumpTo({ center: stop, zoom: 15, pitch: 0, bearing: 0 }); await wait(2500);
  const pan = await frames(() => m.easeTo({ center: [stop[0] + 0.02, stop[1] + 0.006], duration: 2000 }), 2300);
  m.jumpTo({ center: stop, zoom: 12 }); await wait(2000);
  const fly = await frames(() => m.flyTo({ center: stop, zoom: 15, duration: 2000 }), 2300);
  return { pan, fly };
};

// Карточка места (правило 3 — «не растёт бесконечно», правило 4 — одна главная кнопка): открыть «Хан Шатыр» нажатием
// по значку и измерить: высота на экране и всего содержимого (с прокруткой), кнопки, главные кнопки, видна ли главная
// без прокрутки, сколько свёрнутых блоков «Подробнее».
const CARD = () => {
  const vis = (e) => { const b = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return b.width > 0 && b.height > 0 && s.visibility !== "hidden" && s.display !== "none" && b.bottom > 0 && b.top < innerHeight && b.right > 0 && b.left < innerWidth; };
  const card = [...document.querySelectorAll(".r07-card, [role=dialog] article, article")].find(vis);
  if (!card) return null;
  let sc = card;
  for (let e = card; e && e !== document.body; e = e.parentElement) { const o = getComputedStyle(e).overflowY; if ((o === "auto" || o === "scroll") && e.scrollHeight > e.clientHeight + 2) { sc = e; break; } }
  const box = sc.getBoundingClientRect();
  const btns = [...card.querySelectorAll("button, a[href], [role=button]")].filter((e) => e.getClientRects().length);
  const primary = btns.filter((e) => /primary/.test(e.className));
  const inView = (e) => { const b = e.getBoundingClientRect(); return b.top >= Math.max(0, box.top) - 1 && b.bottom <= Math.min(innerHeight, box.bottom) + 1; };
  const title = card.querySelector("h1, h2, h3, [role=heading]");
  return { title: title ? title.innerText.trim().slice(0, 60) : null, visible_h: Math.round(Math.min(box.bottom, innerHeight) - Math.max(box.top, 0)),
    content_h: Math.round(card.scrollHeight), buttons: btns.length, primary: primary.length,
    primary_names: primary.map((e) => (e.innerText || e.getAttribute("aria-label") || "").trim().slice(0, 40)),
    primary_in_view: primary.length ? primary.every(inView) : null, details: card.querySelectorAll("details, [aria-expanded]").length,
    text_chars: card.innerText.replace(/\s+/g, " ").length };
};
async function cardMetrics(page, tag) {
  await page.keyboard.press("Escape").catch(() => null); await L.sleep(600);
  const pt = await L.showPoint(page, STOP, 17);
  if (!pt) return null;
  await L.tap(page, pt.x, pt.y); await L.sleep(2500);
  const m = await page.evaluate(CARD).catch(() => null);
  if (m) { m.shot = `card-${tag}.jpg`; await page.screenshot({ path: path.join(OUT, m.shot), type: "jpeg", quality: 70 }).catch(() => null); }
  await page.keyboard.press("Escape").catch(() => null); await L.sleep(600);
  return m;
}

async function settle(page, maxMs = 30000) {
  const t = Date.now();
  let lastReq = Date.now();
  const on = () => (lastReq = Date.now());
  page.on("request", on);
  try {
    while (Date.now() - t < maxMs) {
      const idle = await page.evaluate(() => { try {
        // eslint-disable-next-line no-undef
        const m = typeof map !== "undefined" && map && map.getStyle ? map : null; return !!m && m.loaded() && m.areTilesLoaded() && !m.isMoving(); } catch (e) { return false; } }).catch(() => false);
      if (idle && Date.now() - lastReq > 1500) return Date.now() - t;
      await L.sleep(100);
    }
    return null;
  } finally { page.off("request", on); }
}

async function newPage(browser, [w, h], lang, mode) {
  const mobile = w < 761;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
  await ctx.addInitScript(([m, l]) => { try { if (!sessionStorage.getItem("r10.init")) { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); sessionStorage.setItem("r10.init", "1"); } } catch (e) { /* нет хранилища */ } }, [mode, lang]);
  await ctx.addInitScript(PROBE);
  if (INJECT_JS) await ctx.addInitScript(INJECT_JS);
  const page = await ctx.newPage();
  return { ctx, page, mobile };
}

async function ensureLang(page, lang) {
  if ((await page.evaluate(() => document.documentElement.lang).catch(() => null)) === lang) return true;
  const b = await L.firstVisible(page.getByRole("button", { name: lang === "kk" ? /^ҚАЗ$/ : /^РУС$/ }));
  if (b) { await b.click().catch(() => null); await L.sleep(1000); }
  return (await page.evaluate(() => document.documentElement.lang).catch(() => null)) === lang;
}

async function loadOnce(browser, base, size, lang, mode, dict, keep) {
  const { ctx, page, mobile } = await newPage(browser, size, lang, mode);
  const primary = mode === "resident" ? T(dict, "complaint.start.button", lang === "kk" ? "Мәселе туралы хабарлау" : "Сообщить о проблеме")
    : T(dict, "heat.hot_title", lang === "kk" ? "Шағымы көп орындар" : "Горячие места");
  await page.addInitScript((re) => { window.__r10_primary = re; }, "^" + L.esc(primary));
  const req = { n: 0, bytes: 0, api: new Set(), failed: 0, types: {} };
  page.on("requestfinished", async (r) => { req.n++; const u = new URL(r.url());
    req.types[r.resourceType()] = (req.types[r.resourceType()] || 0) + 1;
    if (u.pathname.startsWith("/api/")) req.api.add(r.method() + " " + u.pathname);
    try { const s = await r.sizes(); req.bytes += s.responseBodySize + s.responseHeadersSize; } catch {} });
  page.on("requestfailed", () => req.failed++);
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message.slice(0, 160)));
  const t0 = Date.now();
  await page.goto(base, { waitUntil: "commit", timeout: 60000 });
  const settle_ms = await settle(page);
  const wall_ms = Date.now() - t0;
  const nav = await page.evaluate(() => { const n = performance.getEntriesByType("navigation")[0] || {};
    return { ttfb: Math.round(n.responseStart || 0), dcl: Math.round(n.domContentLoadedEventEnd || 0), load: Math.round(n.loadEventEnd || 0) }; });
  // У жителя «главное» — кнопка «Сообщить о проблеме», у акимата — заголовок списка «Горячие места».
  const probe = await page.evaluate(() => { window.__r10.stop = true; return window.__r10; });
  const run = { wall_ms, settle_ms, ...nav, ...probe.t, longtasks: probe.longtasks, longtask_ms: Math.round(probe.longtask_ms),
    requests: req.n, bytes_kb: Math.round(req.bytes / 1024), failed: req.failed, errors: errors.length };
  const extra = keep ? { api_paths: [...req.api].sort(), req_types: req.types, errors } : null;
  return { run, extra, ctx, page, mobile };
}

async function variant(browser, base, size, lang, mode) {
  const dict = L.loadDict(ROOT, lang);
  const tag = `${size[0]}x${size[1]}-${lang}-${mode}`;
  const runs = [];
  let out = { tag };
  for (let i = 0; i < REPEAT; i++) {
    const keep = i === 0;
    const r = await loadOnce(browser, base, size, lang, mode, dict, keep);
    runs.push(r.run);
    if (keep) {
      out.lang_ok = await ensureLang(r.page, lang);
      if (!out.lang_ok) await settle(r.page, 8000);
      out.requests = r.extra;
      out.fingerprint = await r.page.evaluate(FINGERPRINT);
      // Меню: на телефоне и узком экране пункты шапки спрятаны в «Меню» — открыть и переписать новые кнопки.
      const menuRe = new RegExp("^" + L.esc(T(dict, ["common.nav.menu", "shell.menu"], lang === "kk" ? "Мәзір" : "Меню")) + "$", "i");
      const menu = await L.firstVisible(r.page.getByRole("button", { name: menuRe }));
      if (menu) {
        const before = new Set(out.fingerprint.controls.map((c) => c.name));
        await menu.click().catch(() => null); await L.sleep(900);
        const after = await r.page.evaluate(FINGERPRINT);
        out.menu = after.controls.filter((c) => !before.has(c.name)).map((c) => c.name);
        await r.page.keyboard.press("Escape").catch(() => null); await L.sleep(600);
      } else out.menu = null;
      out.shot = `default-${tag}.png`;
      await r.page.screenshot({ path: path.join(OUT, out.shot) }).catch(() => null);
      out.smooth = await r.page.evaluate(SMOOTH, STOP).catch((e) => ({ error: String(e.message).slice(0, 120) }));
      // Карточка — до проверки отклика: та в конце переключает вид «Житель → Акимат».
      out.card = await cardMetrics(r.page, tag);
      out.transitions = await transitions(r.page, dict, lang, mode, r.mobile);
    }
    await r.ctx.close();
  }
  const keys = [...new Set(runs.flatMap((r) => Object.keys(r)))].filter((k) => runs.some((r) => typeof r[k] === "number"));
  out.median = Object.fromEntries(keys.map((k) => [k, L.median(runs.map((r) => r[k]))]));
  out.runs = runs;
  console.log(tag, JSON.stringify(out.median));
  return out;
}

// Время отклика интерфейса: мс от нажатия до видимого результата (одна попытка, после загрузки и замера плавности).
async function transitions(page, dict, lang, mode, mobile) {
  const res = {};
  const menuRe = new RegExp("^" + L.esc(T(dict, ["common.nav.menu", "shell.menu"], lang === "kk" ? "Мәзір" : "Меню")) + "$", "i");
  const press = async (re) => { let b = await L.firstVisible(page.getByRole("button", { name: re }));
    if (!b) { const m = await L.firstVisible(page.getByRole("button", { name: menuRe })); if (m) { await m.click().catch(() => null); await L.sleep(700); b = await L.firstVisible(page.getByRole("button", { name: re })); } }
    if (!b) return false; await b.click({ timeout: 4000 }).catch(() => null); return true; };
  const hasText = (s) => page.evaluate((src) => { const re = new RegExp(src, "i");
    return [...document.querySelectorAll("body *")].some((e) => !e.children.length && e.getBoundingClientRect().width > 0 && re.test(e.textContent)); }, s);
  // Видимый текст: лист без вложенных элементов или заголовок (у заголовка бывает вложенный счётчик).
  const until = (src, t = 15000) => L.timeUntil(page, (s) => { const re = new RegExp(s, "i");
    const vis = (e) => { const b = e.getBoundingClientRect(); return b.width > 0 && b.height > 0 && b.bottom > 0 && b.top < innerHeight; };
    return [...document.querySelectorAll("body *")].some((e) => !e.children.length && vis(e) && re.test(e.textContent))
      || [...document.querySelectorAll("h1, h2, h3, [role=heading]")].some((e) => vis(e) && re.test(e.innerText.trim())); }, src, t);
  const back = async () => { await page.keyboard.press("Escape").catch(() => null); await L.sleep(800); };
  if (mode === "resident") {
    const start = T(dict, "complaint.start.button", lang === "kk" ? "Мәселе туралы хабарлау" : "Сообщить о проблеме");
    const formTitle = T(dict, "complaint.step2.title", lang === "kk" ? "Мәселе қай жерде?" : "Где проблема?");
    res.complaint_form_ms = (await press(L.textRe(start))) ? await until(L.textRe(formTitle).source) : null;
    await back(); await back();
    const mine = T(dict, ["common.nav.mine", "mine.title"], lang === "kk" ? "Менің өтініштерім" : "Мои обращения");
    const empty = T(dict, "mine.empty.title", "Вы ещё ничего не отправляли");
    // До загруженного списка: у нового устройства — «Вы ещё ничего не отправляли» (не «Загружаем обращения…»).
    res.mine_ms = (await press(L.textRe(mine))) ? await until(L.textRe(empty).source) : null;
    await back();
    const akimat = T(dict, ["common.role.akimat", "shell.mode.akimat"], lang === "kk" ? "Әкімдік" : "Акимат");
    // Вид «Акимат» готов, когда видна его кнопка «Что построить?» (у жителя её нет; на телефоне «Горячие места» — в шторке).
    const build = T(dict, "proposal.catalog.title", lang === "kk" ? "Не салу керек?" : "Что построить?");
    res.to_akimat_ms = (await press(new RegExp("^" + L.esc(akimat) + "$", "i"))) ? await until("^" + L.esc(build) + "$") : null;
  } else {
    // Как ведущий на шаге 3: сначала место из «Горячих мест» (вид по умолчанию), потом «Картина дня».
    const hotRe = new RegExp("^" + L.esc(T(dict, "heat.hot_title", lang === "kk" ? "Шағымы көп орындар" : "Горячие места")), "i");
    const item = page.locator("section").filter({ has: page.getByRole("heading", { name: hotRe }) }).getByRole("listitem").getByRole("button").first();
    if (await item.isVisible().catch(() => false)) {
      await page.evaluate(() => { window.__r10hot = null; });
      await item.click({ timeout: 3000 }).catch(() => null);
      // Камера долетела и стоит; место — значок выбран; район из списка (без значка) — полёт был и закончился.
      res.hot_select_ms = await L.timeUntil(page, () => {
        const s = (window.__r10hot = window.__r10hot || { moved: false, t0: performance.now() });
        // eslint-disable-next-line no-undef
        const moving = typeof map !== "undefined" && map.isMoving && map.isMoving();
        if (moving) s.moved = true;
        const e = document.querySelector(".r07-badge--selected");
        return !moving && ((!!e && e.getClientRects().length > 0) || (s.moved && performance.now() - s.t0 > 300)); }, null, 15000);
      await back();
    } else res.hot_select_ms = null;
    const day = T(dict, ["common.nav.day", "shell.section.day", "akim.title"], lang === "kk" ? "Күн қорытындысы" : "Картина дня");
    if (await press(new RegExp("^" + L.esc(day) + "$", "i"))) {
      res.day_kpi_ms = await L.timeUntil(page, () => [...document.querySelectorAll(".bk-kpi, .akim-kpi")].filter((e) => e.getBoundingClientRect().width > 0).length >= 4, null, 20000);
      await back();
      if (!(await hasText("^" + L.esc(T(dict, "heat.hot_title", "Горячие места"))))) await press(new RegExp("^" + L.esc(T(dict, ["common.nav.map", "shell.section.map"], "Карта")) + "$", "i"));
      await L.sleep(1200);
    } else res.day_kpi_ms = null;
  }
  const other = lang === "kk" ? /^РУС$/ : /^ҚАЗ$/, otherLang = lang === "kk" ? "ru" : "kk";
  if (await press(other)) {
    res.lang_switch_ms = await L.timeUntil(page, (l) => document.documentElement.lang === l, otherLang, 8000);
    await press(lang === "kk" ? /^ҚАЗ$/ : /^РУС$/); await L.sleep(800);
  } else res.lang_switch_ms = null;
  return res;
}

async function apiTimes(base) {
  const A = L.api(base);
  const cases = [
    ["GET", "/api/civic/v2/modules"],
    ["GET", "/api/civic/v2/heat?days=30&zoom=12"],
    ["GET", `/api/civic/v2/heat?bbox=${NURA_BBOX}&days=30&zoom=16`],
    ["GET", "/api/civic/v2/akim/summary"],
    ["POST", "/api/civic/v2/classify", { text: DEMO_TEXT }],
    ["POST", "/api/civic/v2/similar", { text: DEMO_TEXT, point: STOP, days: 30 }],
    ["GET", `/api/civic/v2/targets?lon=${STOP[0]}&lat=${STOP[1]}&category=transport`],
    ["GET", "/api/civic/v2/proposals"],
  ];
  const out = {};
  for (const [m, p, body] of cases) {
    const ms = [], st = [];
    let bytes = null;
    for (let i = 0; i < 6; i++) { const r = await A.call(m, p, body); ms.push(Math.round(r.ms)); st.push(r.status); bytes = r.bytes; }
    out[`${m} ${p.split("?")[0]}${p.includes("zoom=") ? " z" + p.match(/zoom=(\d+)/)[1] : ""}`] = { first_ms: ms[0], median_ms: L.median(ms.slice(1)), status: [...new Set(st)], kb: bytes ? Math.round(bytes / 1024) : null };
  }
  return out;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  let server = null, base = args.url;
  if (!base) { server = await L.startServer(ROOT, { staff: false }); base = server.base; }
  const sha = L.buildSha(ROOT);
  console.log(`R10 map_baseline: сборка ${ROOT} @ ${sha}, сервер ${base}`);
  const browser = await chromium.launch();
  const cases = {};
  let apis = null;
  try {
    // Прогрев: первый запрос /heat подключает модули (B-032); страница один раз без замера.
    await L.api(base).call("GET", "/api/civic/v2/heat?days=30&zoom=12");
    { const c = await browser.newContext(); const p = await c.newPage(); await p.goto(base).catch(() => null); await settle(p, 20000); await c.close(); }
    for (const size of SIZES) for (const lang of LANGS) for (const mode of MODES) {
      try { const v = await variant(browser, base, size, lang, mode); cases[v.tag] = v; }
      catch (e) { cases[`${size.join("x")}-${lang}-${mode}`] = { error: String(e.message || e).slice(0, 300) }; console.log("ОШИБКА", size, lang, mode, e.message); }
    }
    apis = await apiTimes(base);
  } finally {
    const version = browser.version();
    await browser.close();
    if (server) await server.stop();
    const meta = { root: ROOT, sha, when: new Date().toISOString(), base: args.url || "(свой сервер, временная база, CIVIC_DEMO=1)",
      repeat: REPEAT, sizes: SIZES.map((s) => s.join("x")), langs: LANGS, modes: MODES, chromium: version, machine: L.machine(),
      ...(INJECT_JS ? { inject_js: String(args["inject-js"]) } : {}) };
    fs.writeFileSync(path.join(OUT, "BASELINE.json"), JSON.stringify({ meta, cases, api: apis }, null, 1));
    fs.writeFileSync(path.join(OUT, "BASELINE.md"), report(meta, cases, apis));
    console.log("→", OUT);
  }
})().catch((e) => { console.error(e); process.exit(2); });

function report(meta, cases, apis) {
  const s = (x) => (typeof x === "number" ? (x / 1000).toFixed(2) : "—");
  const md = [`# R10 · эталон карты · ${meta.sha}${meta.inject_js ? " · С ВСТАВКОЙ СКРИПТА (проверка сравнения)" : ""}`, "",
    "```", JSON.stringify(meta), "```", "",
    "Загрузка, медиана из " + meta.repeat + " окон без кэша, секунды от начала навигации (WebGL программный — сравнивать с прогоном на той же машине):", "",
    "| Вариант | DOM готов | load | карта загружена | 1-й значок с числом | главная кнопка | карта успокоилась | запросов | КБ | длинные задачи, мс |",
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"];
  for (const [tag, c] of Object.entries(cases)) {
    if (c.error) { md.push(`| ${tag} | ошибка: ${c.error.slice(0, 80)} |||||||||`); continue; }
    const m = c.median;
    md.push(`| ${tag} | ${s(m.dcl)} | ${s(m.load)} | ${s(m.map_loaded)} | ${s(m.first_badge)} | ${s(m.primary_visible)} | ${s(m.wall_ms)} | ${m.requests} | ${m.bytes_kb} | ${m.longtask_ms} |`);
  }
  md.push("", "Вид по умолчанию (первое окно):", "", "| Вариант | слоёв видно / всего | значков (с числом) | 3D-табличек | кнопок вне карты | меню | масштаб | кадр |", "|---|---|---|---|---|---|---|---|");
  for (const [tag, c] of Object.entries(cases)) {
    if (c.error || !c.fingerprint) continue;
    const f = c.fingerprint;
    md.push(`| ${tag} | ${f.style ? f.style.layers_visible.length + " / " + f.style.layers_total : "нет карты"} | ${f.markers} (${f.markers_with_number}) | ${f.labels3d} | ${f.controls.length} | ${c.menu ? c.menu.length + ": " + c.menu.join(" · ").slice(0, 120) : "—"} | z${f.style && f.style.zoom} | ${c.shot} |`);
  }
  md.push("", "Плавность (кадр/с · p95 мс · кадров > 50 мс) и отклик интерфейса, мс:", "", "| Вариант | сдвиг | полёт 12→15 | отклик |", "|---|---|---|---|");
  for (const [tag, c] of Object.entries(cases)) {
    if (c.error || !c.smooth) continue;
    const f = (x) => (x ? `${x.fps} · ${x.p95_ms} · ${x.over50}` : "—");
    md.push(`| ${tag} | ${f(c.smooth.pan)} | ${f(c.smooth.fly)} | ${Object.entries(c.transitions || {}).map(([k, v]) => `${k.replace(/_ms$/, "")}: ${v ?? "—"}`).join(", ")} |`);
  }
  md.push("", "Карточка места «Хан Шатыр» (правила 3–4 POLISH_WAVE_2):", "", "| Вариант | заголовок | видно, px | содержимое, px | кнопок | главных | главная без прокрутки | «Подробнее» | кадр |", "|---|---|---:|---:|---:|---:|---|---:|---|");
  for (const [tag, c] of Object.entries(cases)) {
    if (c.error) continue;
    const k = c.card;
    md.push(k ? `| ${tag} | ${k.title} | ${k.visible_h} | ${k.content_h} | ${k.buttons} | ${k.primary} (${k.primary_names.join(", ")}) | ${k.primary_in_view} | ${k.details} | ${k.shot} |` : `| ${tag} | карточка не открылась ||||||||`);
  }
  if (apis) {
    md.push("", "API (6 запросов: первый и медиана остальных):", "", "| Запрос | первый, мс | медиана, мс | КБ | статус |", "|---|---:|---:|---:|---|");
    for (const [k, v] of Object.entries(apis)) md.push(`| ${k} | ${v.first_ms} | ${v.median_ms} | ${v.kb ?? ""} | ${v.status.join(",")} |`);
  }
  md.push("", "Видимые слои стиля по умолчанию (первый вариант каждого вида):", "");
  const seen = new Set();
  for (const [tag, c] of Object.entries(cases)) {
    const mode = tag.split("-").pop();
    if (c.error || !c.fingerprint || !c.fingerprint.style || seen.has(mode)) continue;
    seen.add(mode);
    md.push(`- ${tag}: ${c.fingerprint.style.layers_visible.map((id) => `${id} (${c.fingerprint.style.rendered[id] ?? "?"})`).join(", ")}`);
  }
  return md.join("\n") + "\n";
}
