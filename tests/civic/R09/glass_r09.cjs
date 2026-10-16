/*
 * R09 · стекло (R11 GLASS.md, решение владельца 12 окт) в настоящем приложении: только «Мои обращения» — стекло;
 * мастер жалобы, формы сотрудника и строки «Обращений» — непрозрачные; запасной вид — белый.
 *
 *   node tests/civic/R09/glass_r09.cjs --root <папка сборки с ui-kit R11 со стеклом> [--screenshots <папка>]
 *
 * Контраст — по настоящим пикселям, как tests/civic/R11/review/glass_contrast.cjs: у панели прячем содержимое, снимаем,
 * берём самый тёмный пиксель (без 4 px края) и считаем контраст с тёмным текстом (#152c26) и серым текстом стекла
 * (--glass-text-2). Норма ≥ 4.5:1. Запасной вид: prefers-reduced-transparency: reduce (эмуляция Chromium) и
 * html.bk-glass-off — панель и её шапка непрозрачные белые, без размытия.
 * Сервер: python3 -B app.py с CIVIC_DEMO=1 на временной SQLite. Печатает PASS/FAIL; код выхода 1, если есть FAIL.
 */
"use strict";
const path = require("path");
const fs = require("fs");
const os = require("os");
const net = require("net");
const zlib = require("zlib");
const { spawn, execSync } = require("child_process");

function loadPlaywright() {
  try { return require("playwright"); } catch (e) {
    return require(path.join(execSync("npm root -g").toString().trim(), "playwright"));
  }
}
const { chromium } = loadPlaywright();

const args = process.argv.slice(2);
const ROOT = path.resolve(args.includes("--root") ? args[args.indexOf("--root") + 1] : path.resolve(__dirname, "../../.."));
const SHOTS = args.includes("--screenshots") ? path.resolve(args[args.indexOf("--screenshots") + 1]) : null;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
const STOP = { kind: "object", id: "osm-node-4109037549" };
const POINT = [71.406553, 51.131155];
const INK = [0x15, 0x2c, 0x26];

const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail !== undefined ? " — " + JSON.stringify(detail).slice(0, 300) : "")); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no);
  s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (a) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${a}`, { cwd: ROOT, env, stdio: ["ignore", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  const staff = { user: "r09-glass", pass: "Steklo-" + Math.random().toString(36).slice(2) + "-Aa1!" };
  execSync(`python3 -B -m ui.civic_store --db "${db}" create-editor ${staff.user} --password-stdin`,
           { cwd: ROOT, env, input: staff.pass + "\n", stdio: ["pipe", "ignore", "inherit"] });
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) { srv.staff = staff; return srv; } } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

// --- PNG (8 бит, RGB/RGBA, без чересстрочности) и контраст WCAG
function decodePng(buf) {
  let pos = 8, w = 0, h = 0, ct = 0; const idat = [];
  while (pos < buf.length) {
    const len = buf.readUInt32BE(pos), type = buf.toString("ascii", pos + 4, pos + 8), data = buf.subarray(pos + 8, pos + 8 + len);
    if (type === "IHDR") { w = data.readUInt32BE(0); h = data.readUInt32BE(4); ct = data[9]; }
    else if (type === "IDAT") idat.push(data);
    else if (type === "IEND") break;
    pos += 12 + len;
  }
  const bpp = ct === 6 ? 4 : 3, raw = zlib.inflateSync(Buffer.concat(idat)), stride = w * bpp, out = Buffer.alloc(h * stride);
  for (let y = 0; y < h; y++) {
    const f = raw[y * (stride + 1)], src = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1)), row = y * stride;
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? out[row + x - bpp] : 0, b = y ? out[row - stride + x] : 0, c = x >= bpp && y ? out[row - stride + x - bpp] : 0;
      let v = src[x];
      if (f === 1) v += a; else if (f === 2) v += b; else if (f === 3) v += (a + b) >> 1;
      else if (f === 4) { const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c); v += pa <= pb && pa <= pc ? a : pb <= pc ? b : c; }
      out[row + x] = v & 255;
    }
  }
  return { w, h, bpp, px: out };
}
const lin = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
const lum = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
const hex = (s) => { const m = /#?([0-9a-f]{6})/i.exec(s || ""); return m ? [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16)) : null; };

async function darkestUnder(page, selector, shotPath) {
  // Прячем содержимое панели — остаётся стекло над картой; снимаем и ищем самый тёмный пиксель (без края 4 px).
  await page.evaluate((sel) => { const el = document.querySelector(sel); if (!el) return;
    el.setAttribute("data-r09-probe", "1");
    const st = document.createElement("style"); st.id = "r09-probe";
    // Плашка карты R01 и тосты лежат ПОВЕРХ панели (не под стеклом) — на время замера их прячем.
    st.textContent = '[data-r09-probe] > * { visibility: hidden !important; } [data-r09-probe] { color: transparent !important; }' +
      ' #map-status, .bk-toast, .bk-toasts, .birge-toast { display: none !important; }';
    document.head.appendChild(st); }, selector);
  await sleep(250);
  const buf = await page.locator(selector).screenshot(shotPath ? { path: shotPath } : {});
  await page.evaluate(() => { document.getElementById("r09-probe")?.remove(); document.querySelector("[data-r09-probe]")?.removeAttribute("data-r09-probe"); });
  const img = decodePng(buf);
  let best = null, bestL = 2;
  for (let y = 4; y < img.h - 4; y++) for (let x = 4; x < img.w - 4; x++) {
    const i = (y * img.w + x) * img.bpp, c = [img.px[i], img.px[i + 1], img.px[i + 2]], l = lum(c);
    if (l < bestL) { bestL = l; best = c; }
  }
  return best;
}

async function openPage(browser, size, lang, storage) {
  const ctx = await browser.newContext({ viewport: { width: size[0], height: size[1] }, deviceScaleFactor: 1, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
  await ctx.addInitScript((s) => { for (const [k, v] of Object.entries(s)) { try { localStorage.setItem(k, v); } catch (e) {} } }, storage);
  const page = await ctx.newPage();
  page.errors = [];
  page.on("pageerror", (e) => page.errors.push(String(e).slice(0, 200)));
  return { ctx, page };
}

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r09-glass-"));
  const port = await freePort();
  const srv = await startServer(port, path.join(tmp, "civic.sqlite3"));
  const base = `http://127.0.0.1:${port}`;
  const browser = await chromium.launch();
  try {
    for (const [size, lang] of [[[1366, 768], "ru"], [[375, 812], "kk"], [[1024, 768], "ru"]]) {
      const tag = `${size[0]}-${lang}`;
      const device = "r09glass" + Math.random().toString(36).slice(2, 14);
      // Своя жалоба этого устройства — чтобы в «Моих обращениях» были карточки.
      const res = await fetch(base + "/api/civic/v2/complaints", { method: "POST",
        headers: { "Content-Type": "application/json", "X-Birge-Device": device },
        body: JSON.stringify({ text: "Не горит фонарь на остановке вечером", category: "lighting", point: POINT, target: STOP }) });
      check(`${tag}: подготовка — жалоба устройства`, res.status === 201 || res.status === 200, { http: res.status });
      const { ctx, page } = await openPage(browser, size, lang, { "birge.mode": "resident", "birge.device": device, "birge.lang": lang });
      try {
        await page.goto(`${base}/?lang=${lang}#mine`, { waitUntil: "domcontentloaded" });
        const panel = page.locator(".bc-panel.bk-glass");
        await panel.waitFor({ state: "visible", timeout: 30000 }).catch(() => null);
        await page.waitForSelector(".bc-panel .bc-mine__card", { timeout: 15000 }).catch(() => null);
        await sleep(2500);   // карта под стеклом дорисовалась
        const st = await page.evaluate(() => { const p = document.querySelector(".bc-panel"); if (!p) return null;
          const cs = getComputedStyle(p), head = getComputedStyle(p.querySelector(".bc-head"));
          const card = p.querySelector(".bc-mine__card"), cc = card ? getComputedStyle(card) : null;
          return { glass: p.classList.contains("bk-glass"), step: p.getAttribute("data-step"), bg: cs.backgroundColor,
                   blur: cs.backdropFilter || cs.webkitBackdropFilter, radius: cs.borderTopLeftRadius, headBg: head.backgroundColor,
                   headBlur: head.backdropFilter || head.webkitBackdropFilter, card: cc && cc.backgroundColor, cardLine: cc && cc.boxShadow,
                   text2: cs.getPropertyValue("--c-text-2").trim() }; });
        // Эталон A (13 окт): стекло с текстом — плотное 86 % (.bk-glass--strong); ui-kit до эталона — 80 %.
        check(`${tag}: «Мои обращения» — плотное стекло ui-kit (86 % белого, размытие, радиус)`,
          st && st.glass && st.step === "mine" && /rgba\(255, 255, 255, 0\.8(6)?\)/.test(st.bg) && /blur\(2[0-4]px\)/.test(st.blur || ""), st);
        // ui-kit R11: белая карточка с волосяной линией (D-7) или плашка эталона --c-sub (72 % белого + линия 1 px);
        // в ui-kit до марафона — 70 % белого.
        check(`${tag}: карточки на стекле — плотная подложка (как .bk-card ui-kit)`, st &&
          (/^rgb\(255, 255, 255\)$/.test(st.card || "") && /inset/.test(st.cardLine || "") ||
           /rgba\(255, 255, 255, 0\.72\)/.test(st.card || "") && /inset/.test(st.cardLine || "") || /rgba\(255, 255, 255, 0\.7\)/.test(st.card || "")),
          st && [st.card, st.cardLine]);
        check(`${tag}: шапка «Закрыть» над прокруткой — тем же стеклом (размытие)`, st && /blur/.test(st.headBlur || ""), st && { headBg: st.headBg, headBlur: st.headBlur });
        const under = await page.evaluate(() => { const p = document.querySelector(".civic-panel");
          return { mineOpen: document.documentElement.classList.contains("bc-mine-open"), panel: p ? getComputedStyle(p).visibility : null }; });
        check(`${tag}: под стеклом нет второй панели (R01 .civic-panel скрыта, пока открыты «Мои обращения»)`,
          under.mineOpen && (under.panel === null || under.panel === "hidden"), under);
        if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `glass-${tag}-mine.png`) });
        const dark = await darkestUnder(page, ".bc-panel.bk-glass", SHOTS ? path.join(SHOTS, `glass-${tag}-probe.png`) : null);
        const text2 = hex(st && st.text2) || [0x4c, 0x58, 0x53];
        const cInk = dark ? contrast(INK, dark) : 0, cGrey = dark ? contrast(text2, dark) : 0;
        check(`${tag}: контраст текста на стекле ≥ 4.5 (тёмный ${cInk.toFixed(2)}, серый ${cGrey.toFixed(2)})`, cInk >= 4.5 && cGrey >= 4.5,
          { darkest: dark, text2: st && st.text2 });
        // Запасной вид: «уменьшить прозрачность» и выключатель для слабых ноутбуков — белый без размытия.
        const cdp = await ctx.newCDPSession(page);
        await cdp.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-transparency", value: "reduce" }] });
        await sleep(200);
        const rt = await page.evaluate(() => { const p = document.querySelector(".bc-panel"), cs = getComputedStyle(p), hd = getComputedStyle(p.querySelector(".bc-head"));
          return { bg: cs.backgroundColor, blur: cs.backdropFilter, headBg: hd.backgroundColor, headBlur: hd.backdropFilter }; });
        check(`${tag}: prefers-reduced-transparency — панель и шапка белые, без размытия`,
          rt.bg === "rgb(255, 255, 255)" && rt.blur === "none" && rt.headBg === "rgb(255, 255, 255)" && rt.headBlur === "none", rt);
        await cdp.send("Emulation.setEmulatedMedia", { features: [] });
        await page.evaluate(() => document.documentElement.classList.add("bk-glass-off"));
        await sleep(200);
        const off = await page.evaluate(() => { const p = document.querySelector(".bc-panel"), cs = getComputedStyle(p), hd = getComputedStyle(p.querySelector(".bc-head"));
          return { bg: cs.backgroundColor, blur: cs.backdropFilter, headBg: hd.backgroundColor, headBlur: hd.backdropFilter }; });
        check(`${tag}: html.bk-glass-off — панель и шапка белые, без размытия`,
          off.bg === "rgb(255, 255, 255)" && off.blur === "none" && off.headBg === "rgb(255, 255, 255)" && off.headBlur === "none", off);
        await page.evaluate(() => document.documentElement.classList.remove("bk-glass-off"));
        // Мастер жалобы — форма: непрозрачный.
        await page.keyboard.press("Escape").catch(() => null);
        await sleep(600);
        const fab = page.locator(".bc-fab");
        if (await fab.isVisible().catch(() => false)) await fab.click();
        else await page.evaluate(() => window.BirgeComplaint && window.BirgeComplaint.open && window.BirgeComplaint.open());
        await sleep(1200);
        const wz = await page.evaluate(() => { const p = document.querySelector(".bc-panel"); if (!p || p.hidden) return null; const cs = getComputedStyle(p);
          const cp = document.querySelector(".civic-panel");
          return { step: p.getAttribute("data-step"), glass: p.classList.contains("bk-glass"), bg: cs.backgroundColor, blur: cs.backdropFilter,
                   mineOpen: document.documentElement.classList.contains("bc-mine-open"), panel: cp ? getComputedStyle(cp).visibility : null }; });
        check(`${tag}: мастер жалобы — без стекла (непрозрачный белый); одна шторка — панель оболочки скрыта, пока открыт мастер`,
          wz && wz.step !== "mine" && !wz.glass && wz.bg === "rgb(255, 255, 255)" && wz.blur === "none" && !wz.mineOpen && wz.panel !== "visible", wz);
        await page.keyboard.press("Escape"); await sleep(500);
        const back = await page.evaluate(() => { const cp = document.querySelector(".civic-panel");
          return { open: document.documentElement.classList.contains("bc-open"), panel: cp ? getComputedStyle(cp).visibility : null }; });
        check(`${tag}: панель R09 закрыта — панель оболочки снова видна`, !back.open && back.panel !== "hidden", back);
        check(`${tag}: нет ошибок на странице`, page.errors.length === 0, page.errors);
      } finally { await ctx.close(); }
    }
    // «Обращения» акимата: строки (и форма сотрудника в них) — непрозрачные на листе раздела.
    const { ctx, page } = await openPage(browser, [1366, 768], "ru", { "birge.mode": "akimat" });
    try {
      await page.goto(`${base}/?lang=ru`, { waitUntil: "domcontentloaded" });
      const login = await page.evaluate(async ([u, p]) => (await fetch("/api/civic/v1/session/login", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: u, password: p }) })).status, [srv.staff.user, srv.staff.pass]);
      await page.goto(`${base}/?lang=ru#complaints`, { waitUntil: "domcontentloaded" });
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.waitForSelector(".bc-inbox", { timeout: 30000 }).catch(() => null);
      await sleep(2500);
      // Эталон A (Linear): строки — в одном белом списке с линиями 1 px; непрозрачный — сам список, строки прозрачны поверх.
      const rows = await page.evaluate(() => [...document.querySelectorAll(".bc-inbox__list")].slice(0, 3).map((n) => getComputedStyle(n).backgroundColor));
      check("1366-ru: «Обращения» — список непрозрачный белый", rows.length > 0 && rows.every((c) => c === "rgb(255, 255, 255)"),
        { login, rows });
      if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "glass-1366-ru-inbox.png") });
    } finally { await ctx.close(); }
  } finally {
    await browser.close();
    srv.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  const fail = results.filter((r) => !r.ok).length;
  console.log(`\nИТОГ: ${results.length - fail}/${results.length} ${fail ? "FAIL" : "PASS"}`);
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
