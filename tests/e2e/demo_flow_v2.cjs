// R10 · раунд 15 · сценарий демо v2, часть 2 «Бірге»: сцены 7–9 (IDEA §3, IA_ROUND15 R11 §4) на сборке R01.
//
//   NODE_PATH="$(npm root -g)" node tests/e2e/demo_flow_v2.cjs --root <папка сборки> --out <папка>
//        [--sizes 1366x768,1024x768,375x812] [--langs ru,kk] [--no-world] [--api-only]
//
// Часть 1 (шаги 1–7 FINAL-4) проверяет demo_flow.cjs — его запускать отдельно (регресс).
// Сервер сборки — как run-city.bat демо-мира: CIVIC_DEMO=1 и CIVIC_DEMO_WORLD=1 (единый демо-мир R02, CONTRACT §11),
// временная база, сотрудник r10-operator. Id сцен — из data/civic/astana/demo-world/world_v1.json → scenes (R02 SCHEMA §3).
//
// Два слоя, как demo_flow.cjs:
//   API — сцена через HTTP API v2 (CONTRACT §7): отделяет «нет модуля» от «нет кнопки»;
//   UI  — экраны по адресам IA_ROUND15 (#yard/<двор>, #together/<инициатива>, #agencies/<вкладка>, #crisis/<кризис>, #day),
//         проверки UX (прокрутка вбок, ключи перевода, шрифт, зоны нажатия, контраст) и то, что видно по данным сцены.
// Статусы: PASS, FAIL (с владельцем), NOT_RUN (модуля или экрана нет в сборке — с причиной; это не FAIL).
// Итог: <out>/RESULT.json, RESULT.md (с временем сцен), кадры <размер>-<язык>-<сцена>.jpg.
"use strict";
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path"), os = require("os");
const L = require("./r10_lib.cjs");
const { uiScreen, NOISE } = require("./ux_lib.cjs");
const { sleep, T, esc, textRe, firstVisible } = L;

const args = L.parseArgs(process.argv.slice(2));
const ROOT = path.resolve(args.root || path.join(__dirname, "../.."));
const OUT = path.resolve(args.out || path.join(os.tmpdir(), "r10-e2e-v2"));
const SIZES = String(args.sizes || "1366x768,1024x768,375x812").split(",").map((s) => s.split("x").map(Number));
const LANGS = String(args.langs || "ru,kk").split(",");
const WORLD = !args["no-world"];
const V2 = "/api/civic/v2";
const T0 = Date.now();
const results = [], marks = {};
const add = (layer, step, name, status, detail, owner, shot) => {
  if (typeof status !== "string") status = status === null || status === undefined ? "NOT_RUN" : status ? "PASS" : "FAIL";
  results.push({ layer, step, name, status, detail: detail ?? null, owner: owner || null, shot: shot || null, ms: Date.now() - T0 });
  console.log(`${status.padEnd(7)} ${layer} ${step} ${name}` + (detail ? " — " + JSON.stringify(detail).slice(0, 260) : ""));
};
const ok3 = (v) => (v === null ? "NOT_RUN" : v ? "PASS" : "FAIL");

// Сцены демо-мира (R02 SCHEMA §3). Нет файла мира — сцены не определены: всё NOT_RUN.
function loadScenes() {
  const file = path.join(ROOT, "data/civic/astana/demo-world/world_v1.json");
  if (!fs.existsSync(file)) return null;
  try {
    const w = JSON.parse(fs.readFileSync(file, "utf8"));
    const s = w.scenes || {};
    const ini = (w.initiatives || []).find((x) => x.id === (s.scene7 || {}).initiative) || null;
    const done = (w.initiatives || []).find((x) => x.id === (s.scene7 || {}).initiative_done) || null;
    const comp = (w.complaints || []).find((x) => x.id === (s.scene8 || {}).complaint) || null;
    const inc = (w.incidents || []).find((x) => x.id === (s.scene9 || {}).incident) || null;
    const yard = (w.yards || []).find((x) => x.id === (s.scene7 || {}).yard) || null;
    const conflict = (w.planned_conflicts || []).find((x) => x.id === (s.scene8 || {}).conflict) || null;
    return { raw: s, ini, done, comp, inc, yard, conflict, counts: w.counts || {} };
  } catch (e) { return { error: String(e.message || e) }; }
}

const unwrap = (b) => (b && b.ok !== undefined && b.data !== undefined ? b.data : b);
const rec = (b, ...keys) => { const d = unwrap(b); if (d && typeof d === "object") for (const k of [...keys, "item"]) if (d[k] && typeof d[k] === "object" && !Array.isArray(d[k])) return d[k]; return d; };
const list = (b, ...keys) => { const d = unwrap(b); if (Array.isArray(d)) return d;
  if (d && typeof d === "object") for (const k of [...keys, "items", "rows", "services", "incidents", "conflicts", "frames", "events"]) if (Array.isArray(d[k])) return d[k]; return null; };
const st = (r) => (r.status === 503 ? "нет модуля (503)" : r.status === 404 ? "нет маршрута или записи (404)" : `HTTP ${r.status}`);

// ------------------------------------------------------------------------------------------------ API
async function apiFlow(A, S, staff, timing) {
  const dev = "r10-v2-res-" + Date.now(), dev2 = "r10-v2-res2-" + Date.now();
  const call = async (scene, method, p, body, asStaff, device) => {
    const r = await A.call(method, p, body, asStaff, device);
    (timing[scene] = timing[scene] || []).push(Math.round(r.ms));
    return r;
  };
  // --- сцена 7: «Мой двор» → инициатива → «Я приду» 14 → 15 → «Поддержать» → «Сделано вместе»
  const s7 = S && S.raw.scene7;
  if (!s7) add("API", "7", "сцена 7 «Двор вместе»", "NOT_RUN", "нет scenes.scene7 в файле мира R02", "R02");
  else {
    let r = await call("7", "GET", `${V2}/together/yards/${s7.yard}`, null, false, dev);
    if (r.status !== 200) add("API", "7", `«Мой двор» ${s7.yard}`, r.status === 503 || r.status === 404 ? "NOT_RUN" : "FAIL", st(r), "R16");
    else {
      const d = unwrap(r.body) || {};
      const yard = d.yard || d;
      const counts = d.counts || {};
      add("API", "7", "«Мой двор»: название, соседи — число, проблемы и инициативы двора",
        ok3(!!yard.label_ru && Number.isInteger(yard.members ?? counts.members) && counts.problems !== undefined),
        { label: yard.label_ru, members: yard.members ?? counts.members, problems: counts.problems, initiatives: counts.initiatives }, "R16");
      const items = ((d.initiatives || {}).items || []).map((x) => x.id);
      add("API", "7", `в «Моём дворе» есть инициатива сцены ${s7.initiative}`, ok3(items.includes(s7.initiative)), { items: items.slice(0, 6) }, "R16");
    }
    r = await call("7", "GET", `${V2}/together/initiatives/${s7.initiative}`, null, false, dev);
    const before = r.status === 200 ? (rec(r.body, "initiative") || {}).joined : null;
    // 404 — нет маршрута в шлюзе (R01) или инициативы мира не засеяны (R16 seed_world): NOT_RUN с причиной, а не FAIL.
    if (r.status !== 200) add("API", "7", `инициатива ${s7.initiative}`, [503, 404].includes(r.status) ? "NOT_RUN" : "FAIL", st(r), "R16");
    else {
      add("API", "7", `«Я приду» до сцены = ${s7.joined_before} (демо-мир)`, ok3(before === s7.joined_before), { joined: before }, "R16 + R02");
      const j = await call("7", "POST", `${V2}/together/initiatives/${s7.initiative}/join`, {}, false, dev);
      const after = (rec((await call("7", "GET", `${V2}/together/initiatives/${s7.initiative}`, null, false, dev)).body, "initiative") || {}).joined;
      add("API", "7", `«Я приду» → ${s7.joined_after}`, ok3([200, 201].includes(j.status) && after === s7.joined_after), { status: j.status, joined: after }, "R16");
      const sup = staff ? await call("7", "POST", `${V2}/together/initiatives/${s7.initiative}/support`, s7.support || { inventory: true, pickup_service: "waste" }, true) : null;
      const sv = sup ? rec((await call("7", "GET", `${V2}/together/initiatives/${s7.initiative}`, null, false, dev2)).body, "initiative") || {} : {};
      add("API", "7", "акимат «Поддержать: мешки и вывоз» → у инициативы «Поддержано акиматом»",
        sup ? ok3([200, 201].includes(sup.status) && !!(sv.support && (sv.support.by_akimat || sv.support.inventory))) : null,
        sup ? { status: sup.status, support: sv.support } : "нет входа сотрудника", "R16");
    }
    if (s7.initiative_done) {
      r = await call("7", "GET", `${V2}/together/initiatives/${s7.initiative_done}`, null, false, dev);
      const dn = r.status === 200 ? rec(r.body, "initiative") || {} : null;
      add("API", "7", "сделанная инициатива: статус done, отчёт «Сделано вместе: N соседей»",
        dn ? ok3(dn.status === "done" && !!(dn.report && (dn.report.text || dn.report.joined))) : [503, 404].includes(r.status) ? null : false,
        dn ? { status: dn.status, report: dn.report && (dn.report.text || "").slice(0, 80), joined: dn.joined } : st(r), "R16");
    }
  }
  // --- сцена 8: «Яма после раскопок» → ИИ: 2 службы → совместное исполнение → паспорт → табло → конфликт работ
  const s8 = S && S.raw.scene8;
  if (!s8) add("API", "8", "сцена 8 «Ведомства вместе»", "NOT_RUN", "нет scenes.scene8 в файле мира R02", "R02");
  else {
    const text = (S.comp && S.comp.text) || "Яма после раскопок: Водоканал менял трубу, асфальт не восстановили";
    let r = await call("8", "POST", `${V2}/route`, { text, lang: "ru" });
    const services = r.status === 200 ? ((unwrap(r.body) || {}).services || []).map((x) => (typeof x === "string" ? x : x.service)) : null;
    add("API", "8", "ИИ: «Нужны 2 службы» — маршрутизация жалобы сцены (вода + дороги)",
      r.status === 200 ? ok3(services.length >= 2 && services.includes("water") && services.includes("road")) : r.status === 503 || r.status === 404 ? null : false,
      r.status === 200 ? { services, joint: (unwrap(r.body) || {}).joint } : st(r), "R04");
    let jointSet = false;
    if (staff) {
      r = await call("8", "POST", `${V2}/complaints/${s8.complaint}/services`,
        { services: [{ service: "water", role: "lead" }, { service: "road", role: "partner" }] }, true);
      jointSet = [200, 201].includes(r.status);
      S.jointSet = jointSet;  // для интерфейса: житель видит строку служб в «Моих обращениях»
      add("API", "8", "сотрудник: совместное исполнение — 2 службы у обращения", r.status === 503 || r.status === 404 ? "NOT_RUN" : ok3(jointSet),
        { status: r.status, err: r.body && r.body.error }, "R09");
      r = await call("8", "POST", `${V2}/complaints/${s8.complaint}/part`, { service: "water", status: "done", note: "Трубу заменили" }, true);
      add("API", "8", "сотрудник: часть «Водоканал — сделано»", r.status === 503 || r.status === 404 ? "NOT_RUN" : ok3([200, 201].includes(r.status)),
        { status: r.status, err: r.body && r.body.error }, "R09");
    }
    r = await call("8", "GET", `${V2}/complaints/${s8.complaint}`, null, false, dev);
    const c = r.status === 200 ? rec(r.body, "complaint") || {} : null;
    // §5.1 — services[] у записи; публичный вид R09 отдаёт жителю те же части в joint.services (без причин передач и
    // ролей сотрудников). Принимаем обе формы, форму пишем в отчёт.
    const shape = c && Array.isArray(c.services) && c.services.length ? "services"
      : c && c.joint && Array.isArray(c.joint.services) ? "joint.services" : null;
    const parts = shape === "services" ? c.services : shape ? c.joint.services : [];
    // Без совместного исполнения (маршрута R09 нет) паспорт с двумя службами проверять не на чем — NOT_RUN.
    add("API", "8", "у жителя паспорт с двумя службами и их статусами", c && (jointSet || parts.length) ? ok3(parts.length >= 2 && parts.every((x) => x.service && x.status)) : null,
      c ? (jointSet || parts.length ? { services: parts.map((x) => `${x.service}:${x.status}`), shape } : "совместное исполнение не задано (маршрут R09 не ответил)") : st(r), "R09");
    if (staff) {
      r = await call("8", "GET", `${V2}/agencies/board?days=30`, null, true);
      const rows = r.status === 200 ? list(r.body, "rows", "services") : null;
      add("API", "8", "«Штаб ведомств»: табло служб (строки служб, без имён людей)",
        r.status === 200 ? ok3(Array.isArray(rows) && rows.length >= 5 && !/"(username|full_name|operator_name)"/.test(JSON.stringify(r.body))) : r.status === 503 || r.status === 404 ? null : false,
        r.status === 200 ? { rows: rows && rows.length } : st(r), "R17");
      r = await call("8", "GET", `${V2}/works-conflicts?district=nura`, null, true);
      const cfs = r.status === 200 ? list(r.body, "conflicts", "items") || [] : null;
      const hit = cfs ? cfs.find((x) => S.conflict && (x.id === S.conflict.id || (Array.isArray(x.works) && S.conflict.works.every((w) => x.works.includes(w))))) : null;
      S.conflictApi = hit || null;  // для интерфейса: ссылка #works-calendar/<id> и совет R12 (его собственный текст)
      add("API", "8", "«Календарь работ»: конфликт «асфальт раньше сетей — копаем дважды» и совет ru/kk",
        cfs ? ok3(!!hit && hit.kind === "dig_after_surface" && !!hit.advice_ru && !!hit.advice_kk) : r.status === 503 || r.status === 404 ? null : false,
        cfs ? { found: !!hit, n: cfs.length, kind: hit && hit.kind } : st(r), "R12");
    }
  }
  // --- сцена 9: «Картина дня» → пульс «Снег в Нуре ×N» → кризисный штаб → обновления жителям → «Хроника»
  const s9 = S && S.raw.scene9;
  if (!s9) add("API", "9", "сцена 9 «Буран»", "NOT_RUN", "нет scenes.scene9 в файле мира R02", "R02");
  else {
    let r = await call("9", "GET", `${V2}/akim/summary`);
    const pulse = r.status === 200 ? ((unwrap(r.body) || {}).pulse || {}).items || [] : [];
    const snow = pulse.find((p) => p.category === (s9.category || "snow_ice") && (p.district === s9.district || (p.districts || []).some((d) => d.district === s9.district)));
    add("API", "9", "«Картина дня»: пульс «Снег в Нуре ×N»", r.status === 200 ? ok3(!!snow) : null,
      r.status === 200 ? { pulse: pulse.slice(0, 3).map((p) => `${p.kind}:${p.category}:${p.district || "-"}:×${p.ratio}`) } : st(r), "R08 + R02");
    // «Картина дня» 2.0 (R08 раунда 15): у тревоги «Снег» — ссылка штаба R17 (crisis — активный кризис, crisis_new — шаблон).
    // Признак поставки R08 раунда 15 в сборке — его маршрут akim/board (сотрудник): 404 у модуля → поставки нет → NOT_RUN.
    const r08 = staff ? await call("9", "GET", `${V2}/akim/board`, null, true) : { status: 0 };
    const r15day = r08.status === 200;
    S.pulseCrisis = !!(snow && (snow.crisis || snow.crisis_new));
    add("API", "9", "«Картина дня»: у тревоги «Снег» ссылка «Открыть кризисный штаб» (R17)",
      !r15day ? "NOT_RUN" : ok3(S.pulseCrisis),
      !r15day ? `поставки R08 раунда 15 нет в сборке (akim/board → HTTP ${r08.status})` : { crisis: snow && (snow.crisis || snow.crisis_new) },
      "R08 + R17");
    S.r15day = r15day;
    // Штаб открывает акимат: вид сотрудника (публичная карточка жителя задач служб не показывает — так у R17).
    r = await call("9", "GET", `${V2}/incidents/${s9.incident}`, null, !!staff);
    const inc = r.status === 200 ? rec(r.body, "incident") || {} : null;
    add("API", "9", "кризисный штаб: зона «Нура», 4 службы с задачами, обновления ru/kk",
      inc ? ok3(inc.status === "active" && (inc.tasks || []).length >= 4 && (inc.updates || []).some((u) => u.text_ru && u.text_kk)) : r.status === 503 || r.status === 404 ? null : false,
      inc ? { status: inc.status, tasks: (inc.tasks || []).map((t) => t.service), updates: (inc.updates || []).length } : st(r), "R17");
    // Житель зоны: район «Нура» (зона по параметру; по устройству — двор R16 или подписка R08).
    r = await call("9", "GET", `${V2}/incidents/updates?district=${s9.district}&since=${encodeURIComponent(new Date(Date.now() - 7 * 864e5).toISOString())}`, null, false, dev);
    add("API", "9", "житель зоны получает обновления кризиса", r.status === 200 ? ok3((list(r.body, "events", "updates", "items") || []).length > 0) : r.status === 503 || r.status === 404 ? null : false,
      r.status === 200 ? { n: (list(r.body, "events", "updates", "items") || []).length } : st(r), "R17");
    const day = (n) => new Date(Date.now() - n * 864e5).toISOString().slice(0, 10);
    r = await call("9", "GET", `${V2}/heat/replay?from=${day(7)}&to=${day(0)}&step=day&district=${s9.district}`);
    const frames = r.status === 200 ? list(r.body, "frames") || [] : null;
    add("API", "9", "«Хроника города»: кадры недели с датой (и отметка «Буран»)",
      frames ? ok3(frames.length >= 7 && frames.every((f) => f.date || f.at)) : r.status === 503 || r.status === 404 ? null : false,
      frames ? { frames: frames.length, annotations: JSON.stringify(unwrap(r.body)).includes("Буран") } : st(r), "R07");
  }
}

// ------------------------------------------------------------------------------------------------ UI
// Адреса экранов — IA_ROUND15 R11 §2–§5; экрана нет в оболочке — NOT_RUN (не FAIL).
async function uiFlow(browser, base, [w, h], lang, S, staffAcc, timing) {
  const tag = `${w}-${lang}`;
  const dict = L.loadDict(ROOT, lang);
  const mobile = w < 761;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1,
    locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
  await ctx.addInitScript((lg) => { try { localStorage.setItem("birge.lang", lg); } catch (e) { /* без хранилища */ } }, lang);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message.slice(0, 200)));
  page.on("console", (m) => { if (m.type() === "error" && !NOISE.test(m.text())) errors.push(m.text().slice(0, 200)); });
  const shot = async (s) => { const f = path.join(OUT, `${tag}-${s}.jpg`); await page.screenshot({ path: f, type: "jpeg", quality: 70 }).catch(() => null); return path.basename(f); };
  const step = (s, name, ok, detail, owner, file) => add(`UI ${tag}`, s, name, ok3(ok), detail, owner, file);
  const word = (key, ru, kk) => T(dict, key, lang === "kk" ? kk : ru);
  const setMode = (mode) => L.headerClick(page, new RegExp("^" + esc(mode === "resident" ? word("common.role.resident", "Житель", "Тұрғын") : word("common.role.akimat", "Акимат", "Әкімдік")) + "$", "i"));
  await page.goto(base);
  await page.waitForFunction(() => document.readyState === "complete" && document.body.innerText.length > 50, null, { timeout: 40000 }).catch(() => null);
  await sleep(2500);
  const shell = await page.evaluate(() => {
    const B = window.BirgeShell; if (!B) return null;
    const ids = new Set();
    for (const m of ["akimat", "resident"]) { try { (B.navItems(m) || []).forEach((x) => ids.add(x)); } catch (e) { /* старая оболочка */ } }
    try { (B.moreItems() || []).forEach((x) => ids.add(typeof x === "string" ? x : x.id)); } catch (e) { /* нет «Ещё» */ }
    return { ids: [...ids], globals: ["BirgeTogether", "BirgeAgencies", "BirgeWorksCalendar", "BirgeReplay", "BirgeMeetings", "BirgeAnalyst", "BirgeNotify"].filter((g) => !!window[g]) };
  }).catch(() => null);
  step("0", "оболочка: разделы раунда 15 (IA_ROUND15)", shell ? true : null, shell, "R01");
  const open = async (hash, needGlobal) => {
    if (shell && needGlobal && !shell.globals.includes(needGlobal)) return { ok: null, why: `модуля ${needGlobal} нет на странице` };
    const t = Date.now();
    await page.evaluate((hh) => { location.hash = hh; }, hash);
    await sleep(2200);
    const info = await page.evaluate(() => {
      const root = document.querySelector("#birge-screen:not([hidden]), .birge-screen:not([hidden])");
      const text = root ? (root.innerText || "").trim() : "";
      return { mounted: !!root, chars: text.length, title: (root && (root.querySelector("h1, h2") || {}).textContent || "").trim().slice(0, 60),
        skeleton: !!(root && root.querySelector("[aria-busy=true], .bk-skeleton")), section: window.BirgeShell && window.BirgeShell.section };
    }).catch(() => ({ mounted: false }));
    return { ok: info.mounted && info.chars > 30, ms: Date.now() - t, ...info };
  };
  const quality = async (s, owner, file) => {
    const q = await uiScreen(page);
    step(s, "нет прокрутки вбок", q.scrollW <= q.innerW, { scrollW: q.scrollW, w: q.innerW }, owner, file);
    step(s, "нет ключей перевода и технических слов", q.raw.length === 0 && q.tech.length === 0, { raw: q.raw.slice(0, 5), tech: q.tech.slice(0, 5) }, owner);
    step(s, "шрифт ≥ 13 px", q.tinyN === 0, { tiny: q.tinyN, ex: q.tiny.slice(0, 4) }, owner);
    step(s, "зоны нажатия ≥ 40 px (цель 44)", q.under40.length === 0, { under40: q.under40.slice(0, 5) }, owner);
    step(s, "контраст текста ≥ 4,5:1", q.lowContrastN === 0, { n: q.lowContrastN, ex: (q.lowContrast || []).slice(0, 4) }, owner);
    if (lang === "kk") {
      const ru = await page.evaluate(() => { const r = document.querySelector("#birge-screen:not([hidden])"); return r ? r.innerText : ""; })
        // Границы слова — по буквам Юникода: \b в JS кириллицу не видит.
        .then((t) => (t.match(/(?<!\p{L})(Мой двор|Сделаем вместе|Я приду|Поддержать|Ведомства|Табло|Совместные|Передачи|Календарь работ|Кризис|Проверено жителями|Соседи|Пример)(?!\p{L})/gu) || []));
      // Слово, которое и в казахском словаре R11 такое же («Табло»), — не русское.
      const kkSame = new Set(Object.values(dict || {}).filter((v) => typeof v === "string"));
      const ruOnly = [...new Set(ru)].filter((w) => !kkSame.has(w));
      step(s, "ҚАЗ: на экране нет русских подписей раздела", ruOnly.length === 0, { ru: ruOnly.slice(0, 6) }, owner);
    }
  };
  const visibleText = async (re) => !!(await firstVisible(page.getByText(re)));
  // VISUAL_BRIEF §4 п. 8 / COMMON «ошибка сети»: запросы модуля оборваны → понятное сообщение и «Повторить»,
  // а не пустой экран; после связи «Повторить» возвращает содержимое.
  const retryRe = new RegExp("^" + esc(T(dict, ["common.action.retry", "heat.retry"], lang === "kk" ? "Қайталау" : "Повторить")), "i");
  const errorState = async (s, hash, apiRe, owner) => {
    const block = (route) => route.abort("failed");
    await page.route(apiRe, block);
    await page.evaluate(() => { location.hash = "#map"; }).catch(() => null); await sleep(600);
    await page.evaluate((hh) => { location.hash = hh; }, hash); await sleep(2500);
    const msg = await page.evaluate(() => { const r = document.querySelector("#birge-screen:not([hidden])");
      return r ? (r.innerText || "").trim().slice(0, 160) : ""; }).catch(() => "");
    const retry = await firstVisible(page.getByRole("button", { name: retryRe }));
    const f = await shot(`${s}-offline`);
    await page.unroute(apiRe, block);
    let back = null;
    if (retry) { await retry.click({ timeout: 4000 }).catch(() => null); await sleep(2500);
      back = !(await firstVisible(page.getByRole("button", { name: retryRe }))); }
    step(s, `нет связи: понятное сообщение и «Повторить», после связи данные вернулись (${hash})`,
      msg.length > 10 && !!retry && back !== false, { message: msg.slice(0, 100), retry: !!retry, recovered: back }, owner, f);
  };
  const clickBtn = async (re) => { const b = await firstVisible(page.getByRole("button", { name: re })); if (!b) return false;
    await b.click({ timeout: 4000 }).catch(() => null); await sleep(1500); return true; };

  // --- сцена 7: житель «Мой двор» → «Я приду»; акимат «Поддержать»
  const s7 = S && S.raw.scene7;
  if (s7) {
    const t7 = Date.now();
    await setMode("resident");
    let o = await open(`#yard/${s7.yard}`, "BirgeTogether");
    const f = await shot("7-yard");
    if (o.ok === null) step("7", "«Мой двор» сцены 7", null, o.why, "R16");
    else {
      step("7", `«Мой двор» открыт по адресу #yard/${s7.yard}`, o.ok, { title: o.title, chars: o.chars, section: o.section }, "R16", f);
      if (o.ok) {
        const label = S.yard && (lang === "kk" ? S.yard.label_kk : S.yard.label_ru);
        step("7", "в шапке двора — название и 3 числа (соседей · проблем · инициатив)", label ? await visibleText(new RegExp(esc(label.replace(/^(Двор|Аула):\s*/, "")), "i")) : null, { label }, "R16");
        await quality("7", "R16", f);
        const iniTitle = S.ini && S.ini.title;
        step("7", `в «Обзоре» — инициатива «${iniTitle}»`, iniTitle ? await visibleText(new RegExp(esc(iniTitle), "i")) : null, null, "R16");
        await errorState("7", `#yard/${s7.yard}`, /\/api\/civic\/v2\/together\//, "R16");
      }
    }
    o = await open(`#together/${s7.initiative}`, "BirgeTogether");
    if (o.ok !== null) {
      const goRe = new RegExp("^(" + [word("together.join", "Я приду", "Мен барамын"), "Я приду", "Мен барамын"].map(esc).join("|") + ")", "i");
      const before = await page.evaluate(() => (document.querySelector("#birge-screen:not([hidden])") || document.body).innerText);
      const pressed = await clickBtn(goRe);
      const after = await page.evaluate(() => (document.querySelector("#birge-screen:not([hidden])") || document.body).innerText);
      const f2 = await shot("7-join");
      // Счётчик R16: «14 соседей придут» → «15 соседей придут» (kk «15 көрші келеді»). Ищем число рядом со словом
      // «сосед/көрші», а не любое «15» (сегодня 15 окт — дата на карточке тоже «15»).
      const cnt = (txt) => { const m = /(?<!\d)(\d{1,4})(?!\d)\s*(?:сосед\p{L}*\s+прид|көрші\s+(?:келеді|барады))/iu.exec(txt || ""); return m ? Number(m[1]) : null; };
      const n0 = cnt(before), n1 = cnt(after);
      // API-часть уже нажимала «Я приду» (14 → 15 по миру), поэтому в интерфейсе — «+1 к тому, что на карточке».
      step("7", `карточка инициативы → «Я приду» → счётчик +1 (по миру ${s7.joined_before} → ${s7.joined_after})`,
        pressed ? n0 !== null && n1 === n0 + 1 : false, { pressed, before: n0, after: n1 }, "R16", f2);
    }
    (timing["7"] = timing["7"] || []).push(Date.now() - t7);
  }

  // --- сцена 8 (житель): «Я тоже» на жалобе сцены → «Мои обращения»: «2 службы: Водоканал — сделано · Дорожная служба —
  // в работе» (IDEA §3, R09 joint.resident). Совместное исполнение задал сотрудник в API-части (S.jointSet).
  const s8r = S && S.raw.scene8;
  if (s8r && !S.jointSet) step("8", "житель: «Мои обращения» — две службы и статус каждой", null, "совместное исполнение не задано (маршрута R09 раунда 15 нет в сборке)", "R09");
  else if (s8r) {
    await setMode("resident");
    const dev = await page.evaluate(() => { try { let d = localStorage.getItem("birge.device");
      if (!d || !/^[A-Za-z0-9_-]{16,80}$/.test(d)) { d = "d-r10ui-" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10); localStorage.setItem("birge.device", d); }
      return d; } catch (e) { return null; } }).catch(() => null);
    const me = dev ? await ctx.request.post(base + `api/civic/v2/complaints/${s8r.complaint}/metoo`, { data: { device_id: dev },
      headers: { "X-Birge-Device": dev, Origin: base.replace(/\/$/, "") } }).catch(() => null) : null;
    await page.evaluate(() => { location.hash = "#mine"; }).catch(() => null); await sleep(2800);
    const names = ["service.water", "service.road"].map((k) => T(dict, k, null)).filter(Boolean);
    const jl = await page.evaluate((nm) => {
      const vis = (e) => !!(e && e.getClientRects().length && getComputedStyle(e).visibility !== "hidden");
      const e = [...document.querySelectorAll(".bc-joint-line")].find(vis);
      if (e) return { text: e.innerText.trim().replace(/\s+/g, " ").slice(0, 160), parts: [...e.querySelectorAll("[data-status]")].map((x) => x.getAttribute("data-status")) };
      const t = document.body.innerText;
      return nm.length >= 2 && nm.every((x) => t.includes(x)) ? { text: nm.join(" · "), parts: nm.map(() => "?") } : null;
    }, names).catch(() => null);
    const f = await shot("8-mine-joint");
    step("8", "житель: «Мои обращения» — две службы и статус каждой (совместное исполнение)", jl ? jl.parts.length >= 2 && jl.parts.includes("done") : false,
      { metoo: me && me.status(), line: jl }, "R09", f);
    if (jl) await quality("8m", "R09", f);
    await page.evaluate(() => { location.hash = "#map"; }).catch(() => null); await sleep(800);
  }

  // --- сцены 8–9 ведёт акимат после входа сотрудника (DEMO_SCRIPT: вход перед шагом 5) — сессия на весь контекст.
  if (staffAcc && staffAcc.user) {
    const r = await ctx.request.post(base + "api/civic/v1/session/login", { data: { username: staffAcc.user, password: staffAcc.pass },
      headers: { Origin: base.replace(/\/$/, "") } }).catch(() => null);
    step("8", "вход сотрудника для сцен 8–9", r ? r.ok() : false, { status: r && r.status() }, "R01");
    await page.reload(); await sleep(2500);
  }

  // --- сцена 8: акимат «Ведомства» → табло → календарь работ (конфликт)
  const s8 = S && S.raw.scene8;
  if (s8) {
    const t8 = Date.now();
    await setMode("akimat");
    let o = await open("#agencies/board", "BirgeAgencies");
    const f = await shot("8-board");
    if (o.ok === null) step("8", "«Штаб ведомств» → «Табло»", null, o.why, "R17");
    else {
      step("8", "«Штаб ведомств» → «Табло» открыт", o.ok, { title: o.title, chars: o.chars }, "R17", f);
      if (o.ok) { await quality("8", "R17", f); await errorState("8", "#agencies/board", /\/api\/civic\/v2\/agencies/, "R17"); }
    }
    // IA_ROUND15: «Календарь работ» — вкладка «Ведомств» (#agencies/calendar, R17 191f81e7+); запасной адрес — свой
    // раздел R12 #works-calendar (R17 без вкладки календаря). Признак, что смонтирован календарь, — корень .wcal (R12).
    o = await open("#agencies/calendar", "BirgeWorksCalendar");
    if (o.ok !== null && !(await page.evaluate(() => !!document.querySelector("#birge-screen:not([hidden]) .wcal")).catch(() => false))) {
      o = await open("#works-calendar", "BirgeWorksCalendar");
      step("8", "«Календарь работ» — вкладка «Ведомств» (IA_ROUND15 §5.4)", false, "вкладки нет: календарь открыт своим разделом #works-calendar, из «Ведомств» и «Ещё» к нему не перейти", "R17 + R01");
    }
    const f2 = await shot("8-calendar");
    if (o.ok === null) step("8", "«Календарь работ» (вкладка «Ведомств»)", null, o.why, "R12 + R17");
    else {
      step("8", "«Календарь работ» открыт", o.ok, { title: o.title, chars: o.chars }, "R12", f2);
      if (o.ok) await quality("8c", "R12", f2);
      // Конфликт сцены (R02 scenes.scene8 → R12 works-conflicts): своя ссылка R12 #works-calendar/<id>, совет — текст R12
      // из API (не текст мира R02), улица сцены — в строке календаря.
      const cf = S.conflictApi;
      if (o.ok && cf) {
        const advice = lang === "kk" ? cf.advice_kk : cf.advice_ru;
        const street = (lang === "kk" ? s8.street_kk : s8.street_ru) || "";
        const streetCore = street.replace(/^(улица|проспект|переулок)\s+/i, "").replace(/\s+(көшесі|даңғылы)$/i, "");
        await open(`#works-calendar/${cf.id}`, "BirgeWorksCalendar");
        const f3 = await shot("8-conflict");
        const seenAdvice = advice ? await visibleText(new RegExp(esc(advice.slice(0, 30)), "i")) : false;
        const seenStreet = streetCore ? await visibleText(new RegExp(esc(streetCore), "i")) : true;
        step("8", `конфликт сцены «копаем дважды» (${street || cf.id}) по ссылке #works-calendar/${cf.id}: улица и совет видны`,
          seenAdvice && seenStreet, { advice: advice && advice.slice(0, 50), street: streetCore, seenAdvice, seenStreet }, "R12", f3);
      } else if (o.ok) step("8", "конфликт сцены «копаем дважды» в календаре", null, "конфликта сцены нет в ответе works-conflicts (API-часть)", "R12");
    }
    (timing["8"] = timing["8"] || []).push(Date.now() - t8);
  }

  // --- сцена 9: «Картина дня» → пульс → кризисный штаб
  const s9 = S && S.raw.scene9;
  if (s9) {
    const t9 = Date.now();
    await setMode("akimat");
    await page.evaluate(() => { location.hash = "#day"; }); await sleep(2600);
    // Ключ R11 board.crisis.open («Открыть кризисный штаб» / «Жедел штабты ашу»).
    const crisisRe = new RegExp("^(" + [T(dict, ["board.crisis.open", "akim.pulse.open_crisis"], lang === "kk" ? "Жедел штабты ашу" : "Открыть кризисный штаб"),
      "Открыть кризисный штаб", "Жедел штабты ашу"].map(esc).join("|") + ")", "i");
    // Кнопку ищем по классу R08 (.akim-pulse__crisis) или по названию; подпись сверяем со словарём R11 отдельно —
    // термин «Жедел штаб» / «кризисный штаб» должен быть один во всех экранах.
    const byName = (await firstVisible(page.getByRole("button", { name: crisisRe }))) || (await firstVisible(page.getByRole("link", { name: crisisRe })));
    const byClass = await firstVisible(page.locator(".akim-pulse__crisis"));
    const btn = byName || byClass;
    const btnText = btn ? ((await btn.innerText().catch(() => "")) || "").trim() : null;
    const f = await shot("9-day");
    const why9 = !(shell && shell.globals.includes("BirgeAgencies")) ? "модуля BirgeAgencies нет на странице"
      : !S.r15day ? "поставки R08 раунда 15 («Картина дня» 2.0) нет в сборке" : null;
    step("9", "«Картина дня»: у пульса «Снег» кнопка «Открыть кризисный штаб»", why9 ? null : !!btn,
      why9 || { button: !!btn, text: btnText }, "R08 + R17", f);
    if (!why9 && btn) {
      const term = T(dict, ["board.crisis.open"], null);
      step("9", "подпись кнопки штаба — термин словаря R11 (board.crisis.open)", term ? crisisRe.test(btnText) : null,
        term ? { shown: btnText, r11: term } : "в словаре R11 нет board.crisis.open", "R08 + R11");
    }
    // Адрес штаба: #agencies/crisis/<id> (R17 191f81e7+), прежний #agencies/crisis=<id>; публичная карточка — #crisis/<id>.
    // Экран открыт — мало: штаб должен показать именно этот кризис (название из мира), иначе пробуем следующий адрес
    // (у R17 до 191f81e7 адрес #agencies/crisis/<id> открывает «Табло»).
    const incTitle = S.inc && (lang === "kk" ? S.inc.title_kk : S.inc.title_ru);
    let o = null;
    for (const hh of [`#agencies/crisis/${s9.incident}`, `#agencies/crisis=${s9.incident}`, `#crisis/${s9.incident}`]) {
      o = await open(hh, "BirgeAgencies");
      if (o.ok === null) break;
      if (o.ok && (!incTitle || await visibleText(new RegExp(esc(incTitle), "i")))) { o.addr = hh; break; }
      o = { ...o, ok: false, addr: hh };
    }
    const f2 = await shot("9-crisis");
    if (o.ok === null) step("9", "кризисный штаб", null, o.why, "R17");
    else {
      step("9", `кризис ${s9.incident}: штаб «${incTitle || s9.incident}» открыт по адресу`, o.ok, { addr: o.addr, title: o.title, chars: o.chars }, "R17", f2);
      if (o.ok && S.inc) {
        // VISUAL_BRIEF №5: чипы служб с прогрессом задач — названия служб сцены (по таблице R08) или тексты задач на экране.
        const tasks = (S.inc.tasks || []).map((t) => (lang === "kk" ? t.text_kk : t.text_ru)).filter(Boolean);
        const seen = [];
        for (const t of tasks) if (await visibleText(new RegExp(esc(t.slice(0, 28)), "i"))) seen.push(t.slice(0, 28));
        step("9", `в штабе видны задачи служб (${tasks.length} в демо-мире)`, tasks.length ? seen.length >= Math.min(3, tasks.length) : null,
          { seen: seen.length, of: tasks.length }, "R17");
      }
      if (o.ok) await quality("9", "R17", f2);
    }
    (timing["9"] = timing["9"] || []).push(Date.now() - t9);
  }
  step("*", "консоль без ошибок (кроме шума среды)", errors.length === 0, errors.slice(0, 6), "по тексту ошибки");
  await ctx.close();
}

// ------------------------------------------------------------------------------------------------ Ситуационный центр
// VISUAL_BRIEF №4 (R08): страница /civic/board/ на весь экран — 1920×1080 и 1366×768 без прокрутки, тёмная тема (.bk-dark),
// крупные живые числа (читается с 3 м), контраст ≥ 4,5:1, «Пример» на синтетике, «На весь экран» и «← В Birge».
// VISUAL_BRIEF §1 №11 (R01): режим показа ?show=1 и Ctrl+K «Сцена 7 / 8 / 9» — переход к сцене ≤ 1 с, без мигания.
// Сцены палитра берёт из GET demo/scenes (только с демо-миром). Ожидаемый раздел: 7 — «Мой двор» (или карта двора без
// R16), 8 — «Обращения» с жалобой сцены, 9 — «Ведомства» с кризисом (или «Кризис», или «Картина дня» без R17).
async function showCheck(browser, base, lang, staffAcc) {
  const dict = L.loadDict(ROOT, lang);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 }, deviceScaleFactor: 1, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
  await ctx.addInitScript((lg) => { try { localStorage.setItem("birge.lang", lg); } catch (e) { /* без хранилища */ } }, lang);
  if (staffAcc && staffAcc.user) {
    await ctx.request.post(base + "api/civic/v1/session/login", { data: { username: staffAcc.user, password: staffAcc.pass },
      headers: { Origin: base.replace(/\/$/, "") } }).catch(() => null);
  }
  const page = await ctx.newPage();
  await page.goto(base + "?show=1");
  await page.waitForFunction(() => document.readyState === "complete" && document.body.innerText.length > 50, null, { timeout: 40000 }).catch(() => null);
  await sleep(3000);
  // Сцены ведущий открывает в загруженной странице: ждём затишья сети (карта догрузила heat/meta и значки, до 15 с) — иначе
  // время перехода меряет гонку с загрузкой карты, а не сам переход (B-124: свежая страница 1,6–1,9 с, тёплая — 28 мс).
  const idle = await page.waitForLoadState("networkidle", { timeout: 15000 }).then(() => true, () => false);
  const show = await page.evaluate(() => document.documentElement.dataset.birgeShow === "1").catch(() => false);
  add(`UI show-${lang}`, "S", "режим показа ?show=1 включён (html[data-birge-show])", show ? "PASS" : "NOT_RUN", show ? null : "нет режима показа в сборке", "R01");
  const want = { 7: ["yard", "map"], 8: ["inbox"], 9: ["agencies", "crisis", "day"] };
  for (const n of [7, 8, 9]) {
    const title = T(dict, `shell.palette.scene${n}`, null);
    await page.keyboard.press("Escape").catch(() => null);
    await page.keyboard.press("Control+k").catch(() => null);
    await sleep(500);
    const input = await firstVisible(page.locator(".birge-palette__input"));
    if (!input || !title) { add(`UI show-${lang}`, String(n), `Ctrl+K «Сцена ${n}» → сцена ≤ 1 с`, "NOT_RUN", input ? "нет ключа shell.palette.scene" + n : "палитры Ctrl+K нет", "R01"); continue; }
    await input.fill(title.split("·")[0].trim()).catch(() => null);
    // Палитра дорисовывает команды, когда догрузит сцены (GET demo/scenes) — ждём до 4 с, а не один взгляд.
    let offered = false;
    for (let i = 0; i < 20 && !offered; i++) {
      await sleep(200);
      offered = await page.evaluate((tt) => [...document.querySelectorAll(".birge-palette__item")].some((li) => (li.textContent || "").includes(tt)), title).catch(() => false);
    }
    if (!offered) { add(`UI show-${lang}`, String(n), `Ctrl+K «${title}» → сцена ≤ 1 с`, "NOT_RUN", "команды сцены нет в палитре (нет демо-мира или сцены)", "R01"); continue; }
    // Время меряет сама страница: от нажатия Enter (keydown, capture) до кадра, где раздел сцены открыт с содержимым
    // (requestAnimationFrame) — без накладных расходов опроса из теста.
    await page.evaluate((wantIds) => {
      const box = window.__r10scene = { t0: null, t1: null, section: null };
      addEventListener("keydown", (e) => { if (e.key === "Enter" && box.t0 === null) box.t0 = performance.now(); }, { capture: true, once: true });
      const tick = () => {
        const B = window.BirgeShell, r = document.querySelector("#birge-screen:not([hidden])");
        box.section = B && B.section;
        if (box.t0 !== null && B && wantIds.includes(B.section) && (B.section === "map" || (r && (r.innerText || "").trim().length > 30))) { box.t1 = performance.now(); return; }
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }, want[n]).catch(() => null);
    await page.keyboard.press("Enter").catch(() => null);
    let ms = null, sec = null;
    for (let i = 0; i < 40; i++) {
      const box = await page.evaluate(() => window.__r10scene).catch(() => null);
      sec = box && box.section;
      if (box && box.t1 !== null && box.t0 !== null) { ms = Math.round(box.t1 - box.t0); break; }
      await sleep(100);
    }
    const f = path.join(OUT, `show-${lang}-scene${n}.jpg`);
    await sleep(800);
    await page.screenshot({ path: f, type: "jpeg", quality: 70 }).catch(() => null);
    add(`UI show-${lang}`, String(n), `Ctrl+K «${title}» → раздел ${want[n][0]} ≤ 1 с`, ms === null ? "FAIL" : ms <= 1000 ? "PASS" : "FAIL",
      { ms, section: sec, network_idle_before: idle }, "R01", path.basename(f));
  }
  await ctx.close();
}

async function boardCheck(browser, base, lang, staffAcc) {
  const dict = L.loadDict(ROOT, lang);
  // Адрес страницы — /civic/board/index.html (каталожного индекса у шлюза нет); короткий /civic/board/ — если R01 добавил.
  let page_url = null, head = 0;
  for (const u of ["civic/board/", "civic/board/index.html"]) {
    head = await fetch(base + u).then((r) => r.status).catch(() => 0);
    if (head === 200) { page_url = u; break; }
  }
  if (!page_url) { add("UI board", "9", `Ситуационный центр /civic/board/ (${lang})`, "NOT_RUN", `страницы нет (HTTP ${head})`, "R08"); return; }
  for (const [w, h] of [[1920, 1080], [1366, 768]]) {
    const tag = `${w}-${lang}`;
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
    if (staffAcc && staffAcc.user) {
      // Вход сотрудника — той же сессией, что «Для сотрудников» на главной (страница сама просит войти при 401).
      await ctx.request.post(base + "api/civic/v1/session/login", { data: { username: staffAcc.user, password: staffAcc.pass },
        headers: { Origin: base.replace(/\/$/, "") } }).catch(() => null);
    }
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message.slice(0, 160)));
    await page.goto(base + `${page_url}?lang=${lang}&rotate=0`);
    await sleep(3500);
    const m = await page.evaluate(() => {
      const root = document.documentElement, body = document.body;
      const lum = (c) => { const v = (c.match(/\d+(\.\d+)?/g) || [255, 255, 255]).slice(0, 3).map(Number).map((x) => x / 255)
        .map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4)); return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
      let bg = getComputedStyle(body).backgroundColor;
      if (/rgba\(0, 0, 0, 0\)|transparent/.test(bg)) bg = getComputedStyle(root).backgroundColor;
      const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight; };
      const leaves = [...document.querySelectorAll("body *")].filter((e) => vis(e) && !e.children.length && (e.textContent || "").trim());
      // Текст в SVG (подписи районов мини-карты) масштабирует viewBox: размер на экране = font-size × масштаб CTM.
      // Текст для диктора (.bk-sr-only, 1×1 px) не видно — не считаем.
      const eff = (e) => { const fs = parseFloat(getComputedStyle(e).fontSize);
        if (e instanceof SVGElement && typeof e.getScreenCTM === "function") { const m = e.getScreenCTM(); if (m) return fs * Math.sqrt(m.a * m.a + m.b * m.b); }
        return fs; };
      // Строка лицензии карты («© OpenStreetMap») — служебная, к правилу «читается с 3 м» не относится.
      const shown = leaves.filter((e) => { const r = e.getBoundingClientRect(); return r.width > 1 && r.height > 1
        && !e.closest(".bk-sr-only, .sr-only, .visually-hidden") && !/©/.test(e.textContent || ""); });
      const sizes = shown.map((e) => Math.round(eff(e) * 10) / 10);
      const smallest = shown.map((e) => [Math.round(eff(e) * 10) / 10, (e.textContent || "").trim().slice(0, 30)]).sort((a, b) => a[0] - b[0]).slice(0, 4);
      const big = leaves.filter((e) => /^\d[\d\s.,%×]*$/.test(e.textContent.trim()) && parseFloat(getComputedStyle(e).fontSize) >= 40).length;
      return { dark: root.classList.contains("bk-dark"), bg_lum: Math.round(lum(bg) * 1000) / 1000,
        scrollH: root.scrollHeight, scrollW: root.scrollWidth, innerH: innerHeight, innerW: innerWidth,
        state: (document.getElementById("board") || {}).dataset ? document.getElementById("board").dataset.state : null,
        min_font: sizes.length ? Math.min(...sizes) : null, smallest, big_numbers: big,
        text: (body.innerText || "").slice(0, 4000) };
    }).catch(() => null);
    const f = path.join(OUT, `board-${tag}.jpg`);
    await page.screenshot({ path: f, type: "jpeg", quality: 70 }).catch(() => null);
    const q = await uiScreen(page).catch(() => null);
    const step = (name, ok, detail) => add(`UI board ${tag}`, "9", name, ok3(ok), detail, "R08", path.basename(f));
    if (!m) { step("страница открылась", false, "нет данных страницы"); await ctx.close(); continue; }
    const loginShown = /для сотрудников|қызметкерлеріне/i.test(m.text) && /Войти|Кіру/.test(m.text);
    step("открыта с данными (вход сотрудника принят)", m.state !== "loading" && !loginShown, { state: m.state, login_form: loginShown });
    step("без прокрутки на весь экран", m.scrollH <= m.innerH + 2 && m.scrollW <= m.innerW + 2, { scrollH: m.scrollH, h: m.innerH, scrollW: m.scrollW, w: m.innerW });
    step("тёмная тема только здесь (.bk-dark, тёмный фон)", m.dark && m.bg_lum < 0.2, { dark: m.dark, bg_luminance: m.bg_lum });
    step("крупные живые числа (≥ 40 px) — читается с 3 м", m.big_numbers >= 3, { big_numbers: m.big_numbers });
    step("мелкого текста нет (≥ 14 px на большом экране)", m.min_font === null || m.min_font >= 14, { min_font: m.min_font, smallest: m.smallest });
    if (q) step("контраст текста ≥ 4,5:1 на тёмном", q.lowContrastN === 0, { n: q.lowContrastN, ex: (q.lowContrast || []).slice(0, 4) });
    const sample = /Пример|Үлгі/.test(m.text);
    step("пометка «Пример» на синтетике", sample, null);
    const back = T(dict, "board.back", lang === "kk" ? "Birge-ге" : "В Birge"), full = T(dict, "board.fullscreen", lang === "kk" ? "Толық экран" : "На весь экран");
    const backRe = new RegExp(esc(back.replace(/^←\s*/, "")), "i");
    const hasFull = !!(await firstVisible(page.getByRole("button", { name: new RegExp(esc(full), "i") })));
    const hasBack = !!(await firstVisible(page.getByRole("link", { name: backRe }))) || !!(await firstVisible(page.getByRole("button", { name: backRe })));
    step("«На весь экран» и «← В Birge»", hasFull && hasBack, { full: hasFull, back: hasBack });
    step("консоль без ошибок", errors.length === 0, errors.slice(0, 4));
    await ctx.close();
  }
}

// ------------------------------------------------------------------------------------------------ запуск
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const S = loadScenes();
  add("мир", "0", "файл демо-мира R02 и scenes (сцены 7–9)", S && !S.error && S.raw.scene7 ? "PASS" : "NOT_RUN",
    S ? (S.error || { scenes: Object.keys(S.raw || {}), counts: S.counts }) : "нет data/civic/astana/demo-world/world_v1.json в сборке", "R02");
  const srv = await L.startServer(ROOT, { demo: true, staff: true, world: WORLD });
  const A = L.api(srv.base);
  const staff = srv.staff && srv.staff.user ? (await A.login(srv.staff.user, srv.staff.pass)).ok : false;
  const timing = { api: {}, ui: {} };
  try {
    marks.api = Date.now();
    await apiFlow(A, S && !S.error ? S : null, staff, timing.api);
    if (!args["api-only"]) {
      const browser = await chromium.launch();
      for (const size of SIZES) for (const lang of LANGS) await uiFlow(browser, srv.base, size, lang, S && !S.error ? S : null, srv.staff, timing.ui);
      for (const lang of LANGS) await boardCheck(browser, srv.base, lang, srv.staff);
      for (const lang of LANGS) await showCheck(browser, srv.base, lang, srv.staff);
      await browser.close();
    }
  } finally { await srv.stop(); }
  const counts = { PASS: 0, FAIL: 0, NOT_RUN: 0 };
  for (const r of results) counts[r.status]++;
  const meta = { root: ROOT, sha: L.buildSha(ROOT), world: WORLD, seeds: srv.seeds, sizes: SIZES.map((s) => s.join("x")), langs: LANGS,
    when: new Date().toISOString(), machine: L.machine(), total_ms: Date.now() - T0 };
  fs.writeFileSync(path.join(OUT, "RESULT.json"), JSON.stringify({ meta, counts, timing, results }, null, 1));
  const md = [`# R10 · сценарий v2 · сцены 7–9 · ${meta.sha}`, "", "```", JSON.stringify(meta), "```", "",
    `Итого: PASS ${counts.PASS}, FAIL ${counts.FAIL}, NOT_RUN ${counts.NOT_RUN}`, "",
    "| Слой | Сцена | Проверка | Итог | Подробно | Владелец | Кадр |", "|---|---|---|---|---|---|---|",
    ...results.map((r) => `| ${r.layer} | ${r.step} | ${r.name} | **${r.status}** | ${JSON.stringify(r.detail ?? "").slice(0, 200).replace(/\|/g, "/")} | ${r.owner || ""} | ${r.shot || ""} |`),
    "", "Время сцен (мс): API — сумма запросов сцены; UI — открытие экранов сцены на одном варианте.", "",
    "| Слой | 7 | 8 | 9 |", "|---|---:|---:|---:|",
    ...["api", "ui"].map((l) => `| ${l} | ${["7", "8", "9"].map((s) => (timing[l][s] ? timing[l][s].reduce((a, b) => a + b, 0) : "")).join(" | ")} |`)];
  fs.writeFileSync(path.join(OUT, "RESULT.md"), md.join("\n") + "\n");
  console.log("ИТОГ:", counts, "→", OUT);
  process.exit(counts.FAIL ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
