// R01 · дизайн-марафон (research/round-14/DESIGN_MARATHON.md): кадры оболочки во всех состояниях + замер по чек-листу.
//   node tests/civic/R01/browser/design_shots.cjs <out_dir> [--sizes 1366x768,1024x768,375x812] [--langs ru,kk]
//        [--only map,avatar,...] [--glass on|off]
// Свой сервер: python3 -B app.py, CIVIC_DEMO=1, временная SQLite (синтетика). Не тест «прошёл/упал»: кадры PNG и
// <out_dir>/design.json — по каждому кадру замер оболочки (шапка, меню, кнопки карты, легенда, панель, лист раздела):
//   шрифты (размеры и веса), зоны нажатия < 44 px, обрезанный текст, горизонтальная прокрутка, ошибки JS.
// Стекло по умолчанию держится включённым (?glass=on): в облаке программный WebGL, автовыключатель R01 №8 иначе
// выключил бы его при первом перелёте карты; на ноутбуке так и будет.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(process.env.R01_REPO || path.resolve(__dirname, "../../../.."));  // R01_REPO — другая копия (кадры «до»)
const argv = process.argv.slice(2);
const opt = (name, def) => { const i = argv.indexOf("--" + name); return i >= 0 ? argv[i + 1] : def; };
const OUT = path.resolve(argv.find((a, i) => !a.startsWith("--") && !(i > 0 && argv[i - 1].startsWith("--"))) || "design-out");
const SIZES = opt("sizes", "1366x768,1024x768,375x812").split(",").map((s) => s.split("x").map(Number));
const LANGS = opt("langs", "ru,kk").split(",");
const ONLY = opt("only", "") ? opt("only", "").split(",") : null;
const GLASS = opt("glass", "on");
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet|net::ERR_FAILED/i;
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

// Замер оболочки на текущем кадре: только элементы R01 (шапка, меню, кнопки карты, легенда, плашка, панель/шторка
// как рамка, лист раздела — его шапка). Содержимое модулей ролей не меряем — это их экраны.
const AUDIT = () => {
  const SHELL = [".topbar", "#birge-account", ".birge-more-menu", "#birge-layer-list", ".map-tools", "#birge-legend .birge-legend-line",
    "#map-status", ".civic-sheet-handle", ".birge-day__head", ".birge-screen__head", ".civic-explore"];
  const vis = (e) => { if (!e.getClientRects().length) return false; const s = getComputedStyle(e); return s.visibility !== "hidden" && s.display !== "none" && Number(s.opacity) > 0.05; };
  const roots = SHELL.flatMap((s) => [...document.querySelectorAll(s)]).filter(vis);
  const sizes = {}, weights = {}, small = [], clipped = [], taps = [];
  const seen = new Set();
  for (const r of roots) for (const e of [r, ...r.querySelectorAll("*")]) {
    if (seen.has(e) || !vis(e)) continue; seen.add(e);
    const own = [...e.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").trim();
    const cs = getComputedStyle(e);
    if (own) {
      const fs = Math.round(parseFloat(cs.fontSize) * 10) / 10, fw = cs.fontWeight;
      const where = (e.id ? "#" + e.id : e.className && typeof e.className === "string" ? "." + e.className.split(/\s+/)[0] : e.tagName.toLowerCase()) + " «" + own.slice(0, 16) + "»";
      (sizes[fs] = sizes[fs] || []).length < 4 && sizes[fs].push(where); (weights[fw] = weights[fw] || []).length < 4 && weights[fw].push(where);
      if (fs < 13) small.push(own.slice(0, 24) + "@" + fs);
      if (e.scrollWidth > e.clientWidth + 1 && /hidden|clip/.test(cs.overflow + cs.overflowX) && cs.textOverflow === "ellipsis") clipped.push(own.slice(0, 30));
    }
    if (e.matches("button, a[href], [role=menuitem], [role=option], input, select, summary, label.birge-layer__opt")) {
      const b = e.getBoundingClientRect();
      const zone = e.closest("label"); const zb = zone && zone !== e ? zone.getBoundingClientRect() : null;  // поле внутри подписи — зона = подпись
      if (b.width && b.height && (b.width < 44 || b.height < 44) && !e.closest(".civic-explore-list") && !(zb && zb.height >= 44)) {
        // зона нажатия: своя рамка или ::after с inset < 0 (как у «i» подписи карты)
        const after = getComputedStyle(e, "::after"); const ext = after.content !== "none" && /-/.test(after.inset || after.top || "");
        if (!ext) taps.push((e.id ? "#" + e.id : e.className ? "." + String(e.className).split(/\s+/)[0] : e.tagName) + " " + Math.round(b.width) + "×" + Math.round(b.height));
      }
    }
  }
  const glass = [...document.querySelectorAll(".bk-glass, .bk-glass--control")].filter(vis).map((e) => {
    const s = getComputedStyle(e); return { el: (e.id ? "#" + e.id : "." + String(e.className).split(/\s+/)[0]), bg: s.backgroundColor, blur: (s.backdropFilter || "none") !== "none", r: s.borderRadius };
  });
  return { sizes, weights, small: small.slice(0, 12), clipped: clipped.slice(0, 12), taps: [...new Set(taps)].slice(0, 16), glass,
    hscroll: document.scrollingElement.scrollWidth - innerWidth, glassOff: document.documentElement.classList.contains("bk-glass-off") };
};

async function openPage(browser, base, [w, h], lang, mode, { hash = "", route = null } = {}) {
  const mobile = w < 761;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1,
    locale: lang === "kk" ? "kk-KZ" : "ru-RU", reducedMotion: "no-preference" });
  await ctx.addInitScript(([l, m]) => { try { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", m); } catch (e) { /* пусто */ } }, [lang, mode]);
  if (route) await ctx.route(route.url, route.handler);
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !NOISE.test(m.text())) page.errs.push(m.text().slice(0, 200)); });
  await page.goto(base + (GLASS ? "?glass=" + GLASS : "") + hash);
  return { ctx, page };
}
const ready = (page) => page.waitForFunction(() => window.BirgeShell && typeof mapReady !== "undefined" && mapReady && document.querySelector("#birge-header"),
  null, { timeout: 40000 }).then(() => sleep(2500)).catch(() => null);
const click = async (page, sel) => { const l = page.locator(sel).filter({ visible: true }).first(); if (await l.count()) { await l.click().catch(() => null); return true; } return false; };

// Состояния: [имя, вид, подготовка]. Подготовка возвращает false — состояние не открылось (в отчёт).
const STATES = [
  ["map", "akimat", async () => true],
  ["map-resident", "resident", async () => true],
  ["avatar", "akimat", async (p) => click(p, "#birge-header .birge-avatar")],
  ["more", "akimat", async (p) => click(p, "#birge-header [data-section=more]")],
  ["layers", "akimat", async (p) => click(p, "#birge-layer-btn")],
  ["legend", "akimat", async (p) => click(p, ".birge-legend-q")],
  ["search", "akimat", async (p) => { const i = p.locator(".civic-explore-field input").filter({ visible: true }).first(); if (!(await i.count())) return false;
    await i.click(); await i.fill("Хан"); await sleep(1500); return true; }],
  ["place", "akimat", async (p) => { const i = p.locator(".civic-explore-field input").filter({ visible: true }).first(); if (!(await i.count())) return false;
    await i.click(); await i.fill("Хан Шатыр"); await sleep(1200); await i.press("Enter"); await sleep(3500); return true; }],
  ["day", "akimat", async (p) => { await p.evaluate(() => { location.hash = "#day"; }); await sleep(2500); return true; }],
  ["nearby", "resident", async (p) => { await p.evaluate(() => { location.hash = "#nearby"; }); await sleep(2500); return true; }],
  ["ideas", "resident", async (p) => { await p.evaluate(() => { location.hash = "#ideas"; }); await sleep(2500); return true; }],
  ["mine", "resident", async (p) => (await click(p, "#birge-header [data-action=mine]")) || click(p, "#birge-header .birge-mine-btn").then(async (ok) => { await sleep(1500); return ok; })],
  ["wizard", "resident", async (p) => { const ok = await click(p, ".bc-fab"); await sleep(1200); return ok; }],
  ["projects", "akimat", async (p) => { await p.evaluate(() => { location.hash = "#projects"; }); await sleep(2500); return true; }],
  // слой «Проекты» на карте (кнопка «слои») и каталог R05 «Что построить?»
  ["catalog", "akimat", async (p) => { if (!(await click(p, "#birge-layer-btn"))) return false; await sleep(400);
    if (!(await click(p, '#birge-layer-list [data-layer="projects"], #birge-layer-list .birge-layer__opt:has(input[value="projects"])'))) return false;
    await sleep(2500); const ok = await click(p, ".birge-b3d-toggle"); await sleep(1500); return ok; }],
  ["loading", "akimat", null, { route: { url: /\/api\/civic\/v2\/heat/, handler: async (r) => { await sleep(6000); await r.continue().catch(() => null); } }, early: 1800 }],
  ["error", "akimat", null, { route: { url: /\/api\/civic\/v2\/heat/, handler: (r) => r.fulfill({ status: 503, contentType: "application/json", body: '{"error":"unavailable"}' }) } }],
];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const port = await freePort(), tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r01-design-"));
  const srv = await startServer(port, path.join(tmp, "civic.sqlite3"));
  const base = `http://127.0.0.1:${port}/`;
  const browser = await chromium.launch();
  const report = [];
  try {
    for (const size of SIZES) for (const lang of LANGS) for (const [name, mode, prep, extra = {}] of STATES) {
      if (ONLY && !ONLY.includes(name)) continue;
      const tag = `${size[0]}-${lang}-${name}`;
      const { ctx, page } = await openPage(browser, base, size, lang, mode, { route: extra.route });
      let ok = true;
      try {
        if (extra.early) { await page.waitForFunction(() => document.querySelector("#birge-header"), null, { timeout: 30000 }).catch(() => null); await sleep(extra.early); }
        else { await ready(page); if (prep) ok = await prep(page); await sleep(700); }
        await page.screenshot({ path: path.join(OUT, tag + ".png") });
        const a = await page.evaluate(AUDIT);
        report.push({ tag, ok, ...a, errs: page.errs.slice(0, 5) });
        console.log(`${ok ? "OK " : "NO "} ${tag}  шрифты ${Object.keys(a.sizes).sort((x, y) => x - y).join("/")} веса ${Object.keys(a.weights).join("/")}`
          + (a.small.length ? ` мелко ${a.small.length}` : "") + (a.taps.length ? ` зоны<44 ${a.taps.length}` : "") + (a.clipped.length ? ` обрезано ${a.clipped.length}` : "")
          + (a.hscroll > 0 ? ` прокрутка ${a.hscroll}` : "") + (page.errs.length ? ` ошибки ${page.errs.length}` : ""));
      } catch (e) {
        report.push({ tag, ok: false, error: String(e.message || e).slice(0, 300) }); console.log("ERR " + tag + " " + String(e.message || e).slice(0, 200));
      } finally { await ctx.close(); }
    }
  } finally {
    await browser.close(); srv.kill(); fs.rmSync(tmp, { recursive: true, force: true });
    fs.writeFileSync(path.join(OUT, "design.json"), JSON.stringify({ when: new Date().toISOString(), glass: GLASS, report }, null, 1));
  }
})();
