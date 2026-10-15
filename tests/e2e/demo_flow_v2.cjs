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
    if (r.status !== 200) add("API", "7", `инициатива ${s7.initiative}`, r.status === 503 ? "NOT_RUN" : "FAIL", st(r), "R16");
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
        dn ? ok3(dn.status === "done" && !!(dn.report && (dn.report.text || dn.report.joined))) : r.status === 503 ? null : false,
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
    if (staff) {
      r = await call("8", "POST", `${V2}/complaints/${s8.complaint}/services`,
        { services: [{ service: "water", role: "lead" }, { service: "road", role: "partner" }] }, true);
      add("API", "8", "сотрудник: совместное исполнение — 2 службы у обращения", r.status === 503 || r.status === 404 ? "NOT_RUN" : ok3([200, 201].includes(r.status)),
        { status: r.status, err: r.body && r.body.error }, "R09");
      r = await call("8", "POST", `${V2}/complaints/${s8.complaint}/part`, { service: "water", status: "done", note: "Трубу заменили" }, true);
      add("API", "8", "сотрудник: часть «Водоканал — сделано»", r.status === 503 || r.status === 404 ? "NOT_RUN" : ok3([200, 201].includes(r.status)),
        { status: r.status, err: r.body && r.body.error }, "R09");
    }
    r = await call("8", "GET", `${V2}/complaints/${s8.complaint}`, null, false, dev);
    const c = r.status === 200 ? rec(r.body, "complaint") || {} : null;
    const parts = c && Array.isArray(c.services) ? c.services : [];
    add("API", "8", "у жителя паспорт с двумя службами и их статусами", c ? ok3(parts.length >= 2 && parts.every((x) => x.service && x.status)) : null,
      c ? { services: parts.map((x) => `${x.service}:${x.status}`) } : st(r), "R09");
    if (staff) {
      r = await call("8", "GET", `${V2}/agencies/board?days=30`, null, true);
      const rows = r.status === 200 ? list(r.body, "rows", "services") : null;
      add("API", "8", "«Штаб ведомств»: табло служб (строки служб, без имён людей)",
        r.status === 200 ? ok3(Array.isArray(rows) && rows.length >= 5 && !/"(username|full_name|operator_name)"/.test(JSON.stringify(r.body))) : r.status === 503 || r.status === 404 ? null : false,
        r.status === 200 ? { rows: rows && rows.length } : st(r), "R17");
      r = await call("8", "GET", `${V2}/works-conflicts?district=nura`, null, true);
      const cfs = r.status === 200 ? list(r.body, "conflicts", "items") || [] : null;
      const hit = cfs ? cfs.find((x) => S.conflict && (x.id === S.conflict.id || (Array.isArray(x.works) && S.conflict.works.every((w) => x.works.includes(w))))) : null;
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
    r = await call("9", "GET", `${V2}/incidents/${s9.incident}`);
    const inc = r.status === 200 ? rec(r.body, "incident") || {} : null;
    add("API", "9", "кризисный штаб: зона «Нура», 4 службы с задачами, обновления ru/kk",
      inc ? ok3(inc.status === "active" && (inc.tasks || []).length >= 4 && (inc.updates || []).some((u) => u.text_ru && u.text_kk)) : r.status === 503 || r.status === 404 ? null : false,
      inc ? { status: inc.status, tasks: (inc.tasks || []).map((t) => t.service), updates: (inc.updates || []).length } : st(r), "R17");
    r = await call("9", "GET", `${V2}/incidents/updates?since=${encodeURIComponent(new Date(Date.now() - 7 * 864e5).toISOString())}`, null, false, dev);
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
        .then((t) => (t.match(/\b(Мой двор|Сделаем вместе|Я приду|Поддержать|Ведомства|Табло|Совместные|Передачи|Календарь работ|Кризис|Проверено жителями|Соседи|Пример)\b/g) || []));
      step(s, "ҚАЗ: на экране нет русских подписей раздела", ru.length === 0, { ru: [...new Set(ru)].slice(0, 6) }, owner);
    }
  };
  const visibleText = async (re) => !!(await firstVisible(page.getByText(re)));
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
      }
    }
    o = await open(`#together/${s7.initiative}`, "BirgeTogether");
    if (o.ok !== null) {
      const goRe = new RegExp("^(" + [word("together.join", "Я приду", "Мен келемін"), "Я приду", "Мен келемін", "Барамын"].map(esc).join("|") + ")", "i");
      const before = await page.evaluate(() => (document.querySelector("#birge-screen:not([hidden])") || document.body).innerText);
      const pressed = await clickBtn(goRe);
      const after = await page.evaluate(() => (document.querySelector("#birge-screen:not([hidden])") || document.body).innerText);
      const f2 = await shot("7-join");
      step("7", `карточка инициативы → «Я приду» → счётчик ${s7.joined_before} → ${s7.joined_after}`,
        pressed ? new RegExp(`\\b${s7.joined_after}\\b`).test(after) && !new RegExp(`\\b${s7.joined_after}\\b`).test(before.replace(/\d{4}/g, "")) : false,
        { pressed }, "R16", f2);
    }
    (timing["7"] = timing["7"] || []).push(Date.now() - t7);
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
      if (o.ok) await quality("8", "R17", f);
    }
    o = await open("#agencies/calendar", "BirgeWorksCalendar");
    const f2 = await shot("8-calendar");
    if (o.ok === null) step("8", "«Календарь работ» (вкладка «Ведомств»)", null, o.why, "R12 + R17");
    else {
      const advice = S.conflict && (lang === "kk" ? S.conflict.advice_kk : S.conflict.advice_ru);
      step("8", "«Календарь работ» открыт, виден конфликт работ и совет", o.ok && (advice ? await visibleText(new RegExp(esc(advice.slice(0, 24)), "i")) : true),
        { title: o.title, advice: advice && advice.slice(0, 40) }, "R12", f2);
      if (o.ok) await quality("8c", "R12", f2);
    }
    (timing["8"] = timing["8"] || []).push(Date.now() - t8);
  }

  // --- сцена 9: «Картина дня» → пульс → кризисный штаб
  const s9 = S && S.raw.scene9;
  if (s9) {
    const t9 = Date.now();
    await setMode("akimat");
    await page.evaluate(() => { location.hash = "#day"; }); await sleep(2600);
    const crisisRe = new RegExp("^(" + [word("akim.pulse.open_crisis", "Открыть кризисный штаб", "Дағдарыс штабын ашу"), "Открыть кризисный штаб", "Дағдарыс штабын ашу"].map(esc).join("|") + ")", "i");
    const hasBtn = !!(await firstVisible(page.getByRole("button", { name: crisisRe }))) || !!(await firstVisible(page.getByRole("link", { name: crisisRe })));
    const f = await shot("9-day");
    step("9", "«Картина дня»: у пульса «Снег» кнопка «Открыть кризисный штаб»", shell && shell.globals.includes("BirgeAgencies") ? hasBtn : null,
      shell && shell.globals.includes("BirgeAgencies") ? { button: hasBtn } : "модуля BirgeAgencies нет на странице", "R08 + R17", f);
    const o = await open(`#crisis/${s9.incident}`, "BirgeAgencies");
    const f2 = await shot("9-crisis");
    if (o.ok === null) step("9", "кризисный штаб", null, o.why, "R17");
    else {
      step("9", `кризис ${s9.incident}: открыт, зона, службы и обновления`, o.ok, { title: o.title, chars: o.chars }, "R17", f2);
      if (o.ok) await quality("9", "R17", f2);
    }
    (timing["9"] = timing["9"] || []).push(Date.now() - t9);
  }
  step("*", "консоль без ошибок (кроме шума среды)", errors.length === 0, errors.slice(0, 6), "по тексту ошибки");
  await ctx.close();
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
