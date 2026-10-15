// R06 раунд 15 в браузере: «Работы и отключения» v2 (служба, вид, участок улицы по карте R12), «Проекты и идеи» без
// входа и с картинками по виду, лента уведомлений «Что нового для меня».
//
//   NODE_PATH="$(npm root -g)" PYTHON=python3 node tests/civic/R06/round15/browser_r15.cjs [дерево] [папка-кадров] [--only works,ideas,notify]
//
// Сервер — app.py дерева с CIVIC_DEMO=1 на временной базе (как run-city.bat) + сотрудник для проверки; на каждую часть —
// свежий сервер. В облаке подложка OpenFreeMap не грузится: карта рисует упрощённый фон — это нормально.
// Демо-данные — synthetic («Пример»); в базу владельца ничего не пишется.
"use strict";
const { chromium } = require("playwright");
const { spawn, execFileSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os"), crypto = require("crypto");

const args = process.argv.slice(2);
const onlyArg = args.find((a) => a.startsWith("--only"));
const ONLY = onlyArg ? (onlyArg.split("=")[1] || args[args.indexOf(onlyArg) + 1] || "").split(",") : null;
const positional = args.filter((a, i) => !a.startsWith("--") && !(onlyArg === "--only" && args[i - 1] === "--only"));
const ROOT = path.resolve(positional[0] || ".");
const OUT = positional[1] ? path.resolve(positional[1]) : null;
if (OUT) fs.mkdirSync(OUT, { recursive: true });
const PY = process.env.PYTHON || "python3";
const results = [];
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail && !ok ? " — " + String(detail).slice(0, 600) : ""));
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });
const PASSWORD = "Tulpar-" + crypto.randomBytes(9).toString("base64url") + "-2026";
const TECH = ["undefined", "null", "NaN", "works.", "notify.", "idea.", "proposal.", "[object", "Error:"];

async function start(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1",
    BIRGE_AKIM_SUBSCRIPTIONS: path.join(path.dirname(db), "subs.json") };
  const run = (argv, input) => execFileSync(PY, ["-B", "-m", "ui.civic_store", "--db", db, ...argv],
    { cwd: ROOT, env, input, stdio: [input ? "pipe" : "ignore", "ignore", "inherit"] });
  run(["init"]);
  run(["seed-demo", "--package", "data/civic/astana/demo_synthetic.json"]);
  run(["seed-r14-demo"]);
  run(["create-editor", "checker", "--password-stdin", "--public-label", "Акимат"], PASSWORD + "\n");
  const srv = spawn(PY, ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}
async function fresh() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "r06r15-"));
  const port = await freePort();
  const srv = await start(port, path.join(dir, "civic.sqlite3"));
  return { srv, base: `http://127.0.0.1:${port}`, dir };
}

async function newPage(browser, width, lang, mode) {
  const ctx = await browser.newContext({ viewport: { width, height: width < 600 ? 812 : 768 }, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
  await ctx.addInitScript(([m, l]) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); } catch (e) {} }, [mode, lang]);
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push(e.message));
  return page;
}
async function shot(page, name) {
  if (OUT) await page.screenshot({ path: path.join(OUT, name + ".png"), fullPage: false });
}
async function login(page) {
  const status = await page.evaluate(async (pw) => {
    const r = await fetch("/api/civic/v1/session/login", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "checker", password: pw }) });
    return r.status;
  }, PASSWORD);
  if (status !== 200) throw new Error("login " + status);
}
// Видимый текст экрана раздела: технические слова, горизонтальная прокрутка.
async function textAudit(page, sel) {
  return page.evaluate(([s, tech]) => {
    const root = document.querySelector(s);
    if (!root) return { missing: true };
    const text = root.innerText || "";
    return { tech: tech.filter((w) => text.includes(w)), overflow: document.documentElement.scrollWidth > innerWidth + 1, text };
  }, [sel, TECH]);
}
async function waitMap(page) {
  await page.waitForFunction(() => typeof mapReady !== "undefined" && mapReady && typeof map !== "undefined" && map && map.loaded && map.isStyleLoaded && map.isStyleLoaded(), null, { timeout: 30000 }).catch(() => {});
}

// ------------------------------------------------------------------------------------------------ работы v2
async function worksPart(browser) {
  const { srv, base } = await fresh();
  try {
    for (const [width, lang] of [[1366, "ru"], [1366, "kk"], [375, "ru"]]) {
      const tag = `works-${width}-${lang}`;
      const page = await newPage(browser, width, lang, "akimat");
      await page.goto(base + "/", { waitUntil: "domcontentloaded" });
      await login(page);
      await page.goto(base + "/#works", { waitUntil: "domcontentloaded" });
      await waitMap(page);
      await page.waitForSelector(".rw-card, .rw-head", { timeout: 20000 });
      await page.waitForSelector(".rw-card", { timeout: 20000 }).catch(() => {});
      const metas = await page.$$eval(".rw-card .ri-meta", (els) => els.map((e) => e.textContent));
      check(`${tag}: в строке записи — служба (Водоканал / Сумен…)`, metas.some((t) => /Водоканал|Сумен жабдықтау/.test(t)), metas.join(" | "));
      await shot(page, `${tag}-list`);
      await page.click("[data-key=add]");
      await page.waitForSelector(".rw-form");
      const kinds = await page.$$eval("#rw-kind option", (o) => o.map((x) => x.value));
      check(`${tag}: вид работ v2 — 6 видов`, kinds.join(",") === "dig,surface,closure,landscape,lighting,other", kinds.join(","));
      const services = await page.$$eval("#rw-service option", (o) => o.length);
      check(`${tag}: служба — 20 служб таблицы`, services === 20, services);
      check(`${tag}: поле «Начало работ» у работы`, !!(await page.$("#rw-start[type=date]")));
      check(`${tag}: блок «Участок улицы»`, !!(await page.$(".rw-section [data-key=section-pick]")));
      await page.selectOption("#rw-kind", "dig");
      const svc = await page.$eval("#rw-service", (e) => e.value);
      check(`${tag}: раскопка → служба по умолчанию «Водоканал»`, svc === "water", svc);
      await shot(page, `${tag}-form`);
      if (width === 375) { await page.close(); continue; }
      // Участок по карте: два нажатия на улицу Ильяса Омарова (Нура) → линия R12 → «Готово».
      await page.fill("#rw-title", lang === "kk" ? "Су құбырын ауыстыру" : "Замена водопровода");
      await page.fill("#rw-start", "2026-11-02");
      await page.fill("#rw-planned_end", "2026-11-20");
      for (const k of ["problem", "reason", "result", "inconvenience"]) await page.fill(`#rw-why-${k}`, "Тест " + k);
      await page.click("[data-key=section-pick]");
      await page.waitForSelector(".rw-pick", { timeout: 5000 });
      const a = [71.3695148, 51.1376971], b = [71.3682669, 51.1342208];
      await page.evaluate(([p]) => map.jumpTo({ center: p, zoom: 16.3 }), [[(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]]);
      await sleep(400);
      for (const p of [a, b]) {
        const xy = await page.evaluate((q) => { const r = map.getCanvas().getBoundingClientRect(); const pt = map.project(q); return [r.left + pt.x, r.top + pt.y]; }, p);
        await page.mouse.click(xy[0], xy[1]);
        await sleep(300);
      }
      await page.waitForFunction(() => { const d = document.querySelector("[data-key=section-done]"); return d && !d.disabled; }, null, { timeout: 15000 }).catch(() => {});
      const hint = await page.$eval(".rw-pick .ri-pick__hint", (e) => e.textContent);
      check(`${tag}: предпросмотр участка — улица и метры`, /Омаров/.test(hint) && /\d+\s*м/.test(hint), hint);
      const line = await page.evaluate(() => !!(map.getSource && map.getSource("rw-section")));
      check(`${tag}: линия участка на карте (по форме R12)`, line);
      await shot(page, `${tag}-section-pick`);
      await page.click("[data-key=section-done]");
      await page.waitForSelector(".rw-form", { timeout: 10000 });
      const value = await page.$eval("#rw-section-value", (e) => e.textContent);
      check(`${tag}: форма вернулась с участком`, /Омаров/.test(value), value);
      const keptTitle = await page.$eval("#rw-title", (e) => e.value);
      check(`${tag}: заполненные поля не потерялись`, /водопровод|құбыр/i.test(keptTitle), keptTitle);
      await page.click("[data-key=save]");
      await page.waitForSelector(".rw-card", { timeout: 10000 });
      await sleep(500);
      const saved = await page.evaluate(async () => {
        const s = await (await fetch("/api/civic/v1/session")).json();
        const tok = (s.data || s).csrf_token;
        const r = await fetch("/api/civic/v2/works?district=nura", { headers: { "X-CSRF-Token": tok } });
        return r.json();
      });
      const mine = lang === "kk" ? "Су құбырын ауыстыру" : "Замена водопровода";
      const items = (saved.items || []).filter((x) => x.kind === "dig" && x.segments && x.segments.length &&
        (x.title_ru === mine || x.title_kk === mine));
      check(`${tag}: сервер сохранил участок рёбрами OSM`, items.length === 1 && items[0].segments.every((e) => /^osm-w\d+-\d+$/.test(e)),
        JSON.stringify(saved).slice(0, 300));
      check(`${tag}: служба и даты v2`, items[0] && items[0].service === "water" && items[0].start === "2026-11-02", JSON.stringify(items[0] || {}).slice(0, 300));
      const metaNow = await page.$$eval(".rw-card .ri-meta", (els) => els.map((e) => e.textContent));
      check(`${tag}: в списке — «Раскопка … · Водоканал · улица»`, metaNow.some((t) => /(Раскопка|Қазу) · (Водоканал|Сумен).*Омаров/.test(t)), metaNow.join(" | "));
      const au = await textAudit(page, "#birge-screen");
      check(`${tag}: без технических слов и прокрутки вбок`, !au.missing && !au.tech.length && !au.overflow, JSON.stringify({ tech: au.tech, overflow: au.overflow }));
      await shot(page, `${tag}-saved`);
      check(`${tag}: без ошибок JS`, !page.errs.length, page.errs.join(" | "));
      await page.close();
    }
  } finally {
    srv.kill();
  }
}

// ------------------------------------------------------------------------------------------------ проекты и идеи
async function ideasPart(browser) {
  const { srv, base } = await fresh();
  try {
    for (const [width, lang] of [[1366, "ru"], [1366, "kk"], [375, "ru"], [375, "kk"]]) {
      const tag = `ideas-${width}-${lang}`;
      // 1. Житель: идеи с иллюстрациями по виду, без серой лампочки.
      const page = await newPage(browser, width, lang, "resident");
      await page.goto(base + "/#ideas", { waitUntil: "domcontentloaded" });
      await page.waitForSelector(".ri-pc[data-idea]", { timeout: 20000 });
      await sleep(400);
      const topics = await page.$$eval(".ri-pc[data-idea]", (els) => els.map((e) => e.getAttribute("data-topic")));
      check(`${tag}: у каждой идеи есть вид (тема)`, topics.length >= 4 && topics.every(Boolean), topics.join(","));
      check(`${tag}: «Беседка и скамейки» — иллюстрация «скамейки»`, topics.includes("benches"), topics.join(","));
      const art = await page.$$eval(".ri-pc .ri-thumb", (els) => els.map((e) => ({ line: !!e.querySelector("svg.ri-art"), img: !!e.querySelector("img") })));
      check(`${tag}: картинки — линейные иллюстрации или 3D-превью`, art.length && art.every((a) => a.line || a.img), JSON.stringify(art));
      const greyBulb = await page.$$eval(".ri-pc .ri-thumb svg", (els) => els.some((e) => (e.innerHTML || "").includes("#7E8A85")));
      check(`${tag}: серой лампочки больше нет`, !greyBulb);
      check(`${tag}: житель может поддержать (капсула-кнопка)`, !!(await page.$("button.ri-vote")));
      await shot(page, `${tag}-resident`);
      check(`${tag}: житель — без ошибок JS`, !page.errs.length, page.errs.join(" | "));
      await page.close();
      // 2. Акимат без входа: те же идеи и проекты, только просмотр, тихая «Войти».
      const pub = await newPage(browser, width, lang, "akimat");
      await pub.goto(base + "/#projects", { waitUntil: "domcontentloaded" });
      await pub.waitForSelector(".ri-pc[data-idea], .bk-empty, .bk-error", { timeout: 20000 });
      await sleep(400);
      const pubIdeas = await pub.$$eval(".ri-pc[data-idea]", (els) => els.length);
      check(`${tag}: акимат без входа видит идеи (не «Войдите»)`, pubIdeas >= 4, pubIdeas);
      check(`${tag}: без входа — нет голосования и решений`, !(await pub.$("button.ri-vote")) && !(await pub.$("[data-key=pd-check], [data-key=publish]")));
      check(`${tag}: без входа — тихая «Войти» внизу`, !!(await pub.$(".ri-sheet-ft--public [data-key=login]")));
      check(`${tag}: без входа — нет «Предложить идею»`, !(await pub.$("[data-key=new]")));
      await pub.click("[data-key=tab-projects]");
      await sleep(300);
      const pubProjects = await pub.$$eval(".ri-pc[data-proposal]", (els) => els.length);
      check(`${tag}: акимат без входа видит проекты`, pubProjects >= 5, pubProjects);
      const au = await textAudit(pub, "#birge-screen");
      check(`${tag}: без технических слов и прокрутки вбок`, !au.missing && !au.tech.length && !au.overflow, JSON.stringify({ tech: au.tech, overflow: au.overflow }));
      await shot(pub, `${tag}-akimat-public`);
      check(`${tag}: просмотр — без ошибок JS`, !pub.errs.length, pub.errs.join(" | "));
      // 3. После входа — очередь проверки и решения, как в FINAL-4.
      await login(pub);
      // Два перехода по хешу подряд склеиваются (обработчик читает уже второй хеш) — ждём карту между ними.
      await pub.goto(base + "/#map", { waitUntil: "domcontentloaded" });
      await pub.waitForFunction(() => document.body.dataset.birgeSection === "map", null, { timeout: 10000 });
      await pub.goto(base + "/#projects", { waitUntil: "domcontentloaded" });
      const staffOk = await pub.waitForSelector(".ri-pc[data-idea]", { timeout: 20000 }).then(() => true, () => false);
      if (!staffOk) {
        await shot(pub, `${tag}-akimat-staff-timeout`);
        const txt = await pub.evaluate(() => (document.querySelector("#birge-screen") || document.body).innerText.slice(0, 400));
        check(`${tag}: после входа открылся список сотрудника`, false, txt);
        await pub.close();
        continue;
      }
      await sleep(400);
      const review = await pub.$$eval(".ri-pc[data-idea-status=review]", (els) => els.length);
      check(`${tag}: после входа видна идея «на проверке» (очередь сотрудника)`, review >= 1, review);
      check(`${tag}: после входа нет подсказки «Войти»`, !(await pub.$(".ri-sheet-ft--public")));
      await pub.close();
    }
  } finally {
    srv.kill();
  }
}

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  try {
    if (!ONLY || ONLY.includes("works")) await worksPart(browser);
    if (!ONLY || ONLY.includes("ideas")) await ideasPart(browser);
  } catch (e) {
    check("прогон без исключений", false, e.stack || e);
  } finally {
    await browser.close();
  }
  const failed = results.filter((r) => !r.ok).length;
  console.log(`\nR06 r15 browser: ${results.length - failed} PASS / ${failed} FAIL`);
  process.exit(failed ? 1 : 0);
})();
