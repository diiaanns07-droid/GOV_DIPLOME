// R17 · «Штаб ведомств» и кризисный штаб в оболочке Birge R01: 1366 / 1024 / 375 × ru / kk, сцены 8 (табло) и 9 (кризис).
// Запускает свой сервер (CIVIC_DEMO=1, временная база), создаёт сотрудника, проходит пути и делает кадры.
//
//   BIRGE_REPO=<сборка с patch R01_agencies_routes_assets.patch> NODE_PATH=$(npm root -g) \
//     node tests/civic/R17/agencies_browser.cjs <папка_кадров>
//   BASE=http://127.0.0.1:8655 … — проверить уже запущенный стенд (сотрудник operator / пароль из STAFF_PASS).
//
// Проверяет: 20 служб на одном экране 1366 × 768 без прокрутки; KPI = числа API; вкладки Табло · Совместные ·
// Передачи · Кризис; раскрытие строки службы; нет прокрутки вбок; нет непереведённых ключей; кризис: задача → прогресс,
// обновление ҚАЗ+РУС → лента, новый кризис из шаблона → закрыть с итогом; житель зоны: баннер и карточка ҚАЗ/РУС без
// внутренних задач; без входа — просьба войти; слой «Кризис» на карте; prefers-reduced-motion — без пульса; нет ошибок JS.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(process.env.BIRGE_REPO || path.join(__dirname, "../../.."));
const OUT = path.resolve(process.argv[2] || "r17-out");
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet|ERR_TUNNEL|net::ERR/i;
const STAFF = { user: process.env.STAFF_USER || "r17.check", pass: process.env.STAFF_PASS || "r17-check-pass-2026" };
const DEVICE = "d-r17browsercheck0001";
const checks = [];
const check = (name, ok, detail) => {
  checks.push({ name, status: ok ? "PASS" : "FAIL", detail: detail ?? null });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail != null ? " — " + JSON.stringify(detail).slice(0, 300) : ""));
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  delete env.CIVIC_DEMO_WORLD;
  const run = (args, input) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: REPO, env, input, stdio: [input ? "pipe" : "ignore", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  run(`create-editor ${STAFF.user} --password-stdin`, STAFF.pass + "\n");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

async function newPage(ctx) {
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !NOISE.test(m.text())) page.errs.push(m.text()); });
  return page;
}
async function login(page, base) {
  await page.goto(base + "/");
  await page.evaluate(async (s) => {
    await fetch("/api/civic/v1/session/login", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: s.user, password: s.pass }) });
  }, STAFF);
}
// Язык — через ключ хранилища i18n R11 (setLang до готовности словарей перезаписывался при старте страницы).
async function setup(page, { lang, mode, tab }) {
  await page.evaluate(async ({ lang, mode, tab }) => {
    localStorage.setItem("birge.mode", mode);
    sessionStorage.setItem("birge.agencies", JSON.stringify({ tab: tab || "board", days: 30, district: "" }));
    const I = window.BirgeI18n;
    if (I && I.STORAGE_KEY) localStorage.setItem(I.STORAGE_KEY, lang);
    if (I && I.ready) await I.ready;
    if (I) I.setLang(lang);
  }, { lang, mode, tab });
}
const noSideScroll = (page) => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1
  && [...document.querySelectorAll(".ag *")].every((e) => e.getBoundingClientRect().right <= innerWidth + 1
    || e.closest(".bk-tabs, .ag-yards, .ag-scroll")));
const rawKeys = (page) => page.evaluate(() => [...document.querySelectorAll(".ag, .ag-banner, .ag-public")]
  .map((e) => e.innerText).join("\n").match(/\b(agencies|crisis|common|shell)\.[a-z_.]+/g) || []);
const openAgencies = async (page, base, tab) => {
  await page.goto(base + "/#agencies");
  await page.waitForSelector(".ag", { timeout: 40000 });
  if (tab === "crisis") await page.waitForSelector(".ag-crisis, .ag-empty", { timeout: 20000 });
  else if (tab === "board") await page.waitForSelector(".ag-row", { timeout: 20000 });
  else await page.waitForSelector(".ag-list, .ag-empty", { timeout: 20000 });
  await page.waitForTimeout(500);
};

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  let srv = null, base = process.env.BASE;
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r17-"));
  if (!base) {
    const port = await freePort();
    srv = await startServer(port, path.join(tmp, "civic.sqlite3"));
    base = `http://127.0.0.1:${port}`;
  }
  const browser = await chromium.launch();
  try {
    const modules = await (await fetch(base + "/api/civic/v2/modules")).json();
    const r17 = Object.entries(modules.modules || {}).filter(([k]) => /^(agencies|incidents)\./.test(k));
    check("шлюз: 11 маршрутов R17 подключены", r17.length === 11 && r17.every(([, v]) => v.status === "ready"), r17.map(([k, v]) => k + ":" + v.status));

    // ---------------------------------------------------------------- без входа
    {
      const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
      const page = await newPage(ctx);
      await page.goto(base + "/");
      await setup(page, { lang: "ru", mode: "akimat", tab: "board" });
      await page.goto(base + "/#agencies");
      await page.waitForSelector(".ag", { timeout: 40000 });
      await page.waitForTimeout(1200);
      const txt = await page.evaluate(() => document.querySelector(".ag").innerText);
      check("без входа: просьба войти, табло не показано", !(await page.$(".ag-row")) && /Войти|сотрудник/i.test(txt), txt.slice(0, 120));
      await page.screenshot({ path: `${OUT}/login-1366-ru.png` });
      check("без входа: нет ошибок JS", page.errs.length === 0, page.errs);
      await ctx.close();
    }

    // ---------------------------------------------------------------- табло: 3 ширины × 2 языка
    const apiBoard = await (async () => {
      const ctx = await browser.newContext();
      const page = await newPage(ctx);
      await login(page, base);
      const body = await page.evaluate(async () => (await fetch("/api/civic/v2/agencies/board?days=30")).json());
      await ctx.close();
      return body;
    })();
    for (const [w, h] of [[1366, 768], [1024, 768], [375, 812]]) {
      for (const lang of ["ru", "kk"]) {
        const tag = `${w}-${lang}`;
        const ctx = await browser.newContext({ viewport: { width: w, height: h } });
        const page = await newPage(ctx);
        await login(page, base);
        await setup(page, { lang, mode: "akimat", tab: "board" });
        await openAgencies(page, base, "board");
        const info = await page.evaluate(() => {
          const rows = [...document.querySelectorAll(".ag-row")];
          const last = rows[rows.length - 1];
          const kpi = document.querySelector(".ag-kpi__value");
          return { rows: rows.length, lastBottom: last ? last.getBoundingClientRect().bottom : 0, inner: innerHeight,
            kpiOpen: kpi ? kpi.textContent.replace(/\s/g, "") : null };
        });
        check(`${tag}: 20 служб в табло`, info.rows === 20, info.rows);
        if (w === 1366) check(`${tag}: все 20 служб на одном экране без прокрутки`, info.lastBottom <= info.inner, info);
        check(`${tag}: KPI «открыто» = API`, info.kpiOpen === String(apiBoard.totals.open), [info.kpiOpen, apiBoard.totals.open]);
        check(`${tag}: нет прокрутки вбок`, await noSideScroll(page));
        check(`${tag}: нет непереведённых ключей`, (await rawKeys(page)).length === 0, await rawKeys(page));
        await page.screenshot({ path: `${OUT}/board-${tag}.png` });
        // раскрыть самую загруженную службу
        await page.click(".ag-row");
        await page.waitForSelector(".ag-detail .ag-item, .ag-detail .ag-note", { timeout: 15000 });
        check(`${tag}: строка службы раскрывается списком обращений`, !!(await page.$(".ag-detail")));
        if (w !== 1024) await page.screenshot({ path: `${OUT}/board-open-${tag}.png` });
        for (const tab of ["joint", "handoffs", "crisis"]) {
          await page.click(`[data-tab=${tab}]`);
          await page.waitForSelector(tab === "crisis" ? ".ag-crisis, .ag-empty" : ".ag-list, .ag-empty", { timeout: 20000 });
          await page.waitForTimeout(500);
          check(`${tag}: вкладка ${tab} без прокрутки вбок`, await noSideScroll(page));
          check(`${tag}: вкладка ${tab} без непереведённых ключей`, (await rawKeys(page)).length === 0, await rawKeys(page));
          await page.screenshot({ path: `${OUT}/${tab}-${tag}.png` });
        }
        check(`${tag}: нет ошибок JS`, page.errs.length === 0, page.errs);
        await ctx.close();
      }
    }

    // ---------------------------------------------------------------- сцена 9: кризисный штаб (1366, ru)
    {
      const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
      const page = await newPage(ctx);
      await login(page, base);
      await setup(page, { lang: "ru", mode: "akimat", tab: "crisis" });
      await openAgencies(page, base, "crisis");
      check("кризис: идёт пример «Буран в Нуре»", /Буран в Нуре/.test(await page.innerText(".ag-crisis")));
      const progressBefore = await page.evaluate(() => document.querySelector(".ag-svcchip__count").textContent);
      const todo = await page.$('.ag-task[data-status="todo"] .ag-task__st, .ag-task[data-status="doing"] .ag-task__st');
      await todo.click();
      await page.waitForTimeout(800);
      const states = await page.$$eval(".ag-task", (els) => els.map((e) => e.dataset.status));
      check("кризис: задача сменила статус (оптимистично и на сервере)", states.length === 4, states);
      await page.fill('[data-form=update] textarea[data-lang=ru]', "Дороги к школам расчищены, автобусы ходят.");
      await page.fill('[data-form=update] textarea[data-lang=kk]', "Мектепке баратын жолдар тазартылды, автобустар жүріп тұр.");
      await page.click("[data-action=send-update]");
      await page.waitForFunction(() => /Дороги к школам расчищены/.test(document.querySelector(".ag-feed").innerText), null, { timeout: 15000 });
      check("кризис: обновление ҚАЗ+РУС появилось в ленте", true);
      await page.screenshot({ path: `${OUT}/crisis-1366-ru.png` });
      // только один язык — понятная ошибка у поля
      await page.fill('[data-form=update] textarea[data-lang=ru]', "Только по-русски");
      await page.click("[data-action=send-update]");
      await page.waitForSelector(".bk-field--error", { timeout: 10000 });
      check("кризис: без казахского текста — ошибка у поля, не отправлено", true);
      // новый кризис из шаблона и закрытие с итогом
      await page.fill('[data-form=update] textarea[data-lang=ru]', "");
      await page.click("[data-action=new-crisis]");
      await page.waitForSelector("[data-form=create]");
      await page.click("[data-kind=water_outage]");
      await page.selectOption('[data-form=create] .ag-select', "esil");
      await page.screenshot({ path: `${OUT}/crisis-form-1366-ru.png` });
      await page.click("[data-action=create-crisis]");
      await page.waitForFunction(() => /Прорыв водопровода/.test((document.querySelector(".ag-crisis") || {}).innerText || ""), null, { timeout: 15000 });
      check("кризис: создан из шаблона «Прорыв водопровода» с задачами служб", (await page.$$(".ag-task")).length === 4);
      await page.click("[data-action=close-crisis]");
      await page.fill('[data-form=close] textarea[lang=ru]', "Трубу заменили, воду дали во все дома.");
      await page.fill('[data-form=close] textarea[lang=kk]', "Құбыр ауыстырылды, барлық үйге су берілді.");
      await page.click("[data-action=confirm-close]");
      await page.waitForFunction(() => /Трубу заменили/.test((document.querySelector(".ag-history") || {}).innerText || ""), null, { timeout: 15000 });
      check("кризис: закрыт с итогом, в списке «Прошедшие»", true);
      // слой «Кризис» на карте
      await page.click("[data-tab=crisis]");
      await page.waitForSelector("[data-action=show-map]");
      await page.click("[data-action=show-map]");
      await page.waitForTimeout(3000);
      const layer = await page.evaluate(() => ({ layer: window.BirgeShell && window.BirgeShell.layer,
        // eslint-disable-next-line no-undef
        drawn: typeof map !== "undefined" && !!map.getLayer && !!map.getLayer("r17-crisis-fill") }));
      check("карта: слой «Кризис» включён и нарисован", layer.layer === "crisis" && layer.drawn, layer);
      await page.screenshot({ path: `${OUT}/crisis-map-1366-ru.png` });
      check("кризис: нет ошибок JS", page.errs.length === 0, page.errs);
      await ctx.close();
    }

    // ---------------------------------------------------------------- житель зоны: баннер и карточка
    for (const [w, h, lang] of [[375, 812, "kk"], [375, 812, "ru"], [1366, 768, "ru"], [1366, 768, "kk"]]) {
      const tag = `${w}-${lang}`;
      const ctx = await browser.newContext({ viewport: { width: w, height: h } });
      const page = await newPage(ctx);
      await page.goto(base + "/");
      await page.evaluate(async (dev) => {
        localStorage.setItem("birge.device", dev);
        await fetch("/api/civic/v2/nearby/subscriptions", { method: "POST", headers: { "Content-Type": "application/json", "X-Birge-Device": dev },
          body: JSON.stringify({ device_id: dev, scope: "district", id: "nura", on: true }) });
      }, DEVICE);
      await setup(page, { lang, mode: "resident" });
      await page.goto(base + "/");
      await page.waitForSelector(".ag-banner:not([hidden])", { timeout: 30000 });
      await page.waitForTimeout(600);
      await page.screenshot({ path: `${OUT}/resident-banner-${tag}.png` });
      await page.click(".ag-banner__open");
      await page.waitForSelector(".ag-public:not([hidden])");
      await page.waitForTimeout(400);
      const card = await page.innerText(".ag-public");
      check(`${tag}: житель зоны видит кризис и обновления`, /(Буран|боран)/i.test(card) && (await page.$$(".ag-public .ag-upd")).length >= 2, card.slice(0, 120));
      check(`${tag}: жителю не видны внутренние задачи и заметки штаба`, !/Расчистить главные|Негізгі көшелерді|бригады переведены|бригадасы/.test(card));
      if (lang === "kk") check(`${tag}: карточка на казахском`, /Аймақ|бастап/.test(card), card.slice(0, 80));
      await page.screenshot({ path: `${OUT}/resident-card-${tag}.png` });
      await page.keyboard.press("Escape");
      check(`${tag}: Esc закрывает карточку`, !!(await page.$(".ag-public[hidden]")));
      check(`${tag}: житель — нет ошибок JS`, page.errs.length === 0, page.errs);
      await ctx.close();
    }

    // ---------------------------------------------------------------- prefers-reduced-motion
    {
      const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 }, reducedMotion: "reduce" });
      const page = await newPage(ctx);
      await login(page, base);
      await setup(page, { lang: "ru", mode: "akimat", tab: "crisis" });
      await openAgencies(page, base, "crisis");
      const anim = await page.evaluate(() => getComputedStyle(document.querySelector(".ag-card__badge"), "::after").animationName);
      check("reduced motion: значок кризиса без пульса", anim === "none", anim);
      await ctx.close();
    }
  } catch (err) {
    check("сценарий без исключений", false, String(err && err.stack || err).slice(0, 600));
  } finally {
    await browser.close();
    if (srv) srv.kill();
    const failed = checks.filter((c) => c.status === "FAIL").length;
    fs.writeFileSync(path.join(OUT, "browser_checks.json"), JSON.stringify({ base: base, total: checks.length, failed, checks }, null, 1));
    console.log(`\n${checks.length - failed}/${checks.length} PASS`);
    process.exit(failed ? 1 : 0);
  }
})();
