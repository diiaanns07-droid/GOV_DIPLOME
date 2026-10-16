// R06 раунд 15 в браузере: «Работы и отключения» v2 (служба, вид, участок улицы по карте R12), «Проекты и идеи» без
// входа и с картинками по виду, лента уведомлений «Что нового для меня».
//
//   NODE_PATH="$(npm root -g)" PYTHON=python3 node tests/civic/R06/round15/browser_r15.cjs [дерево] [папка-кадров] [--only works,ideas,notify,together]
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
// Кадр — когда карта оболочки готова (в облаке — или «упрощённая подложка»): без «Загружаем карту…» за панелью.
async function mapSettled(page) {
  await page.waitForFunction(() => { const s = document.getElementById("map-status");
    return !s || s.classList.contains("hidden") || document.body.classList.contains("offline-basemap"); }, null, { timeout: 20000 }).catch(() => {});
}
async function shot(page, name) {
  if (!OUT) return;
  await mapSettled(page);
  await page.screenshot({ path: path.join(OUT, name + ".png"), fullPage: false });
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
    // Мельче токена --fs-xs сборки текста нет (R11 раунда 15: 13 px, R10 B-112; ui-kit FINAL-4 — 12 px).
    const min = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--fs-xs")) || 12;
    const tiny = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const el = n.parentElement, t = n.textContent.trim();
      if (!t || !el || el.closest(".bk-sr-only, [aria-hidden=true]")) continue;
      const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
      if (!r.width || cs.visibility === "hidden" || cs.display === "none") continue;
      if (parseFloat(cs.fontSize) < min - 0.01) tiny.push(cs.fontSize + " «" + t.slice(0, 24) + "»");
    }
    return { tech: tech.filter((w) => text.includes(w)), overflow: document.documentElement.scrollWidth > innerWidth + 1, text,
      tiny: tiny.slice(0, 6), min };
  }, [sel, TECH]);
}
async function waitMap(page) {
  await page.waitForFunction(() => typeof mapReady !== "undefined" && mapReady && typeof map !== "undefined" && map && map.loaded && map.isStyleLoaded && map.isStyleLoaded(), null, { timeout: 30000 }).catch(() => {});
}

// ------------------------------------------------------------------------------------------------ работы v2
async function worksPart(browser) {
  const { srv, base } = await fresh();
  try {
    // Своё название у каждого прогона с участком: сервер один, записи копятся.
    const TITLES = { "1366-ru": "Замена водопровода", "1366-kk": "Су құбырын ауыстыру", "1024-ru": "Ремонт водопровода",
      "1024-kk": "Су құбырын жөндеу" };
    for (const [width, lang] of [[1366, "ru"], [1366, "kk"], [1024, "ru"], [1024, "kk"], [375, "ru"], [375, "kk"]]) {
      const tag = `works-${width}-${lang}`;
      const mine = TITLES[`${width}-${lang}`];
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
      if (!mine) { await page.close(); continue; }
      // Участок по карте: два нажатия на улицу Ильяса Омарова (Нура) → линия R12 → «Готово».
      await page.fill("#rw-title", mine);
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
      const items = (saved.items || []).filter((x) => x.kind === "dig" && x.segments && x.segments.length &&
        (x.title_ru === mine || x.title_kk === mine));
      check(`${tag}: сервер сохранил участок рёбрами OSM`, items.length === 1 && items[0].segments.every((e) => /^osm-w\d+-\d+$/.test(e)),
        JSON.stringify(saved).slice(0, 300));
      check(`${tag}: служба и даты v2`, items[0] && items[0].service === "water" && items[0].start === "2026-11-02", JSON.stringify(items[0] || {}).slice(0, 300));
      const metaNow = await page.$$eval(".rw-card .ri-meta", (els) => els.map((e) => e.textContent));
      check(`${tag}: в списке — «Раскопка … · Водоканал · улица»`, metaNow.some((t) => /(Раскопка|Қазу) · (Водоканал|Сумен).*Омаров/.test(t)), metaNow.join(" | "));
      const au = await textAudit(page, "#birge-screen");
      check(`${tag}: без технических слов и прокрутки вбок`, !au.missing && !au.tech.length && !au.overflow, JSON.stringify({ tech: au.tech, overflow: au.overflow }));
      check(`${tag}: текст не мельче ${au.min} px (токен --fs-xs)`, !au.missing && !au.tiny.length, JSON.stringify(au.tiny));
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
    for (const [width, lang] of [[1366, "ru"], [1366, "kk"], [1024, "ru"], [1024, "kk"], [375, "ru"], [375, "kk"]]) {
      const tag = `ideas-${width}-${lang}`;
      // 1. Житель: идеи с иллюстрациями по виду, без серой лампочки.
      const page = await newPage(browser, width, lang, "resident");
      await page.goto(base + "/#ideas", { waitUntil: "domcontentloaded" });
      await page.waitForSelector(".ri-pc[data-idea]", { timeout: 20000 });
      await sleep(400);
      const topics = await page.$$eval(".ri-pc[data-idea]", (els) => els.map((e) => e.getAttribute("data-topic")));
      check(`${tag}: у каждой идеи есть вид (тема)`, topics.length >= 4 && topics.every(Boolean), topics.join(","));
      check(`${tag}: «Беседка и скамейки» — иллюстрация «скамейки»`, topics.includes("benches"), topics.join(","));
      // П1 (поправка владельца 15 окт): у карточки — маленький значок вида (≤ 48 px), без рисунков, рендеров и <img>.
      const tiles = await page.$$eval(".ri-pc", (els) => els.map((e) => {
        const t = e.querySelector(".ri-kind"), r = t && t.getBoundingClientRect();
        return { kind: t && t.getAttribute("data-kind"), w: r ? Math.round(r.width) : 0, h: r ? Math.round(r.height) : 0,
          icon: !!(t && t.querySelector("svg.ic")), img: !!e.querySelector("img"), bigSvg: [...e.querySelectorAll("svg")].some((s) => s.getBoundingClientRect().width > 48) };
      }));
      check(`${tag}: у каждой карточки — значок вида ≤ 48 px из набора иконок`, tiles.length && tiles.every((x) => x.icon && x.w <= 48 && x.h <= 48), JSON.stringify(tiles));
      check(`${tag}: ни картинок, ни больших рисунков в списке (П1)`, tiles.every((x) => !x.img && !x.bigSvg), JSON.stringify(tiles));
      check(`${tag}: значок по виду — «скамейки» у беседки`, tiles.some((x) => x.kind === "benches"), JSON.stringify(tiles.map((x) => x.kind)));
      const pdBig = await page.$$eval(".ri-pd img, .ri-pd svg", (els) => els.filter((e) => e.getBoundingClientRect().width > 48).length);
      check(`${tag}: в карточке выбранного нет больших картинок (П1)`, pdBig === 0, pdBig);
      // R11 R06-3: слово в плитке (район, объект) переносится по слогам, а не посреди слога («Спортпл / ощадка»,
      // «Скамейк / и»): в облаке у Chrome нет словаря переносов. Каждая идея списка по очереди.
      const wordTiles = [];
      for (const id of await page.$$eval(".ri-pc[data-idea]", (els) => els.map((e) => e.getAttribute("data-idea")))) {
        const open = await page.$(`.ri-pc[data-idea="${id}"][aria-current="true"]`);
        if (!open) await page.click(`.ri-pc[data-idea="${id}"] .ri-pc__open`);
        await page.waitForSelector(".ri-pd .ri-facts", { timeout: 5000 }).catch(() => {});
        wordTiles.push(...await page.$$eval(".ri-pd .ri-fact--word > b", (els) => els.map((b) => {
          const node = b.firstChild, txt = node ? node.textContent : "", tops = [], bad = [];
          for (let i = 0; i < txt.length; i++) {
            const r = document.createRange(); r.setStart(node, i); r.setEnd(node, i + 1);
            const rc = [...r.getClientRects()].filter((q) => q.width > 0.5);
            tops.push(rc.length ? Math.round(rc[rc.length - 1].top) : null);
          }
          for (let i = 1; i < txt.length; i++) {
            if (tops[i] == null || tops[i - 1] == null || tops[i] <= tops[i - 1] + 2) continue;
            if (!/[\s­-]/.test(txt[i - 1]) && !/\s/.test(txt[i])) bad.push((txt.slice(0, i) + " / " + txt.slice(i)).replace(/­/g, ""));
          }
          return { text: txt.replace(/­/g, ""), bad };
        })));
      }
      check(`${tag}: слова в плитках карточки (район, объект) не рвутся посреди слога (R11 R06-3)`,
        wordTiles.length >= 4 && wordTiles.every((x) => !x.bad.length), JSON.stringify(wordTiles.filter((x) => x.bad.length).concat(wordTiles.length < 4 ? [wordTiles] : [])));
      if (width === 1366 && lang === "ru") check(`${tag}: «Спортплощадка» в плитке — с переносом по слогам`, wordTiles.some((x) => x.text === "Спортплощадка"), JSON.stringify(wordTiles.map((x) => x.text)));
      // R10 B-136: заголовок строки — рамка ≥ 44 px (аудит П3 меряет рамку и ≤ 12 px вокруг; вся карточка нажимается и так).
      const titleBoxes = await page.$$eval(".ri-pc__open", (els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
      check(`${tag}: заголовки строк — рамка нажатия ≥ 44 px (R10 B-136)`, titleBoxes.length && titleBoxes.every((x) => x >= 44), JSON.stringify(titleBoxes));
      if (width === 1366 && lang === "ru") {
        // Проекты не загрузились (связь оборвалась только у proposals) — не «Проекты · 0»: без числа, внутри «Повторить».
        const block = (route) => route.abort("failed");
        await page.route(/\/api\/civic\/v2\/proposals/, block);
        await page.evaluate(() => { location.hash = "#map"; });
        await page.waitForFunction(() => document.body.dataset.birgeSection === "map", null, { timeout: 10000 }).catch(() => {});
        await page.evaluate(() => { location.hash = "#ideas"; });
        await page.waitForSelector('[data-key="tab-projects"]', { timeout: 15000 }).catch(() => {});
        await sleep(600);
        const tabText = await page.$eval('[data-key="tab-projects"]', (e) => e.textContent).catch(() => "");
        check(`${tag}: проекты не загрузились — во вкладке нет «· 0»`, tabText && !/·/.test(tabText), tabText);
        await page.click('[data-key="tab-projects"]');
        await sleep(300);
        const retry = await page.$(".ri-plist .bk-state--error button, .ri-plist [class*=error] button");
        check(`${tag}: проекты не загрузились — ошибка с «Повторить»`, !!retry, await page.evaluate(() => (document.querySelector(".ri-plist") || {}).innerText || ""));
        await page.unroute(/\/api\/civic\/v2\/proposals/, block);
        if (retry) await retry.click();
        const back = await page.waitForSelector(".ri-pc[data-proposal]", { timeout: 10000 }).then(() => true, () => false);
        const tabAfter = await page.$eval('[data-key="tab-projects"]', (e) => e.textContent).catch(() => "");
        check(`${tag}: после «Повторить» проекты вернулись, число во вкладке`, back && /·\s*\d/.test(tabAfter), tabAfter);
        await page.click('[data-key="tab-ideas"]').catch(() => {});
        await sleep(300);
      }
      // Кадр — с идеей спортплощадки (самое длинное слово плитки).
      const sports = await page.$(`.ri-pc[data-topic="sports"]:not([aria-current="true"]) .ri-pc__open`);
      if (sports) { await sports.click(); await sleep(300); }
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
      check(`${tag}: текст не мельче ${au.min} px (токен --fs-xs)`, !au.missing && !au.tiny.length, JSON.stringify(au.tiny));
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

// ------------------------------------------------------------------------------------------------ уведомления
// Нужен патч R01 (маршруты /notifications): дерево — tree_with_r01_patch.sh. Без маршрутов часть — NOT_RUN.
async function api(base, method, path, body, auth) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) { headers.Cookie = auth.cookie; headers["X-CSRF-Token"] = auth.csrf; headers.Origin = base; }
  const r = await fetch(base + path, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
  const text = await r.text();
  let json = null;
  try { json = JSON.parse(text); } catch (e) { json = null; }
  if (json && json.ok === true && "data" in json) json = json.data;
  return { status: r.status, json, headers: r.headers };
}
async function staffAuth(base) {
  const r = await fetch(base + "/api/civic/v1/session/login", { method: "POST", headers: { "Content-Type": "application/json", Origin: base },
    body: JSON.stringify({ username: "checker", password: PASSWORD }) });
  const cookie = (r.headers.get("set-cookie") || "").split(";")[0];
  const json = await r.json();
  return { cookie, csrf: (json.data || json).csrf_token };
}
async function notifyPart(browser) {
  const { srv, base } = await fresh();
  try {
    const probe = await api(base, "GET", "/api/civic/v2/notifications?device_id=d-probeprobeprobeprobe1");
    if (probe.status === 404) {
      console.log("NOT_RUN уведомления: в дереве нет маршрутов /notifications (нужен патч R01 r01_round15_r06.patch)");
      return;
    }
    const MAIN = "d-" + "A".repeat(24), IDEAS = "dev-" + "a".repeat(32);
    const auth = await staffAuth(base);
    // Житель A: своя идея (опубликована), голос за проект (одобрен), подписка «Рядом» на Нуру (работы рядом).
    const idea = await api(base, "POST", "/api/civic/v2/ideas", { title: "Скамейки у подъезда", description: "Пожилым негде присесть.",
      geometry: { type: "Point", coordinates: [71.3665, 51.1375] }, device_id: IDEAS, lang: "ru" });
    check("уведомления: идея жителя создана", idea.status === 201, JSON.stringify(idea.json).slice(0, 200));
    const ideaId = idea.json && idea.json.item && idea.json.item.id;
    const pub = await api(base, "POST", `/api/civic/v2/ideas/${ideaId}/decide`, { action: "publish" }, auth);
    check("уведомления: сотрудник опубликовал идею", pub.status === 200, pub.status);
    const projects = await api(base, "GET", "/api/civic/v2/proposals");
    const project = projects.json.items.find((x) => x.status === "proposal");
    await api(base, "POST", `/api/civic/v2/proposals/${project.id}/vote`, { value: 1, device_id: IDEAS });
    const approve = await api(base, "POST", `/api/civic/v2/proposals/${project.id}/approve`, {}, auth);
    check("уведомления: проект одобрен", approve.status === 200, approve.status);
    const sub = await api(base, "POST", "/api/civic/v2/nearby/subscriptions", { device_id: MAIN, scope: "district", id: "nura" });
    check("уведомления: подписка «Рядом» на Нуру", sub.status === 200, JSON.stringify(sub.json).slice(0, 200));
    const feed = await (await fetch(base + "/api/civic/v2/notifications", { headers: { "X-Birge-Device": MAIN, "X-Birge-Ideas-Device": IDEAS } })).json();
    const kinds = new Set((feed.items || []).map((e) => e.kind));
    check("уведомления API: идея, проект и работы рядом", kinds.has("idea.update") && kinds.has("project.update") && kinds.has("work.near"),
      JSON.stringify(feed).slice(0, 400));
    check("уведомления API: в ответе нет id устройств", !JSON.stringify(feed).includes(MAIN) && !JSON.stringify(feed).includes(IDEAS));
    check("уведомления API: ссылки — только внутренние адреса", (feed.items || []).every((e) => e.link === null || /^#[a-z]/.test(e.link)));
    check("уведомления API: есть непрочитанные", feed.unread >= 3, feed.unread);

    // Ноутбук 1366 и 1024: колокольчик в капсуле справа. Последний прогон (1366 ru) открывает уведомление и «Прочитать все».
    for (const [width, lang] of [[1366, "kk"], [1024, "ru"], [1024, "kk"], [1366, "ru"]]) {
      const tag = `notify-${width}-${lang}`;
      const flow = width === 1366 && lang === "ru";
      const ctx = await browser.newContext({ viewport: { width, height: 768 }, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
      await ctx.addInitScript(([l, main, ideas]) => {
        try { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l);
          localStorage.setItem("birge.device", main); localStorage.setItem("birge.device_id", ideas); } catch (e) {}
      }, [lang, MAIN, IDEAS]);
      const page = await ctx.newPage();
      page.errs = [];
      page.on("pageerror", (e) => page.errs.push(e.message));
      // Сколько непрочитанных сейчас (прогон ru мог отметить всё прочитанным).
      const now = await (await fetch(base + "/api/civic/v2/notifications", { headers: { "X-Birge-Device": MAIN, "X-Birge-Ideas-Device": IDEAS } })).json();
      const unread0 = now.unread;
      await page.goto(base + "/", { waitUntil: "domcontentloaded" });
      const bellSel = '[data-action="notifications"]';
      const hasBell = await page.waitForSelector(bellSel, { timeout: 20000 }).then(() => true, () => false);
      check(`${tag}: колокольчик в капсуле справа (вид «Житель»)`, hasBell);
      if (!hasBell) { await shot(page, `${tag}-no-bell`); await ctx.close(); continue; }
      if (unread0) await page.waitForFunction((sel) => { const b = document.querySelector(sel + " .bk-nav__badge"); return b && !b.hidden && b.textContent; }, bellSel, { timeout: 15000 }).catch(() => {});
      else await sleep(1500);
      const badge = await page.$eval(bellSel + " .bk-nav__badge", (e) => (e.hidden ? "" : e.textContent)).catch(() => "");
      check(`${tag}: счётчик непрочитанных на колокольчике (нет новых — нет числа)`,
        badge === (unread0 > 9 ? "9+" : unread0 ? String(unread0) : ""), `${badge} vs ${unread0}`);
      const size = await page.$eval(bellSel, (e) => { const r = e.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; });
      check(`${tag}: кнопка-колокольчик ≥ 44 px`, size[0] >= 44 && size[1] >= 44, size);
      await page.click(bellSel);
      await page.waitForSelector(".bk-notify .bk-feed__item", { timeout: 10000 });
      await sleep(400);   // появление панели (200 мс) закончилось — кадр без полупрозрачности
      const panel = await page.evaluate(() => {
        const p = document.querySelector(".bk-notify"), r = p.getBoundingClientRect();
        return { w: Math.round(r.width), groups: [...p.querySelectorAll(".bk-feed__group")].map((g) => g.textContent),
          items: p.querySelectorAll(".bk-feed__item").length, unread: p.querySelectorAll('.bk-feed__item[data-unread="true"]').length,
          big: [...p.querySelectorAll("svg, img")].filter((x) => x.getBoundingClientRect().width > 48).length, text: p.innerText };
      });
      check(`${tag}: панель 360, группы «Новые»/«Раньше», строки ленты`, panel.w <= 360 && panel.groups.length >= 1 && panel.items >= 3
        && panel.unread === unread0, JSON.stringify(panel).slice(0, 300));
      check(`${tag}: в панели нет картинок > 48 px (П1)`, panel.big === 0, panel.big);
      check(`${tag}: в панели нет технических слов`, !TECH.some((w) => panel.text.includes(w)), panel.text.slice(0, 300));
      const pa = await textAudit(page, ".bk-notify");
      check(`${tag}: в панели текст не мельче ${pa.min} px (токен --fs-xs)`, !pa.missing && !pa.tiny.length, JSON.stringify(pa.tiny));
      if (lang === "kk") check(`${tag}: подписи по-казахски`, /Хабарламалар/.test(panel.text) && /Жаңа|Бұрынғы/.test(panel.text)
        && !/Новые|Раньше|Прочитать/.test(panel.text), panel.text.slice(0, 200));
      await shot(page, `${tag}-panel`);
      await page.keyboard.press("Escape");
      const closed = await page.evaluate((sel) => !document.querySelector(".bk-notify") && document.activeElement === document.querySelector(sel), bellSel);
      check(`${tag}: Esc закрывает панель, фокус — на колокольчике`, closed);
      if (flow) {
        // Нажатие на уведомление об идее открывает её карточку в «Идеях» и отмечает прочитанным.
        await page.click(bellSel);
        await page.waitForSelector(".bk-notify .bk-feed__item");
        await page.click('.bk-notify .bk-feed__item[data-kind="idea"]');
        const opened = await page.waitForFunction((id) => {
          const c = document.querySelector('.ri-pc[aria-current="true"]');
          return document.body.dataset.birgeSection === "ideas" && c && c.getAttribute("data-idea") === id;
        }, ideaId, { timeout: 15000 }).then(() => true, () => false);
        check(`${tag}: уведомление открыло конкретную идею (не главную)`, opened);
        await shot(page, `${tag}-opened-idea`);
        await page.waitForFunction((args) => { const b = document.querySelector(args[0] + " .bk-nav__badge"); return b && (b.hidden ? 0 : Number(b.textContent)) === args[1] - 1; },
          [bellSel, unread0], { timeout: 10000 }).then(() => check(`${tag}: счётчик −1 после открытия`, true), () => check(`${tag}: счётчик −1 после открытия`, false));
        await page.click(bellSel);
        await page.waitForSelector(".bk-notify__readall:not([hidden])");
        await page.click(".bk-notify__readall");
        const zero = await page.waitForFunction((sel) => { const b = document.querySelector(sel + " .bk-nav__badge"); return !b || b.hidden; }, bellSel, { timeout: 10000 })
          .then(() => true, () => false);
        check(`${tag}: «Прочитать все» — счётчика нет`, zero);
        // Кризис R17 (если модуль в сборке и событие в ленте): уведомление открывает его карточку — «#crisis/<id>».
        await sleep(800);   // «Прочитать все» перерисовывает ленту дважды (сразу и по ответу сервера)
        const crisisSel = '.bk-notify .bk-feed__item[data-kind="crisis"]';
        const crisis = await page.$(crisisSel);
        if (crisis) {
          const href = await page.getAttribute(crisisSel, "href");
          await page.click(crisisSel);
          const opened = await page.waitForFunction(() => document.body.dataset.birgeSection === "crisis", null, { timeout: 10000 })
            .then(() => true, () => false);
          check(`${tag}: уведомление о кризисе открыло его карточку (${href})`, opened && /^#crisis\//.test(href || ""), href);
          await sleep(800);
          await shot(page, `${tag}-opened-crisis`);
          await page.goto(base + "/#map", { waitUntil: "domcontentloaded" });
          await page.waitForSelector(bellSel, { timeout: 20000 });
        } else {
          console.log(`NOT_RUN ${tag}: кризис — в ленте нет события R17 (модуля нет в сборке)`);
          await page.keyboard.press("Escape");
        }
        // Вид «Акимат»: колокольчика нет (IA §5.7 — только житель).
        await page.evaluate(() => window.BirgeShell && window.BirgeShell.setMode && window.BirgeShell.setMode("akimat"));
        await sleep(600);
        const inAkimat = await page.$$eval(bellSel, (els) => els.filter((e) => e.offsetParent !== null).length);
        check(`${tag}: в виде «Акимат» колокольчика нет`, inAkimat === 0, inAkimat);
      }
      check(`${tag}: без ошибок JS`, !page.errs.length, page.errs.join(" | "));
      await ctx.close();
    }
    // Новое событие после «Прочитать все» (вторая идея жителя опубликована) — на телефоне будет что считать.
    const idea2 = await api(base, "POST", "/api/civic/v2/ideas", { title: "Урны у остановки", description: "Мусор летит на дорогу.",
      geometry: { type: "Point", coordinates: [71.3671, 51.1371] }, device_id: IDEAS, lang: "ru" });
    const pub2 = idea2.status === 201
      ? await api(base, "POST", `/api/civic/v2/ideas/${idea2.json.item.id}/decide`, { action: "publish" }, auth) : null;
    check("уведомления: вторая идея жителя опубликована (новое событие после «Прочитать все»)", idea2.status === 201 && pub2 && pub2.status === 200,
      JSON.stringify(idea2.json).slice(0, 200));
    await sleep(5500);   // сборщик ленты кэширует ответ на 5 с — следующий житель увидит новое
    // Телефон: экран «Уведомления» (#notifications) — лента и пустое состояние.
    for (const [lang, main, ideas, empty] of [["ru", MAIN, IDEAS, false], ["kk", MAIN, IDEAS, false], ["ru", "d-" + "Z".repeat(24), null, true]]) {
      const tag = `notify-375-${lang}${empty ? "-empty" : ""}`;
      const ctx = await browser.newContext({ viewport: { width: 375, height: 812 }, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
      await ctx.addInitScript(([l, m, i]) => {
        try { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l); localStorage.setItem("birge.device", m);
          if (i) localStorage.setItem("birge.device_id", i); } catch (e) {}
      }, [lang, main, ideas]);
      const page = await ctx.newPage();
      page.errs = [];
      page.on("pageerror", (e) => page.errs.push(e.message));
      await page.goto(base + "/#notifications", { waitUntil: "domcontentloaded" });
      const ok = await page.waitForSelector(empty ? ".rn .rn-empty" : ".rn .bk-feed__item", { timeout: 20000 }).then(() => true, () => false);
      check(`${tag}: экран «Уведомления» ${empty ? "— пусто: значок, текст" : "— лента"}`, ok);
      if (ok && empty) {
        const ic = await page.$eval(".rn-empty__ic", (e) => { const r = e.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; });
        check(`${tag}: значок пустого состояния ≤ 48 px (П1)`, ic[0] <= 48 && ic[1] <= 48, ic);
      }
      const au = await textAudit(page, "#birge-screen");
      check(`${tag}: без технических слов и прокрутки вбок`, !au.missing && !au.tech.length && !au.overflow, JSON.stringify({ tech: au.tech, overflow: au.overflow }));
      check(`${tag}: текст не мельче ${au.min} px (токен --fs-xs)`, !au.missing && !au.tiny.length, JSON.stringify(au.tiny));
      await shot(page, tag);
      if (!empty && lang === "ru") {
        // Оболочка раунда 15 (R01 B0.4): на телефоне колокольчика нет — первый пункт меню аватара «Уведомления · N» и точка
        // на аватаре; число — из BirgeNotify.onCount. Оболочка без этого пункта (FINAL-4) — NOT_RUN.
        const want = (await (await fetch(base + "/api/civic/v2/notifications", { headers: { "X-Birge-Device": MAIN, "X-Birge-Ideas-Device": IDEAS } })).json()).unread;
        await page.goto(base + "/#map", { waitUntil: "domcontentloaded" });
        await page.waitForFunction(() => document.body.dataset.birgeSection === "map", null, { timeout: 10000 }).catch(() => {});
        await sleep(1500);
        const dot = await page.$eval(".birge-avatar", (e) => e.hasAttribute("data-badge")).catch(() => null);
        await page.click(".birge-avatar").catch(() => {});
        const item = await page.waitForSelector('.bk-menu__item[data-section="notifications"]', { timeout: 4000 }).then((x) => x, () => null);
        if (!item) {
          console.log(`NOT_RUN ${tag}: в меню аватара нет пункта «Уведомления» (оболочка без IA §5.7)`);
        } else {
          const badge = await item.$eval(".bk-nav__badge", (e) => e.textContent).catch(() => "");
          check(`${tag}: меню аватара — «Уведомления · ${want}» и точка на аватаре`, want > 0 && badge === (want > 9 ? "9+" : String(want)) && dot === true,
            JSON.stringify({ want, badge, dot }));
          await shot(page, `${tag}-avatar-menu`);
          await item.click();
          const opened = await page.waitForSelector(".rn .bk-feed__item", { timeout: 10000 }).then(() => true, () => false);
          check(`${tag}: пункт меню аватара открывает ленту`, opened && (await page.evaluate(() => document.body.dataset.birgeSection)) === "notifications");
        }
      }
      check(`${tag}: без ошибок JS`, !page.errs.length, page.errs.join(" | "));
      await ctx.close();
    }
  } finally {
    srv.kill();
  }
}

// ------------------------------------------------------------------------------------------------ идея → инициатива (R16)
// Нужен модуль R16 ui/civic_together в дереве (neighbors_tree.sh или сборка R01 с R16), иначе — NOT_RUN. Экран R16 в
// дереве может не быть подключён: у жителя — заглушка BirgeTogether {open, mount}, проверяется вызов open("initiative", id).
async function togetherPart(browser) {
  if (!fs.existsSync(path.join(ROOT, "ui", "civic_together"))) {
    console.log("NOT_RUN идея → инициатива: в дереве нет модуля R16 ui/civic_together");
    return;
  }
  const { srv, base } = await fresh();
  try {
    let made = null;
    for (const [width, lang] of [[1366, "ru"], [375, "kk"]]) {
      const tag = `together-${width}-${lang}`;
      const page = await newPage(browser, width, lang, "akimat");
      await page.goto(base + "/", { waitUntil: "domcontentloaded" });
      await login(page);
      await page.goto(base + "/#map", { waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => document.body.dataset.birgeSection === "map", null, { timeout: 10000 }).catch(() => {});
      await page.goto(base + "/#projects", { waitUntil: "domcontentloaded" });
      await page.waitForSelector(".ri-pc[data-idea-status=voting]", { timeout: 20000 });
      const id = made || await page.$eval(".ri-pc[data-idea-status=voting]", (e) => e.getAttribute("data-idea"));
      await page.evaluate((x) => window.BirgeIdeas.open(x), id);
      if (!made) {
        const btn = await page.waitForSelector(`[data-pd="${id}"] [data-key=together-make]`, { timeout: 10000 }).then(() => true, () => false);
        check(`${tag}: у опубликованной идеи — тихая «Сделать инициативой» (R16 в сборке)`, btn);
        const primary = await page.$$eval(`[data-pd="${id}"] .bk-btn--primary`, (els) => els.length);
        check(`${tag}: главная кнопка карточки одна`, primary <= 1, primary);
        await shot(page, `${tag}-staff-make`);
        await page.click(`[data-pd="${id}"] [data-key=together-make]`);
        made = id;
      }
      const line = await page.waitForSelector(`[data-pd="${id}"] [data-key=together-line]`, { timeout: 10000 }).then(() => true, () => false);
      check(`${tag}: после — строка «Сделайте вместе» со ссылкой на дело`, line);
      const href = line ? await page.$eval(`[data-pd="${id}"] [data-key=together-open]`, (e) => e.getAttribute("href")) : "";
      check(`${tag}: ссылка — #together/<id дела>`, /^#together\/[A-Za-z0-9._:-]+$/.test(href), href);
      check(`${tag}: кнопки «Сделать инициативой» больше нет`, !(await page.$(`[data-pd="${id}"] [data-key=together-make]`)));
      await shot(page, `${tag}-staff-done`);
      check(`${tag}: без ошибок JS`, !page.errs.length, page.errs.join(" | "));
      await page.close();
    }
    // Повтор с сервера — то же дело (без второго), жителю — строка и переход в дело R16.
    const auth = await staffAuth(base);
    const again = await api(base, "POST", `/api/civic/v2/ideas/${made}/to-initiative`, {}, auth);
    const first = await api(base, "GET", `/api/civic/v2/ideas`);
    const item = (first.json.items || []).find((x) => x.id === made) || {};
    check("идея → инициатива: повтор не создаёт второе дело", again.status === 201 && again.json && again.json.created === false
      && again.json.initiative && item.initiative && again.json.initiative.id === item.initiative.id, JSON.stringify(again.json).slice(0, 300));
    // Экран R16 в сборке (web/civic/together) — «Открыть дело» ведёт в настоящий раздел «Сделаем вместе»;
    // нет — заглушка BirgeTogether проверяет вызов open("initiative", id).
    const realR16 = fs.existsSync(path.join(ROOT, "web", "civic", "together", "together.js"))
      && fs.readFileSync(path.join(ROOT, "web", "index.html"), "utf8").includes("/civic/together/together.js");
    for (const lang of ["ru", "kk"]) {
      const tag = `together-375-resident-${lang}`;
      const page = await newPage(browser, 375, lang, "resident");
      if (!realR16) {
        await page.addInitScript(() => {
          window.BirgeTogether = { version: "stub", open: (kind, id) => { window.__opened = [kind, id]; return true; },
            mount: (el) => { el.textContent = "R16"; return {}; } };
        });
      }
      await page.goto(base + "/#ideas/" + made, { waitUntil: "domcontentloaded" });
      const ok = await page.waitForSelector(`[data-pd="${made}"] [data-key=together-line]`, { timeout: 20000 }).then(() => true, () => false);
      check(`${tag}: житель видит «Сделайте вместе — поддержим инвентарём»`, ok);
      const text = ok ? await page.$eval(`[data-pd="${made}"] [data-key=together-line]`, (e) => e.innerText) : "";
      check(`${tag}: подпись на языке интерфейса`, lang === "kk" ? /Бірге жасаңыз/.test(text) : /Сделайте вместе/.test(text), text);
      await shot(page, tag);
      if (ok && !realR16) {
        await page.click(`[data-pd="${made}"] [data-key=together-open]`);
        const opened = await page.evaluate(() => window.__opened || null);
        check(`${tag}: «Открыть дело» → BirgeTogether.open("initiative", id)`, opened && opened[0] === "initiative" && opened[1] === item.initiative.id, JSON.stringify(opened));
      } else if (ok) {
        await page.click(`[data-pd="${made}"] [data-key=together-open]`);
        const inTogether = await page.waitForFunction(() => document.body.dataset.birgeSection === "together", null, { timeout: 10000 })
          .then(() => true, () => false);
        check(`${tag}: «Открыть дело» → раздел «Сделаем вместе» R16`, inTogether);
        await sleep(1200);
        const shown = await page.evaluate(() => (document.querySelector("#birge-screen") || document.body).innerText);
        const titles = [item.title_ru, item.title_kk, item.title].filter(Boolean);
        check(`${tag}: R16 показывает это дело (название идеи)`, titles.some((t) => shown.includes(t)), titles.join(" / ") + " — " + shown.slice(0, 300));
        await shot(page, `${tag}-r16`);
      }
      check(`${tag}: без ошибок JS`, !page.errs.length, page.errs.join(" | "));
      await page.close();
    }
    // Без экрана R16 (нет BirgeTogether) — у жителя строки нет: нечего открывать (в сборке с R16 — проверка про то же).
    const bare = await newPage(browser, 1366, "ru", "resident");
    await bare.goto(base + "/#ideas/" + made, { waitUntil: "domcontentloaded" });
    await bare.waitForSelector(`[data-pd="${made}"]`, { timeout: 20000 }).catch(() => {});
    const hasLine = !!(await bare.$(`[data-pd="${made}"] [data-key=together-line]`));
    check("житель без экрана R16: строки «Сделайте вместе» нет", !hasLine || await bare.evaluate(() => !!window.BirgeTogether));
    await bare.close();
  } finally {
    srv.kill();
  }
}

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  try {
    if (!ONLY || ONLY.includes("works")) await worksPart(browser);
    if (!ONLY || ONLY.includes("ideas")) await ideasPart(browser);
    if (!ONLY || ONLY.includes("notify")) await notifyPart(browser);
    if (!ONLY || ONLY.includes("together")) await togetherPart(browser);
  } catch (e) {
    check("прогон без исключений", false, e.stack || e);
  } finally {
    await browser.close();
  }
  const failed = results.filter((r) => !r.ok).length;
  console.log(`\nR06 r15 browser: ${results.length - failed} PASS / ${failed} FAIL`);
  process.exit(failed ? 1 : 0);
})();
