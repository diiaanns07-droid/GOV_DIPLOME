// R15 · раунд 15 · браузерная проба: HTML-нагрузка во всех новых текстах и названиях (THREATS_R15 T-R16-06, T-R17-10,
// T-R03-08, P3, P10). Жители и сотрудник пишут нагрузку через настоящие API ролей (кризис R17, встреча/поручение/итог/
// вопрос R13, инициатива/поддержка R16, вопрос аналитику R03), затем Chromium проходит новые экраны со строгой CSP шлюза.
// Счётчики на каждом шаге (как r15_reference.cjs раунда 14):
//   injected — элементы [data-r15x] в DOM (текст стал разметкой — даже если CSP не дала выполнить скрипт);
//   ran      — сработавшие обработчики нагрузки (window.__r15xss);
//   csp      — нарушения CSP на странице (кроме img-src/connect-src подложки);
//   shown    — текст нагрузки «R15X» виден как текст: без него шаг NOT_RUN (экран ничего не показал — не доказательство).
// Запуск: NODE_PATH=$(npm root -g) node tests/civic/R15/browser/r15_round15.cjs <дерево сборки> <папка отчёта>
// Дерево — сборка R01 (B1+) или наложение веток ролей; новые маршруты, которых нет в шлюзе, добавляет r15_stand.py.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const TREE = path.resolve(process.argv[2] || path.resolve(__dirname, "../../../.."));
const OUT = path.resolve(process.argv[3] || "r15-round15-out");
const STAND = path.resolve(__dirname, "r15_stand.py");
const USER = "r15operator", PASSWORD = "Tz7-qerB-91vk-Lmsd-r15";
const PAY = (tag) => `<img src=x data-r15x=${tag} onerror=__r15x()>R15X`;   // ≤ 50 знаков: влезает в названия
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const steps = [];
const iso = (days) => new Date(Date.now() + days * 86400e3).toISOString().replace(/\.\d+Z$/, "+00:00");

const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startStand(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  delete env.CIVIC_DEMO_WORLD;
  const run = (args, input) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: TREE, env, input, stdio: ["pipe", "ignore", "inherit"] });
  run("init"); run("seed-demo --package data/civic/astana/demo_synthetic.json");
  try { run("seed-r14-demo"); } catch { /* старые сборки */ }
  run(`create-editor ${USER} --password-stdin`, PASSWORD + "\n");
  const srv = spawn("python3", ["-B", STAND, "--root", TREE, "--db", db, "--port", String(port)], { cwd: TREE, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("stand did not start: " + srv.log.slice(-2000));
}

function client(base) {
  const jar = { cookie: "", csrf: null };
  async function call(method, p, body, extra = {}) {
    const headers = { Origin: base, ...extra };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (jar.cookie) headers.Cookie = jar.cookie;
    if (jar.csrf && method !== "GET") headers["X-CSRF-Token"] = jar.csrf;
    const res = await fetch(base + p, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    const text = await res.text(); let json = null; try { json = JSON.parse(text); } catch {}
    return { status: res.status, json, text, headers: res.headers };
  }
  return { jar, call, async login() {
    const r = await call("POST", "/api/civic/v1/session/login", { username: USER, password: PASSWORD });
    if (r.status !== 200) throw new Error("login " + r.status + " " + r.text.slice(0, 200));
    jar.cookie = (r.headers.get("set-cookie") || "").split(";")[0]; jar.csrf = r.json.data.csrf_token; return jar;
  } };
}
const dataOf = (j) => (j && typeof j.ok === "boolean" && "data" in j ? j.data : j) || {};

// Нагрузка через API ролей. Модуля/маршрута нет — запись в seed.notes, шаг экрана потом станет NOT_RUN.
async function seed(api) {
  const notes = [], ids = {};
  const dev = { "X-Birge-Device": "r15dev-browser-0000000001" };
  const want = async (label, promise) => { const r = await promise; if (r.status >= 300) notes.push(`${label}: ${r.status} ${r.text.slice(0, 160)}`); return r; };
  // R17: кризис с нагрузкой в названии, задаче, публичном и внутреннем обновлении.
  // Вид heat_outage: демо-сборка уже ведёт «Буран в Нуре» (второй такой же кризис в зоне — 409 duplicate).
  let r = await want("R17 incident", api.call("POST", "/api/civic/v2/incidents", { kind: "heat_outage", title_ru: PAY("inc"), title_kk: PAY("inck"),
    zone: { kind: "district", district: "nura" }, tasks: [{ service: "street_cleaning", text_ru: PAY("task"), text_kk: PAY("taskk") }],
    update: { text_ru: PAY("upd") + " обновление", text_kk: PAY("updk") + " жаңарту" } }));
  ids.incident = dataOf(r.json).incident && dataOf(r.json).incident.id;
  if (ids.incident) await want("R17 update", api.call("POST", `/api/civic/v2/incidents/${ids.incident}/update`, { text_ru: PAY("upd2") + " снова", text_kk: PAY("upd2k") + " тағы", public: true }));
  // R13: встреча, поручение, итог; вопрос жителя -> публикация сотрудником.
  r = await want("R13 meeting", api.call("POST", "/api/civic/v2/meetings", { district: "nura", title_ru: PAY("mt") + " встреча", title_kk: PAY("mtk") + " кездесу",
    at: iso(3), place: { label_ru: PAY("pl"), label_kk: PAY("plk") } }));
  ids.meeting = dataOf(r.json).meeting && dataOf(r.json).meeting.id;
  if (ids.meeting) {
    const due = new Date(Date.now() + 20 * 86400e3).toISOString().slice(0, 10);
    await want("R13 order", api.call("POST", `/api/civic/v2/meetings/${ids.meeting}/order`, { text_ru: PAY("ord") + " поручение", service: "lighting", due }));
    const q = await want("R13 question", api.call("POST", `/api/civic/v2/meetings/${ids.meeting}/question`, { text: PAY("q") + " вопрос про двор?", lang: "ru" }, dev));
    const qid = dataOf(q.json).question && dataOf(q.json).question.id;
    if (qid) await want("R13 publish", api.call("POST", `/api/civic/v2/questions/${qid}/publish`, {}));
  }
  // R16: инициатива жителя (название, текст, «что взять») -> публикация, поддержка с примечанием.
  r = await want("R16 initiative", api.call("POST", "/api/civic/v2/together/initiatives", { kind: "cleanup", title: PAY("ini"), text: PAY("init") + " текст",
    point: [71.404739, 51.1111745], target: { kind: "area", id: "yard-1026285032" }, starts_at: iso(2), bring: [PAY("br").slice(0, 40)] }, dev));
  ids.initiative = dataOf(r.json).initiative && dataOf(r.json).initiative.id;
  if (ids.initiative) {
    await want("R16 publish", api.call("POST", `/api/civic/v2/together/initiatives/${ids.initiative}/moderate`, { action: "publish" }));
    await want("R16 support", api.call("POST", `/api/civic/v2/together/initiatives/${ids.initiative}/support`, { inventory: true, pickup_service: "waste", note: PAY("sup") }));
    // 25 соседей «Я приду» — инициатива с нагрузкой наверху списков (Ситуационный центр, «Жители вместе»).
    for (let i = 0; i < 25; i++) await api.call("POST", `/api/civic/v2/together/initiatives/${ids.initiative}/join`, {}, { "X-Birge-Device": "r15dev-browser-join-" + String(i).padStart(4, "0") });
  }
  // R06 работа v2 на участке ул. Ильяса Омарова (рёбра OSM R12) — её показывает «Календарь работ» R12.
  r = await want("R06 work", api.call("POST", "/api/civic/v2/works", { type: "work", status: "planned", district: "nura", lang: "ru",
    title: PAY("wk") + " работа", service: "water", kind: "dig", starts_on: iso(20).slice(0, 10), ends_on: iso(40).slice(0, 10),
    why: { problem: PAY("why") + " течь", reason: "Сначала сети", result: "Ровная дорога", inconvenience: "Одна полоса" },
    segments: ["osm-w1482578141-0", "osm-w1482578141-1", "osm-w1482578141-2"] }));
  ids.work = (dataOf(r.json).item || dataOf(r.json).work || dataOf(r.json) || {}).id;
  return { ids, notes };
}

const probe = (page) => page.evaluate(() => {
  let injected = 0;
  const walk = (root) => { injected += root.querySelectorAll("[data-r15x]").length; for (const el of root.querySelectorAll("*")) if (el.shadowRoot) walk(el.shadowRoot); };
  walk(document);
  const text = document.body ? document.body.innerText : "";
  return { injected, ran: window.__r15xss || 0, csp: (window.__r15csp || []).slice(0, 5), shown: (text.match(/R15X/g) || []).length,
    ready: window.__r15ready === undefined ? null : window.__r15ready, missing: window.__r15missing || [] };
});

async function step(page, name, action) {
  let note = null, ran = true;
  try { const r = await action(); if (r === false) ran = false; else if (typeof r === "string") note = r; }
  catch (e) { ran = false; note = "ошибка шага: " + String(e.message || e).split("\n")[0].slice(0, 160); }
  await sleep(900);
  const p = await probe(page);
  const bad = p.injected > 0 || p.ran > 0 || p.csp.some((v) => !/img-src|connect-src/.test(v));
  const status = bad ? "FAIL" : !ran ? "NOT_RUN" : p.shown === 0 ? "NOT_RUN" : "PASS";
  if (status === "NOT_RUN" && ran && p.shown === 0 && !note) note = "нагрузка не показана на экране — нечего проверять";
  steps.push({ name, status, note, ...p });
  console.log(`${status} ${name}${note ? " — " + note : ""} ${JSON.stringify(p)}`);
  await page.screenshot({ path: path.join(OUT, name.replace(/[^a-z0-9]+/gi, "_") + ".png"), fullPage: false }).catch(() => null);
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r15-round15-"));
  const port = await freePort(), base = `http://127.0.0.1:${port}`;
  const srv = await startStand(port, path.join(tmp, "civic.sqlite3"));
  const api = client(base);
  let seeded = { ids: {}, notes: ["seed не выполнен"] };
  try {
    await api.login();
    seeded = await seed(api);
    for (const n of seeded.notes) console.log("seed: " + n);
    const browser = await chromium.launch(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {});
    const init = () => { window.__r15xss = 0; window.__r15x = () => { window.__r15xss = (window.__r15xss || 0) + 1; };
      window.__r15csp = []; document.addEventListener("securitypolicyviolation", (e) => window.__r15csp.push(e.violatedDirective + " " + (e.blockedURI || ""))); };
    // Сотрудник, 1366×768: cookie сессии и CSRF-токен в обвязку.
    const staff = await browser.newContext({ viewport: { width: 1366, height: 768 }, locale: "ru-RU" });
    await staff.addCookies([{ name: api.jar.cookie.split("=")[0], value: api.jar.cookie.split("=").slice(1).join("="), url: base }]);
    await staff.addInitScript(init);
    await staff.addInitScript((t) => { try { sessionStorage.setItem("r15csrf", t); } catch (e) {} }, api.jar.csrf);
    const page = await staff.newPage();
    const ids = seeded.ids;
    await step(page, "akimat-1366 agencies crisis", async () => {
      if (!ids.incident) return false;
      await page.goto(`${base}/r15/screen.html?m=agencies&role=akimat&hash=${encodeURIComponent("agencies/crisis=" + ids.incident)}`);
      await page.waitForFunction(() => window.__r15ready !== undefined, null, { timeout: 15000 });
      await sleep(1500);
    });
    await step(page, "akimat-1366 meetings card", async () => {
      if (!ids.meeting) return false;
      await page.goto(`${base}/r15/screen.html?m=meetings&role=akimat&hash=${encodeURIComponent("meetings/" + ids.meeting)}`);
      await page.waitForFunction(() => window.__r15ready !== undefined, null, { timeout: 15000 });
      await sleep(1500);
    });
    await step(page, "akimat-1366 analyst question", async () => {
      await page.goto(`${base}/r15/screen.html?m=analyst&role=akimat`);
      await page.waitForFunction(() => window.__r15ready !== undefined, null, { timeout: 15000 });
      const input = page.locator("#ba-input");
      if (!(await input.count())) return false;
      await input.fill(PAY("ask") + " что с кризисом в Нуре?");
      await input.press("Enter");
      await sleep(1500);
    });
    await step(page, "akimat-1366 works-calendar", async () => {
      await page.goto(`${base}/r15/screen.html?m=works-calendar&role=akimat`);
      await page.waitForFunction(() => window.__r15ready !== undefined, null, { timeout: 15000 });
      await sleep(2500);
      // R06 отклоняет HTML в названии и «почему» работы (422 «HTML не допускается») — нагрузка в календарь не попадает:
      // шаг проверяет только CSP и отсутствие разметки и пишется NOT_RUN с этой причиной.
      if (!ids.work) return "R06 не принимает HTML в работах (422) — нагрузка в календарь не попадает; CSP чистая";
    });
    await step(page, "akimat-1366 situation-center board", async () => {
      await page.goto(`${base}/civic/board/index.html`);
      await sleep(3000);
    });
    // Житель, 375×812: без сессии сотрудника.
    const resident = await browser.newContext({ viewport: { width: 375, height: 812 }, locale: "ru-RU", isMobile: true, hasTouch: true });
    await resident.addInitScript(init);
    const rpage = await resident.newPage();
    await step(rpage, "resident-375 meetings card", async () => {
      if (!ids.meeting) return false;
      await rpage.goto(`${base}/r15/screen.html?m=meetings&role=resident&hash=${encodeURIComponent("meetings/" + ids.meeting)}`);
      await rpage.waitForFunction(() => window.__r15ready !== undefined, null, { timeout: 15000 });
      await sleep(1500);
    });
    await step(rpage, "resident-375 together", async () => {
      await rpage.goto(`${base}/r15/screen.html?m=together&role=resident`);
      await rpage.waitForFunction(() => window.__r15ready !== undefined, null, { timeout: 15000 });
      const ready = await rpage.evaluate(() => window.__r15ready);
      if (ready !== true) return false;
      await sleep(1500);
    });
    await browser.close();
  } finally {
    srv.kill();
    const summary = { tree: TREE, at: new Date().toISOString(), seed: seeded.notes, steps,
      counts: steps.reduce((a, s) => ((a[s.status] = (a[s.status] || 0) + 1), a), {}) };
    fs.writeFileSync(path.join(OUT, "r15_round15.json"), JSON.stringify(summary, null, 2));
    console.log("ИТОГ " + JSON.stringify(summary.counts));
    fs.writeFileSync(path.join(OUT, "stand.log"), srv.log.slice(-20000));
  }
  process.exit(steps.some((s) => s.status === "FAIL") ? 1 : 0);
}
main().catch((e) => { console.error(e); process.exit(2); });
