#!/usr/bin/env node
// R10 · раунд 15 · аудит новых экранов по VISUAL_BRIEF §4 (R10.txt, задача 5): шрифт (не мельче 13 px, не больше 3 размеров
// на экране — п. 3), зоны нажатия ≥ 44 px и видимый фокус (п. 10), контраст ≥ 4,5:1 (и на стекле), нет прокрутки вбок
// на 375, нет ключей перевода и технических слов, казахский не обрезан (п. 3), состояние «нет связи» с «Повторить» (п. 8).
// Размеры 1366×768, 1024×768, 375×812; ҚАЗ и РУС; демо-мир R02 (CIVIC_DEMO_WORLD=1).
//
//   NODE_PATH="$(npm root -g)" node tests/e2e/visual_audit.cjs --root <сборка> --out <папка>
//        [--sizes 1366x768,375x812] [--langs ru,kk] [--only yard,agencies] [--no-world]
//
// Экран, модуля которого нет на странице, — NOT_RUN с причиной. «Смотреть» (WARN) — правило брифа, которое не валит
// приёмку: 4+ размеров шрифта, зоны 40–43 px. Итог: AUDIT.json, AUDIT.md (по экранам и владельцам), кадры экранов.
"use strict";
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path"), os = require("os");
const L = require("./r10_lib.cjs");
const { uiScreen, NOISE, sheetMetrics, aiMark, mapHook, mapOverview } = require("./ux_lib.cjs");
const { sleep, T, esc, firstVisible } = L;

const args = L.parseArgs(process.argv.slice(2));
const ROOT = path.resolve(args.root || path.join(__dirname, "../.."));
const OUT = path.resolve(args.out || path.join(os.tmpdir(), "r10-visual-audit"));
const SIZES = String(args.sizes || "1366x768,1024x768,375x812").split(",").map((s) => s.split("x").map(Number));
const LANGS = String(args.langs || "ru,kk").split(",");
const ONLY = args.only ? new Set(String(args.only).split(",")) : null;
const WORLD = !args["no-world"];
fs.mkdirSync(OUT, { recursive: true });

function worldScenes() {
  try {
    const w = JSON.parse(fs.readFileSync(path.join(ROOT, "data/civic/astana/demo-world/world_v1.json"), "utf8"));
    const sc = w.scenes || {};
    return { yard: (sc.scene7 || {}).yard, initiative: (sc.scene7 || {}).initiative, incident: (sc.scene9 || {}).incident,
      conflict: (sc.scene8 || {}).conflict };
  } catch (e) { return {}; }
}
const W15 = worldScenes();

// Новые экраны раунда 15 (IA_ROUND15 R11, адреса оболочки R01). api — запросы модуля (для состояния «нет связи»).
const API = (re) => new RegExp("/api/civic/v2/" + re);
const SCREENS = [
  { id: "yard", hash: W15.yard ? `#yard/${W15.yard}` : "#yard", mode: "resident", global: "BirgeTogether", owner: "R16", api: API("together/") },
  { id: "together", hash: "#together", mode: "resident", global: "BirgeTogether", owner: "R16", api: API("together/") },
  { id: "together-card", hash: W15.initiative ? `#together/${W15.initiative}` : null, mode: "resident", global: "BirgeTogether", owner: "R16", api: API("together/") },
  { id: "meetings", hash: "#meetings", mode: "resident", global: "BirgeMeetings", owner: "R13", api: API("meetings") },
  { id: "crisis-card", hash: W15.incident ? `#crisis/${W15.incident}` : null, mode: "resident", global: "BirgeAgencies", owner: "R17", api: API("incidents") },
  { id: "agencies-board", hash: "#agencies/board", mode: "akimat", global: "BirgeAgencies", owner: "R17", api: API("agencies") },
  { id: "agencies-joint", hash: "#agencies/joint", mode: "akimat", global: "BirgeAgencies", owner: "R17", api: API("agencies") },
  { id: "agencies-handoffs", hash: "#agencies/handoffs", mode: "akimat", global: "BirgeAgencies", owner: "R17", api: API("agencies") },
  { id: "agencies-calendar", hash: "#agencies/calendar", alt: "#works-calendar", mode: "akimat", global: "BirgeWorksCalendar", owner: "R12 + R17", api: API("works-(calendar|conflicts)") },
  { id: "crisis-hq", hash: W15.incident ? `#agencies/crisis/${W15.incident}` : null, alt: W15.incident ? `#agencies/crisis=${W15.incident}` : null, mode: "akimat", global: "BirgeAgencies", owner: "R17", api: API("incidents") },
  // «Спросить Birge» при открытии запросов не шлёт — «нет связи» проверяем на вопросе (act).
  { id: "analyst", hash: "#analyst", mode: "akimat", global: "BirgeAnalyst", owner: "R03", api: API("assistant"),
    act: async (page, lang) => {
      const box = await firstVisible(page.locator("#birge-screen:not([hidden]) input[type=text], #birge-screen:not([hidden]) textarea"));
      if (!box) return false;
      await box.fill(lang === "kk" ? "Нұрада 30 күнде қанша шағым түсті?" : "Сколько жалоб в Нуре за 30 дней?").catch(() => null);
      await box.press("Enter").catch(() => null);
      return true;
    } },
  { id: "meetings-staff", hash: "#meetings", mode: "akimat", global: "BirgeMeetings", owner: "R13", api: API("meetings") },
  // П3 (16 окт): все листы-разделы — R01 проверяет ширину листа, роли — свои экраны по VISUAL_BRIEF §4; сцена 0 R04.
  // legacy — экраны до раунда 15: «нет связи» у них — «смотреть» (WARN), остальное по VISUAL_BRIEF §4 — как у новых.
  { id: "inbox", hash: "#inbox", mode: "akimat", global: ["BirgeInbox", "BirgeComplaintList"], owner: "R09", api: API("complaints"), legacy: true },
  { id: "day", hash: "#day", mode: "akimat", global: null, owner: "R08", api: API("akim/summary"), root: "#birge-day:not([hidden])", legacy: true },
  { id: "projects", hash: "#projects", mode: "akimat", global: ["BirgeProjects", "BirgeIdeas"], owner: "R06 + R05", api: API("(proposals|ideas)"), legacy: true },
  { id: "ideas", hash: "#ideas", mode: "resident", global: ["BirgeIdeas"], owner: "R06 + R05", api: API("ideas"), legacy: true },
  { id: "notifications", hash: "#notifications", mode: "resident", global: ["BirgeNotify"], owner: "R06", api: API("notifications"), legacy: true },
  { id: "services", hash: "#services", mode: "akimat", global: ["BirgeServices"], owner: "R08", api: null, legacy: true },
  { id: "intake", hash: "#intake", mode: "akimat", global: ["BirgeIntake"], owner: "R04", api: API("intake/") },
];
const GLOBALS = [...new Set(SCREENS.flatMap((sc) => [].concat(sc.global || [])))];
// Отдельные страницы (без оболочки): Ситуационный центр и «Картина недели» R08 — только сотрудник.
const PAGES = [
  { id: "board-page", urls: ["civic/board/", "civic/board/index.html"], owner: "R08", api: API("akim/board") },
  { id: "week-page", urls: ["civic/akim/week.html"], owner: "R08", api: API("akim/week") },
];

const rows = [];
const add = (screen, owner, variant, check, status, detail, shot) => {
  rows.push({ screen, owner, variant, check, status, detail: detail ?? null, shot: shot || null });
  console.log(`${status.padEnd(8)} ${variant.padEnd(8)} ${screen.padEnd(18)} ${check}` + (detail != null ? " — " + JSON.stringify(detail).slice(0, 220) : ""));
};

// Метрики п. 3 и п. 10 внутри корня экрана: размеры шрифта видимого текста, зоны нажатия < 44 px.
function screenMetrics(page, sel) {
  return page.evaluate((s) => {
    const root = document.querySelector(s);
    if (!root) return null;
    const vis = (e) => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
      return r.width > 1 && r.height > 1 && cs.visibility !== "hidden" && cs.display !== "none" && r.bottom > 0 && r.top < innerHeight
        && !e.closest(".bk-sr-only, .sr-only, .visually-hidden"); };
    const sizes = new Map(), tinyEx = [];
    for (const el of root.querySelectorAll("*")) {
      const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").trim();
      // Строка лицензии карты («© OpenStreetMap») — служебная подпись, правило шрифта к ней не относится (как в ux_lib).
      if (!own || !vis(el) || el.closest("svg, .maplibregl-ctrl-attrib") || /©/.test(own)) continue;
      const fs = Math.round(parseFloat(getComputedStyle(el).fontSize) * 2) / 2;
      if (fs > 0) sizes.set(fs, (sizes.get(fs) || 0) + 1);
      if (fs > 0 && fs < 13 && tinyEx.length < 6) tinyEx.push(`${fs}px «${own.slice(0, 28)}»`);
    }
    // Зона нажатия = рамка + точки вокруг неё, которые ловит та же кнопка (::after ui-kit R11 «inset: -6px 0», прозрачная
    // рамка) — как hitBox в ux_lib.cjs. До 16 окт мерилась только рамка (ложные FAIL «Я приду» 32 px, «Скоро · Сделано» 30 px).
    const hitBox = (box) => {
      const r = box.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      // За краем экрана elementFromPoint ничего не видит — там берём зону, заявленную псевдоэлементом (::after «inset: -6px 0»).
      const own = (x, y) => { if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return "out";
        const h = document.elementFromPoint(x, y); return !!h && (h === box || box.contains(h)); };
      const declared = (side) => { let best = 0;
        for (const pe of ["::before", "::after"]) { const cs = getComputedStyle(box, pe);
          if (cs.content === "none" || cs.position !== "absolute" || cs.pointerEvents === "none") continue;
          const v = parseFloat(cs[side]); if (Number.isFinite(v) && v < 0) best = Math.max(best, -v); }
        return Math.min(best, 12); };
      const grow = (f, side) => { let k = 0; while (k < 12) { const o = f(k + 1); if (o === "out") return Math.max(k, declared(side)); if (!o) break; k++; } return k; };
      const dh = grow((k) => own(cx, r.top - k), "top") + grow((k) => own(cx, r.bottom - 1 + k), "bottom");
      const dw = grow((k) => own(r.left - k, cy), "left") + grow((k) => own(r.right - 1 + k, cy), "right");
      return { h: Math.round(r.height + dh), w: Math.round(r.width + dw), ...(dh || dw ? { frame: `${Math.round(r.width)}×${Math.round(r.height)}` } : {}) };
    };
    const small = [];
    for (const e of root.querySelectorAll("button, a[href], [role=button], [role=tab], input, select, summary, textarea")) {
      if (!vis(e) || e.closest(".maplibregl-marker")) continue;
      const box = (/^(checkbox|radio)$/.test(e.type) && e.closest("label")) || e;
      const z = hitBox(box);
      if (z.h < 44 || z.w < 44) small.push({ ...z,
        t: (box.innerText || e.getAttribute("aria-label") || e.getAttribute("title") || "").trim().replace(/\s+/g, " ").slice(0, 24) });
    }
    // Вкладка за краем полосы (полоса прокручивается вбок): видна «Төтенше жа…» — подпись выглядит обрезанной.
    const tabsCut = [];
    for (const t of root.querySelectorAll("[role=tab]")) {
      if (!vis(t)) continue;
      const r = t.getBoundingClientRect();
      let edge = { left: 0, right: innerWidth };
      for (let n = t.parentElement; n && n !== document.body; n = n.parentElement) {
        if (/(auto|scroll|hidden|clip)/.test(getComputedStyle(n).overflowX)) { const pr = n.getBoundingClientRect(); edge = { left: pr.left, right: pr.right }; break; }
      }
      if (r.right > edge.right + 1 || r.left < edge.left - 1) tabsCut.push((t.innerText || "").trim().slice(0, 24));
    }
    // П1 «Без ИИ-слопа» (AMENDMENTS 15 окт): иллюстрации — только малые значки ≤ 48 px; эмодзи в интерфейсе нет.
    const bigIll = [];
    for (const e of root.querySelectorAll("svg, img")) {
      if (!vis(e) || e.closest(".maplibregl-map, canvas")) continue;
      const use = e.querySelector && e.querySelector("use");
      const ref = (use && (use.getAttribute("href") || use.getAttribute("xlink:href"))) || e.getAttribute("src") || "";
      const cls = String(e.getAttribute("class") || "");
      if (!/(^|[#\/_-])ill[-_]|bk-ill|illustr/i.test(ref + " " + cls)) continue;
      const r = e.getBoundingClientRect();
      if (r.width > 48 || r.height > 48) bigIll.push(`${Math.round(r.width)}×${Math.round(r.height)} ${(ref || cls).slice(0, 40)}`);
    }
    // Эмодзи — знаки, которые рисуются цветной картинкой: Emoji_Presentation или знак + VS16 (▶ ⚠ ✓ как текст — можно).
    const emoji = ((root.innerText || "").match(/\p{Emoji_Presentation}|\p{Extended_Pictographic}\uFE0F/gu) || []).filter((c) => !/^[0-9#*]/.test(c));
    return { sizes: [...sizes.entries()].sort((a, b) => a[0] - b[0]), tinyEx, small, tabsCut, bigIll, emoji: [...new Set(emoji)].slice(0, 6) };
  }, sel);
}

// Видимый фокус (п. 10): Tab с клавиатуры до первого элемента внутри экрана — у него контур или тень.
async function focusCheck(page, sel) {
  await page.evaluate((s) => { const r = document.querySelector(s); const h = r && (r.querySelector("h1, h2") || r);
    if (h) { if (!h.hasAttribute("tabindex")) h.setAttribute("tabindex", "-1"); h.focus(); } }, sel).catch(() => null);
  for (let i = 0; i < 6; i++) {
    await page.keyboard.press("Tab").catch(() => null);
    await sleep(120);
    const f = await page.evaluate((s) => {
      const a = document.activeElement, r = document.querySelector(s);
      if (!a || !r || !r.contains(a) || a === r) return null;
      const cs = getComputedStyle(a);
      const ring = (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0) || (cs.boxShadow && cs.boxShadow !== "none");
      return { tag: a.tagName.toLowerCase(), text: (a.innerText || a.getAttribute("aria-label") || "").trim().slice(0, 24), ring: !!ring,
        outline: `${cs.outlineStyle} ${cs.outlineWidth}`, shadow: (cs.boxShadow || "").slice(0, 40) };
    }, sel).catch(() => null);
    if (f) return f;
  }
  return null;
}

async function auditVariant(browser, base, [w, h], lang, staffAcc) {
  const variant = `${w}-${lang}`;
  const dict = L.loadDict(ROOT, lang);
  const mobile = w < 761;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1,
    locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
  await ctx.addInitScript((lg) => { try { localStorage.setItem("birge.lang", lg); } catch (e) { /* без хранилища */ } }, lang);
  await ctx.addInitScript(mapHook);
  if (staffAcc && staffAcc.user) {
    await ctx.request.post(base + "api/civic/v1/session/login", { data: { username: staffAcc.user, password: staffAcc.pass },
      headers: { Origin: base.replace(/\/$/, "") } }).catch(() => null);
  }
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message.slice(0, 160)));
  page.on("console", (m) => { if (m.type() === "error" && !NOISE.test(m.text())) errors.push(m.text().slice(0, 160)); });
  const word = (key, ru, kk) => T(dict, key, lang === "kk" ? kk : ru);
  const setMode = (mode) => L.headerClick(page, new RegExp("^" + esc(mode === "resident" ? word("common.role.resident", "Житель", "Тұрғын")
    : word("common.role.akimat", "Акимат", "Әкімдік")) + "$", "i"));
  const retryRe = new RegExp("^" + esc(T(dict, ["common.action.retry", "heat.retry"], lang === "kk" ? "Қайталау" : "Повторить")), "i");
  await page.goto(base);
  await page.waitForFunction(() => document.readyState === "complete" && document.body.innerText.length > 50, null, { timeout: 40000 }).catch(() => null);
  await sleep(2500);
  const globals = await page.evaluate((gs) => gs.filter((g) => !!window[g]), GLOBALS).catch(() => []);
  const SEL = "#birge-screen:not([hidden])";
  let mode = null;
  const mounted = async (sel = SEL) => page.evaluate((s) => { const r = document.querySelector(s); return r ? (r.innerText || "").trim().length : 0; }, sel).catch(() => 0);
  const errorsBefore = () => errors.length;
  // П3, кадры 02 и 08: обзорная карта (житель и акимат) — точки каких слоёв рисуются на масштабе < 13 и наезжают друг на друга.
  for (const md of ["resident", "akimat"]) {
    if (ONLY && !ONLY.has("map-overview")) break;
    await setMode(md); mode = md;
    await page.evaluate(() => { location.hash = "#map"; }).catch(() => null);
    await sleep(2500);
    await overview(page, variant, md);
  }

  for (const sc of SCREENS) {
    if (ONLY && !ONLY.has(sc.id)) continue;
    if (!sc.hash) { add(sc.id, sc.owner, variant, "экран", "NOT_RUN", "нет записи демо-мира для адреса"); continue; }
    const need = [].concat(sc.global || []);
    if (need.length && !need.some((g) => globals.includes(g))) { add(sc.id, sc.owner, variant, "экран", "NOT_RUN", `модуля ${need.join(" / ")} нет на странице`); continue; }
    if (mode !== sc.mode) { await setMode(sc.mode); mode = sc.mode; }
    const e0 = errorsBefore();
    await page.evaluate(() => { location.hash = "#map"; }).catch(() => null); await sleep(400);
    await page.evaluate((hh) => { location.hash = hh; }, sc.hash).catch(() => null);
    await sleep(2600);
    const rootSel = sc.root || SEL;
    let chars = await mounted(rootSel);
    if (sc.id === "agencies-calendar" && !(await page.evaluate((s) => !!document.querySelector(s + " .wcal"), SEL).catch(() => false))) {
      add(sc.id, sc.owner, variant, "вкладка «Календарь работ» в «Ведомствах» (IA_ROUND15)", "FAIL", "вкладки нет — открыт свой раздел #works-calendar");
      await page.evaluate((hh) => { location.hash = hh; }, sc.alt).catch(() => null); await sleep(2600);
      chars = await mounted();
    } else if (chars < 30 && sc.alt) {
      await page.evaluate((hh) => { location.hash = hh; }, sc.alt).catch(() => null); await sleep(2600);
      chars = await mounted();
    }
    const shot = path.join(OUT, `${variant}-${sc.id}.jpg`);
    await page.screenshot({ path: shot, type: "jpeg", quality: 70 }).catch(() => null);
    const f = path.basename(shot);
    if (chars < 30) { add(sc.id, sc.owner, variant, "экран открыт с содержимым", "FAIL", { chars, hash: sc.hash }, f); continue; }
    add(sc.id, sc.owner, variant, "экран открыт с содержимым", "PASS", { chars }, f);
    await measure(page, sc, variant, lang, w, f, rootSel, retryRe, errors, e0, true);
  }
  // Отдельные страницы R08.
  for (const pg of PAGES) {
    if (ONLY && !ONLY.has(pg.id)) continue;
    let url = null;
    for (const u of pg.urls) { const st = await fetch(base + u).then((r) => r.status).catch(() => 0); if (st === 200) { url = u; break; } }
    if (!url) { add(pg.id, pg.owner, variant, "страница", "NOT_RUN", `страницы нет в сборке (${pg.urls.join(" | ")})`); continue; }
    const e0 = errorsBefore();
    await page.goto(base + url + `?lang=${lang}&rotate=0`).catch(() => null);
    await sleep(3500);
    const shot = path.join(OUT, `${variant}-${pg.id}.jpg`);
    await page.screenshot({ path: shot, type: "jpeg", quality: 70 }).catch(() => null);
    const chars = await page.evaluate(() => (document.body.innerText || "").trim().length).catch(() => 0);
    add(pg.id, pg.owner, variant, "страница открыта с содержимым", chars > 60 ? "PASS" : "FAIL", { chars, url }, path.basename(shot));
    if (chars > 60) await measure(page, { ...pg, hash: null }, variant, lang, w, path.basename(shot), "body", retryRe, errors, e0, false, base + url + `?lang=${lang}&rotate=0`);
    await page.goto(base).catch(() => null); await sleep(2000); mode = null;
  }
  add("*", "по тексту ошибки", variant, "консоль без ошибок на новых экранах", errors.length ? "FAIL" : "PASS", errors.slice(0, 5));
  await ctx.close();
}

// Чей слой: префикс id слоя → роль (кольца FINAL-5.1 — civic-r03-point*: web/civic/map/civic-map.js, объекты карты R12).
const LAYER_OWNER = [[/^civic-r03-|^r12-|works|geo/i, "R12"], [/^r05-|build3d|project/i, "R05"], [/^r06-|ideas|proposal/i, "R06"],
  [/^r17-|crisis|incident/i, "R17"], [/^r16-|together|yard/i, "R16"], [/^r13-|meeting/i, "R13"]];
const layerOwner = (layers) => [...new Set(layers.map((l) => (LAYER_OWNER.find(([re]) => re.test(l)) || [null, "R07"])[1]))].join(" + ");

async function overview(page, variant, md) {
  const o = await mapOverview(page).catch((e) => { console.log("OVERVIEW-ERR", e.message); return null; });
  if (process.env.R10_DEBUG) console.log("OVERVIEW", JSON.stringify(o));
  const id = "map-overview-" + md;
  if (!o) { add(id, "R07", variant, "обзорная карта: точки слоёв на масштабе < 13", "NOT_RUN", "экземпляр карты не найден (перехват mapHook)"); return; }
  if (o.zoom >= 13) { add(id, "R07", variant, "обзорная карта: точки слоёв на масштабе < 13", "NOT_RUN", { zoom: o.zoom, why: "карта не на обзорном масштабе" }); return; }
  const owner = o.layers.length ? `${layerOwner(o.layers)} (+ R07)` : "R07";
  const shot = path.join(OUT, `${variant}-${id}.jpg`);
  await page.screenshot({ path: shot, type: "jpeg", quality: 70 }).catch(() => null);
  add(id, owner, variant, "обзорная карта (< 13): нет кучки наезжающих значков и колец (П3, кадры 02, 08)", o.close.length || o.underBadge.length ? "FAIL" : "PASS",
    { zoom: o.zoom, close: o.close, underBadge: o.underBadge, layers: o.layers }, path.basename(shot));
  if (!o.close.length && o.points) add(id, owner, variant, "обзорная карта (< 13): точки объектов — один значок с числом или скрыть (П3)", "WARN",
    { points: o.points, layers: o.layers, sample: o.sample });
}

async function measure(page, sc, variant, lang, w, f, SEL, retryRe, errors, e0, inShell, pageUrl) {
  const q = await uiScreen(page);
  const m = await screenMetrics(page, SEL);
  const own = sc.owner;
  add(sc.id, own, variant, "нет прокрутки вбок", q.scrollW <= q.innerW ? "PASS" : "FAIL", { scrollW: q.scrollW, w: q.innerW }, f);
  add(sc.id, own, variant, "нет ключей перевода и технических слов", q.raw.length || q.tech.length ? "FAIL" : "PASS", { raw: q.raw.slice(0, 4), tech: q.tech.slice(0, 4) });
  if (m) {
    const sizes = m.sizes.map(([s]) => s);
    const min = sizes.length ? sizes[0] : null;
    add(sc.id, own, variant, "шрифт не мельче 13 px", min === null || min >= 13 ? "PASS" : "FAIL", { min, ex: m.tinyEx, sizes: m.sizes.slice(0, 8) });
    add(sc.id, own, variant, "не больше 3 размеров шрифта (VISUAL_BRIEF §4 п. 3)", sizes.length <= 3 ? "PASS" : "WARN", { n: sizes.length, sizes });
    const under40 = m.small.filter((x) => x.h < 40 || x.w < 40), mid = m.small.filter((x) => !(x.h < 40 || x.w < 40));
    add(sc.id, own, variant, "зоны нажатия ≥ 44 px (п. 10)", under40.length ? "FAIL" : mid.length ? "WARN" : "PASS",
      { under40: under40.slice(0, 5), from40to43: mid.slice(0, 3), n: m.small.length });
  }
  add(sc.id, own, variant, "контраст текста ≥ 4,5:1 (крупный ≥ 3:1)", q.lowContrastN ? "FAIL" : "PASS", { n: q.lowContrastN, ex: (q.lowContrast || []).slice(0, 3) });
  if (lang === "kk") {
    // Перекрытие графикой (рамка SVG спарклайна, точка) рядом с подписью буквы часто не задевает — «смотреть», не FAIL.
    const svgOnly = (x) => /под «(svg|circle|path|g|rect|line|polyline|polygon|use)»$/i.test(x);
    const hard = q.clipped.filter((x) => !svgOnly(x)), soft = q.clipped.filter(svgOnly);
    add(sc.id, own, variant, "казахский не обрезан и не перекрыт", q.cutN || hard.length ? "FAIL" : soft.length ? "WARN" : "PASS",
      { cut: q.cut.slice(0, 3), clipped: hard.slice(0, 3), svg: soft.slice(0, 3) });
  }
  if (m && m.tabsCut.length) add(sc.id, own, variant, "вкладки целиком (полоса вкладок не режет подпись краем)", "WARN", { cut: m.tabsCut });
  if (m) add(sc.id, own, variant, "П1: иллюстрации ≤ 48 px, без эмодзи (AMENDMENTS П1)", m.bigIll.length || m.emoji.length ? "FAIL" : "PASS",
    { big: m.bigIll.slice(0, 4), emoji: m.emoji });
  // П3 — то, что видно на кадрах FINAL-5.1 (review_final51): лист раздела.
  const sh = inShell ? await sheetMetrics(page, SEL).catch(() => null) : null;
  if (sh) {
    if (sh.stickyPeek.length || sh.stickyOver.length) add(sc.id, own, variant, "липкая плашка: над ней не видно строк при прокрутке, на строку не наезжает (П3, кадр 05)", "FAIL",
      { peek: sh.stickyPeek.slice(0, 2), over: sh.stickyOver.slice(0, 2) }, f);
    add(sc.id, own, variant, "кнопка действия не обрезана краем листа (П3, кадр 07)", sh.cutEnd.length ? "FAIL" : sh.cutNow.length ? "WARN" : "PASS",
      { atEnd: sh.cutEnd.slice(0, 3), initial: sh.cutNow.slice(0, 3) }, f);
    if (sh.margins) add(sc.id, `R01 + ${own}`, variant, "лист не шире содержимого: без пустых полей слева и справа (П3, R01)",
      sh.margins.left > 96 && sh.margins.right > 96 ? "WARN" : "PASS", sh.margins, f);
    add(sc.id, own, variant, "нет серого квадрата с крошечным значком — «пропавшей картинки» (П1, П3 кадр 04)", sh.placeholder.length ? "WARN" : "PASS",
      sh.placeholder.length ? sh.placeholder : null, f);
  }
  const fc = await focusCheck(page, SEL);
  add(sc.id, own, variant, "видимый фокус с клавиатуры (п. 10)", fc === null ? "NOT_RUN" : fc.ring ? "PASS" : "FAIL", fc || "Tab не дошёл до элементов экрана");
  // Состояние «нет связи» (п. 8) — один размер на язык (1366): запросы модуля оборваны → понятный текст и «Повторить»,
  // после связи «Повторить» возвращает данные.
  if (w === 1366 && sc.api) {
    const block = (route) => route.abort("failed");
    await page.route(sc.api, block);
    if (inShell) {
      await page.evaluate(() => { location.hash = "#map"; }).catch(() => null); await sleep(500);
      await page.evaluate((hh) => { location.hash = hh; }, sc.hash).catch(() => null);
    } else await page.goto(pageUrl).catch(() => null);
    await sleep(sc.act ? 1500 : 3000);
    if (sc.act) { await sc.act(page, lang).catch(() => null); await sleep(2500); }
    const msg = await page.evaluate((s) => { const r = document.querySelector(s); return r ? (r.innerText || "").trim().replace(/\s+/g, " ").slice(0, 140) : ""; }, SEL).catch(() => "");
    const retry = await firstVisible(page.getByRole("button", { name: retryRe }));
    const shot = path.join(OUT, `${variant}-${sc.id}-offline.jpg`);
    await page.screenshot({ path: shot, type: "jpeg", quality: 70 }).catch(() => null);
    await page.unroute(sc.api, block);
    let back = null;
    if (retry) { await retry.click({ timeout: 4000 }).catch(() => null); await sleep(2500); back = !(await firstVisible(page.getByRole("button", { name: retryRe }))); }
    add(sc.id, own, variant, "нет связи: понятный текст и «Повторить», после связи данные вернулись (п. 8)",
      msg.length > 10 && retry && back !== false ? "PASS" : sc.legacy ? "WARN" : "FAIL", { message: msg.slice(0, 90), retry: !!retry, recovered: back }, path.basename(shot));
    // Ошибки консоли от оборванных запросов — ожидаемые, в счёт экрана не идут.
    errors.splice(e0);
  }
}

function report(meta) {
  const by = {};
  for (const r of rows) (by[r.screen] = by[r.screen] || []).push(r);
  const counts = { PASS: 0, WARN: 0, FAIL: 0, NOT_RUN: 0 };
  for (const r of rows) counts[r.status] = (counts[r.status] || 0) + 1;
  const md = [`# R10 · аудит новых экранов (VISUAL_BRIEF §4) — ${meta.label}`, "",
    `Сборка: \`${meta.root}\` @ ${meta.sha} · демо-мир: ${WORLD ? "да" : "нет"} · ${meta.when}`, "",
    `Итог: PASS ${counts.PASS} · WARN ${counts.WARN} · FAIL ${counts.FAIL} · NOT_RUN ${counts.NOT_RUN}`, "",
    "WARN — правило брифа, которое приёмку не валит (4+ размеров шрифта на экране, зоны 40–43 px при цели 44).",
    "В облаке подложка карты — упрощённый фон; стекло оценивается поверх белого (как светлая карта).", "",
    "| Экран | Владелец | Вариант | FAIL | WARN | NOT_RUN | Что именно |", "|---|---|---|---:|---:|---:|---|"];
  for (const [screen, list] of Object.entries(by)) {
    const variants = [...new Set(list.map((r) => r.variant))];
    for (const v of variants) {
      const rs = list.filter((r) => r.variant === v);
      const fail = rs.filter((r) => r.status === "FAIL"), warn = rs.filter((r) => r.status === "WARN"), nr = rs.filter((r) => r.status === "NOT_RUN");
      const what = [...fail, ...warn].map((r) => `${r.status === "FAIL" ? "❌" : "⚠"} ${r.check}: ${JSON.stringify(r.detail).slice(0, 110)}`).join("<br>")
        || (nr.length ? nr.map((r) => r.detail).join("; ").slice(0, 120) : "");
      md.push(`| ${screen} | ${rs[0].owner} | ${v} | ${fail.length} | ${warn.length} | ${nr.length} | ${what.replace(/\|/g, "/")} |`);
    }
  }
  md.push("", "## По владельцам (FAIL)", "");
  const owners = {};
  for (const r of rows.filter((x) => x.status === "FAIL")) (owners[r.owner] = owners[r.owner] || new Set()).add(`${r.screen}: ${r.check}`);
  for (const [o, s] of Object.entries(owners)) md.push(`- **${o}**: ${[...s].join("; ")}`);
  if (!Object.keys(owners).length) md.push("- нет");
  fs.writeFileSync(path.join(OUT, "AUDIT.md"), md.join("\n") + "\n");
  fs.writeFileSync(path.join(OUT, "AUDIT.json"), JSON.stringify({ ...meta, counts, rows }, null, 1));
  console.log("ИТОГ:", counts, "→", OUT);
}

(async () => {
  const srv = await L.startServer(ROOT, { demo: true, staff: true, world: WORLD });
  const browser = await chromium.launch();
  try {
    for (const size of SIZES) for (const lang of LANGS) await auditVariant(browser, srv.base, size, lang, srv.staff);
  } finally {
    await browser.close();
    await srv.stop();
  }
  report({ label: args.label || path.basename(ROOT), root: ROOT, sha: L.buildSha(ROOT), when: new Date().toISOString(), sizes: SIZES.map((s) => s.join("x")), langs: LANGS });
})().catch((e) => { console.error(e); process.exit(2); });
