#!/usr/bin/env node
/*
 * R09 · раунд 15+ (поправка П3) · «Обращения» в НАСТОЯЩЕМ приложении: раскладка по кадру 05 review_final51 и задачи
 * «ИИ-разбора пачки»:  node tests/civic/R09/inbox_layout_r09.cjs [--root <дерево сборки>] [--screenshots <папка>]
 *   • ≥ 1200 px (1366 × ru, kk): две колонки «список | карточка», экран по высоте листа оболочки (лист сам не
 *     прокручивается), «Обращения» во всю ширину листа; при прокрутке списка плашка группы — у верхнего края списка;
 *   • < 1200 px (1024 × ru, 375 × kk): одна колонка во всю ширину листа, карточка под строкой; при прокрутке листа плашка
 *     группы — у самого края листа (над ней не видно уехавших строк);
 *   • задачи «ИИ-разбора» (integration.intake_commit, пример — demo): пометка «Разбор пачки» в строке, «Источник: разбор
 *     пачки» в карточке, действия сотрудника есть (пример пачки рабочий);
 *   • «Разобрать пачку» — только когда экран R04 в сборке (window.BirgeIntake; здесь — заглушка) → раздел «intake»;
 *   • метка «ИИ» (BirgeUI.aiTag ui-kit R11) у «Похоже, нужны 2 службы» — если ui-kit сборки её умеет.
 * Сервер: python3 -B app.py (CIVIC_DEMO=1, CIVIC_DEMO_WORLD=1 — мир R02 сборки) на ВРЕМЕННОЙ SQLite. В репозиторий не пишет.
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
const PIT_TARGET = "osm-w243047611-4";                  // сцена 8 мира R02: «Участок: улица Баян Сулу»
// Задача пачки — в месте без жалоб мира (своя группа «место + категория»): «примерное место» у точки, парковка.
const QUIET = [71.452, 51.171];
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet|ReadPixels/i;
const SAY = {
  ru: { tag: "Разбор пачки", source: "Источник: разбор пачки", open: "Разобрать пачку", ai: "Подсказка ИИ — проверьте" },
  kk: { tag: "Топтаманы талдау", source: "Дереккөз: топтаманы талдау", open: "Топтаманы талдау",
        ai: "Жасанды интеллект кеңесі — тексеріңіз" },
};
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail !== undefined ? " — " + JSON.stringify(detail).slice(0, 300) : "")); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no);
  s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", CIVIC_DEMO_WORLD: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (a) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${a}`, { cwd: ROOT, env, stdio: ["ignore", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  const staff = { user: "r09-layout", pass: "Birge-layout-" + Math.random().toString(36).slice(2) + "-Aa1!" };
  execSync(`python3 -B -m ui.civic_store --db "${db}" create-editor ${staff.user} --password-stdin`,
           { cwd: ROOT, env, input: staff.pass + "\n", stdio: ["pipe", "ignore", "inherit"] });
  // Задачи «ИИ-разбора пачки» — той же функцией R09, которую зовёт R04 (пример пачки — demo).
  const tasks = [{ id: "n1", category: "parking", services: [{ id: "parking", role: "lead" }], target: null, point: QUIET,
                   text_ids: ["t1", "t2"], people: 2, title_ru: "Машины ставят на газон у дома" }];
  const texts = { t1: "Каждую ночь машины паркуют прямо на газоне у подъезда", t2: "Көліктерді түнде көгалға қояды" };
  const made = execSync(`python3 -B -c "import json,sys; from ui.civic_feedback.v2.integration import intake_commit; ` +
    `print(json.dumps(intake_commit(sys.argv[1], 'night-layout', json.loads(sys.argv[2]), json.loads(sys.argv[3]), demo=True)))" ` +
    `"${db}" '${JSON.stringify(tasks)}' '${JSON.stringify(texts)}'`, { cwd: ROOT, env }).toString();
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  srv.intake = JSON.parse(made);
  for (let i = 0; i < 200; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) { srv.staff = staff; return srv; } } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}
const shellReady = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined"
  && mapReady && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 60000 });
async function shot(page, name) { if (SHOTS) { await sleep(400); await page.screenshot({ path: path.join(SHOTS, name + ".png") }); } }

// Геометрия: лист оболочки (ближайший прокручиваемый предок «Обращений»), сам экран, колонка списка.
const GEOMETRY = () => {
  const box = document.querySelector(".bc-inbox");
  let sheet = box && box.parentElement;
  while (sheet && sheet !== document.body && !/(auto|scroll)/.test(getComputedStyle(sheet).overflowY)) sheet = sheet.parentElement;
  const r = (el) => { const b = el.getBoundingClientRect(); return { l: b.left, t: b.top, r: b.right, b: b.bottom, w: b.width, h: b.height }; };
  const cs = sheet ? getComputedStyle(sheet) : null;
  return { split: box.hasAttribute("data-split"), box: r(box), sheet: sheet && sheet !== document.body ? r(sheet) : null,
           pad: cs ? { l: parseFloat(cs.paddingLeft), r: parseFloat(cs.paddingRight), t: parseFloat(cs.paddingTop) } : null,
           sheetScroll: sheet ? { h: sheet.scrollHeight, ch: sheet.clientHeight } : null };
};

async function variant(browser, base, width, height, lang, staff, intakeId) {
  const tag = `${width}-${lang}`;
  const say = SAY[lang];
  const wide = width >= 1200;
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, hasTouch: width < 1024 });
  await ctx.addInitScript(([l]) => {
    try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); } catch (e) {}
    // Экран R04 «Разбор обращений» — заглушка (в сборке его может ещё не быть): кнопка «Разобрать пачку» появляется по нему.
    window.BirgeIntake = { mount: (root) => { root.textContent = "intake"; return { destroy() {}, setLang() {} }; } };
  }, [lang]);
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
    const ready = await page.waitForSelector(".bc-inbox__row", { timeout: 15000 }).then(() => true, () => false);
    check(`${tag}: сотрудник вошёл, «Обращения» открыты`, logged && ready);
    if (!ready) return;
    await sleep(500);
    let g = await page.evaluate(GEOMETRY);
    const fill = g.sheet && Math.abs(g.box.l - (g.sheet.l + g.pad.l)) <= 2 && Math.abs(g.box.r - (g.sheet.r - g.pad.r)) <= 2;
    check(`${tag}: «Обращения» во всю ширину листа — без пустых полей слева и справа`, fill,
          { box: [Math.round(g.box.l), Math.round(g.box.r)], sheet: g.sheet && [Math.round(g.sheet.l), Math.round(g.sheet.r)], pad: g.pad });
    check(`${tag}: ${wide ? "две колонки «список | карточка»" : "одна колонка"}`, g.split === wide, { split: g.split });
    if (wide) check(`${tag}: экран — по высоте листа, сам лист не прокручивается (прокрутка — у колонок)`,
                    g.sheetScroll && g.sheetScroll.h <= g.sheetScroll.ch + 2, g.sheetScroll);
    // Текст строк не уходит под соседей — как R10 visual_audit «не обрезан и не перекрыт»: точки по строкам самого текста
    // (Range), обрезка — только у предков; прозрачная зона нажатия без своего текста в точке не закрывает (1024 kk, П3).
    const under = await page.evaluate(() => {
      const clearAt = (hit, x, y) => {
        const cs = getComputedStyle(hit);
        if (!/^(transparent|rgba\(0, 0, 0, 0\))$/.test(cs.backgroundColor) || cs.backgroundImage !== "none" || cs.boxShadow !== "none") return false;
        const rg = document.createRange(); rg.selectNodeContents(hit);
        return ![...rg.getClientRects()].some((q) => x >= q.left && x <= q.right && y >= q.top && y <= q.bottom);
      };
      const bad = [];
      for (const el of document.querySelectorAll(".bc-inbox__line *")) {
        const own = [...el.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim());
        const r = el.getBoundingClientRect();
        if (!own.length || r.width < 20 || r.top < 0 || r.bottom > innerHeight) continue;
        let c = { l: 0, t: 0, r: innerWidth, b: innerHeight };
        for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) {
          const cs = getComputedStyle(n);
          if (cs.overflowX === "visible" && cs.overflowY === "visible") continue;
          const q = n.getBoundingClientRect();
          c = { l: Math.max(c.l, q.left), t: Math.max(c.t, q.top), r: Math.min(c.r, q.right), b: Math.min(c.b, q.bottom) };
        }
        for (const tn of own) {
          const rg = document.createRange(); rg.selectNodeContents(tn);
          for (const q of [...rg.getClientRects()].slice(0, 3)) {
            const y = q.top + q.height / 2;
            for (const x of [q.left + 2, q.left + q.width / 2, q.right - 2]) {
              if (x < c.l || x > c.r || y < c.t || y > c.b) continue;
              const hit = document.elementFromPoint(x, y);
              if (hit && hit !== el && !el.contains(hit) && !hit.contains(el) && !clearAt(hit, x, y)) {
                bad.push(`«${tn.textContent.trim().slice(0, 24)}» под «${(hit.innerText || hit.tagName).trim().slice(0, 24)}»`);
              }
            }
          }
        }
      }
      return [...new Set(bad)].slice(0, 4);
    });
    check(`${tag}: текст строк не уходит под плашку числа и срок (многоточие — внутри своей коробки)`, under.length === 0, under);

    // Строка сцены 8 → карточка: справа (две колонки) или под строкой (одна).
    const pit = page.locator(`.bc-inbox__item[data-target="${PIT_TARGET}"] .bc-inbox__row`).first();
    await pit.click();
    await page.waitForSelector(".bc-inbox__detail .bc-joint", { timeout: 10000 }).catch(() => null);
    const placed = await page.evaluate(([target]) => {
      const detail = document.querySelector(".bc-inbox__detail");
      const li = document.querySelector(`.bc-inbox__item--open[data-target="${target}"]`);
      const pane = document.querySelector(".bc-inbox__pane");
      return { inPane: !!(pane && detail && pane.contains(detail)), underRow: !!(li && detail && li.contains(detail)),
               paneTitle: (document.querySelector(".bc-inbox__pane-title") || {}).textContent || "",
               rowPlace: li ? (li.querySelector(".bc-inbox__place")?.childNodes[0]?.textContent || "") : "",
               ai: !!document.querySelector(".bc-inbox__detail .bc-joint-hint__title .bk-ai"),
               aiTitle: document.querySelector(".bc-inbox__detail .bc-joint-hint__title .bk-ai")?.getAttribute("title") || "",
               kit: !!(window.BirgeUI && typeof window.BirgeUI.aiTag === "function") };
    }, [PIT_TARGET]);
    check(`${tag}: карточка ямы — ${wide ? "справа, с названием места сверху" : "под строкой"}`,
          wide ? placed.inPane && !placed.underRow && clean(placed.paneTitle) === clean(placed.rowPlace) : placed.underRow && !placed.inPane,
          placed);
    check(`${tag}: у «Похоже, нужны 2 службы» — ${placed.kit ? `метка «ИИ» с подсказкой «${say.ai}»` : "ui-kit без aiTag — метки нет, ошибок нет"}`,
          placed.kit ? placed.ai && placed.aiTitle === say.ai : !placed.ai, placed);
    await shot(page, `layout-${tag}-1-open`);

    // Липкая плашка: прокрутить список (две колонки) или лист (одна колонка) — плашка у верхнего края, строк над ней нет.
    const stuck = await page.evaluate(async (two) => {
      const box = document.querySelector(".bc-inbox");
      let scroller = two ? box.querySelector(".bc-inbox__groups") : box.parentElement;
      while (!two && scroller && !/(auto|scroll)/.test(getComputedStyle(scroller).overflowY)) scroller = scroller.parentElement;
      scroller.scrollTop += 700;
      await new Promise((ok) => setTimeout(ok, 300));
      const edge = scroller.getBoundingClientRect().top + scroller.clientTop;
      const heads = [...box.querySelectorAll(".bc-inbox__ghead")];
      const head = heads.find((hd) => Math.abs(hd.getBoundingClientRect().top - edge) <= 1.5) || null;
      const rect = head ? head.getBoundingClientRect() : null;
      // Над плашкой (между краем и плашкой) — ничего из строк списка.
      const probe = rect ? document.elementFromPoint(rect.left + 60, Math.max(edge + 1, rect.top - 2)) : null;
      return { scrolled: scroller.scrollTop, edge: Math.round(edge), headTop: rect ? Math.round(rect.top) : null,
               above: probe ? (probe.closest(".bc-inbox__row") ? "row" : probe.closest(".bc-inbox__ghead") ? "head" : probe.tagName) : null };
    }, wide);
    check(`${tag}: при прокрутке плашка группы — у самого верхнего края ${wide ? "списка" : "листа"}, уехавших строк над ней не видно`,
          stuck.headTop !== null && stuck.above !== "row", stuck);
    await shot(page, `layout-${tag}-2-sticky`);

    // Задача «ИИ-разбора пачки»: пометка в строке, источник в карточке, действия сотрудника (пример пачки — рабочий).
    await page.evaluate(() => { const s = document.querySelector(".bc-inbox__groups"); if (s) s.scrollTop = 0; });
    const intakeRow = page.locator(".bc-inbox__item").filter({ has: page.locator(".bc-tag--intake") }).first();
    const tagText = clean(await intakeRow.locator(".bc-tag--intake").textContent().catch(() => "")).replace(/^·\s*/, "");
    check(`${tag}: задача пачки в списке — пометка «${say.tag}» в строке темы`, tagText === say.tag, tagText);
    if (tagText) {
      await intakeRow.locator(".bc-inbox__row").click();
      await page.waitForSelector(".bc-inbox__detail .bc-staff__source", { timeout: 10000 }).catch(() => null);
      const card = await page.evaluate(() => ({ source: document.querySelector(".bc-inbox__detail .bc-staff__source")?.textContent || "",
        actions: !!document.querySelector(".bc-inbox__detail .bc-staff__open-fix, .bc-inbox__detail .bc-joint__actions, .bc-inbox__detail .bc-joint"),
        readonly: /пример|үлгі/i.test(document.querySelector(".bc-inbox__detail .bc-inbox__staff")?.textContent || "") &&
                  !document.querySelector(".bc-inbox__detail .bc-joint") }));
      check(`${tag}: карточка задачи пачки — «${say.source}» и действия сотрудника (не «только просмотр»)`,
            clean(card.source) === say.source && card.actions && !card.readonly, card);
      await shot(page, `layout-${tag}-3-intake`);
    }

    // «Разобрать пачку» — экран R04 в сборке (заглушка) → раздел «Разбор обращений».
    const btn = page.locator(".bc-inbox__intake");
    const label = clean(await btn.textContent().catch(() => ""));
    check(`${tag}: кнопка «${say.open}» в шапке «Обращений» (экран R04 в сборке)`, label === say.open, label);
    if (label) {
      await btn.click();
      const went = await page.waitForFunction(() => document.body.dataset.birgeSection === "intake" || /#intake/.test(location.hash),
        null, { timeout: 5000 }).then(() => true, () => false);
      check(`${tag}: «${say.open}» → раздел «Разбор обращений» (#intake)`, went,
            await page.evaluate(() => ({ section: document.body.dataset.birgeSection, hash: location.hash })));
    }
    check(`${tag}: нет ошибок на странице`, errors.length === 0, errors.slice(0, 3));
  } catch (err) {
    check(`${tag}: сценарий прошёл без исключений`, false, String(err && err.message).slice(0, 300));
  } finally {
    await ctx.close();
  }
}

(async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "r09-layout-"));
  const port = await freePort();
  let srv = null;
  const browser = await chromium.launch();
  try {
    srv = await startServer(port, path.join(dir, "civic.sqlite3"));
    check("задача «ИИ-разбора» создана функцией R09 (intake_commit)", (srv.intake.created || []).length === 1, srv.intake);
    for (const [w, h, lang] of [[1366, 768, "ru"], [1366, 768, "kk"], [1024, 768, "ru"], [375, 812, "kk"]]) {
      await variant(browser, `http://127.0.0.1:${port}`, w, h, lang, srv.staff);
    }
  } catch (err) {
    check("приложение и браузер запустились", false, String(err && err.message).slice(0, 300));
  } finally {
    await browser.close();
    if (srv) srv.kill();
    fs.rmSync(dir, { recursive: true, force: true });
  }
  const ok = results.filter((r) => r.ok).length;
  console.log(`\nИТОГ: ${ok}/${results.length} ${ok === results.length ? "PASS" : "FAIL"}`);
  process.exit(ok === results.length ? 0 : 1);
})();
