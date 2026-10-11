/*
 * R04 · волна мелочей п. 8 и п. 9 в настоящем приложении (сборка R01 + patch'и R04), Chromium, 375/1366 × ru/kk.
 *
 *   node tests/civic/R04/round14/app_polish_r04.cjs --root <папка сборки> [--screenshots <папка>]
 *
 * Сервер: python3 -B app.py с CIVIC_DEMO=1 на ВРЕМЕННОЙ SQLite (seed-demo R02 + демо-жалобы R01/R09) + сотрудник.
 * Сцена у остановки «Хан Шатыр» (OSM node 4109037549, Нура), тексты синтетические:
 *   - жалобы с грубыми словами (ru и kk): всё, что получает устройство жителя (ответ API, «Мои обращения»), — со
 *     звёздочками; на экранах жителя текстов нет вовсе (п. 8, публичная сторона);
 *   - акимат в карточке остановки видит оригинал с меткой «Содержит грубые слова» (п. 8);
 *   - ошибочное «Я тоже» с текстом другого жителя и ошибочно отмеченный дубль — в блоке «Объединено с этим»;
 *     «Это разные проблемы» — одно нажатие: отдельная жалоба, число людей у остановки пересчитано (п. 9).
 * Печатает PASS/FAIL по каждой проверке; код выхода 1, если есть FAIL.
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
const ROOT = path.resolve(args.includes("--root") ? args[args.indexOf("--root") + 1] : path.resolve(__dirname, "../../../.."));
const SHOTS = args.includes("--screenshots") ? path.resolve(args[args.indexOf("--screenshots") + 1]) : null;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
const STOP = [71.406553, 51.131155];
const TARGET = { kind: "object", id: "osm-node-4109037549" };
const YARD = [71.4102, 51.1328];      // двор ~300 м от остановки: другая цель
const AUTHOR = "d-r04-author-rude-0000000001";
const RUDE = {
  ru: "Вечером на остановке темно, заебали уже! Когда почините фонарь?",
  kk: "Аялдамада кешке жарық жоқ, ақымақтар! Шамды қашан жөндейсіздер?",
};
const NOTE = {   // у каждого варианта своё ошибочное «Я тоже»
  "375-ru": "Во дворе дома 3 не вывозят мусор вторую неделю",
  "375-kk": "Ауладағы қоқыс екі апта бойы шығарылмайды",
  "1366-kk": "Ауладағы қоқыс жәшіктері толып кетті",
  "1366-ru": "Во дворе дома 7 переполнены мусорные баки",
};
const PIT = [71.4031, 51.1296];       // другое место: ошибочно отмеченный дубль
const WORDS = {
  ru: { rude: "Содержит грубые слова", merged: "Объединено с этим", separate: "Это разные проблемы", separated: "Разделено" },
  kk: { rude: "Дөрекі сөздер бар", merged: "Осымен біріктірілген", separate: "Бұл әртүрлі мәселелер", separated: "Бөлінді" },
};
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet|ReadPixels/i;
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
  const staff = { user: "r04-operator", pass: "R04-app-" + Math.random().toString(36).slice(2) + "-Aa1!" };
  execSync(`python3 -B -m ui.civic_store --db "${db}" create-editor ${staff.user} --password-stdin`,
           { cwd: ROOT, env, input: staff.pass + "\n", stdio: ["pipe", "ignore", "inherit"] });
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) { srv.staff = staff; return srv; } } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

// API из Node: житель (заголовок устройства) и сотрудник (cookie + CSRF), как браузер того же сайта.
function api(base) {
  let cookie = null, csrf = null;
  const call = async (method, p, body, device) => {
    const headers = { "Content-Type": "application/json", Origin: base.replace(/\/$/, "") };
    if (device) headers["X-Birge-Device"] = device;
    if (cookie) { headers.Cookie = cookie; if (method !== "GET") headers["X-CSRF-Token"] = csrf; }
    const res = await fetch(base.replace(/\/$/, "") + p, { method, headers, body: body ? JSON.stringify(body) : undefined });
    const data = await res.json().catch(() => null);
    if (p.endsWith("/session/login") && res.ok) { cookie = res.headers.get("set-cookie").split(";")[0]; csrf = data.data.csrf_token; }
    return { status: res.status, data };
  };
  return { call, staff: (user, pass) => call("POST", "/api/civic/v1/session/login", { username: user, password: pass }) };
}

const shellReady = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined"
  && mapReady && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 });

async function shot(page, name) {
  if (!SHOTS) return;
  await sleep(450);
  await page.screenshot({ path: path.join(SHOTS, name + ".jpg"), type: "jpeg", quality: 82 });
}

async function tapStop(page, width) {
  // Остановка — в середине свободной части карты (над шторкой на телефоне, слева от панели на ноутбуке), нажатие точно в неё.
  const xy = await page.evaluate(async (p) => {
    const c = map.getCanvas().getBoundingClientRect();
    const panel = document.querySelector(".r07-panel, .bc-panel"); const r = panel && !panel.hidden ? panel.getBoundingClientRect() : null;
    const mobile = innerWidth < 1024;
    const want = { x: (c.left + (r && !mobile ? r.left : c.right)) / 2, y: (c.top + (r && mobile ? Math.min(r.top, c.bottom) : c.bottom)) / 2 };
    map.jumpTo({ center: p, zoom: 17 });
    const q = map.project(p);
    map.panBy([c.left + q.x - want.x, c.top + q.y - want.y], { duration: 0 });
    await new Promise((ok) => setTimeout(ok, 700));
    const now = map.project(p);
    return { x: c.left + now.x, y: c.top + now.y };
  }, STOP);
  await sleep(500);
  if (width < 1024) await page.touchscreen.tap(xy.x, xy.y); else await page.mouse.click(xy.x, xy.y);
}

// Карточка остановки: как житель — нажатием в значок на карте; если на телефоне значок закрыт шторкой —
// ссылкой «#target=…» (тот же путь, что из «Картины дня» и QR). В отчёт пишем, каким путём открыли.
// У акимата на телефоне место нажатия совпадает с кнопкой «Что построить?» (R11, круг 16) — там сразу ссылка.
async function openStop(page, width, linkFirst) {
  if (!linkFirst) {
    await tapStop(page, width);
    if (await page.waitForSelector(".r07-card", { timeout: 6000 }).then(() => true, () => false)) return "нажатием на карте";
  }
  await page.evaluate((id) => { location.hash = "#target=object:" + id; }, TARGET.id);
  if (await page.waitForSelector(".r07-card", { timeout: 8000 }).then(() => true, () => false)) return "по ссылке #target";
  return "нет карточки";
}

// Тосты появляются и исчезают — запоминаем текст всех добавленных узлов.
async function watchToasts(page) {
  await page.evaluate(() => {
    window.__r04toasts = [];
    new MutationObserver((list) => list.forEach((m) => m.addedNodes.forEach((n) => {
      if (n.nodeType === 1 && /toast/.test(String(n.className) + " " + String(n.parentElement && n.parentElement.className))) window.__r04toasts.push(n.textContent);
    }))).observe(document.body, { childList: true, subtree: true });
  });
}

const reportedCount = async (page) => Number(((await page.textContent(".r07-card__reported").catch(() => "")) || "").replace(/\s/g, "").match(/\d+/)?.[0] || NaN);

async function variant(browser, base, width, height, lang, srv, resident, extraDup) {
  const tag = `${width}-${lang}`;
  const W = WORDS[lang];
  // Новое ошибочное «Я тоже» с текстом другого жителя (у каждого варианта своё — предыдущее уже разделено).
  const mv = `d-r04-metoo-${tag.replace(/\W/g, "")}-000000`;
  const top = srv.rudeId;
  const joined = await resident.call("POST", `/api/civic/v2/complaints/${top}/metoo`, { note: { text: NOTE[tag], point: YARD, category: "waste" } }, mv);
  check(`${tag}: житель нажал «Я тоже» (текст ушёл вместе с ним)`, joined.status === 200 && joined.data.data.result === "added", joined.data);

  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, hasTouch: width < 1024 });
  await ctx.addInitScript(([l, d]) => { try { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l);
    localStorage.setItem("birge.device", d); } catch (e) {} }, [lang, AUTHOR]);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !NOISE.test(m.text())) errors.push(m.text()); });
  await page.goto(base);
  await shellReady(page);
  await sleep(800);

  // п. 8 — житель: всё, что получает его устройство, без мата (ответ «Мои обращения» — со звёздочками),
  // а на экране жителя (карточка остановки) чужих текстов нет совсем.
  const mineApi = await resident.call("GET", "/api/civic/v2/complaints/mine", null, AUTHOR);
  const mineTexts = (mineApi.data?.data?.items || []).map((i) => i.text);
  check(`${tag}: житель — ответ «Мои обращения» со звёздочками (оригинал не уходит на устройство)`,
        mineTexts.some((x) => x.includes("з******")) && mineTexts.some((x) => x.includes("а********"))
        && !JSON.stringify(mineApi.data).includes("заебали") && !JSON.stringify(mineApi.data).includes("ақымақтар"), mineTexts);
  const via = await openStop(page, width, false);
  const pub = ((await page.textContent("body").catch(() => "")) || "");
  check(`${tag}: житель — карточка остановки (${via}) без грубых слов`, via !== "нет карточки" && !/заебали|ақымақтар/.test(pub));
  await shot(page, `r04-${tag}-1-resident-card-clean`);

  // Акимат: вход, карточка остановки.
  const logged = await page.evaluate(async ([u, p]) => (await fetch("/api/civic/v1/session/login", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: u, password: p }) })).ok, [srv.staff.user, srv.staff.pass]);
  await page.reload();
  await shellReady(page);
  await page.evaluate(() => window.BirgeShell?.setMode?.("akimat"));
  await sleep(1200);
  const via2 = await openStop(page, width, width < 1024);
  const card = via2 !== "нет карточки";
  await page.waitForSelector(".r07-tag--rude", { timeout: 10000 }).catch(() => null);
  const quotes = await page.$$eval(".r07-texts .r07-quotes li", (n) => n.map((li) => li.textContent.replace(/\s+/g, " ").trim()));
  const orig = quotes.filter((q) => q.includes("заебали") || q.includes("ақымақтар"));
  check(`${tag}: акимат (${via2}) — оригинал текста и метка «${W.rude}»`, logged && card && orig.length >= 1 && orig.every((q) => q.includes(W.rude)), quotes);
  await page.evaluate(() => document.querySelector(".r07-texts")?.scrollIntoView({ block: "start" }));
  await shot(page, `r04-${tag}-2-akimat-original-rude-tag`);

  // п. 9 — «Объединено с этим».
  const merged = await page.waitForSelector(".r07-merged", { timeout: 10000 }).then(() => true, () => false);
  if (merged) {
    await page.click(".r07-merged > summary");
    await sleep(300);
    await page.evaluate(() => document.querySelector(".r07-merged")?.scrollIntoView({ block: "start" }));
  }
  const items = await page.$$eval(".r07-merged li", (n) => n.map((li) => ({ text: li.textContent.replace(/\s+/g, " ").trim(),
    id: li.querySelector("[data-act='separate']")?.dataset.item, h: Math.round(li.querySelector("[data-act='separate']")?.getBoundingClientRect().height || 0) })));
  const mine2 = items.find((i) => i.text.includes(NOTE[tag]));
  check(`${tag}: акимат — «${W.merged}»: ошибочное «Я тоже» с текстом жителя и кнопкой «${W.separate}» (≥ 44 px)`,
        merged && mine2 && mine2.id && mine2.id.startsWith("mt-") && mine2.text.includes(W.separate) && mine2.h >= 44, items);
  await shot(page, `r04-${tag}-3-akimat-merged`);

  const before = await reportedCount(page);
  await watchToasts(page);
  if (mine2) await page.click(`[data-act='separate'][data-item='${mine2.id}']`);
  await sleep(600);
  await shot(page, `r04-${tag}-4-separated-toast`);
  await sleep(1500);
  const toasts = await page.evaluate(() => window.__r04toasts || []);
  const after = await reportedCount(page);
  const restIds = await page.$$eval(".r07-merged [data-act='separate']", (n) => n.map((b) => b.dataset.item));
  check(`${tag}: «${W.separate}» — одно нажатие: «${W.separated}…», у остановки стало ${before} → ${after}`,
        toasts.some((x) => x.includes(W.separated)) && after === before - 1 && mine2 && !restIds.includes(mine2.id), { before, after, toasts });
  const separated = await resident.call("GET", "/api/civic/v2/complaints/mine", null, mv);
  const own = (separated.data?.data?.items || []).map((i) => [i.relation, i.text]);
  check(`${tag}: у того жителя «Мои обращения» — теперь его собственная жалоба с его текстом`,
        own.length === 1 && own[0][0] === "author" && own[0][1] === NOTE[tag], own);

  if (extraDup) {   // ошибочно отмеченный дубль — тоже одним нажатием
    const dupItem = items.find((i) => i.id && !i.id.startsWith("mt-"));
    if (dupItem) {
      await page.evaluate(() => { const d = document.querySelector(".r07-merged"); if (d && !d.open) d.querySelector("summary").click(); });
      await sleep(300);
      const b2 = await reportedCount(page);
      await page.click(`[data-act='separate'][data-item='${dupItem.id}']`);
      await sleep(600);
      await shot(page, `r04-${tag}-5-duplicate-separated`);
      await sleep(2000);
      const a2 = await reportedCount(page);
      check(`${tag}: ошибочный дубль (другое место) разделён одним нажатием: у остановки ${b2} → ${a2}`, a2 === b2 - 1, { b2, a2 });
    } else check(`${tag}: в «${W.merged}» есть отмеченный дубль`, false, items);
  }
  const scroll = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);
  check(`${tag}: нет прокрутки вбок`, scroll);
  check(`${tag}: нет ошибок на странице`, errors.length === 0, errors.slice(0, 3));
  await ctx.close();
}

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r04-app-"));
  const port = await freePort();
  const base = `http://127.0.0.1:${port}/`;
  let srv = null, browser = null;
  try {
    srv = await startServer(port, path.join(tmp, "civic.sqlite3"));
    const client = api(base);       // станет сотрудником после входа
    const resident = api(base);     // житель: без входа, только заголовок устройства
    // Сцена: две жалобы с грубыми словами от одного жителя (ru и kk) у остановки и ошибочный «дубль».
    const made = [];
    for (const lang of ["ru", "kk"]) {
      const r = await client.call("POST", "/api/civic/v2/complaints", { text: RUDE[lang], category: "lighting", point: STOP, target: TARGET }, AUTHOR);
      made.push(r);
    }
    check("жалобы с грубыми словами созданы; автору ответ уже со звёздочками",
          made.every((r) => r.status === 201) && made[0].data.data.complaint.text.includes("з******"), made.map((r) => r.data?.data?.complaint?.text));
    srv.rudeId = made[0].data.data.complaint.id;
    const pit = await client.call("POST", "/api/civic/v2/complaints", { text: "Большая яма на дороге у въезда во двор, машины объезжают",
      category: "roads", point: PIT }, "d-r04-pothole-000000000001");
    await client.staff(srv.staff.user, srv.staff.pass);
    const dup = await client.call("POST", `/api/civic/v2/complaints/${pit.data.data.complaint.id}/duplicate`, { of: srv.rudeId });
    check("сотрудник ошибочно отметил «яму» дублем «нет света»", dup.status === 200, dup.data);
    browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
    const runs = [[375, 812, "ru"], [375, 812, "kk"], [1366, 768, "kk"], [1366, 768, "ru"]];
    for (const [i, [w, h, lang]] of runs.entries()) {
      await variant(browser, base, w, h, lang, srv, resident, i === runs.length - 1);
    }
  } catch (err) {
    console.error(err);
    check("приложение и браузер запустились", false, String(err && err.message));
  } finally {
    if (browser) await browser.close();
    if (srv) srv.kill();
  }
  const failed = results.filter((r) => !r.ok).length;
  console.log(`\nИТОГ: ${results.length - failed}/${results.length} PASS`);
  process.exit(failed ? 1 : 0);
})();
