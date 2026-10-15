#!/usr/bin/env node
/*
 * R09 · раунд 15 · сцена 8 «Ведомства вместе» в НАСТОЯЩЕМ приложении (сборка с путями R09 и патчем маршрутов R01):
 *   node tests/civic/R09/joint_r09.cjs [--root <дерево сборки>] [--screenshots <папка>] [--only 1366-ru]
 * Сервер: python3 -B app.py (CIVIC_DEMO=1) на ВРЕМЕННОЙ SQLite + демо-мир R09 (фикстура world_sample_r09.json через
 * seed_world). Нужны маршруты complaints/{id}/handoff · /services · /part в шлюзе (research/round-15-results/R09/
 * R01_v2_routes_r09.patch): без них проверка честно падает на «маршруты шлюза».
 * Путь: сотрудник «Обращения» → строка «Участок ул. Сарайшык» → подсказка «Похоже, нужны 2 службы: Водоканал и
 * Дорожная служба» → «Принять» → части служб под строкой → «Водоканал — сделано» с заметкой → «исправлено» ждёт
 * Дорожную службу → её часть «в работе» прямо из строки → «Передать в другую службу» на другом обращении (причина —
 * чип) → житель («Я тоже» на той же яме) видит «Работают 2 службы: Водоканал — сделано · Дорожная служба — в работе».
 * 1366 и 375 × ru и kk; каждая пара — своя свежая база (сцена с начала). Ничего не пишет в репозиторий.
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
const ONLY = args.includes("--only") ? args[args.indexOf("--only") + 1].split(",") : null;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
// --world <файл мира R02> --target <id цели жалобы сцены 8>: та же проверка на настоящем мире (scene8 R02 — «Участок:
// улица Баян Сулу», osm-w243047611-4). По умолчанию — фикстура R09 той же формы (цель osm-w123-4).
const WORLD = args.includes("--world") ? path.resolve(args[args.indexOf("--world") + 1]) : path.join(ROOT, "tests/civic/R09/fixtures/world_sample_r09.json");
const PIT_TARGET = args.includes("--target") ? args[args.indexOf("--target") + 1] : "osm-w123-4";
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet|ReadPixels/i;
const SAY = {
  ru: { hint: "Похоже, нужны 2 службы: Водоканал и Дорожная служба", water: "Водоканал", road: "Дорожная служба",
        done: "сделано", work: "в работе", resident: "Работают 2 службы:", waiting: "Сначала отметят свою часть",
        handoff: "Передано: Дорожная служба", note: "Трубу заменили" },
  kk: { hint: "2 қызмет керек сияқты: Сумен жабдықтау қызметі және Жол қызметі", water: "Сумен жабдықтау қызметі",
        road: "Жол қызметі", done: "орындалды", work: "орындалуда", resident: "2 қызмет жұмыс істейді:",
        waiting: "Алдымен өз бөлігін белгілейді", handoff: "Жіберілді: Жол қызметі", note: "Құбыр ауыстырылды" },
};
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
  const staff = { user: "r09-joint", pass: "Birge-scene8-" + Math.random().toString(36).slice(2) + "-Aa1!" };
  execSync(`python3 -B -m ui.civic_store --db "${db}" create-editor ${staff.user} --password-stdin`,
           { cwd: ROOT, env, input: staff.pass + "\n", stdio: ["pipe", "ignore", "inherit"] });
  // Демо-мир R09 (до world_v1.json R02 — фикстура той же формы): та же функция, которую зовёт шлюз R01.
  const seeded = execSync(`python3 -B -c "import json,sys; from ui.civic_feedback.v2.integration import seed_world; ` +
    `print(json.dumps(seed_world(sys.argv[1], json.load(open(sys.argv[2], encoding='utf-8')))))" "${db}" "${WORLD}"`,
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
const clean = (s) => (s || "").replace(/\s+/g, " ").trim();

async function api(base, method, p, body, headers) {
  const r = await fetch(base + "/api/civic/v2" + p, { method, headers: { "Content-Type": "application/json", ...(headers || {}) },
                                                     body: body === undefined ? undefined : JSON.stringify(body) });
  let j = null; try { j = await r.json(); } catch (e) { /* */ }
  return { status: r.status, body: j };
}

async function variant(browser, base, width, height, lang, staff) {
  const tag = `${width}-${lang}`;
  const say = SAY[lang];
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, hasTouch: width < 1024 });
  await ctx.addInitScript(([l]) => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); } catch (e) {} }, [lang]);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !NOISE.test(m.text())) errors.push(m.text()); });
  try {
    await page.goto(base + "/?lang=" + lang);
    await shellReady(page);
    const logged = await page.evaluate(async ([u, p]) => (await fetch("/api/civic/v1/session/login", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: u, password: p }) })).ok, [staff.user, staff.pass]);
    await page.reload();
    await shellReady(page);
    await page.evaluate(() => { window.BirgeShell?.setMode?.("akimat"); window.BirgeShell?.setSection?.("complaints"); });
    const inbox = await page.waitForSelector(".bc-inbox__row", { timeout: 10000 }).then(() => true, () => false);
    check(`${tag}: сотрудник вошёл, «Обращения» с жалобами демо-мира`, logged && inbox);
    if (!inbox) return;
    // Строка ямы — цель жалобы сцены 8 (фикстура: «Участок ул. Сарайшык»; мир R02: «Участок: улица Баян Сулу»).
    const row = page.locator(`.bc-inbox__item[data-target="${PIT_TARGET}"]`).first();
    await row.locator(".bc-inbox__row").click();
    const block = await page.waitForSelector(".bc-inbox__item--open .bc-joint", { timeout: 8000 }).then(() => true, () => false);
    const parts0 = block ? await page.$$eval(".bc-inbox__item--open .bc-joint__part", (n) => n.map((x) => x.getAttribute("data-service"))) : [];
    check(`${tag}: в карточке — блок «Службы»: ведущая по таблице (Дорожная служба)`, block && parts0.join() === "road", parts0);
    const hint = clean(await page.textContent(".bc-inbox__item--open .bc-joint-hint").catch(() => ""));
    check(`${tag}: подсказка R04 — «${say.hint}»`, hint.includes(say.hint), hint.slice(0, 120));
    await shot(page, `joint-${tag}-1-hint`);
    // «Принять» — одним нажатием: Водоканал ведущая, Дорожная служба участвует.
    await page.click(".bc-inbox__item--open .bc-joint-hint__accept");
    await page.waitForFunction(() => document.querySelectorAll(".bc-inbox__item--open .bc-joint__part").length === 2, null, { timeout: 8000 })
      .catch(() => null);
    const parts1 = await page.$$eval(".bc-inbox__item--open .bc-joint__part", (n) => n.map((x) => x.getAttribute("data-service")));
    const roles = clean(await page.textContent(".bc-inbox__item--open .bc-joint__parts").catch(() => ""));
    check(`${tag}: «Принять» → совместное исполнение: Водоканал (ведущая) и Дорожная служба`, parts1.join() === "water,road" &&
          roles.includes(say.water) && roles.includes(say.road), { parts1, roles: roles.slice(0, 120) });
    const hintGone = await page.$(".bc-inbox__item--open .bc-joint-hint");
    check(`${tag}: подсказка исчезла после «Принять»`, !hintGone);
    // Водоканал — «Сделано» с заметкой для жителей.
    await page.click('.bc-inbox__item--open .bc-joint__part[data-service="water"] .bc-joint__segbtn[data-status="done"]');
    await page.fill(".bc-inbox__item--open [name=part_note]", say.note);
    await shot(page, `joint-${tag}-2-part-note`);
    await page.click(".bc-inbox__item--open .bc-joint__noteform button[type=submit]");
    await page.waitForSelector('.bc-inbox__item--open .bc-joint__part[data-service="water"][data-status="done"]', { timeout: 8000 }).catch(() => null);
    const fixBtn = await page.$eval(".bc-inbox__item--open .bc-staff__open-fix", (b) => ({ disabled: b.disabled,
      wait: (document.querySelector(".bc-inbox__item--open .bc-joint__waiting") || {}).textContent || "" })).catch(() => null);
    check(`${tag}: «Отметить исправленным» ждёт Дорожную службу («${say.waiting}…»)`, fixBtn && fixBtn.disabled &&
          fixBtn.wait.includes(say.waiting) && fixBtn.wait.includes(say.road), fixBtn);
    await shot(page, `joint-${tag}-3-waiting`);
    // «Черновик ответа» R04 — только если маршрут reply-draft готов в сборке (GET /modules); текст — в «Обновление для всех».
    const draftBtn = await page.$(".bc-inbox__item--open .bc-staff__draft:not([hidden])");
    if (draftBtn) {
      await draftBtn.click();
      await page.waitForFunction(() => { const a = document.querySelector(".bc-inbox__item--open [name=text]"); return a && a.value.length > 20; },
        null, { timeout: 8000 }).catch(() => null);
      const draft = await page.$eval(".bc-inbox__item--open [name=text]", (a) => a.value).catch(() => "");
      check(`${tag}: «Черновик ответа» R04 — текст в «Обновление для всех», сотрудник правит`, draft.length > 20, draft.slice(0, 120));
      await shot(page, `joint-${tag}-3b-draft`);
    } else {
      console.log(`  ${tag}: «Черновик ответа» не показан — маршрута R04 reply-draft нет в этой сборке (так и задумано)`);
    }
    // Часть Дорожной службы — прямо из строки (чип под строкой → меню → «в работе»).
    const chips = await page.$$eval(".bc-inbox__item--open .bc-inbox__part", (n) => n.map((x) => x.textContent.replace(/\s+/g, " ").trim()))
      .catch(() => []);
    const chip = page.locator('.bc-inbox__item--open .bc-inbox__part[data-service="road"]');
    await chip.click();
    await page.click('.bc-inbox__partmenu .bc-inbox__menu-item:nth-child(2)');
    await page.waitForFunction(() => { const c = document.querySelector('.bc-inbox__part[data-service="road"]');
      return c && c.getAttribute("data-status") === "in_progress"; }, null, { timeout: 8000 }).catch(() => null);
    const roadNow = await page.$eval('.bc-inbox__part[data-service="road"]', (c) => c.getAttribute("data-status")).catch(() => null);
    check(`${tag}: часть Дорожной службы «в работе» — прямо из строки «Обращений»`, roadNow === "in_progress", { roadNow, chips });
    await shot(page, `joint-${tag}-4-row-parts`);
    // Передача на другом обращении → Дорожная служба (если уже у неё — Служба благоустройства), причина — чип.
    // Вторая строка — любое другое «Новое» обращение (фикстура: «Гололёд на тротуаре у школы», примерное место).
    // Только строки демо-мира (data-world): примеры шага 2 «Хан Шатыр» — только просмотр, карточки действий у них нет.
    const other = page.locator(`.bc-inbox__group[data-group="new"] .bc-inbox__item[data-world="true"]:not([data-target="${PIT_TARGET}"])`).first();
    if (await other.count()) {
      await other.locator(".bc-inbox__row").click();
      await page.waitForSelector(".bc-inbox__item--open .bc-joint__open-handoff", { timeout: 8000 });
      await page.click(".bc-inbox__item--open .bc-joint__open-handoff");
      const to = await page.$eval(".bc-inbox__item--open [name=to]", (sel) => [...sel.options].some((o) => o.value === "road") ? "road" : "landscaping");
      await page.selectOption(".bc-inbox__item--open [name=to]", to);
      await page.click('.bc-inbox__item--open .bc-joint__reasons [data-reason="not_our_zone"]');
      await shot(page, `joint-${tag}-5-handoff-form`);
      await page.click(".bc-inbox__item--open .bc-joint__handoff button[type=submit]");
      const want = to === "road" ? say.handoff : (lang === "kk" ? "Жіберілді: Абаттандыру қызметі" : "Передано: Служба благоустройства");
      // Причина-чип в истории — на языке экрана (сервер хранит русскую подпись кода для журналов R17).
      const reason = lang === "kk" ? "Біздің жауапкершілік аймағы емес" : "Не наша зона ответственности";
      await page.waitForFunction((w) => { const n = document.querySelector(".bc-inbox__item--open .bc-staff__note");
        return n && n.textContent.includes(w); }, want, { timeout: 8000 }).catch(() => null);
      const note = clean(await page.textContent(".bc-inbox__item--open .bc-staff__note").catch(() => ""));
      const hist = clean(await page.textContent(".bc-inbox__item--open .bc-joint__history").catch(() => ""));
      check(`${tag}: «Передать в другую службу» → «${want}…», в «Передачах» — причина «${reason}» и роль`, note.includes(want) &&
            /→/.test(hist) && hist.includes(reason), { note, hist: hist.slice(0, 160) });
      await shot(page, `joint-${tag}-6-handoff-done`);
    } else {
      check(`${tag}: вторая строка для передачи найдена`, false);
    }
    const list = await api(base, "GET", "/complaints?days=30");
    const pit = ((list.body && list.body.data && list.body.data.items) || []).filter((c) => (c.target || {}).id === PIT_TARGET)[0];
    // Табло R17 → «Открыть в «Обращениях»» (INTEGRATION R17 §4): фильтр в sessionStorage + событие birge:inbox-filter.
    // «Обращения» Дорожной службы (она — партнёр ямы), строка ямы открыта сразу.
    if (pit) {
      await page.evaluate(() => window.BirgeShell.setSection("map"));
      await page.evaluate((id) => {
        const detail = { service: "road", ids: [id] };
        sessionStorage.setItem("birge.inbox.filter", JSON.stringify(detail));
        window.BirgeShell.setSection("complaints");
        setTimeout(() => document.dispatchEvent(new CustomEvent("birge:inbox-filter", { detail })), 0);
      }, pit.id);
      await page.waitForSelector(`.bc-inbox__item--open[data-target="${PIT_TARGET}"]`, { timeout: 10000 }).catch(() => null);
      const filtered = await page.evaluate((target) => ({
        chip: (document.querySelector('.bc-inbox__filter-chip[data-filter="service"]') || {}).textContent || "",
        open: !!document.querySelector(`.bc-inbox__item--open[data-target="${target}"]`),
        rows: document.querySelectorAll(".bc-inbox__item").length,
        left: (() => { try { return sessionStorage.getItem("birge.inbox.filter"); } catch (e) { return "?"; } })(),
      }), PIT_TARGET);
      check(`${tag}: из табло R17 — «Обращения» Дорожной службы, строка ямы открыта, фильтр взят один раз`,
            filtered.chip.includes(say.road) && filtered.open && filtered.left === null, filtered);
      await shot(page, `joint-${tag}-6b-from-agencies`);
      await page.click('.bc-inbox__filter-chip[data-filter="service"]');
      await page.waitForFunction(() => !document.querySelector('.bc-inbox__filter-chip[data-filter="service"]'), null, { timeout: 8000 })
        .catch(() => null);
      const cleared = await page.$('.bc-inbox__filter-chip[data-filter="service"]');
      check(`${tag}: чип «Служба: …» снимает фильтр`, !cleared);
      // Адрес раздела оболочки R01 раунда 15 (IA_ROUND15 §7.3): #inbox/<id жалобы> — сцена 8 открывается ссылкой.
      // Оболочка FINAL-4 путей разделов не знает (адрес остаётся #inbox) — тогда шаг не нужен и пропускается.
      await page.evaluate(() => window.BirgeShell.setSection("map"));
      await page.evaluate((id) => window.BirgeShell.setSection("inbox", { path: id }), pit.id);
      const pathShell = await page.evaluate((id) => location.hash === "#inbox/" + id, pit.id);
      if (!pathShell) console.log(`  ${tag}: оболочка без путей разделов (FINAL-4) — шаг «адрес #inbox/<id>» не нужен`);
      if (pathShell) {
        const seen = async () => page.evaluate((target) => {
          const li = document.querySelector(`.bc-inbox__item--open[data-target="${target}"]`);
          const r = li && li.getBoundingClientRect();
          return { open: !!li, top: r ? Math.round(r.top) : null, visible: !!r && r.top >= 0 && r.top < innerHeight - 40,
                   hash: location.hash, stored: (() => { try { return sessionStorage.getItem("birge.inbox.filter"); } catch (e) { return "?"; } })() };
        }, PIT_TARGET);
        await page.waitForSelector(`.bc-inbox__item--open[data-target="${PIT_TARGET}"]`, { timeout: 10000 }).catch(() => null);
        await sleep(400);
        const mounted = await seen();
        check(`${tag}: адрес #inbox/<id> — экран открыт на яме, строка в видимой части, без фильтра в sessionStorage`,
              mounted.open && mounted.visible && mounted.stored === null && mounted.hash === "#inbox/" + pit.id, mounted);
        await shot(page, `joint-${tag}-6c-path`);
        // Тот же раздел, другой путь — оболочка зовёт handle.setPath без перемонтажа: другая строка, потом снова яма.
        const otherRow = page.locator(".bc-inbox__item:not(.bc-inbox__item--open) .bc-inbox__row").first();
        await otherRow.click();
        await sleep(400);
        const closed = !(await seen()).open;
        await page.evaluate(() => window.BirgeShell.setSection("inbox", { path: "" }));
        await page.evaluate((id) => window.BirgeShell.setSection("inbox", { path: id }), pit.id);
        await page.waitForSelector(`.bc-inbox__item--open[data-target="${PIT_TARGET}"]`, { timeout: 8000 }).catch(() => null);
        await sleep(400);
        const again = await seen();
        check(`${tag}: смена пути без перемонтажа (setPath) — открыта другая строка, путь ямы снова открывает яму`,
              closed && again.open && again.visible, { closed, again });
      }
    }
    // Житель: «Я тоже» на той же яме → в «Моих обращениях» — две службы со статусами.
    const device = "r09joint" + Math.random().toString(36).slice(2, 14);
    const me = pit ? await api(base, "POST", `/complaints/${pit.id}/metoo`, {}, { "X-Birge-Device": device }) : { status: 0 };
    check(`${tag}: житель «Я тоже» на той же яме`, me.status === 200, me.status);
    const rctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, hasTouch: width < 1024 });
    await rctx.addInitScript(([l, d]) => { try { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l);
      localStorage.setItem("birge.device", d); } catch (e) {} }, [lang, device]);
    const rpage = await rctx.newPage();
    rpage.on("pageerror", (e) => errors.push("resident pageerror: " + e.message));
    await rpage.goto(base + "/?lang=" + lang + "#mine");
    await rpage.waitForSelector(".bc-mine__card", { timeout: 15000 }).catch(() => null);
    const line = clean(await rpage.textContent(".bc-mine__card .bc-joint-line").catch(() => ""));
    const icons = await rpage.$$eval(".bc-mine__card .bc-joint-line__part", (n) => n.map((x) => [x.getAttribute("data-status"),
      !!x.querySelector("svg")])).catch(() => []);
    check(`${tag}: житель — «${say.resident} ${say.water} — ${say.done} · ${say.road} — ${say.work}» со статус-иконками`,
          line.includes(say.resident) && line.includes(`${say.water} — ${say.done}`) && line.includes(`${say.road} — ${say.work}`) &&
          icons.length === 2 && icons.every((x) => x[1]), { line: line.slice(0, 160), icons });
    const flat = clean(await rpage.textContent(".bc-panel").catch(() => ""));
    check(`${tag}: житель не видит причин передач и ролей сотрудников`, !/Совместное исполнение|оператор|Бірлескен орындау/.test(flat),
          flat.slice(0, 80));
    await shot(rpage, `joint-${tag}-7-resident`);
    const scroll = await rpage.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);
    check(`${tag}: житель — нет прокрутки вбок`, scroll);
    await rctx.close();
    const scrollStaff = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);
    check(`${tag}: сотрудник — нет прокрутки вбок`, scrollStaff);
    check(`${tag}: нет ошибок на странице`, errors.length === 0, errors.slice(0, 3));
  } catch (err) {
    check(`${tag}: сценарий прошёл без исключений`, false, String(err && err.message).slice(0, 300));
  } finally {
    await ctx.close();
  }
}

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r09-joint-"));
  let browser = null;
  try {
    browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
    const runs = [[1366, 768, "ru"], [375, 812, "kk"], [1024, 768, "ru"], [1366, 768, "kk"], [375, 812, "ru"], [1024, 768, "kk"]]
      .filter(([w, , l]) => !ONLY || ONLY.includes(`${w}-${l}`));
    for (const [i, [w, h, lang]] of runs.entries()) {
      const port = await freePort();
      const srv = await startServer(port, path.join(tmp, `civic-${i}.sqlite3`));
      try {
        // Маршруты R01 (CONTRACT §7): без патча шлюз отвечает 404 — проверка честно падает здесь.
        const probe = await api(`http://127.0.0.1:${port}`, "POST", "/complaints/c-nothere00/handoff", { to: "water", reason: "проверка" });
        check(`${w}-${lang}: маршруты шлюза complaints/{id}/handoff есть (без сессии — 401/403)`, [401, 403].includes(probe.status), probe.status);
        check(`${w}-${lang}: демо-мир засеян (${srv.seeded.inserted})`, srv.seeded.inserted >= 5,
              { ...srv.seeded, invalid: (srv.seeded.invalid || []).length });
        await variant(browser, `http://127.0.0.1:${port}`, w, h, lang, srv.staff);
      } finally { srv.kill(); }
    }
  } catch (err) {
    console.error(err);
    check("приложение и браузер запустились", false, String(err && err.message));
  } finally {
    if (browser) await browser.close();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  const failed = results.filter((r) => !r.ok).length;
  console.log(`\nИТОГ: ${results.length - failed}/${results.length} PASS`);
  process.exit(failed ? 1 : 0);
})();
