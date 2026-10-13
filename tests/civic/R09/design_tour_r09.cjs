/*
 * R09 · дизайн-марафон: обход всех экранов пути жителя и «Обращений» в настоящем приложении (кадры + замеры по чек-листу).
 *
 *   node tests/civic/R09/design_tour_r09.cjs --root <папка сборки> --out <папка> [--only 375-ru,1366-kk]
 *
 * Сервер: python3 -B app.py с CIVIC_DEMO=1 на временной SQLite (как app_demo_r09.cjs). Размеры 375×812 и 1366×768, ru и kk
 * (и 1024×768 — проектор — по --only 1024-ru).
 * Состояния: карта с кнопкой → «Где проблема?» → варианты места → текст (пусто / подсказка категории и уточнения / фото /
 * сетка категорий / срочный случай) → «Я тоже» → проверка перед отправкой → ошибка отправки → успех (новое и «Я тоже») →
 * «Мои обращения» (загрузка / список / «Подробнее» / «Ждут вашей проверки» / проверено / ошибка / пусто) → «Обращения»
 * акимата (без входа / список / карточка). Ошибки и загрузка — подменой ответов (page.route), данные — синтетические.
 * Для каждого кадра в tour.json — замеры панели R09 (чек-лист DESIGN_MARATHON): размеры и веса шрифта, зоны нажатия < 44,
 * число главных кнопок, прокрутка вбок, обрезанный текст. Код выхода 0 — кадры сняты (это обход, не приёмка).
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
const arg = (k, d) => (args.includes(k) ? args[args.indexOf(k) + 1] : d);
const ROOT = path.resolve(arg("--root", path.resolve(__dirname, "../../..")));
const OUT = path.resolve(arg("--out", path.join(os.tmpdir(), "r09-design")));
const ONLY = arg("--only", "") ? arg("--only").split(",") : null;
fs.mkdirSync(OUT, { recursive: true });
const STOP = [71.406553, 51.131155];
const TEXT = { ru: "Вечером не горит фонарь у остановки, очень темно", kk: "Кешке аялдама жанындағы шам жанбайды, өте қараңғы" };
const GAS = { ru: "В подъезде сильно пахнет газом", kk: "Подъезде газдың иісі қатты шығады" };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no);
  s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });
const tour = [];

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (a) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${a}`, { cwd: ROOT, env, stdio: ["ignore", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  const staff = { user: "r09-design", pass: "Dizain-" + Math.random().toString(36).slice(2) + "-Aa1!" };
  execSync(`python3 -B -m ui.civic_store --db "${db}" create-editor ${staff.user} --password-stdin`,
           { cwd: ROOT, env, input: staff.pass + "\n", stdio: ["pipe", "ignore", "inherit"] });
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) { srv.staff = staff; return srv; } } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

// Сотрудник через API (как r10_lib): вход, cookie + CSRF.
function staffApi(base) {
  let cookie = null, csrf = null;
  const call = async (method, p, body, device) => {
    const headers = { "Content-Type": "application/json", Origin: base };
    if (cookie) { headers.Cookie = cookie; headers["X-CSRF-Token"] = csrf; }
    if (device) headers["X-Birge-Device"] = device;
    const res = await fetch(base + p, { method, headers, body: body ? JSON.stringify(body) : undefined });
    let json = null; try { json = await res.json(); } catch {}
    return { status: res.status, data: json && json.data !== undefined ? json.data : json };
  };
  return {
    call,
    async login(user, pass) {
      const res = await fetch(base + "/api/civic/v1/session/login", { method: "POST", headers: { "Content-Type": "application/json", Origin: base },
        body: JSON.stringify({ username: user, password: pass }) });
      const set = res.headers.get("set-cookie"); const j = await res.json().catch(() => ({}));
      const d = j.data || j; cookie = set && set.split(";")[0]; csrf = d && (d.csrf_token || (d.session && d.session.csrf_token));
      return !!csrf;
    },
  };
}

// PNG 160×120 одного цвета — «фото» для поля выбора (синтетика, без EXIF).
function pngBuffer(w = 160, h = 120, rgb = [96, 120, 140]) {
  const crc = (b) => zlib.crc32(b) >>> 0;
  const chunk = (type, data) => { const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
    const td = Buffer.concat([Buffer.from(type), data]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([len, td, c]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  const raw = Buffer.alloc((w * 3 + 1) * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { const i = y * (w * 3 + 1) + 1 + x * 3; raw[i] = rgb[0] + (x % 40); raw[i + 1] = rgb[1] + (y % 30); raw[i + 2] = rgb[2]; }
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]);
}

// Замеры по чек-листу в панели R09 (или в корне «Обращений»).
async function measure(page) {
  return page.evaluate(() => {
    const root = (() => { const p = document.querySelector(".bc-panel"); if (p && !p.hidden) return p;
      return document.querySelector(".bc-inbox") || document.body; })();
    const vis = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none" && r.bottom > 0 && r.top < innerHeight; };
    const sizes = {}, weights = {}, small = [], tiny = [], cut = [];
    root.querySelectorAll("*").forEach((el) => {
      if (!vis(el)) return;
      const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
      const cs = getComputedStyle(el);
      if (own) {
        const fs = Math.round(parseFloat(cs.fontSize)); sizes[fs] = (sizes[fs] || 0) + 1;
        weights[cs.fontWeight] = (weights[cs.fontWeight] || 0) + 1;
        if (fs < 13) small.push(el.textContent.trim().slice(0, 30) + " " + fs);
        if ((cs.overflow === "hidden" || cs.textOverflow === "ellipsis") && el.scrollWidth > el.clientWidth + 1) cut.push(el.textContent.trim().slice(0, 30));
      }
      if (el.matches("button, a[href], input:not([type=hidden]):not([type=file]), select, textarea, [role=button], summary")) {
        const r = el.getBoundingClientRect();
        if (Math.min(r.width, r.height) < 44) tiny.push((el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 24) + ` ${Math.round(r.width)}×${Math.round(r.height)}`);
      }
    });
    const primaries = [...root.querySelectorAll(".bk-btn--primary")].filter(vis).length;
    return { root: root.className.toString().slice(0, 60), sizes, weights, small: small.slice(0, 8), tiny: tiny.slice(0, 10), cut: cut.slice(0, 5),
             primaries, hscroll: document.documentElement.scrollWidth > innerWidth + 1 || root.scrollWidth > root.clientWidth + 1 };
  });
}

async function shot(page, tag, name, note) {
  await sleep(500);
  const file = `${tag}-${name}.png`;
  await page.screenshot({ path: path.join(OUT, file) });
  const m = await measure(page).catch((e) => ({ error: String(e) }));
  tour.push({ tag, name, file, note: note || null, ...m });
  console.log(`shot ${file}` + (m.small && m.small.length ? ` small:${m.small.length}` : "") + (m.tiny && m.tiny.length ? ` tiny:${m.tiny.length}` : "") +
              (m.primaries > 1 ? ` primaries:${m.primaries}` : "") + (m.hscroll ? " HSCROLL" : ""));
}
async function bottom(page) { await page.evaluate(() => { const p = document.querySelector(".bc-panel"); if (p) p.scrollTop = p.scrollHeight; }); await sleep(300); }

const shellReady = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined"
  && mapReady && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 });

async function tapStop(page, width) {
  const xy = await page.evaluate(async (p) => {
    const c = map.getCanvas().getBoundingClientRect();
    const panel = document.querySelector(".bc-panel"); const r = panel && !panel.hidden ? panel.getBoundingClientRect() : null;
    const mobile = innerWidth < 1024;
    // Ноутбук: панель R09 — карточка слева (эталон A) или справа (до 13 окт): середина видимой части карты.
    const leftCard = r && !mobile && r.left + r.width / 2 < (c.left + c.right) / 2;
    const want = { x: ((leftCard ? r.right : c.left) + (r && !mobile && !leftCard ? r.left : c.right)) / 2, y: (c.top + (r && mobile ? r.top : c.bottom)) / 2 };
    map.jumpTo({ center: p, zoom: 17 });
    const q = map.project(p);
    map.panBy([c.left + q.x - want.x, c.top + q.y - want.y], { duration: 0 });
    await new Promise((ok) => setTimeout(ok, 600));
    const now = map.project(p);
    return { x: c.left + now.x, y: c.top + now.y };
  }, STOP);
  await sleep(500);
  if (width < 1024) await page.touchscreen.tap(xy.x, xy.y); else await page.mouse.click(xy.x, xy.y);
}

async function toText(page, width, lang, text) {
  await page.click(".bc-fab");
  await page.waitForSelector(".bc-panel[data-step='2']", { timeout: 8000 });
  await tapStop(page, width);
  await page.waitForSelector(".bc-option--first", { timeout: 10000 });
  await page.click(".bc-option--first");
  await page.waitForSelector(".bc-panel[data-step='3']", { timeout: 8000 });
  if (text) { await page.fill("#bc-text", text); await page.waitForSelector(".bc-cat-row .bk-chip[aria-pressed='true']", { timeout: 8000 }).catch(() => null); }
}

async function newPage(browser, width, height, lang, mode, device) {
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, hasTouch: width < 1024 });
  await ctx.addInitScript(([l, m, d]) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l);
    if (d) localStorage.setItem("birge.device", d); } catch (e) {} }, [lang, mode, device]);
  const page = await ctx.newPage();
  return { ctx, page };
}

async function resident(browser, base, srv, width, height, lang) {
  const tag = `${width}-${lang}`;
  const device = "r09tour" + Math.random().toString(36).slice(2, 14);
  const { ctx, page } = await newPage(browser, width, height, lang, "resident", device);
  try {
    await page.goto(base); await shellReady(page); await sleep(1200);
    await shot(page, tag, "01-map");
    await page.click(".bc-fab");
    await page.waitForSelector(".bc-panel[data-step='2']", { timeout: 8000 });
    await shot(page, tag, "02-place");
    await tapStop(page, width);
    await page.waitForSelector(".bc-option--first", { timeout: 10000 });
    await shot(page, tag, "03-candidates");
    await page.click(".bc-option--first");
    await page.waitForSelector(".bc-panel[data-step='3']", { timeout: 8000 });
    await shot(page, tag, "04-text-empty");
    await page.fill("#bc-text", TEXT[lang]);
    await page.waitForSelector(".bc-cat-row .bk-chip[aria-pressed='true']", { timeout: 8000 }).catch(() => null);
    await shot(page, tag, "05-text-suggested");
    await page.setInputFiles("#bc-photo-input", { name: "photo.png", mimeType: "image/png", buffer: pngBuffer() }).catch(() => null);
    await sleep(1200); await bottom(page);
    await shot(page, tag, "06-text-photo-bottom");
    await page.evaluate(() => { const p = document.querySelector(".bc-panel"); if (p) p.scrollTop = 0; });
    const change = await page.$(".bc-change");
    if (change) { await change.click(); await sleep(500); await shot(page, tag, "07-category-grid");
      await page.click(".bk-catgrid > button[aria-pressed='true']").catch(() => null); await sleep(400); }
    await page.fill("#bc-text", GAS[lang]); await sleep(1800);
    await shot(page, tag, "08-emergency");
    await page.fill("#bc-text", TEXT[lang]); await sleep(1800);
    await page.click(".bc-send");
    await page.waitForSelector(".bc-panel[data-step='4']", { timeout: 15000 });
    await shot(page, tag, "09-similar");
    await bottom(page); await shot(page, tag, "09b-similar-bottom");
    await page.click(".bc-different");
    await page.waitForSelector(".bc-panel[data-review='1']", { timeout: 10000 });
    await shot(page, tag, "10-review");
    await bottom(page); await shot(page, tag, "10b-review-bottom");
    // Ошибка отправки (сервер ответил 500) → тост «что случилось + повторить».
    await page.route("**/api/civic/v2/complaints", (r) => (r.request().method() === "POST" ? r.fulfill({ status: 500, contentType: "application/json",
      body: JSON.stringify({ ok: false, error: { code: "server", message: "fail" } }) }) : r.continue()));
    await page.click(".bc-panel[data-review='1'] .bc-send");
    await page.waitForSelector(".bc-toast:not([hidden])", { timeout: 10000 }).catch(() => null);
    await shot(page, tag, "11-send-error");
    await page.unroute("**/api/civic/v2/complaints");
    const retry = await page.$(".bc-toast .bk-btn");
    if (retry) await retry.click(); else await page.click(".bc-panel .bc-send");
    await page.waitForSelector(".bc-panel[data-step='5']", { timeout: 15000 });
    await sleep(700);   // галочка успеха дорисовалась
    await shot(page, tag, "12-done-new");
    await bottom(page); await shot(page, tag, "12b-done-new-bottom");
    await page.keyboard.press("Escape"); await sleep(800);
    // «Я тоже»: второй проход — успех «вы присоединились».
    await toText(page, width, lang, TEXT[lang]);
    await page.click(".bc-send");
    await page.waitForSelector(".bc-panel[data-step='4']", { timeout: 15000 });
    await page.click(".bc-panel[data-step='4'] .bk-btn--primary");
    await page.waitForSelector(".bc-panel[data-step='5']", { timeout: 10000 });
    await sleep(700);   // галочка успеха дорисовалась
    await shot(page, tag, "13-done-metoo");
    await page.keyboard.press("Escape"); await sleep(800);
    // «Мои обращения»: загрузка (ответ задержан) → список → «Подробнее».
    await page.route("**/api/civic/v2/complaints/mine*", async (r) => { await sleep(2500); await r.continue(); });
    await page.evaluate(() => window.CivicShell?.openMine?.());
    await sleep(700);
    await shot(page, tag, "14-mine-loading");
    await page.waitForSelector(".bc-mine__card", { timeout: 15000 }).catch(() => null);
    await page.unroute("**/api/civic/v2/complaints/mine*");
    await shot(page, tag, "15-mine-list");
    const more = await page.$(".bc-mine__card .bc-more > summary");
    if (more) { await more.click(); await sleep(500); await more.scrollIntoViewIfNeeded().catch(() => null); }
    await shot(page, tag, "16-mine-details");
    await page.keyboard.press("Escape"); await sleep(600);
    // Служба сообщила об устранении (через API сотрудника) → «Ждут вашей проверки» → «Да, исправлено».
    const A = staffApi(base);
    if (await A.login(srv.staff.user, srv.staff.pass)) {
      const mine = await A.call("GET", "/api/civic/v2/complaints/mine", null, device);
      const items = (mine.data && (mine.data.items || mine.data.complaints)) || [];
      const own = items.find((c) => c.relation !== "metoo") || items[0];
      if (own) {
        await A.call("POST", `/api/civic/v2/complaints/${own.id}/status`, { status: "in_progress" });
        await A.call("POST", `/api/civic/v2/complaints/${own.id}/status`, { status: "fixed", what_done: lang === "kk" ? "Шам ауыстырылды" : "Заменили лампу" });
      }
    }
    await page.evaluate(() => window.CivicShell?.openMine?.());
    await page.waitForSelector(".bc-wait", { timeout: 10000 }).catch(() => null);
    await shot(page, tag, "17-mine-verify");
    const yes = await page.$(".bc-wait .bc-verify__yes");
    if (yes) { await yes.click(); await sleep(1800); }
    await shot(page, tag, "18-mine-verified");
    await page.keyboard.press("Escape"); await sleep(600);
    // Ошибка загрузки «Моих обращений».
    await page.route("**/api/civic/v2/complaints/mine*", (r) => r.fulfill({ status: 500, contentType: "application/json", body: "{}" }));
    await page.evaluate(() => window.CivicShell?.openMine?.());
    await sleep(1500);
    await shot(page, tag, "19-mine-error");
    await page.unroute("**/api/civic/v2/complaints/mine*");
    await page.keyboard.press("Escape");
  } finally { await ctx.close(); }
  // Пусто: новое устройство без обращений.
  const fresh = await newPage(browser, width, height, lang, "resident", "r09tour" + Math.random().toString(36).slice(2, 14));
  try {
    await fresh.page.goto(base); await shellReady(fresh.page); await sleep(800);
    await fresh.page.evaluate(() => window.CivicShell?.openMine?.());
    await sleep(1500);
    await shot(fresh.page, tag, "20-mine-empty");
  } finally { await fresh.ctx.close(); }
}

async function akimat(browser, base, srv, width, height, lang) {
  const tag = `${width}-${lang}`;
  const { ctx, page } = await newPage(browser, width, height, lang, "akimat", null);
  try {
    await page.goto(base); await shellReady(page); await sleep(800);
    await page.evaluate(() => window.BirgeShell?.setSection?.("complaints"));
    await sleep(1500);
    await shot(page, tag, "21-inbox-need-staff");
    await page.evaluate(async ([u, p]) => (await fetch("/api/civic/v1/session/login", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: u, password: p }) })).ok, [srv.staff.user, srv.staff.pass]);
    await page.reload(); await shellReady(page); await sleep(600);
    await page.evaluate(() => { window.BirgeShell?.setMode?.("akimat"); window.BirgeShell?.setSection?.("complaints"); });
    await page.waitForSelector(".bc-inbox__row", { timeout: 10000 }).catch(() => null);
    await shot(page, tag, "22-inbox");
    const row = await page.$(".bc-inbox__row");
    if (row) { await row.click(); await sleep(1500); }
    await shot(page, tag, "23-inbox-detail");
    // Пустая вкладка (ноль у вкладки скрыт) и «нет связи» «Обращений» (круг 7: иллюстрации ui-kit).
    const emptyTab = await page.$(".bc-inbox__tab:has(.bc-inbox__count[data-zero])");
    if (emptyTab) { await emptyTab.click(); await sleep(700); }
    await shot(page, tag, "23b-inbox-empty-tab");
    await page.route("**/api/civic/v2/complaints/inbox*", (r) => r.abort());
    await page.evaluate(() => window.BirgeShell?.setSection?.("map")); await sleep(400);
    await page.evaluate(() => window.BirgeShell?.setSection?.("complaints")); await sleep(1500);
    await shot(page, tag, "23c-inbox-error");
    await page.unroute("**/api/civic/v2/complaints/inbox*");
    // Карточка цели R07 на карте: блок сотрудника R09 (паспорт, «Обновление для всех») и форма «что сделали».
    // Открытое настоящее обращение у остановки (демо-примеры не меняются) — синтетика, своё устройство.
    await fetch(base + "/api/civic/v2/complaints", { method: "POST", headers: { "Content-Type": "application/json",
      "X-Birge-Device": "r09tourstaff" + Math.random().toString(36).slice(2, 12) },
      body: JSON.stringify({ text: TEXT[lang], category: "lighting", point: STOP, target: { kind: "object", id: "osm-node-4109037549" } }) }).catch(() => null);
    await page.evaluate(() => window.BirgeShell?.setSection?.("map"));
    await sleep(1200);
    await tapStop(page, width);
    const card = await page.waitForSelector(".r07-card", { timeout: 8000 }).then(() => true, () => false);
    if (card) {
      await sleep(1200);
      await shot(page, tag, "24-r07-card-staff");
      const take = await page.$(".r07-card [data-act='take']");
      if (take) { await take.click(); await sleep(1500); }
      const fixed = await page.$(".r07-card [data-act='fixed']");
      if (fixed) { await fixed.click(); await page.waitForSelector(".r07-fixform", { timeout: 4000 }).catch(() => null); await sleep(600);
        await shot(page, tag, "25-r07-fixform"); }
    }
  } finally { await ctx.close(); }
}

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r09-tour-"));
  let srv = null, browser = null;
  try {
    browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
    // 1024×768 (проектор) — только по запросу: --only 1024-ru
    const runs = [[375, 812, "ru"], [375, 812, "kk"], [1366, 768, "ru"], [1366, 768, "kk"], [1024, 768, "ru"]]
      .filter(([w, , l]) => (ONLY ? ONLY.includes(`${w}-${l}`) : w !== 1024));
    for (const [w, h, lang] of runs) {
      // Свежая демо-база на каждый вариант: «Я тоже» и проверка начинаются с одного и того же вида.
      if (srv) srv.kill();
      const port = await freePort();
      srv = await startServer(port, path.join(tmp, `civic-${w}-${lang}.sqlite3`));
      const base = `http://127.0.0.1:${port}`;
      try { await resident(browser, base, srv, w, h, lang); } catch (e) { console.error(`${w}-${lang} resident:`, e.message); tour.push({ tag: `${w}-${lang}`, error: e.message }); }
      try { await akimat(browser, base, srv, w, h, lang); } catch (e) { console.error(`${w}-${lang} akimat:`, e.message); tour.push({ tag: `${w}-${lang}`, error: e.message }); }
    }
  } finally {
    if (browser) await browser.close();
    if (srv) srv.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
    fs.writeFileSync(path.join(OUT, "tour.json"), JSON.stringify(tour, null, 1));
  }
  console.log(`\nкадров: ${tour.filter((t) => t.file).length}, ошибок обхода: ${tour.filter((t) => t.error).length} → ${OUT}`);
})();
