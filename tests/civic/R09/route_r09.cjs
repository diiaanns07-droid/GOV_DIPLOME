#!/usr/bin/env node
/*
 * R09 · раунд 15 · подсказка R04 «нужны 2 службы» по запросу из карточки в НАСТОЯЩЕМ приложении:
 *   node tests/civic/R09/route_r09.cjs [--root <дерево сборки>] [--screenshots <папка>]
 * Жалобу подали до подключения R04 — в записи нет route_hint. Карточка сотрудника сама спрашивает POST /route, но
 * только если шлюз объявил маршрут готовым (GET /modules, ключ ml.route):
 *   • в сборке есть R04 (ветка R01 раунда 15) — настоящий route() R04, без подмен: баннер «Похоже, нужны 2 службы:
 *     Водоканал и Дорожная служба» → «Принять» → совместное исполнение, сервер сохранил подсказку (asked_at, accepted_at);
 *   • R04 в сборке нет (FINAL-4) — ни запроса /route, ни баннера, ни ошибок в консоли.
 * Сервер: python3 -B app.py (CIVIC_DEMO=1) на ВРЕМЕННОЙ SQLite + мир R09 (фикстура) с жалобой «траншея» без подсказки.
 * 1366-ru и 375-kk. Ничего не пишет в репозиторий.
 */
"use strict";
const path = require("path");
const fs = require("fs");
const os = require("os");
const net = require("net");
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
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet|ReadPixels/i;
const TRENCH = "osm-w777-1";
const SAY = {
  ru: { hint: "Похоже, нужны 2 службы: Водоканал и Дорожная служба", accept: "Принять" },
  kk: { hint: "2 қызмет керек сияқты: Сумен жабдықтау қызметі және Жол қызметі", accept: "Қабылдау" },
};
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail !== undefined ? " — " + JSON.stringify(detail).slice(0, 300) : "")); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no);
  s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

// Мир R09 (фикстура) + жалоба «траншея»: та же форма, что «яма» сцены 8, но без route_hint — её подали до R04.
function worldFile(dir) {
  const world = JSON.parse(fs.readFileSync(path.join(ROOT, "tests/civic/R09/fixtures/world_sample_r09.json"), "utf-8"));
  const pit = world.complaints.find((c) => c.id === "w-c-pit");
  const trench = JSON.parse(JSON.stringify(pit));
  Object.assign(trench, { id: "w-c-trench", scene: null, text: "Раскопали трубу водоканала и не закопали траншею, на дороге яма",
    target: { kind: "segment", id: TRENCH, label_ru: "Участок ул. Кенесары", label_kk: "Кенесары көшесінің бөлігі" },
    point: [71.4301, 51.1209], metoo: 1, metoo_times: [{ ago_hours: 5 }] });
  delete trench.route_hint;
  world.complaints.push(trench);
  const file = path.join(dir, "world_route_r09.json");
  fs.writeFileSync(file, JSON.stringify(world));
  return file;
}

async function startServer(port, db, world) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (a) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${a}`, { cwd: ROOT, env, stdio: ["ignore", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  const staff = { user: "r09-route", pass: "Birge-route-" + Math.random().toString(36).slice(2) + "-Aa1!" };
  execSync(`python3 -B -m ui.civic_store --db "${db}" create-editor ${staff.user} --password-stdin`,
           { cwd: ROOT, env, input: staff.pass + "\n", stdio: ["pipe", "ignore", "inherit"] });
  const seeded = execSync(`python3 -B -c "import json,sys; from ui.civic_feedback.v2.integration import seed_world; ` +
    `print(json.dumps(seed_world(sys.argv[1], json.load(open(sys.argv[2], encoding='utf-8')))))" "${db}" "${world}"`,
    { cwd: ROOT, env }).toString();
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  srv.seeded = JSON.parse(seeded);
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) { srv.staff = staff; return srv; } } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

const shellReady = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined"
  && mapReady && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 });
async function shot(page, name) { if (SHOTS) { await sleep(400); await page.screenshot({ path: path.join(SHOTS, name + ".png") }); } }

async function variant(browser, base, width, height, lang, staff) {
  const tag = `${width}-${lang}`;
  const say = SAY[lang];
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, hasTouch: width < 1024 });
  await ctx.addInitScript(([l]) => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); } catch (e) {} }, [lang]);
  const page = await ctx.newPage();
  const errors = [];
  const asked = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !NOISE.test(m.text())) errors.push(m.text()); });
  page.on("request", (r) => { if (/\/api\/civic\/v2\/route(\?|$)/.test(r.url())) asked.push({ method: r.method(), body: r.postData() }); });
  try {
    await page.goto(base + "/?lang=" + lang);
    await shellReady(page);
    const logged = await page.evaluate(async ([u, p]) => (await fetch("/api/civic/v1/session/login", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: u, password: p }) })).ok, [staff.user, staff.pass]);
    await page.reload();
    await shellReady(page);
    // Есть ли R04 в сборке — как его видит карточка: GET /modules, ключ ml.route со статусом ready.
    const r04 = await page.evaluate(async () => {
      try {
        const j = await (await fetch("/api/civic/v2/modules", { headers: { Accept: "application/json" } })).json();
        const list = (j && (j.modules || (j.data && j.data.modules))) || {};
        return Object.keys(list).some((k) => /(^|\.)route$/.test(k) && list[k] && list[k].status === "ready");
      } catch (e) { return false; }
    });
    await page.evaluate(() => { window.BirgeShell?.setMode?.("akimat"); window.BirgeShell?.setSection?.("complaints"); });
    const row = page.locator(`.bc-inbox__item[data-target="${TRENCH}"]`).first();
    await row.waitFor({ timeout: 10000 });
    check(`${tag}: сотрудник вошёл, в «Обращениях» жалоба «траншея» без подсказки в записи (R04 в сборке: ${r04 ? "да" : "нет"})`,
          logged && (await row.count()) === 1);
    await row.locator(".bc-inbox__row").click();
    await page.waitForSelector(".bc-inbox__item--open .bc-joint", { timeout: 8000 });
    if (!r04) {
      await sleep(1500);
      const banner = await page.$(".bc-inbox__item--open .bc-joint-hint");
      check(`${tag}: R04 нет в сборке — карточка не спрашивает /route и не показывает подсказку`, asked.length === 0 && !banner,
            { asked: asked.length, banner: !!banner });
    } else {
      await page.waitForSelector(".bc-inbox__item--open .bc-joint-hint", { timeout: 10000 }).catch(() => null);
      const title = clean(await page.textContent(".bc-inbox__item--open .bc-joint-hint__title").catch(() => ""));
      const why = clean(await page.textContent(".bc-inbox__item--open .bc-joint-hint__why").catch(() => ""));
      const sent = asked[0] && asked[0].body ? JSON.parse(asked[0].body) : {};
      check(`${tag}: карточка один раз спросила R04 POST /route по тексту жалобы`, asked.length === 1 && asked[0].method === "POST" &&
            /траншею/.test(sent.text || "") && sent.category === "roads", { asked: asked.length, sent });
      check(`${tag}: подсказка настоящего R04 — «${say.hint}»`, title.includes(say.hint), { title, why: why.slice(0, 90) });
      await shot(page, `route-${tag}-1-hint`);
      await page.click(".bc-inbox__item--open .bc-joint-hint__accept");
      await page.waitForFunction(() => document.querySelectorAll(".bc-inbox__item--open .bc-joint__part").length === 2, null,
        { timeout: 8000 }).catch(() => null);
      const parts = await page.$$eval(".bc-inbox__item--open .bc-joint__part", (n) => n.map((x) => x.getAttribute("data-service")))
        .catch(() => []);
      const hintGone = !(await page.$(".bc-inbox__item--open .bc-joint-hint"));
      check(`${tag}: «${say.accept}» → совместное исполнение Водоканал (ведущая) и Дорожная служба, подсказка исчезла`,
            parts.join() === "water,road" && hintGone, { parts, hintGone });
      const saved = await page.evaluate(async (target) => {
        const shell = window.CivicShell || {};
        const csrf = typeof shell.csrfToken === "function" ? (shell.csrfToken() || "") : "";   // как у «Обращений»
        const inbox = await (await fetch("/api/civic/v2/complaints/inbox", { headers: { "X-CSRF-Token": csrf } })).json();
        const group = ((inbox.data || {}).items || []).find((g) => (g.target || {}).id === target);
        const id = group && group.complaints && group.complaints[0] && group.complaints[0].id;
        if (!id) return null;
        const one = await (await fetch("/api/civic/v2/complaints/" + id, { headers: { "X-CSRF-Token": csrf } })).json();
        return ((one.data || {}).complaint || {}).joint || null;
      }, TRENCH);
      const hint = saved && saved.route_hint;
      check(`${tag}: сервер сохранил подсказку R04 — «запрошена из карточки» и «принята»`, !!hint && hint.services.join() === "water,road" &&
            !!hint.asked_at && !!hint.accepted_at, hint);
      await shot(page, `route-${tag}-2-accepted`);
    }
    const scroll = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);
    check(`${tag}: нет прокрутки вбок`, scroll);
    check(`${tag}: нет ошибок на странице`, errors.length === 0, errors.slice(0, 3));
  } catch (err) {
    check(`${tag}: сценарий прошёл без исключений`, false, String(err && err.message).slice(0, 300));
  } finally {
    await ctx.close();
  }
}

(async () => {
  const browser = await chromium.launch();
  try {
    for (const [w, h, lang] of [[1366, 768, "ru"], [375, 812, "kk"]]) {
      const dir = fs.mkdtempSync(path.join(os.tmpdir(), "r09-route-"));
      const port = await freePort();
      let srv = null;
      try {
        srv = await startServer(port, path.join(dir, "civic.sqlite3"), worldFile(dir));
        check(`${w}-${lang}: мир засеян с жалобой «траншея» (${srv.seeded.inserted})`, srv.seeded.inserted >= 6, srv.seeded);
        await variant(browser, `http://127.0.0.1:${port}`, w, h, lang, srv.staff);
      } catch (err) {
        check(`${w}-${lang}: приложение запустилось`, false, String(err && err.message).slice(0, 300));
      } finally {
        if (srv) srv.kill();
        fs.rmSync(dir, { recursive: true, force: true });
      }
    }
  } finally {
    await browser.close();
  }
  const ok = results.filter((r) => r.ok).length;
  console.log(`\nИТОГ: ${ok}/${results.length} ${ok === results.length ? "PASS" : "FAIL"}`);
  process.exit(ok === results.length ? 0 : 1);
})();
