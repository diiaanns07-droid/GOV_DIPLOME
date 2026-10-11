// R01 round 14, wave 2 (POLISH_WAVE_2, «Защита интерфейса от перегруза»): the menu per view and section screens.
//   - by default the map and the header look as in FINAL-candidate 8e67c65: only items whose module is in the build;
//   - ?screens=all shows the full menu: resident «Карта · Мои обращения · Рядом · Идеи · Ещё»,
//     akimat «Карта · Картина дня · Обращения · Проекты и идеи · Ещё» (≤ 5 items), rare sections in «Ещё»;
//   - a section is its own screen (#nearby, #ideas, #more, …), not a layer over the map; back returns to the map;
//   - a role module plugs in by window global or BirgeShell.registerScreen and gets api/lang/role; destroy on leave;
//   - extra map layers: one switch, at most one active, nothing on the map until a module registers a layer;
//   - a QR link (/?report=…) or a #target link does not change the chosen language.
// Usage: node tests/civic/R01/browser/r14_wave2.cjs <out_dir>
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(__dirname, "../../../..");
const OUT = path.resolve(process.argv[2] || "r14-wave2-out");
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet/i;
const R03_RING = /civic-r03-demo-ring/;
const checks = [];
const check = (name, ok, detail) => { checks.push({ name, status: ok ? "PASS" : "FAIL", detail: detail ?? null });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail !== undefined && detail !== null ? " — " + JSON.stringify(detail).slice(0, 400) : "")); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (args) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: REPO, env, stdio: ["ignore", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}
const ready = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && window.BirgeShell && typeof mapReady !== "undefined" && mapReady
  && document.querySelector("#birge-header"), null, { timeout: 40000 }).then(() => page.waitForTimeout(800));

async function newPage(ctx) {
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push("pageerror: " + e.message));
  page.on("console", (m) => {
    if (!["error", "warning"].includes(m.type()) || NOISE.test(m.text()) || R03_RING.test(m.text())) return;
    // Ключа модуля роли ещё нет в словаре R11 — у модуля свой запасной текст: это список для R11, не ошибка страницы.
    const key = /\[i18n\] неизвестный ключ: (\S+)/.exec(m.text());
    if (key) { MISSING_KEYS.add(key[1]); return; }
    page.errs.push(m.type() + ": " + m.text());
  });
  return page;
}
const MISSING_KEYS = new Set();
// Меню по схеме R11 IA_WAVE2 §1; в сборке видны только разделы с модулем роли (BirgeShell.navItems).
const IA = { akimat: ["map", "day", "inbox", "projects", "more"], resident: ["map", "mine", "nearby", "ideas", "more"] };
const inOrder = (ids, mode) => { let i = 0; for (const id of ids) { i = IA[mode].indexOf(id, i); if (i < 0) return false; i++; } return true; };
const menuOk = async (page, n, mode, must) => {
  const expected = await page.evaluate((m) => window.BirgeShell.navItems(m), mode);
  return JSON.stringify(n.ids) === JSON.stringify(expected) && inOrder(n.ids, mode) && must.every((id) => n.ids.includes(id));
};
// Visible menu items (labels and ids), pressed item, overflow.
const nav = (page) => page.evaluate(() => {
  const vis = (e) => e.getClientRects().length && getComputedStyle(e).display !== "none" && getComputedStyle(e).visibility !== "hidden";
  const items = [...document.querySelectorAll("#birge-header .birge-nav > button")].filter(vis);
  const all = [...document.querySelectorAll("#birge-header button")].filter(vis).map((b) => b.getBoundingClientRect());
  return {
    ids: items.map((b) => b.dataset.section || b.dataset.action), labels: items.map((b) => b.textContent.trim()),
    pressed: items.filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.dataset.section || b.dataset.action),
    out: all.filter((r) => r.right > innerWidth + 0.5 || r.left < -0.5).length, scrollW: document.documentElement.scrollWidth,
    mode: document.body.dataset.birgeMode, section: document.body.dataset.birgeSection, hash: location.hash, lang: document.documentElement.lang,
    layerBtn: !!document.querySelector("#birge-layer-btn") && vis(document.querySelector("#birge-layer-btn")),
  };
});
const screenState = (page) => page.evaluate(() => {
  const s = document.getElementById("birge-screen");
  return { shown: !!s && !s.hidden, screen: s?.dataset.screen || "", title: document.getElementById("birge-screen-title")?.textContent || "",
    text: s ? s.innerText.slice(0, 300) : "", mapHidden: getComputedStyle(document.getElementById("civic-root")).visibility === "hidden",
    fab: document.querySelector(".bc-fab") ? getComputedStyle(document.querySelector(".bc-fab")).display : "absent",
    focus: document.activeElement?.id || "" };
});

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r01-w2-"));
  const port = await freePort();
  const srv = await startServer(port, path.join(tmp, "civic.sqlite3"));
  const base = `http://127.0.0.1:${port}/`;
  const browser = await chromium.launch();
  try {
    // ---------------------------------------------------------------- default build: menu as in FINAL-candidate
    let ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
    let page = await newPage(ctx);
    await page.goto(base);
    await ready(page);
    let n = await nav(page);
    check("default akimat menu: IA order, only sections whose module is in the build (Карта · Картина дня always)",
      await menuOk(page, n, "akimat", ["map", "day"]), n);
    const layers0 = await page.evaluate(() => ({ active: window.BirgeShell.layer,
      options: [...document.querySelectorAll("#birge-layer-list input")].map((i) => i.value) }));
    check("default map: one «слои» button with «Проекты» (R05), no extra layer on — map shows complaints and city works only",
      n.layerBtn && layers0.active === null && JSON.stringify(layers0.options) === '["","projects"]', { n, layers0 });
    // Маркеры MapLibre (элемент из new Marker({element})): без transition на transform/left/top — значок не отстаёт.
    await page.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready"
      && [...document.querySelectorAll(".maplibregl-marker")].some((e) => e.getBoundingClientRect().width > 0), null, { timeout: 20000 }).catch(() => null);
    const markers = await page.evaluate(async () => {
      const els = [...document.querySelectorAll(".maplibregl-marker")];
      const bad = els.filter((e) => { const s = getComputedStyle(e); const props = s.transitionProperty.split(","), durs = s.transitionDuration.split(",");
        return props.some((p, i) => /^(all|transform|translate|left|top)$/.test(p.trim()) && parseFloat(durs[i % durs.length]) > 0); })
        .map((e) => e.className.split(" ")[0]);
      // Сдвиг карты: через 80 мс значок стоит там, где его точка (с transition 0,2 с он был бы ещё в пути).
      // eslint-disable-next-line no-undef
      const m = typeof map !== "undefined" && map && typeof map.panBy === "function" ? map : null;
      const one = els.find((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
      if (!m || !one) return { count: els.length, bad, lag: null, map: !!m, one: !!one };
      const before = one.getBoundingClientRect();
      m.panBy([140, 90], { duration: 0 });
      await new Promise((r) => setTimeout(r, 80));
      const after = one.getBoundingClientRect();
      const dx = after.left - before.left, dy = after.top - before.top;  // panBy(+x) двигает содержимое карты влево
      const moved = Math.min(Math.hypot(dx + 140, dy + 90), Math.hypot(dx - 140, dy - 90));
      m.panBy([-140, -90], { duration: 0 });
      return { count: els.length, bad, lag: Math.round(moved) };
    });
    check("map markers: no transition on transform/left/top; a badge follows the map at once (lag ≤ 2 px)",
      markers.count > 0 && markers.bad.length === 0 && markers.lag !== null && markers.lag <= 2, markers);
    await page.click("#birge-header [data-mode=resident]");
    await page.waitForTimeout(300);
    n = await nav(page);
    check("default resident menu: IA order, only sections with a module (Карта · Мои обращения always)",
      await menuOk(page, n, "resident", ["map", "mine"]) && n.labels.includes("Мои обращения"), n);
    // ---- читаемость карты (владелец, 11 окт): п. 3 панели, п. 7 границы районов, п. 8 наклон
    await page.click("#birge-header [data-mode=akimat]");
    await page.waitForTimeout(400);
    const read = await page.evaluate(() => {
      const box = (sel) => { const e = document.querySelector(sel); if (!e || !e.getClientRects().length || getComputedStyle(e).display === "none") return null;
        const r = e.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height }; };
      const bar = box(".topbar"), ex = box(".civic-explore"), legend = box("#birge-legend"), b3d = document.getElementById("birge-build3d-root");
      const lines = map.getLayer("civic-explore-lines") ? { color: map.getPaintProperty("civic-explore-lines", "line-color"),
        visible: map.getLayoutProperty("civic-explore-lines", "visibility") !== "none" } : null;
      let free = 0, total = 0;
      for (let y = 4; y < innerHeight; y += 8) for (let x = 4; x < innerWidth; x += 8) {
        total++; const e = document.elementFromPoint(x, y);
        if (e && (e.tagName === "CANVAS" || e.closest(".maplibregl-canvas-container"))) free++;
      }
      return { explore: document.body.dataset.birgeExplore, exploreInBar: !!(ex && bar && ex.t >= bar.t && ex.b <= bar.b + 1), barH: bar && Math.round(bar.h),
        legendH: legend && Math.round(legend.h), legendOpen: document.getElementById("birge-legend")?.dataset.open,
        titleShown: !!box("#birge-legend .r07-legend__title"), projects: b3d ? getComputedStyle(b3d).display : "absent",
        lines, pitch: Math.round(map.getPitch()), free: Math.round((free / total) * 1000) / 10 };
    });
    check("readability 3: district + street search in the header (1366), header 68 px", read.explore === "header" && read.exploreInBar && read.barH === 68, read);
    check("readability 3: legend is one compact row (no title) next to «?»; projects and «Что построить?» hidden by default",
      read.legendOpen === "false" && !read.titleShown && read.legendH <= 56 && read.projects === "none", read);
    check("readability 3: free map ≥ 60 % of the 1366×768 screen (akimat)", read.free >= 60, read.free);
    check("readability 7: thin neutral district borders on the city map (not green)", !!read.lines && read.lines.visible && read.lines.color === "#8e8a80", read.lines);
    await page.click("#birge-legend .birge-legend-q");
    await page.waitForTimeout(200);
    const opened = await page.evaluate(() => ({ open: document.getElementById("birge-legend").dataset.open,
      title: !!document.querySelector("#birge-legend .r07-legend__title")?.getClientRects().length,
      label: document.querySelector("#birge-legend .birge-legend-q").getAttribute("aria-label") }));
    check("legend «?» expands the title and hints (aria-label says how to fold it back)", opened.open === "true" && opened.title && /Свернуть/.test(opened.label || ""), opened);
    await page.click("#birge-legend .birge-legend-q");
    // п. 8: город — 0°, приближение ≥ 15 — плавный наклон 3D, отдаление < 14 — снова плоско.
    const tilt = async (z) => { await page.evaluate((zz) => map.easeTo({ zoom: zz, center: [71.4065, 51.1312], duration: 0 }), z);
      await page.waitForFunction(() => !map.isMoving(), null, { timeout: 8000 }).catch(() => {}); await page.waitForTimeout(1300);
      await page.waitForFunction(() => !map.isMoving(), null, { timeout: 8000 }).catch(() => {});
      return page.evaluate(() => ({ pitch: Math.round(map.getPitch()), pressed: document.getElementById("toggle-3d").getAttribute("aria-pressed") })); };
    const near = await tilt(15.6), far = await tilt(11);
    check("readability 8: city view flat (0°); zoom ≥ 15 tilts to 3D smoothly, zoom < 14 flattens; 3D button follows",
      read.pitch === 0 && near.pitch >= 35 && near.pressed === "true" && far.pitch === 0 && far.pressed === "false", { start: read.pitch, near, far });
    check("no page errors (default build)", page.errs.length === 0, page.errs);
    await ctx.close();

    // ---------------------------------------------------------------- ?screens=all: the full menu of wave 2
    ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
    page = await newPage(ctx);
    await page.goto(base + "?screens=all");
    await ready(page);
    n = await nav(page);
    check("akimat menu (wave 2): Карта · Картина дня · Обращения · Проекты и идеи · Ещё",
      JSON.stringify(n.ids) === '["map","day","inbox","projects","more"]'
      && JSON.stringify(n.labels) === '["Карта","Картина дня","Обращения","Проекты и идеи","Ещё"]', n);
    // «Ещё» у акимата — его инструменты (IA_WAVE2 §1): вопросы жителей, работы и отключения, QR-таблички, службы.
    await page.click("#birge-header .birge-nav [data-section=more]");
    await page.waitForTimeout(200);
    const akimatMenu = await page.evaluate(() => { const m = document.querySelector("#birge-header .birge-more-menu");
      return { role: m?.getAttribute("role"), shown: !!m && !m.hidden, items: [...(m?.querySelectorAll("[role=menuitem]") || [])].map((i) => i.textContent),
        expanded: document.querySelector("#birge-header .birge-nav [data-section=more]").getAttribute("aria-expanded") }; });
    check("akimat «Ещё» is a small menu (role=menu, ≤ 4): Вопросы жителей · Работы и отключения · QR-таблички · Службы",
      akimatMenu.role === "menu" && akimatMenu.shown && akimatMenu.expanded === "true"
      && JSON.stringify(akimatMenu.items) === '["Вопросы жителей","Работы и отключения","QR-таблички","Службы"]', akimatMenu);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(150);
    check("1366 akimat: header with 5 items fits, no horizontal scroll", n.out === 0 && n.scrollW <= 1366, n);
    await page.screenshot({ path: path.join(OUT, "w2_1366_akimat_menu.png") });
    await page.click("#birge-header [data-mode=resident]");
    await page.waitForTimeout(300);
    n = await nav(page);
    check("resident menu (wave 2): Карта · Мои обращения · Рядом · Идеи · Ещё",
      JSON.stringify(n.ids) === '["map","mine","nearby","ideas","more"]'
      && JSON.stringify(n.labels) === '["Карта","Мои обращения","Рядом","Идеи","Ещё"]', n);
    check("1366 resident: header fits", n.out === 0 && n.scrollW <= 1366, n);

    // A section is its own screen; the map stays alive under it; «Сообщить о проблеме» hidden there.
    await page.click("#birge-header [data-section=nearby]");
    await page.waitForTimeout(300);
    n = await nav(page);
    let sc = await screenState(page);
    check("«Рядом» opens its own screen (#nearby), not a map layer; pressed in the menu",
      n.hash === "#nearby" && n.section === "nearby" && sc.shown && sc.screen === "nearby" && sc.title === "Рядом" && JSON.stringify(n.pressed) === '["nearby"]', { n, sc });
    check("section screen covers the map (map hidden, no «Сообщить о проблеме» on top), focus on the screen title",
      sc.mapHidden && sc.fab === "none" && sc.focus === "birge-screen-title", sc);
    // «Рядом» — модуль R08 (с FINAL-2): экран роли, а не заглушка. Заглушку «скоро появится» проверяем на разделе
    // жителя, модуля которого в сборке нет (Идеи — R06 волна 2); есть все — NOT_RUN с причиной.
    const nearbyModule = await page.evaluate(() => typeof window.BirgeNearby?.mount === "function");
    if (nearbyModule) check("with the module: «Рядом» is the R08 screen (no «скоро появится»)", !/скоро появится/.test(sc.text) && sc.text.length > 40, sc.text.slice(0, 120));
    await page.screenshot({ path: path.join(OUT, "w2_1366_nearby.png") });
    const soonId = await page.evaluate(() => {
      const has = { nearby: ["BirgeNearby"], ideas: ["BirgeIdeas"] };
      return Object.keys(has).find((id) => !has[id].some((g) => typeof window[g]?.mount === "function")) || null; });
    if (soonId) {
      await page.goto(base + "?screens=all#" + soonId);
      await page.waitForFunction(() => window.BirgeShell && document.getElementById("birge-screen") && !document.getElementById("birge-screen").hidden, null, { timeout: 15000 }).catch(() => {});
      await page.waitForTimeout(300);
      sc = await screenState(page);
      check(`without the module (#${soonId}): understandable «скоро появится» with a way back (UX_BRIEF rule 7)`, /скоро появится/.test(sc.text) && /Вернуться к карте/.test(sc.text), sc.text);
      await page.screenshot({ path: path.join(OUT, `w2_1366_${soonId}_soon.png`) });
      await page.click("#birge-screen .birge-day-empty .bk-btn");
      await page.waitForTimeout(300);
      n = await nav(page); sc = await screenState(page);
      check(`«Вернуться к карте» → map, address without #${soonId}`, n.section === "map" && n.hash === "" && !sc.shown && !sc.mapHidden, { n, sc });
    } else {
      console.log("NOT_RUN «скоро появится»: у всех разделов жителя есть модули в этой сборке");
    }

    // «Ещё» — маленькое меню, не страница (IA_WAVE2 §1); у жителя в нём «Вопрос акиму».
    await page.click("#birge-header .birge-nav [data-section=more]");
    await page.waitForTimeout(200);
    const moreItems = await page.evaluate(() => [...document.querySelectorAll("#birge-header .birge-more-menu [role=menuitem]")].map((b) => b.dataset.section));
    sc = await screenState(page);
    check("«Ещё» (resident) opens a menu over the map (no screen): «Вопрос акиму»", !sc.shown && JSON.stringify(moreItems) === '["questions"]', { sc, moreItems });
    await page.click("#birge-header .birge-more-menu [data-section=questions]");
    await page.waitForTimeout(300);
    n = await nav(page); sc = await screenState(page);
    check("«Вопрос акиму» from «Ещё»: #questions screen, «Ещё» stays pressed, menu closed",
      n.hash === "#questions" && sc.screen === "questions" && sc.title === "Вопрос акиму" && JSON.stringify(n.pressed) === '["more"]'
      && await page.evaluate(() => document.querySelector("#birge-header .birge-more-menu").hidden), { n, sc });
    await page.goBack();
    await page.waitForTimeout(300);
    n = await nav(page); sc = await screenState(page);
    check("browser Back returns to the previous place (the map)", n.section === "map" && !sc.shown, { n, sc });
    await page.evaluate(() => { location.hash = "#ask"; });  // прежний адрес волны 2 — тот же раздел
    await page.waitForTimeout(300);
    n = await nav(page);
    check("old link #ask still opens «Вопрос акиму» (#questions)", n.section === "questions", n);
    await page.click("#birge-header [data-section=map]");
    await page.waitForTimeout(200);

    // Direct link to a section of the other view switches the view (link from a message, QR, «Ещё»).
    await page.click("#birge-header [data-mode=akimat]");
    await page.evaluate(() => { location.hash = "#ideas"; });
    await page.waitForTimeout(400);
    n = await nav(page);
    check("link #ideas in the akimat view → resident view, «Идеи» screen", n.mode === "resident" && n.section === "ideas", n);
    await page.click("#birge-header [data-mode=akimat]");
    await page.waitForTimeout(300);
    n = await nav(page);
    check("switching to «Акимат» from a resident-only section returns to the map", n.mode === "akimat" && n.section === "map", n);

    // ҚАЗ: menu labels from the dictionary/fallback, no raw keys.
    await page.click("#birge-header [data-lang=kk]");
    await page.waitForFunction(() => document.documentElement.lang === "kk", null, { timeout: 5000 }).catch(() => null);
    n = await nav(page);
    const rawKeys = await page.evaluate(() => (document.getElementById("birge-header").innerText.match(/\b(shell|common)\.[a-z_.]+\b/g) || []));
    check("ҚАЗ: akimat menu in Kazakh, no raw keys, header fits", n.lang === "kk" && n.labels.length === 5 && !n.labels.includes("Ещё")
      && n.labels.includes("Күн қорытындысы") && rawKeys.length === 0 && n.out === 0, { n, rawKeys });
    await page.screenshot({ path: path.join(OUT, "w2_1366_akimat_menu_kk.png") });
    await page.click("#birge-header [data-lang=ru]");
    await page.waitForTimeout(300);
    check("no page errors (?screens=all)", page.errs.length === 0, page.errs);
    await ctx.close();

    // ---------------------------------------------------------------- a role module plugs in (no ?screens=all)
    ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
    page = await newPage(ctx);
    await page.goto(base);
    await ready(page);
    await page.click("#birge-header [data-mode=resident]");
    const registered = await page.evaluate(() => window.BirgeShell.registerScreen({ id: "nearby", mount(root, opts) {
      window.__w2 = { mounted: true, api: typeof opts.api?.v2 === "function", lang: opts.lang, role: opts.role, section: opts.section,
        openTarget: typeof opts.openTarget === "function", close: typeof opts.close === "function" };
      root.innerHTML = "<h2>Что делают рядом</h2><p>пример</p>";
      return { destroy() { window.__w2.destroyed = true; } };
    } }));
    await page.waitForTimeout(200);
    n = await nav(page);
    check("registerScreen(nearby): «Рядом» appears in the resident menu only when the module is there", registered
      && await menuOk(page, n, "resident", ["map", "mine", "nearby"]) && n.labels[n.ids.indexOf("nearby")] === "Рядом", n);
    await page.click("#birge-header [data-section=nearby]");
    await page.waitForTimeout(300);
    const mounted = await page.evaluate(() => ({ w2: window.__w2, html: document.getElementById("birge-screen-root").innerText }));
    check("module mounted with api.v2, lang, role, section, openTarget, close", mounted.w2?.mounted && mounted.w2.api && mounted.w2.lang === "ru"
      && mounted.w2.role === "resident" && mounted.w2.section === "nearby" && mounted.w2.openTarget && mounted.w2.close && /Что делают рядом/.test(mounted.html), mounted);
    await page.click("#birge-header [data-section=map]");
    await page.waitForTimeout(200);
    const destroyed = await page.evaluate(() => window.__w2.destroyed === true);
    check("leaving the section destroys the module (no work behind the map)", destroyed, destroyed);
    await page.evaluate(() => window.BirgeShell.registerScreen({ id: "qr-sheets", href: "/civic/qr/", modes: ["akimat"],
      title: { ru: "Листы QR для остановок", kk: "Аялдамаларға арналған QR парақтары" } }));
    await page.click("#birge-header [data-mode=akimat]");
    await page.waitForTimeout(300);
    n = await nav(page);
    await page.click("#birge-header .birge-nav [data-section=more]");
    await page.waitForTimeout(200);
    const akimatMore = await page.evaluate(() => [...document.querySelectorAll("#birge-header .birge-more-menu [role=menuitem]")].map((a) => [a.textContent, a.getAttribute("href")]));
    check("akimat «Ещё» appears with a registered role link (QR sheets) and lists it; «Рядом» stays a resident section",
      n.ids.includes("more") && !n.ids.includes("nearby") && akimatMore.length <= 4
      && akimatMore.some(([label, href]) => label === "Листы QR для остановок" && href === "/civic/qr/"), { ids: n.ids, akimatMore });
    await page.keyboard.press("Escape");

    // ---------------------------------------------------------------- one extra map layer at a time
    const layerLog = await page.evaluate(() => {
      window.__layers = [];
      const mk = (id, ru) => ({ id, title: { ru, kk: ru },
        show(m) { window.__layers.push("show:" + id + (m && typeof m.addLayer === "function" ? "" : ":no-map")); },
        hide(m) { window.__layers.push("hide:" + id + (m && typeof m.addLayer === "function" ? "" : ":no-map")); } });
      window.BirgeShell.registerLayer(mk("ideas", "Идеи жителей"));
      window.BirgeShell.registerLayer(mk("nearby", "Что делают рядом"));
      return window.__layers.slice();
    });
    n = await nav(page);
    check("registering layers adds one «слои» button to the map tools; nothing is shown yet", n.layerBtn && layerLog.length === 0, { n, layerLog });
    await page.click("#birge-layer-btn");
    await page.check("#birge-layer-list input[value=ideas]");
    await page.waitForTimeout(100);
    await page.click("#birge-layer-btn");
    await page.check("#birge-layer-list input[value=nearby]");
    await page.waitForTimeout(100);
    await page.click("#birge-layer-btn");
    await page.check("#birge-layer-list input[value='']");
    const after = await page.evaluate(() => ({ log: window.__layers, active: window.BirgeShell.layer, body: document.body.dataset.birgeLayer }));
    check("at most one extra layer: ideas → nearby hides ideas first; «Только жалобы» hides it; show/hide get the MapLibre map",
      JSON.stringify(after.log) === '["show:ideas","hide:ideas","show:nearby","hide:nearby"]' && after.active === null && after.body === "", after);
    await page.screenshot({ path: path.join(OUT, "w2_1366_layer_switch.png") });
    check("no page errors (modules)", page.errs.length === 0, page.errs);
    await ctx.close();

    // ---------------------------------------------------------------- QR / link do not change the language
    ctx = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });
    page = await newPage(ctx);
    await page.goto(base);
    await ready(page);
    await page.evaluate(() => { localStorage.setItem("birge.mode", "akimat"); window.BirgeI18n.setLang("kk"); });
    await page.waitForFunction(() => document.documentElement.lang === "kk", null, { timeout: 5000 }).catch(() => null);
    await page.goto(base + "?report=osm-node-4109037549");
    await ready(page);
    n = await nav(page);
    const savedMode = await page.evaluate(() => localStorage.getItem("birge.mode"));
    check("QR link /?report=…: language stays ҚАЗ, resident view for this visit, saved view untouched",
      n.lang === "kk" && n.mode === "resident" && savedMode === "akimat", { n, savedMode });
    await page.goto(base + "#target=object:osm-node-4109037549");
    await ready(page);
    n = await nav(page);
    check("link #target=…: language stays ҚАЗ, map section", n.lang === "kk" && n.section === "map", n);
    await page.goto(base + "?screens=all#nearby");
    await ready(page);
    n = await nav(page); sc = await screenState(page);
    check("375: link #nearby opens the section screen inside the window, language ҚАЗ", n.lang === "kk" && sc.shown && sc.screen === "nearby" && n.scrollW <= 375, { n, sc });
    await page.screenshot({ path: path.join(OUT, "w2_375_nearby_kk.png") });
    check("no page errors (375, links)", page.errs.length === 0, page.errs);
    await ctx.close();
  } finally {
    await browser.close();
    srv.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  const summary = { pass: checks.filter((c) => c.status === "PASS").length, fail: checks.filter((c) => c.status === "FAIL").length };
  fs.writeFileSync(path.join(OUT, "r14_wave2.json"), JSON.stringify({ summary, checks }, null, 1));
  if (MISSING_KEYS.size) console.log("INFO keys of role modules missing in the R11 dictionary (module fallback text shown): " + [...MISSING_KEYS].sort().join(", "));
  console.log(JSON.stringify(summary));
  process.exit(summary.fail ? 1 : 0);
}
main().catch((e) => { console.error(e); process.exit(2); });
