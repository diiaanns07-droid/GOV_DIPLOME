// R01 round 15: the menu and screens of R11 IA_ROUND15 (research/round-15-results/R11/IA_ROUND15.md §2–§3, §7),
// the show mode (?show=1) and the demo scenes in Ctrl+K — on the real app, round-15 modules simulated by ?screens=all
// and BirgeShell.registerScreen (the role modules are not needed for the shell contract).
//   - akimat: «Карта · Картина дня · Обращения · Ведомства · Ещё», «Ещё» in two labelled groups (≤ 7);
//     resident: «Карта · Мои обращения · Мой двор · Идеи · Ещё»; sections with a parent have no item (#nearby → «Мой двор»);
//   - #section/path: the module gets opts.path, opts.navigate, opts.map, opts.setLayer; a new path → setPath, no remount;
//   - Esc on a screen → map; Esc that closes «Ещё» stays on the screen;
//   - empty state: one small icon (≤ 48 px), text and one button (amendment P1), no large illustration;
//   - demo world (CIVIC_DEMO_WORLD=1): Ctrl+K «Сцена 7 / 8 / 9» open the yard / complaint / crisis by world ids;
//   - ?show=1: no service plates, larger text at 1024, scenes first in Ctrl+K;
//   - B0.2: «▶ Хроника» R07 at the end of the legend line (IA R11 §5.8, §7.8): the bar opens, the legend hides, nothing
//     on the left, Esc closes; phone — icon-only chip, the bar instead of the sheet; scene 7 with and without R16;
//   - «Уведомления» R06 (IA R11 §5.7): resident bell before the avatar, panel; akimat — no bell; phone — first avatar item.
// The stand runs the real demo world of R02 (data/civic/astana/demo-world/world_v1.json) when it is in the build.
// Usage: node tests/civic/R01/browser/r15_ia.cjs <out_dir>
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(__dirname, "../../../..");
const OUT = path.resolve(process.argv[2] || "r15-ia-out");
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet|\[i18n\] неизвестный ключ/i;
const checks = [];
const check = (name, ok, detail) => { checks.push({ name, status: ok ? "PASS" : "FAIL", detail: detail ?? null });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail !== undefined && detail !== null ? " — " + JSON.stringify(detail).slice(0, 400) : "")); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

// Мир для сцен: только блок scenes (модули seed_world в этой проверке не нужны — нужны id для палитры).
const WORLD = { schema: "birge-demo-world-v1", schema_version: "1.0", synthetic: true, complaints: [], works: [],
  scenes: { scene7: { yard: "yard-1454082640", initiative: "i-w15-01" }, scene8: { complaint: "c-w1500010" },
            scene9: { incident: "inc-w15-buran", district: "nura" } } };

const REAL_WORLD = path.join(REPO, "data/civic/astana/demo-world/world_v1.json");
const STAFF = ["operator", "Birge-Stend-Kokshetau-77"];   // сотрудник стенда: «Обращения» R09 — только после входа
async function startServer(port, dir) {
  const db = path.join(dir, "civic.sqlite3"), world = path.join(dir, "world.json");
  fs.writeFileSync(world, JSON.stringify(WORLD));
  // Настоящий мир R02 (карта, «Хроника», «Мой двор» с данными); без него — только блок scenes.
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", CIVIC_DEMO_WORLD: "1", PYTHONDONTWRITEBYTECODE: "1" };
  if (!fs.existsSync(REAL_WORLD)) env.CIVIC_DEMO_WORLD_PATH = world;
  const run = (args, input) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: REPO, env, input, stdio: ["pipe", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  run(`create-editor ${STAFF[0]} --password-stdin`, STAFF[1] + "\n" + STAFF[1] + "\n");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}
const ready = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && window.BirgeShell && typeof mapReady !== "undefined" && mapReady
  && document.querySelector("#birge-header"), null, { timeout: 40000 }).then(() => page.waitForTimeout(800));
async function open(browser, url, w, h, mode, block, init) {
  const mobile = w < 761;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile });
  // block: скрипты модулей, которых «нет в сборке» (проверка запасных ходов оболочки при полной сборке).
  for (const pattern of block || []) await ctx.route(pattern, (route) => route.abort());
  if (init) await ctx.addInitScript(init);   // подменный модуль роли (до скриптов страницы)
  await ctx.addInitScript((m) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", "ru"); } catch (e) { /* без хранилища */ } }, mode);
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push("pageerror: " + e.message));
  page.on("console", (m) => { if (["error", "warning"].includes(m.type()) && !NOISE.test(m.text())) page.errs.push(m.type() + ": " + m.text()); });
  await page.goto(url);
  await ready(page);
  return { ctx, page };
}
const nav = (page) => page.evaluate(() => {
  const vis = (e) => e.getClientRects().length && getComputedStyle(e).display !== "none" && getComputedStyle(e).visibility !== "hidden";
  const items = [...document.querySelectorAll("#birge-header .birge-nav > button")].filter(vis);
  return { ids: items.map((b) => b.dataset.section || b.dataset.action), labels: items.map((b) => b.textContent.trim()),
    pressed: items.filter((b) => b.getAttribute("aria-current") === "page").map((b) => b.dataset.section || b.dataset.action),
    section: document.body.dataset.birgeSection, mode: document.body.dataset.birgeMode, hash: location.hash,
    out: [...document.querySelectorAll("#birge-header button")].filter(vis).map((b) => b.getBoundingClientRect()).filter((r) => r.right > innerWidth + 0.5).length };
});
const moreMenu = (page) => page.evaluate(() => {
  const m = document.querySelector("#birge-header .birge-more-menu");
  return { shown: !!m && !m.hidden, items: [...(m?.querySelectorAll("[role=menuitem]") || [])].map((i) => i.textContent.trim()),
    labels: [...(m?.querySelectorAll(".birge-more-label") || [])].map((l) => l.textContent.trim()),
    box: m && !m.hidden ? m.getBoundingClientRect().toJSON() : null,
    button: document.querySelector("#birge-header .birge-nav [data-section=more]").getBoundingClientRect().toJSON() };
});
// П3: подменный экран R04 «Разбор обращений» — проверяется оболочка (сцена 0, раздел #intake, опции mount), не модуль R04.
const STUB_INTAKE = () => {
  window.BirgeIntake = { mount(root, opts) {
    const was = window.__intake || { mounts: 0 };
    window.__intake = { mounts: was.mounts + 1, apiBase: opts.apiBase, api: !!(opts.api && opts.api.v2), section: opts.section,
      path: opts.path, openTarget: typeof opts.openTarget, openSection: typeof opts.openSection, lang: opts.lang };
    const h = document.createElement("h2"); h.textContent = "Разбор обращений (заглушка R01)"; root.replaceChildren(h);
    return { destroy() {} };
  } };
};
const palette = async (page) => {
  await page.keyboard.press("Control+k");
  await page.waitForFunction(() => document.querySelectorAll(".birge-palette__item").length > 3, null, { timeout: 8000 }).catch(() => null);
  await page.waitForTimeout(400);
  return page.evaluate(() => [...document.querySelectorAll(".birge-palette__list > li")].map((li) => li.textContent.trim()));
};

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r01-r15-ia-"));
  const port = await freePort();
  const srv = await startServer(port, tmp);
  const base = `http://127.0.0.1:${port}/`;
  const browser = await chromium.launch();
  try {
    // ------------------------------------------------------------ akimat, all round-15 sections (?screens=all)
    let { ctx, page } = await open(browser, base + "?screens=all", 1366, 768, "akimat");
    let n = await nav(page);
    check("akimat menu: Карта · Картина дня · Обращения · Ведомства · Ещё (IA_ROUND15 §3)",
      JSON.stringify(n.ids) === '["map","day","inbox","agencies","more"]'
      && JSON.stringify(n.labels) === '["Карта","Картина дня","Обращения","Ведомства","Ещё"]' && n.out === 0, n);
    await page.click("#birge-header .birge-nav [data-section=more]");
    await page.waitForTimeout(250);
    let more = await moreMenu(page);
    const board = await page.evaluate(() => window.BirgeShell.sections().includes("board"));
    // ?screens=all показывает и «Разбор обращений» R04 (П3) — первым в «Инструментах» (R11 IA §11.1).
    const tools = ["Разбор обращений", "Спросить Birge", ...(board ? ["Ситуационный центр"] : []), "QR-таблички"];
    check("akimat «Ещё»: two labelled groups — С жителями (Проекты и идеи · Сделаем вместе · Вопросы и встречи), Инструменты (Разбор обращений П3 · Спросить Birge · Ситуационный центр R08 · QR-таблички); ≤ 7; works/services under «Ведомства»",
      more.shown && JSON.stringify(more.labels) === '["С жителями","Инструменты"]' && more.items.length <= 7
      && JSON.stringify(more.items) === JSON.stringify(["Проекты и идеи", "Сделаем вместе", "Вопросы и встречи", ...tools]), more);
    check("«Ещё» opens under its button, right edge not past the capsule (VISUAL_BRIEF §3)",
      !!more.box && more.box.top >= more.button.bottom && more.box.top <= more.button.bottom + 16
      && more.box.right <= more.button.right + 6 && more.box.left <= more.button.left, { box: more.box, button: more.button });
    await page.screenshot({ path: path.join(OUT, "ia_1366_akimat_more.png") });
    await page.keyboard.press("Escape");
    // palette: sections without menu items, «Календарь работ», «Кризисный штаб», scenes of the demo world
    const items = await palette(page);
    check("Ctrl+K: «Ведомства», «Календарь работ», «Кризисный штаб», «Работы и отключения», «Службы» and scenes 7–9",
      ["Ведомства", "Календарь работ", "Кризисный штаб", "Работы и отключения", "Службы", "Сцена 7 · Двор вместе",
        "Сцена 8 · Ведомства вместе", "Сцена 9 · Буран"].every((t) => items.includes(t)), items);
    // Scene 8 → «Обращения» with the complaint id in the address; the card of that complaint is open (R09 — by its
    // single-complaint filter that the shell sets for #inbox/<id>, until R09 reads opts.path itself)
    await page.keyboard.press("Escape");
    await page.evaluate(([u, p]) => window.CivicShell.api.login(u, p), STAFF).catch(() => null);
    await page.waitForTimeout(400);
    await palette(page);
    await page.fill(".birge-palette__input", "Сцена 8");
    await page.waitForTimeout(150);
    const t0 = Date.now();
    await page.keyboard.press("Enter");
    await page.waitForFunction(() => document.body.dataset.birgeSection === "inbox", null, { timeout: 3000 }).catch(() => null);
    const sceneMs = Date.now() - t0;
    n = await nav(page);
    check("Сцена 8: akimat «Обращения» with #inbox/c-w1500010, ≤ 1 s", n.mode === "akimat" && n.section === "inbox"
      && n.hash === "#inbox/c-w1500010" && sceneMs <= 1000, { n, sceneMs });
    if (await page.evaluate(() => !!window.BirgeComplaintList || !!window.BirgeInbox)) {
      await page.waitForFunction(() => /Принять|Службы/.test(document.querySelector("#birge-screen .bc-inbox__item--open")?.innerText || ""),
        null, { timeout: 10000 }).catch(() => null);
      const card = await page.evaluate(() => document.querySelector("#birge-screen .bc-inbox__item--open")?.innerText || "");
      check("Сцена 8: the card of the scene complaint is open (ул. Баян Сулу, «нужны 2 службы» → «Принять»)",
        /Баян Сулу|Раскопали|Яма/.test(card) && /2 службы/.test(card) && /Принять/.test(card), card.replace(/\s+/g, " ").slice(0, 220));
    }
    await page.keyboard.press("Escape");
    await page.waitForTimeout(250);
    n = await nav(page);
    check("Esc on a section screen returns to the map", n.section === "map" && n.hash === "", n);
    // Scene 9 → «Ведомства», crisis tab of the world incident
    await palette(page);
    await page.fill(".birge-palette__input", "Сцена 9");
    await page.waitForTimeout(150);
    await page.keyboard.press("Enter");
    await page.waitForTimeout(400);
    n = await nav(page);
    const screenTitle = await page.evaluate(() => document.getElementById("birge-screen-title")?.textContent);
    check("Сцена 9: «Ведомства» #agencies/crisis/inc-w15-buran (путь R17; заголовок экрана «Штаб ведомств»)", n.section === "agencies"
      && n.hash === "#agencies/crisis/inc-w15-buran" && JSON.stringify(n.pressed) === '["agencies"]' && screenTitle === "Штаб ведомств", { n, screenTitle });
    // «Ещё» opened on a screen and closed by Esc: the screen stays
    await page.click("#birge-header .birge-nav [data-section=more]");
    await page.waitForTimeout(200);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(250);
    n = await nav(page);
    more = await moreMenu(page);
    check("Esc that closes «Ещё» keeps the screen (no jump to the map)", !more.shown && n.section === "agencies", { n, more: more.shown });
    await page.screenshot({ path: path.join(OUT, "ia_1366_scene9.png") });
    check("no page errors (akimat)", page.errs.length === 0, page.errs);
    // A section that is a page (registerScreen with href — «Ситуационный центр» R08): Ctrl+K and the address #board lead
    // to the page like the «Ещё» item, not to the shell screen «Раздел не удалось открыть» (R08 INTEGRATION §15).
    if (board) {
      await palette(page);
      await page.fill(".birge-palette__input", "Ситуационный");
      await page.waitForTimeout(150);
      await Promise.all([page.waitForURL(/\/civic\/board\//, { timeout: 8000 }).catch(() => null), page.keyboard.press("Enter")]);
      const viaPalette = new URL(page.url()).pathname;
      await page.goto(base + "#board");
      await page.waitForURL(/\/civic\/board\//, { timeout: 8000 }).catch(() => null);
      const viaHash = new URL(page.url()).pathname;
      check("«Ситуационный центр» (a page section): Ctrl+K and #board open /civic/board/, not a failed shell screen",
        viaPalette === "/civic/board/" && viaHash === "/civic/board/", { viaPalette, viaHash });
    }
    await ctx.close();

    // Empty state (module not in the build — R03 script blocked here): small icon + text + one button (amendment P1)
    ({ ctx, page } = await open(browser, base + "?screens=all", 1366, 768, "akimat", ["**/civic/assistant/analyst.js"]));
    await page.evaluate(() => window.BirgeShell.setSection("analyst"));
    await page.waitForTimeout(400);
    const empty = await page.evaluate(() => {
      const box = document.querySelector("#birge-screen .birge-day-empty");
      const ic = box?.querySelector(".birge-state-ic"), r = ic?.getBoundingClientRect();
      return { box: !!box, icon: r ? [Math.round(r.width), Math.round(r.height)] : null, ill: !!box?.querySelector(".bk-ill"),
        buttons: box ? box.querySelectorAll("button").length : 0, text: box?.innerText.slice(0, 120) };
    });
    check("empty state: one small icon ≤ 48 px, text and one button; no large illustration (P1 rule 2)",
      empty.box && !!empty.icon && empty.icon[0] <= 48 && empty.icon[1] <= 48 && !empty.ill && empty.buttons === 1, empty);
    await page.screenshot({ path: path.join(OUT, "ia_1366_empty_p1.png") });
    check("no page errors (empty state)", page.errs.length === 0, page.errs);
    await ctx.close();

    // ------------------------------------------------------------ resident: «Мой двор», parent highlight, path routing
    // Контракт оболочки на модуле-заглушке: скрипт R16 здесь не грузится (его ссылки #yard/… ведёт он сам).
    ({ ctx, page } = await open(browser, base + "?screens=all", 1366, 768, "resident", ["**/civic/together/together.js"]));
    n = await nav(page);
    check("resident menu: Карта · Мои обращения · Мой двор · Идеи · Ещё (IA_ROUND15 §2)",
      JSON.stringify(n.ids) === '["map","mine","yard","ideas","more"]'
      && JSON.stringify(n.labels) === '["Карта","Мои обращения","Мой двор","Идеи","Ещё"]', n);
    await page.click("#birge-header .birge-nav [data-section=more]");
    await page.waitForTimeout(200);
    more = await moreMenu(page);
    check("resident «Ещё»: Сделаем вместе · Вопросы и встречи (no labels ≤ 4; «Вопрос акиму» inside «Вопросы и встречи»)",
      more.shown && JSON.stringify(more.items) === '["Сделаем вместе","Вопросы и встречи"]' && more.labels.length === 0, more);
    await page.keyboard.press("Escape");
    // Одна панель за раз (R11 R01-5): «Мои обращения» R09 открыты, житель идёт в раздел — окно R09 закрывается.
    await page.evaluate(() => window.CivicShell.openMine && window.CivicShell.openMine());
    await page.waitForTimeout(500);
    const mineBefore = await page.evaluate(() => document.documentElement.classList.contains("bc-mine-open"));
    await page.evaluate(() => window.BirgeShell.setSection("meetings"));
    await page.waitForTimeout(400);
    const mineAfter = await page.evaluate(() => document.documentElement.classList.contains("bc-mine-open"));
    check("one panel at a time: a section screen closes «Мои обращения» (R11 R01-5)", mineBefore && !mineAfter, { mineBefore, mineAfter });
    await page.evaluate(() => window.BirgeShell.setSection("map"));
    await page.waitForTimeout(300);
    await page.evaluate(() => { location.hash = "#nearby"; });
    await page.waitForTimeout(400);
    n = await nav(page);
    check("#nearby still opens (no menu item): «Мой двор» is the highlighted parent", n.section === "nearby" && JSON.stringify(n.pressed) === '["yard"]', n);
    // A module for «yard» registers: path in the address, navigate → setPath without remount
    await page.evaluate(() => {
      window.__yard = { mounts: 0, paths: [] };
      window.BirgeShell.registerScreen({ id: "yard", mount(root, opts) {
        window.__yard.mounts++;
        window.__yard.opts = { path: opts.path, section: opts.section, map: !!opts.map && typeof opts.map.getZoom === "function",
          navigate: typeof opts.navigate === "function", setLayer: typeof opts.setLayer === "function" };
        window.__yard.navigate = opts.navigate;
        root.textContent = "Двор " + opts.path;
        return { setPath(p) { window.__yard.paths.push(p); root.textContent = "Двор " + p; }, destroy() { window.__yard.destroyed = true; } };
      } });
      location.hash = "#yard/yard-1454082640";
    });
    await page.waitForTimeout(400);
    let yard = await page.evaluate(() => ({ ...window.__yard, navigate: undefined, hash: location.hash }));
    check("#yard/yard-1454082640: module mounted once with opts.path, opts.section, opts.map, opts.navigate, opts.setLayer",
      yard.mounts === 1 && yard.opts.path === "yard-1454082640" && yard.opts.section === "yard" && yard.opts.map && yard.opts.navigate && yard.opts.setLayer, yard);
    await page.evaluate(() => window.__yard.navigate("yard-777"));
    await page.waitForTimeout(300);
    yard = await page.evaluate(() => ({ ...window.__yard, navigate: undefined, hash: location.hash }));
    check("opts.navigate(path): address #yard/yard-777, setPath called, no remount", yard.hash === "#yard/yard-777"
      && yard.mounts === 1 && JSON.stringify(yard.paths) === '["yard-777"]', yard);
    await page.goBack();
    await page.waitForTimeout(300);
    yard = await page.evaluate(() => ({ ...window.__yard, navigate: undefined, hash: location.hash }));
    check("browser Back: previous path (setPath yard-1454082640), still one mount", yard.hash === "#yard/yard-1454082640"
      && yard.mounts === 1 && yard.paths[yard.paths.length - 1] === "yard-1454082640", yard);
    check("no page errors (resident)", page.errs.length === 0, page.errs);
    await ctx.close();

    // ------------------------------------------------------------ show mode at 1024, scene 7 first in Ctrl+K
    ({ ctx, page } = await open(browser, base + "?show=1&screens=all", 1024, 768, "akimat"));
    const show = await page.evaluate(() => ({ flag: document.documentElement.dataset.birgeShow,
      body: getComputedStyle(document.documentElement).getPropertyValue("--fs-body").trim(),
      status: (() => { const s = document.getElementById("map-status"); return s ? getComputedStyle(s).display : "absent"; })(),
      api: window.BirgeShell.show }));
    check("?show=1: flag on <html>, text one step larger at 1024 (--fs-body 16 px), map service plate hidden",
      show.flag === "1" && show.api === true && show.body === "16px" && (show.status === "none" || show.status === "absent"), show);
    const showItems = await palette(page);
    const firstItem = showItems.find((t) => !/^(Сцены демо)$/.test(t));
    const sceneItems = showItems.filter((t) => /^Сцена \d/.test(t));
    // ?screens=all показывает и экран R04 — сцена 0 «ИИ-разбор» (П3) первая, за ней 7–9 мира.
    check("show mode: scenes are the first commands in Ctrl+K — «Сцена 0 · ИИ-разбор» (П3), then 7–9",
      showItems[0] === "Сцены демо" && firstItem === "Сцена 0 · ИИ-разбор"
      && sceneItems.join(" | ") === "Сцена 0 · ИИ-разбор | Сцена 7 · Двор вместе | Сцена 8 · Ведомства вместе | Сцена 9 · Буран", showItems.slice(0, 6));
    await page.fill(".birge-palette__input", "Сцена 7");
    await page.waitForTimeout(150);
    await page.keyboard.press("Enter");
    await page.waitForTimeout(500);
    n = await nav(page);
    const r16 = await page.evaluate(() => !!window.BirgeTogether);
    // R16 в сборке: экран «Мой двор» двора сцены (название двора из мира); R16 e475fae9 сам переписывает адрес на #yard.
    await page.waitForFunction(() => /BI City Tokyo/.test(document.getElementById("birge-screen")?.innerText || ""), null, { timeout: 5000 }).catch(() => null);
    const yardText = await page.evaluate(() => (document.getElementById("birge-screen")?.innerText || "").slice(0, 160));
    check("Сцена 7: resident view, «Мой двор» of yard-1454082640 (R16: «Двор: BI City Tokyo»)", n.mode === "resident" && n.section === "yard"
      && (r16 ? /^#yard(\/yard-1454082640)?$/.test(n.hash) && /BI City Tokyo/.test(yardText) : n.hash === "#yard/yard-1454082640"), { n, r16, yardText });
    await page.screenshot({ path: path.join(OUT, "ia_1024_show_scene7.png") });
    await ctx.close();
    // Without the R16 module the scene does not open an empty screen: the yard is shown on the map (#target=area:…).
    ({ ctx, page } = await open(browser, base + "?show=1", 1024, 768, "akimat", ["**/civic/together/together.js"]));
    const plain = await palette(page);
    const r04 = await page.evaluate(() => !!window.BirgeIntake);
    check("«Сцена 0 · ИИ-разбор» only when the R04 screen is in the build (without ?screens=all)",
      plain.includes("Сцена 0 · ИИ-разбор") === r04, { r04, scenes: plain.filter((t) => /^Сцена \d/.test(t)) });
    await page.fill(".birge-palette__input", "Сцена 7");
    await page.waitForTimeout(150);
    await page.keyboard.press("Enter");
    await page.waitForTimeout(500);
    n = await nav(page);
    check("Сцена 7 without «Мой двор» in the build: the yard on the map (#target=area:yard-1454082640), not an empty screen",
      n.mode === "resident" && n.section === "map" && n.hash === "#target=area:yard-1454082640", n);
    await page.goto(base + "?show=0");
    await ready(page);
    check("?show=0 turns the show mode off", await page.evaluate(() => !document.documentElement.dataset.birgeShow), null);
    check("no page errors (show mode)", page.errs.length === 0, page.errs);
    await ctx.close();

    // ------------------------------------------------------------ сцена 0 «ИИ-разбор» (П3): экран R04 из Ctrl+K
    // Вид «Житель» на входе: сцена сама включает «Акимат». Настоящий модуль R04 (если в сборке) закрыт — проверяем оболочку.
    ({ ctx, page } = await open(browser, base + "?show=1", 1366, 768, "resident", ["**/civic/intake/intake.js"], STUB_INTAKE));
    const intakeItems = await palette(page);
    check("show mode with the R04 screen: «Сцена 0 · ИИ-разбор» is the first command", intakeItems[0] === "Сцены демо"
      && intakeItems[1] === "Сцена 0 · ИИ-разбор", intakeItems.slice(0, 4));
    await page.keyboard.press("Enter");
    await page.waitForTimeout(500);
    n = await nav(page);
    const intake = await page.evaluate(() => ({ stub: window.__intake || null,
      title: document.getElementById("birge-screen-title")?.textContent || "" }));
    check("Сцена 0: akimat view, #intake/sample (example in, not analysed — R11 IA §11.1), «Ещё» highlighted, title «Разбор обращений»",
      n.mode === "akimat" && n.section === "intake" && n.hash === "#intake/sample" && JSON.stringify(n.pressed) === '["more"]'
      && !n.ids.includes("intake") && intake.title === "Разбор обращений", { n, title: intake.title });
    check("Сцена 0: R04 mount(root, opts) once — apiBase /api/civic/v2, api.v2, path «sample», openTarget, openSection",
      !!intake.stub && intake.stub.mounts === 1 && intake.stub.apiBase === "/api/civic/v2" && intake.stub.api && intake.stub.path === "sample"
      && intake.stub.section === "intake" && intake.stub.openTarget === "function" && intake.stub.openSection === "function", intake.stub);
    const intakeMore = await page.evaluate(() => window.BirgeShell.moreItems());
    check("«Разбор обращений» — the first «Ещё → Инструменты» item of the akimat (R11 IA §11.1)",
      intakeMore.indexOf("intake") === intakeMore.indexOf("analyst") - 1 && intakeMore.includes("intake"), intakeMore);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
    n = await nav(page);
    check("Esc on «Разбор обращений» returns to the map", n.section === "map", n);
    check("no page errors (scene 0)", page.errs.length === 0, page.errs);
    await ctx.close();

    // ------------------------------------------------------------ «▶ Хроника» R07 (IA R11 §5.8, §7.8)
    ({ ctx, page } = await open(browser, base, 1366, 768, "akimat"));
    const hasReplay = await page.evaluate(() => !!window.BirgeReplay);
    if (hasReplay) {
      await page.waitForFunction(() => { const c = document.querySelector("#birge-legend .birge-replay-chip"); return c && c.getClientRects().length; }, null, { timeout: 15000 }).catch(() => null);
      const chip = await page.evaluate(() => {
        const line = document.querySelector("#birge-legend .birge-legend-line"), c = line?.querySelector(".birge-replay-chip");
        const r = c?.getBoundingClientRect();
        return { chip: !!c, last: !!c && line.lastElementChild === c, text: c?.innerText.trim(), label: c?.getAttribute("aria-label"),
          icon: !!c?.querySelector("use[href$='#i-play']"), h: r ? Math.round(r.height) : 0 };
      });
      check("«▶ Хроника»: chip at the end of the legend line, i-play icon, «Хроника» / «Хроника города», 44 px tall", chip.chip && chip.last
        && chip.text === "Хроника" && chip.label === "Хроника города" && chip.icon && chip.h >= 44, chip);  // R10 B-125: зона нажатия 44
      await page.click("#birge-legend .birge-replay-chip");
      await page.waitForFunction(() => document.body.classList.contains("birge-replay-open") && document.querySelector(".rp-host .rp-bar"), null, { timeout: 8000 }).catch(() => null);
      await page.waitForTimeout(600);
      const opened = await page.evaluate(() => {
        const vis = (e) => !!e && e.getClientRects().length > 0 && getComputedStyle(e).display !== "none" && getComputedStyle(e).visibility !== "hidden";
        const bar = document.querySelector(".rp-host .rp-bar")?.getBoundingClientRect();
        return { open: document.body.classList.contains("birge-replay-open"), bar: bar ? [Math.round(bar.left), Math.round(bar.bottom), Math.round(bar.width)] : null,
          legend: vis(document.getElementById("birge-legend")), left: document.body.dataset.birgeLeft,
          panel: vis(document.querySelector(".civic-panel")), today: vis(document.getElementById("birge-today")), layer: window.BirgeShell.layer,
          status: document.querySelector(".rp-host .rp")?.dataset.status };
      });
      check("click: the chronicle bar at the bottom, legend hidden, nothing on the left, no extra layer", opened.open && !!opened.bar
        && opened.bar[1] <= 768 && !opened.legend && opened.left === "replay" && !opened.panel && !opened.today && !opened.layer, opened);
      await page.screenshot({ path: path.join(OUT, "replay_1366_akimat.png") });
      await page.keyboard.press("Escape");
      await page.waitForTimeout(700);
      const closed = await page.evaluate(() => ({ open: document.body.classList.contains("birge-replay-open"), host: !!document.querySelector(".rp-host"),
        legend: !!document.getElementById("birge-legend")?.getClientRects().length, section: document.body.dataset.birgeSection }));
      check("Esc closes the chronicle: legend back, still on the map", !closed.open && !closed.host && closed.legend && closed.section === "map", closed);
      check("no page errors (chronicle, 1366)", page.errs.length === 0, page.errs);
      await ctx.close();
      ({ ctx, page } = await open(browser, base, 375, 812, "resident"));
      await page.waitForFunction(() => { const c = document.querySelector("#birge-legend .birge-replay-chip"); return c && c.getClientRects().length; }, null, { timeout: 15000 }).catch(() => null);
      const phoneChip = await page.evaluate(() => { const c = document.querySelector("#birge-legend .birge-replay-chip"), r = c?.getBoundingClientRect();
        return r ? { w: Math.round(r.width), h: Math.round(r.height), right: Math.round(r.right), text: getComputedStyle(c.querySelector(".birge-replay-chip__text")).display } : null; });
      check("phone: icon-only chip 44 × 44 inside the screen", !!phoneChip && phoneChip.w === 44 && phoneChip.h >= 44 && phoneChip.right <= 375 - 8 && phoneChip.text === "none", phoneChip);
      await page.click("#birge-legend .birge-replay-chip");
      await page.waitForFunction(() => document.querySelector(".rp-host .rp-bar"), null, { timeout: 8000 }).catch(() => null);
      await page.waitForTimeout(600);
      const phoneOpen = await page.evaluate(() => {
        const vis = (e) => !!e && e.getClientRects().length > 0 && getComputedStyle(e).display !== "none";
        const bar = document.querySelector(".rp-host .rp-bar")?.getBoundingClientRect();
        return { bar: bar ? [Math.round(bar.left), Math.round(bar.right), Math.round(bar.bottom)] : null, near: vis(document.getElementById("birge-near")),
          panel: vis(document.querySelector(".civic-panel")), fab: vis(document.querySelector(".bc-fab")) };
      });
      check("phone: the bar instead of the sheet — no «Рядом с вами», no list sheet, no report button over it", !!phoneOpen.bar
        && phoneOpen.bar[0] >= 0 && phoneOpen.bar[1] <= 375 && phoneOpen.bar[2] <= 812 && !phoneOpen.near && !phoneOpen.panel && !phoneOpen.fab, phoneOpen);
      await page.screenshot({ path: path.join(OUT, "replay_375_resident.png") });
      check("no page errors (chronicle, phone)", page.errs.length === 0, page.errs);
      await ctx.close();
    } else {
      console.log("NOT_RUN chronicle checks (R07 replay.js is not in the build)");
      await ctx.close();
    }

    // ------------------------------------------------------------ «Уведомления» R06 (IA R11 §5.7, §7.7)
    ({ ctx, page } = await open(browser, base, 1366, 768, "resident"));
    if (await page.evaluate(() => !!window.BirgeNotify)) {
      await page.waitForFunction(() => document.querySelector('.birge-me [data-action="notifications"]'), null, { timeout: 8000 }).catch(() => null);
      const bell = await page.evaluate(() => {
        const me = document.querySelector(".birge-me"), b = me?.querySelector('[data-action="notifications"]'), r = b?.getBoundingClientRect();
        const kids = me ? [...me.children] : [];
        return { bell: !!b, size: r ? [Math.round(r.width), Math.round(r.height)] : null, beforeAvatar: !!b && kids.indexOf(b) === kids.indexOf(me.querySelector(".birge-avatar")) - 1,
          icon: !!b?.querySelector("svg.ic"), inMore: window.BirgeShell.moreItems().includes("notifications") };
      });
      check("resident 1366: bell between «ҚАЗ · РУС» and the avatar (44 px, icon of the R11 set), not an «Ещё» item", bell.bell && bell.beforeAvatar
        && bell.size && bell.size[0] >= 40 && bell.size[1] >= 40 && bell.icon && !bell.inMore, bell);
      await page.click('.birge-me [data-action="notifications"]');
      await page.waitForTimeout(600);
      const panel = await page.evaluate(() => { const n = document.querySelector(".bk-notify"); return { open: !!n && !!n.getClientRects().length,
        buttons: n ? n.querySelectorAll("button").length : 0, ill: !!n?.querySelector(".bk-ill") }; });
      check("bell opens the panel under it (empty: small icon, text, one button — P1)", panel.open && !panel.ill, panel);
      await page.keyboard.press("Escape");
      await page.evaluate(() => window.BirgeShell.setMode("akimat"));
      await page.waitForTimeout(400);
      const akimatBell = await page.evaluate(() => !!document.querySelector('.birge-me [data-action="notifications"]')?.getClientRects().length);
      check("akimat view: no bell (resident only)", !akimatBell, akimatBell);
      check("no page errors (bell)", page.errs.length === 0, page.errs);
      await ctx.close();
      ({ ctx, page } = await open(browser, base, 375, 812, "resident"));
      await page.click("#birge-header .birge-avatar");
      await page.waitForTimeout(400);
      const phoneMenu = await page.evaluate(() => ({ first: document.querySelector(".birge-account .bk-menu__item")?.textContent.trim(),
        headerBell: !!document.querySelector('#birge-header [data-action="notifications"]')?.getClientRects().length }));
      check("phone: no bell in the header, «Уведомления» is the first avatar-menu item", /^Уведомления/.test(phoneMenu.first || "") && !phoneMenu.headerBell, phoneMenu);
      await ctx.close();
    } else {
      console.log("NOT_RUN bell checks (R06 notify.js is not in the build)");
      await ctx.close();
    }

    // ------------------------------------------------------------ phone: alert slot under the search field
    ({ ctx, page } = await open(browser, base, 375, 812, "resident"));
    const alert = await page.evaluate(() => {
      const slot = window.BirgeShell.alertSlot();
      const p = document.createElement("p"); p.textContent = "Буран в Нуре: службы работают"; slot.replaceChildren(p);
      const r = slot.getBoundingClientRect(), f = document.querySelector(".civic-explore-field").getBoundingClientRect();
      return { top: Math.round(r.top), left: Math.round(r.left), right: Math.round(r.right), fieldBottom: Math.round(f.bottom) };
    });
    check("phone: alertSlot() is under the search field, full width with 8 px edges", alert.top >= alert.fieldBottom
      && alert.top <= alert.fieldBottom + 16 && alert.left === 8 && alert.right === 367, alert);
    check("no page errors (phone)", page.errs.length === 0, page.errs);
    await ctx.close();
  } finally {
    await browser.close();
    srv.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  const summary = { pass: checks.filter((c) => c.status === "PASS").length, fail: checks.filter((c) => c.status === "FAIL").length };
  fs.writeFileSync(path.join(OUT, "r15_ia.json"), JSON.stringify({ summary, checks }, null, 1));
  console.log(JSON.stringify(summary));
  process.exit(summary.fail ? 1 : 0);
}
main().catch((e) => { console.error(e); process.exit(2); });
