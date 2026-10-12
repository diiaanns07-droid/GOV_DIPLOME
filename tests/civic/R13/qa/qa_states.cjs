// R13 · дизайн-марафон: снимки всех состояний «Вопроса акиму» и блока «Пульс» в «Картине дня» (1366/375 × ru/kk).
// Запускает свой сервер (CIVIC_DEMO=1, временная база), создаёт сотрудника. Загрузку, «пусто», ошибку и отправку
// показывает подменой ответов API в браузере (page.route) — сервер и данные не меняются.
//
//   BIRGE_REPO=<сборка R01> node tests/civic/R13/qa/qa_states.cjs <папка> [--sizes 1366x768,375x812] [--langs ru,kk]
//
// Кадры: <ширина>-<язык>-<состояние>.png; рядом STATES.json — что снято и замеры (шрифты, веса, зоны нажатия).
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(process.env.BIRGE_REPO || path.join(__dirname, "../../../.."));
const args = process.argv.slice(2);
const OUT = path.resolve(args.find((a) => !a.startsWith("--")) || "r13-qa-states");
const opt = (name, def) => { const i = args.indexOf("--" + name); return i >= 0 ? args[i + 1] : def; };
const SIZES = opt("sizes", "1366x768,375x812").split(",").map((s) => s.split("x").map(Number));
const LANGS = opt("langs", "ru,kk").split(",");
const STAFF = { user: "qa.states", pass: "qa-states-pass-2026" };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });
const idle = (page) => page.waitForFunction(() => !document.querySelector(".qa-list--busy, .qa-skeleton"), null, { timeout: 15000 }).catch(() => null);
const LONG_KK = "Сарыарқа ауданындағы жаңа тұрғын үй кешендерінің жанындағы балалар алаңдары мен жаяу жүргіншілер жолдары қашан "
  + "абаттандырылады және қыста қардан тазалау кестесі тұрғындарға қай жерде жарияланады? Кешке жарық жоқ, балалар қараңғыда жүреді.";

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (a, input) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${a}`, { cwd: REPO, env, input, stdio: [input ? "pipe" : "ignore", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  run(`create-editor ${STAFF.user} --password-stdin`, STAFF.pass + "\n");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

// Замеры экрана: размеры и веса шрифта текста .qa, зоны нажатия кнопок, ширина строки текста вопроса (знаков).
const measure = (page) => page.evaluate(() => {
  const root = document.querySelector(".qa") || document.querySelector(".akim-pulse");
  if (!root) return null;
  const sizes = {}, weights = {}, small = [];
  for (const el of root.querySelectorAll("*")) {
    if (![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    if (!r.width || cs.visibility === "hidden") continue;
    sizes[cs.fontSize] = (sizes[cs.fontSize] || 0) + 1;
    weights[cs.fontWeight] = (weights[cs.fontWeight] || 0) + 1;
  }
  for (const b of root.querySelectorAll("button, a, summary, select, [role=tab]")) {
    const r = b.getBoundingClientRect();
    if (r.width && (r.height < 44 || r.width < 44)) small.push({ text: (b.textContent || b.getAttribute("aria-label") || "").trim().slice(0, 30), w: Math.round(r.width), h: Math.round(r.height) });
  }
  const q = root.querySelector(".qa-card__text");
  const chars = q ? Math.round(q.getBoundingClientRect().width / (parseFloat(getComputedStyle(q).fontSize) * 0.5)) : null;
  return { sizes, weights, small: small.slice(0, 8), lineChars: chars };
});

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const port = await freePort(), base = `http://127.0.0.1:${port}`;
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r13-states-"));
  const srv = await startServer(port, path.join(tmp, "civic.sqlite3"));
  const browser = await chromium.launch(fs.existsSync("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    ? { executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" } : {});
  const shots = [];
  const errors = [];
  try {
    for (const lang of LANGS) for (const [w, hgt] of SIZES) {
      const tag = `${w}-${lang}`;
      const shot = async (page, name, sel) => {
        const file = path.join(OUT, `${tag}-${name}.png`);
        if (sel) { const el = await page.$(sel); if (el) await el.screenshot({ path: file }); else return; }
        else await page.screenshot({ path: file });
        shots.push({ tag, name, file: path.basename(file), measure: await measure(page).catch(() => null) });
      };
      const open = async (mode, routes) => {
        const ctx = await browser.newContext({ viewport: { width: w, height: hgt }, deviceScaleFactor: w < 500 ? 2 : 1, reducedMotion: "reduce" });
        await ctx.addInitScript(([l, m]) => { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); }, [lang, mode]);
        const page = await ctx.newPage();
        page.on("pageerror", (e) => errors.push(tag + " " + e.message));
        if (routes) await routes(page);
        return { ctx, page };
      };
      const ready = (page) => page.waitForSelector(".qa-card, .qa-empty, .qa-login, .qa .bk-error, .qa-state", { timeout: 30000 }).then(() => sleep(500));

      // ---- житель: загрузка (ответ API задержан), список, «С ответом», пусто, ошибка
      let { ctx, page } = await open("resident", (p) => p.route(/\/api\/civic\/v2\/questions\?/, async (r) => { await sleep(5000); await r.continue().catch(() => null); }));
      await page.goto(`${base}/#questions`); await page.waitForSelector(".qa", { timeout: 40000 }); await sleep(700);
      await shot(page, "r-loading"); await ctx.close();

      ({ ctx, page } = await open("resident")); await page.goto(`${base}/#questions`); await ready(page);
      await shot(page, "r-top");
      await page.click(".qa-tabs [role=tab]:nth-child(3)"); await idle(page); await page.waitForSelector(".qa-answer", { timeout: 10000 }); await sleep(400);
      await shot(page, "r-answered");
      // форма: пустая, ошибка, длинный казахский текст, отправка, «отправлено»
      await page.click(".qa-tabs [role=tab]:nth-child(1)"); await idle(page); await sleep(600);
      await page.click(".qa__lead .bk-btn--primary"); await page.waitForSelector("#qa-text"); await sleep(300);
      await shot(page, "r-form");
      await page.click(".qa-form button[type=submit]"); await sleep(300);
      await shot(page, "r-form-error");
      await page.fill("#qa-text", LONG_KK.slice(0, 300)); await page.selectOption("#qa-district", "saryarka"); await sleep(200);
      await shot(page, "r-form-long");
      await page.route(/\/api\/civic\/v2\/questions$/, async (r) => { if (r.request().method() === "POST") { await sleep(4000); } await r.continue().catch(() => null); });
      await page.click(".qa-form button[type=submit]"); await sleep(500);
      await shot(page, "r-sending");
      await page.waitForSelector(".qa-sent", { timeout: 15000 }); await sleep(300);
      await shot(page, "r-sent");
      await ctx.close();

      ({ ctx, page } = await open("resident", (p) => p.route(/\/api\/civic\/v2\/questions\?/, (r) => r.fulfill({ status: 200, contentType: "application/json",
        body: JSON.stringify({ tab: "top", items: [], counts: { top: 0, new: 0, answered: 0 }, weekly_top: 5 }) }))));
      await page.goto(`${base}/#questions`); await ready(page); await shot(page, "r-empty"); await ctx.close();

      ({ ctx, page } = await open("resident", (p) => p.route(/\/api\/civic\/v2\/questions\?/, (r) => r.abort("failed"))));
      await page.goto(`${base}/#questions`); await ready(page); await shot(page, "r-error"); await ctx.close();

      // ---- акимат: без входа, очередь, отказ, топ-5 с ответом, отвечено, пустая очередь
      ({ ctx, page } = await open("akimat")); await page.goto(`${base}/#questions`); await ready(page);
      await shot(page, "a-login");
      await page.evaluate(async (s) => { await fetch("/api/civic/v1/session/login", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: s.user, password: s.pass }) }); }, STAFF);
      await page.reload(); await page.waitForFunction(() => window.CivicShell?.csrfToken?.(), null, { timeout: 20000 });
      await ready(page); await shot(page, "a-queue");
      const pii = await page.$(".qa-card .qa-card__warn");
      const card = pii ? await pii.evaluateHandle((n) => n.closest(".qa-card")) : await page.$(".qa-card");
      const rid = await card.evaluate((c) => c.dataset.id);
      await page.click(`.qa-card[data-id="${rid}"] .qa-card__actions .bk-btn--ghost`); await sleep(300);
      await page.evaluate((id) => document.querySelector(`.qa-card[data-id="${id}"]`).scrollIntoView({ block: "center" }), rid); await sleep(200);
      await shot(page, "a-reject");
      await page.click(`.qa-card[data-id="${rid}"] .qa-panel .bk-btn--ghost`); await sleep(200);
      await page.click(".qa-tabs [role=tab]:nth-child(2)"); await idle(page); await page.waitForSelector(".qa__week", { timeout: 10000 }); await sleep(300);
      await shot(page, "a-top");
      await page.click(".qa-card .qa-card__actions .bk-btn:not(.bk-btn--ghost)"); await sleep(300);
      await shot(page, "a-answer");
      await page.click(".qa-card .qa-panel .bk-btn--ghost"); await sleep(200);
      await page.click(".qa-tabs [role=tab]:nth-child(3)"); await idle(page); await page.waitForSelector(".qa-answer", { timeout: 10000 }); await sleep(300);
      await shot(page, "a-answered");
      // «Картина дня»: блок «Пульс района» (R08 экран, метод R08 + проверка R13)
      await page.evaluate(() => window.BirgeShell?.setSection?.("day"));
      await page.waitForSelector(".akim-pulse", { timeout: 30000 }).catch(() => null); await sleep(800);
      await page.evaluate(() => document.querySelector(".akim-pulse")?.scrollIntoView({ block: "start" })); await sleep(300);
      await shot(page, "d-pulse", ".akim-pulse");
      await shot(page, "d-day");
      await ctx.close();

      ({ ctx, page } = await open("akimat", (p) => p.route(/\/api\/civic\/v2\/questions\/staff\?/, (r) => r.fulfill({ status: 200, contentType: "application/json",
        body: JSON.stringify({ tab: "queue", items: [], counts: { queue: 0, top: 0, answered: 0 }, week: { answered: 0, limit: 5 }, reasons: [] }) }))));
      await page.goto(`${base}/#questions`); await ready(page); await shot(page, "a-empty"); await ctx.close();
      console.log("done", tag);
    }
  } catch (e) {
    errors.push("exception: " + String(e && e.stack || e).slice(0, 800));
  } finally {
    await browser.close();
    srv.kill();
    fs.writeFileSync(path.join(OUT, "STATES.json"), JSON.stringify({ repo: REPO, shots, errors }, null, 1));
    console.log(`R13 qa_states: ${shots.length} кадров, ошибок ${errors.length}`);
    if (errors.length) console.log(errors.slice(0, 5).join("\n"));
    process.exit(errors.length ? 1 : 0);
  }
})();
