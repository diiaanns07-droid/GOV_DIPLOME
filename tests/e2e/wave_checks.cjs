// R10 · раунд 14 · приёмка новых пунктов POLISH_WAVE.md и POLISH_WAVE_2.md — написана ДО поставок ролей.
//
//   node tests/e2e/wave_checks.cjs --root <папка сборки> --out <папка> [--sizes 1366x768,375x812] [--langs ru,kk]
//        [--only W2-1,W1-3]   — только эти пункты
//        [--force]            — проверять и без кода роли (проверка самой проверки: на 8e67c65 ждём FAIL без падений, не приёмка)
//        [--stand nearby=<адрес экрана>]  — экран раздела на стенде роли до сборки R01 (например, R08 demo_server.py:
//                                http://127.0.0.1:8508/civic/nearby/): шаги «меню → раздел» и «Карта» — NOT_RUN
//
// Каждый пункт сначала спрашивает сборку, есть ли он: модуль раздела загружен в странице (window.BirgeNearby и т. п. —
// контракт оболочки R01, INTEGRATION.txt §11) или код роли в web/ и ui/ (не словари R11 — тексты приходят раньше кода).
// Нет — статус ЖДЁТ с причиной: это не дефект, роль ещё не сдала. Есть — проверка критерия «готово, когда» из
// POLISH_WAVE*.md по схеме экранов R11 (research/round-14-results/R11/IA_WAVE2.md): PASS / FAIL, кадры 1366/375 × ru/kk.
// Слова интерфейса: словарь сборки, иначе — tests/e2e/fixtures/wave_words.json (словарь R11 b0614f9, ru и kk).
//
// Пункты:
//   W1-3  срочные случаи: газ → 104, дым/пожар → 112, оборванный провод → 112 — баннер и tel: до отправки (R09, R11)
//   W2-1  центральная сцена (+W1-4, W2-3): сотрудник «Сообщить жителям» (что сделали + фото «после») → «служба сообщила
//         об устранении» (не зелёный) → житель «Да, исправлено» → «проверено жителями» (зелёный); «Я тоже» видят тот же
//         вопрос; «Проблема осталась» → снова в работе, «вернули жители», история сохранена, объект снова красный
//   W2-2  паспорт решения: «Передано», «Следующий шаг», «Ответ службы до», «Устранение: ориентир / пока не определено»;
//         сотрудник — 3 поля (R09)
//   W2-4  «Рядом»: свой экран, 4 вкладки, отключения (где, когда, обход, источник, «обновлено»), «Зачем?» — 4 строки,
//         задержки, одна главная кнопка «Следить…» (R08 + R06)
//   W2-6  QR: /?report=<id> — вид «Житель», язык не меняется (R01); карточка объекта, «Я тоже», «Сообщить о другом»,
//         неизвестный id; лист для печати (R12)
//   W2-7  идеи: честная фраза, «Предложить идею», голос +1 без удвоения, отказ с причиной и «Можно доработать» (R06 + R05)
//   P-12  перегруз: меню жителя и акимата ≤ 5 (?screens=all — ровно как в POLISH_WAVE_2), «Картины дня» нет у жителя,
//         «Ещё» ≤ 4 пунктов, дополнительный слой — не больше одного (R01, R11)
// Ничего не пишет в репозиторий; база — временная (как run-city.bat). Код возврата 1 — только при FAIL.
"use strict";
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path"), os = require("os");
const L = require("./r10_lib.cjs");

const args = L.parseArgs(process.argv.slice(2));
const ROOT = path.resolve(args.root || path.join(__dirname, "../.."));
const OUT = path.resolve(args.out || path.join(os.tmpdir(), "r10-wave"));
const SIZES = String(args.sizes || "1366x768,375x812").split(",").map((s) => s.split("x").map(Number));
const LANGS = String(args.langs || "ru,kk").split(",");
const ONLY = args.only ? String(args.only).split(",") : null;
const STAND = Object.fromEntries(String(args.stand || "").split(",").filter(Boolean).map((x) => { const i = x.indexOf("="); return [x.slice(0, i), x.slice(i + 1)]; }));
const esc = L.esc;
const NURA_BBOX = "71.375,51.115,71.420,51.140";
const WORDS = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures/wave_words.json"), "utf8"));
// Реальные остановки Нуры из OSM (data/civic/astana/geo/objects.json R12). «Хан Шатыр» — с демо-жалобами (CIVIC_DEMO=1).
const STOPS = [
  { id: "osm-node-5756851369", name: "Центр материнства и детства", point: [71.40432, 51.1251454] },
  { id: "osm-node-5756882393", name: "Жилой комплекс Зелёный Квартал", point: [71.3966837, 51.1278101] },
  { id: "osm-node-2716977767", name: "Национальный кардиологический центр", point: [71.4131502, 51.1276695] },
  { id: "osm-node-13394597038", name: "Республиканский диагностический центр", point: [71.4060541, 51.1266034] },
];
const KHAN = { id: "osm-node-4109037549", name: "Хан Шатыр", point: [71.406553, 51.131155] };

const results = [];
const add = (item, scope, name, status, detail, shot) => {
  results.push({ item, scope, name, status, detail: detail ?? null, shot: shot || null });
  console.log(`${status.padEnd(7)} ${item} ${scope} ${name}` + (detail ? " — " + JSON.stringify(detail).slice(0, 240) : ""));
};
const st = (ok) => (ok === null ? "NOT_RUN" : ok ? "PASS" : "FAIL");

// ------------------------------------------------------------------------------------------------ слова
let DICTS = {};
// Текст ключа: словарь сборки → словарь R11 (fixtures/wave_words.json) → запасной текст. Плюральные формы — «many».
function W(lang, keys, fallback = null) {
  for (const k of [].concat(keys)) {
    for (const d of [DICTS[lang], WORDS[lang]]) {
      const v = d && d[k];
      if (typeof v === "string") return v;
      if (v && (v.many || v.other || v.one)) return v.many || v.other || v.one;
    }
  }
  return fallback;
}
const exact = (s) => new RegExp("^" + esc(s).replace(/\s+/g, "\\s+") + "$", "i");
const part = (s) => L.textRe(s);  // неизменная часть строки с {параметрами}

// ------------------------------------------------------------------------------------------------ есть ли пункт в сборке
// Поиск по исходникам сборки (без tests/ и research/, без словарей и ui-kit R11 — это тексты, а не поставка).
function grepBuild(dirs, re, exclude = /(^|\/)(ui-kit|i18n|vendor|tests?|research|labeling|govtech)\//) {
  const hits = [];
  const walk = (d) => {
    let list = [];
    try { list = fs.readdirSync(path.join(ROOT, d), { withFileTypes: true }); } catch { return; }
    for (const e of list) {
      if (hits.length > 5) return;
      const rel = path.join(d, e.name);
      if (exclude.test(rel + (e.isDirectory() ? "/" : ""))) continue;
      if (e.isDirectory()) walk(rel);
      else if (/\.(js|mjs|py|html)$/.test(e.name)) {
        const m = fs.readFileSync(path.join(ROOT, rel), "utf8").match(re);
        if (m) hits.push(`${rel}: ${m[0].slice(0, 40)}`);
      }
    }
  };
  for (const d of dirs) walk(d);
  return hits;
}
const R09 = ["web/civic/feedback", "ui/civic_feedback"];
const STATIC = {
  emergency: () => grepBuild(R09, /complaint\.emergency|emergency_phone|tel:(104|112)/),
  // heat.reported_fixed — старый ключ R07 («Сообщали N человек», есть в 8e67c65), не состояние волны 2.
  central: () => grepBuild([...R09, "web/civic/heat", "ui/civic_heat"], /verify\.(yes|no|cant|question)|verified_fixed|status\.verified|(?<!heat\.)reported_fixed|fix\.what_done/),
  passport: () => grepBuild([...R09, "web/civic/heat", "ui/civic_heat"], /passport\.(next|answer_due|fix_eta)|next_step|answer_due/),
  shellReport: () => grepBuild(["web/civic/shell"], /[?&]report=/, /(^|\/)(vendor|tests?)\//),
  qrR12: () => [...(fs.existsSync(path.join(ROOT, "web/civic/qr")) ? ["web/civic/qr/"] : []),
    ...grepBuild(["web/civic", "ui"], /qr\.card\.(metoo|report_other|number)/, /(^|\/)(ui-kit|i18n|vendor|tests?|shell)\//)],
  shellMenu: () => grepBuild(["web/civic/shell"], /nav\.more|\bNAV\s*=/, /(^|\/)(vendor|tests?)\//),
};
const PROBE_TEXT = {
  "W1-3": "код R09: complaint.emergency / emergency_phone / tel:104|112 в web/civic/feedback, ui/civic_feedback",
  "W2-1": "код R09/R07: verify.* / verified / reported_fixed (кроме старого heat.reported_fixed) / fix.what_done",
  "W2-2": "код R09: passport.next / answer_due / fix_eta",
  "W2-4": "модуль R08 window.BirgeNearby в странице (контракт R01 §11.2)",
  "W2-6": "оболочка R01 с ?report= или R12: web/civic/qr/, qr.card.*",
  "W2-7": "модуль R06/R05 window.BirgeIdeas в странице",
  "P-12": "оболочка R01 с меню по видам (NAV, «Ещё»)",
};

// Какие модули разделов загружены (window.<имя>) — один заход на главную.
async function runtimeProbe(browser, base) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const page = await ctx.newPage();
  try {
    await page.goto(base); await L.sleep(4000);
    return await page.evaluate(() => {
      const g = {};
      for (const k of ["BirgeNearby", "BirgeIdeas", "BirgeProjects", "BirgeComplaintList", "BirgeAsk", "BirgeShell"]) g[k] = typeof window[k] !== "undefined";
      const sh = window.BirgeShell || {};
      return { globals: g, registerScreen: typeof sh.registerScreen === "function", registerLayer: typeof sh.registerLayer === "function",
        nav: typeof sh.navItems === "function" ? { resident: sh.navItems("resident"), akimat: sh.navItems("akimat") } : null };
    });
  } catch (e) { return { error: String(e.message).slice(0, 200), globals: {} }; } finally { await ctx.close(); }
}

// ------------------------------------------------------------------------------------------------ браузер
async function openPage(browser, [w, h], lang, storage = {}) {
  const mobile = w < 761;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
  await ctx.addInitScript((s) => { try { if (!sessionStorage.getItem("r10.init")) { for (const [k, v] of Object.entries(s)) localStorage.setItem(k, v); sessionStorage.setItem("r10.init", "1"); } } catch (e) { /* пусто */ } },
    { "birge.lang": lang, ...storage });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message.slice(0, 160)));
  return { ctx, page, mobile, errors };
}
async function goto(page, url, lang, { fixLang = true } = {}) {
  await page.goto(url);
  await page.waitForFunction(() => document.readyState === "complete" && document.body.innerText.length > 50, null, { timeout: 40000 }).catch(() => null);
  await L.sleep(2500);
  if (fixLang && (await page.evaluate(() => document.documentElement.lang)) !== lang) {
    const b = await L.firstVisible(page.getByRole("button", { name: lang === "kk" ? /^ҚАЗ$/ : /^РУС$/ }));
    if (b) { await b.click().catch(() => null); await L.sleep(1000); }
  }
}
const menuRe = (lang) => exact(W(lang, ["common.nav.menu", "shell.menu"], lang === "kk" ? "Мәзір" : "Меню"));
// Кнопка в шапке или в «Меню» (телефон и экраны уже 1024).
async function header(page, lang, re, wait = 1500) {
  let ok = await L.clickText(page, re, { wait });
  if (!ok && (await L.clickText(page, menuRe(lang)))) { ok = await L.clickText(page, re, { wait }); if (!ok) await page.keyboard.press("Escape").catch(() => null); }
  return ok;
}
const modeRe = (lang, mode) => exact(mode === "akimat" ? W(lang, ["common.role.akimat", "shell.mode.akimat"], lang === "kk" ? "Әкімдік" : "Акимат") : W(lang, ["common.role.resident", "shell.mode.resident"], lang === "kk" ? "Тұрғын" : "Житель"));
const mineRe = (lang) => part(W(lang, ["common.nav.mine", "mine.title"], lang === "kk" ? "Менің өтініштерім" : "Мои обращения"));
const shotOf = (page, name) => { const f = path.join(OUT, name + ".jpg"); return page.screenshot({ path: f, type: "jpeg", quality: 70 }).then(() => path.basename(f), () => null); };
// Сколько главных кнопок видно в области (правило 4–5 IA_WAVE2: одна на экран и на открытую карточку).
const primaries = (scope) => scope.locator("button[class*=primary], a[class*=primary]").evaluateAll((els) => els.filter((e) => e.getClientRects().length && getComputedStyle(e).visibility !== "hidden")
  .map((e) => (e.innerText || e.getAttribute("aria-label") || "").trim().slice(0, 40)));

async function staffLogin(page, lang, staff) {
  if (!staff || !staff.user) return false;
  await header(page, lang, modeRe(lang, "akimat"), 1200);
  if (!(await header(page, lang, part(lang === "kk" ? "Қызметкерлерге" : "Для сотрудников"), 1800))) return false;
  const user = await L.firstVisible(page.locator("input[autocomplete=username], input[name=username]"));
  const pass = await L.firstVisible(page.locator("input[type=password]"));
  if (!user || !pass) return false;
  await user.fill(staff.user); await pass.fill(staff.pass); await pass.press("Enter");
  await L.sleep(2500);
  const ok = !!(await L.firstVisible(page.getByRole("button", { name: /^(Выйти|Шығу)$/i })));
  if (ok && !(await L.clickText(page, /^(Закрыть кабинет|Кабинетті жабу)$/i))) await page.keyboard.press("Escape").catch(() => null);
  await L.sleep(800);
  return ok;
}
// Открыть карточку места нажатием по значку (как ведущий): вернуть видимую карточку.
async function openCard(page, stop) {
  const p = await L.showPoint(page, stop.point, 17);
  if (p) await L.tap(page, p.x, p.y);
  await L.sleep(2500);
  return L.firstVisible(page.locator(".r07-card, article").filter({ hasText: new RegExp(esc(stop.name), "i") }));
}
// Мастер жалобы до шага текста: «Сообщить о проблеме» → нажать на карту у точки → место из списка.
async function wizardToText(page, lang, point) {
  await header(page, lang, modeRe(lang, "resident"), 1200);
  const start = W(lang, "complaint.start.button", lang === "kk" ? "Мәселе туралы хабарлау" : "Сообщить о проблеме");
  if (!(await L.clickText(page, part(start), { wait: 1500 }))) return { ok: false, why: "нет кнопки «" + start + "»" };
  const form = await L.firstVisible(page.getByRole("dialog").filter({ hasText: part(W(lang, "complaint.step2.title", lang === "kk" ? "Мәселе қай жерде?" : "Где проблема?")) }));
  if (!form) return { ok: false, why: "форма «Где проблема?» не открылась" };
  const pt = await L.showPoint(page, point, 17);
  if (pt) { const at = pt.onCanvas || !pt.near ? pt : pt.near; await L.tap(page, at.x, at.y); }
  await L.sleep(3000);
  const approx = part(W(lang, "complaint.step2.approximate", lang === "kk" ? "Шамамен орны" : "Примерное место"));
  const choice = (await L.firstVisible(form.getByRole("button", { name: approx }))) || (await L.firstVisible(form.getByRole("button").filter({ hasNotText: /назад|артқа|закрыть|жабу/i })));
  if (!choice) return { ok: false, why: "после нажатия на карту нет вариантов места" };
  await choice.click().catch(() => null); await L.sleep(1500);
  const dlg = (await L.firstVisible(page.getByRole("dialog"))) || page;
  const box = await L.firstVisible(dlg.getByRole("textbox"));
  return box ? { ok: true, dlg, box } : { ok: false, why: "нет поля текста" };
}

// ------------------------------------------------------------------------------------------------ API-помощники
const devId = (p) => `r10${p}${Math.random().toString(36).slice(2, 14)}${Date.now().toString(36)}`.slice(0, 40);
// Состояние цели на тепловой карте: reported (служба сообщила), verified (проверено жителями), fixed (как в 8e67c65), open.
function heatState(it) {
  if (!it) return null;
  const vals = [it.state, it.heat_state, it.fixed_state, it.status, it.level].map((x) => String(x ?? ""));
  if (vals.some((v) => /reported/.test(v))) return "reported";
  if (vals.some((v) => /verified/.test(v))) return "verified";
  if (it.fixed_until || it.level === "fixed") return "fixed";
  return Number(it.level) >= 1 ? "open" : "none";
}
async function heatItem(A, id) {
  const h = await A.call("GET", `/api/civic/v2/heat?bbox=${NURA_BBOX}&days=30&zoom=16`);
  const it = ((A.data(h) || {}).items || []).find((i) => i.target && i.target.id === id);
  return it ? { level: it.level, weight: it.weight, count: it.count, fixed_until: it.fixed_until, state: it.state || it.heat_state || it.fixed_state || null,
    reopened: it.reopened || null, derived: heatState(it) } : null;
}
async function fileComplaint(A, stop, device, text) {
  const body = { text, lang: "ru", category: "transport", category_source: "resident", point: stop.point,
    target: { kind: "object", id: stop.id, label_ru: `Остановка «${stop.name}»` }, device_id: device, demo: true };
  const r = await A.call("POST", "/api/civic/v2/complaints", body, false, device);
  return (A.data(r) || {}).complaint || A.data(r) || null;
}
async function complaintById(A, id) {
  const l = await A.call("GET", `/api/civic/v2/complaints?bbox=${NURA_BBOX}`, null, true);
  return ((A.data(l) || {}).items || []).find((x) => x.id === id) || null;
}
const historyOf = (rec) => ((rec && rec.status_history) || []).map((h) => h.status || h.to || h.event || h);
// «Исправлено» сотрудником через API: волна 2 может требовать строку «что сделали» и другое имя статуса.
async function staffFixApi(A, id) {
  const tries = [{ status: "fixed", what_done: "Заменили крышу павильона" }, { status: "reported_fixed", what_done: "Заменили крышу павильона" }, { status: "fixed" }];
  for (const b of tries) { const r = await A.call("POST", `/api/civic/v2/complaints/${id}/status`, b, true); if ([200, 201].includes(r.status)) return { ok: true, body: b }; }
  return { ok: false };
}

// ------------------------------------------------------------------------------------------------ W1-3 срочные случаи
async function checkEmergency(ctx) {
  const { browser, base, variants } = ctx;
  const cases = [
    { name: "газ (текст)", text: { ru: "Сильно пахнет газом в подъезде", kk: "Подъездде газ иісі қатты шығып тұр" }, phone: "104" },
    { name: "пожар (текст)", text: { ru: "Во дворе что-то горит, идёт дым", kk: "Аулада бірдеңе жанып жатыр, түтін шығып тұр" }, phone: "112" },
    { name: "оборванный провод (уточнение)", text: { ru: "Фонарь не горит, провод висит до земли", kk: "Шам жанбайды, сым жерге дейін салбырап тұр" }, phone: "112", chip: "subtopic.wire_down" },
  ];
  for (const [size, lang] of variants) {
    const tag = `${size[0]}-${lang}`;
    for (const c of cases) {
      const P = await openPage(browser, size, lang);
      try {
        await goto(P.page, base, lang);
        const wz = await wizardToText(P.page, lang, STOPS[0].point);
        if (!wz.ok) { add("W1-3", tag, `${c.name}: мастер жалобы до шага текста`, "FAIL", wz.why); continue; }
        await wz.box.fill(c.text[lang]).catch(() => null);
        await L.sleep(3000);
        if (c.chip) {
          const chipText = W(lang, c.chip);
          const chip = chipText ? await L.clickText(wz.dlg, exact(chipText), { wait: 1200 }) : false;
          add("W1-3", tag, `${c.name}: чип уточнения «${chipText}» есть и нажимается`, st(chip), { chip: chipText });
        }
        const title = W(lang, "complaint.emergency.title");
        const banner = await L.visibleText(P.page, part(title));
        const link = await L.firstVisible(P.page.locator(`a[href^="tel:${c.phone}"]`));
        const linkPrimary = link ? await link.evaluate((e) => /primary/.test(e.className)).catch(() => null) : null;
        // UX_SPEC §10: ссылка «Позвонить N» — главная кнопка, «Отправить» — второстепенная, но доступна.
        const send = await L.firstVisible(wz.dlg.getByRole("button", { name: part(W(lang, ["complaint.step3.send", "complaint.send"], lang === "kk" ? "Жіберу" : "Отправить")) }));
        const sendEnabled = send ? await send.isEnabled().catch(() => false) : false;
        const sendPrimary = send ? await send.evaluate((e) => /primary/.test(e.className)).catch(() => null) : null;
        const still = await L.visibleText(P.page, part(W(lang, "complaint.emergency.still_send")));
        const shot = await shotOf(P.page, `${tag}-W1-3-${c.phone}-${c.chip ? "chip" : c.name.split(" ")[0]}`);
        add("W1-3", tag, `${c.name}: до отправки баннер «${title}» и главная кнопка — ссылка tel:${c.phone}`, st(banner && !!link && linkPrimary === true),
          { banner, tel: !!link, linkPrimary, text: link ? (await link.innerText().catch(() => "")).trim() : null }, shot);
        add("W1-3", tag, `${c.name}: «${W(lang, "complaint.emergency.still_send")}» — «Отправить» доступна и не главная`, st(still && sendEnabled && sendPrimary === false), { still, send: !!send, sendEnabled, sendPrimary });
      } finally { await P.ctx.close(); }
    }
  }
}

// ------------------------------------------------------------------------------------------------ W2-1 центральная сцена
// Строки разделены по владельцам: запись обращения (R09: status + resolution.state reported → verified / reopened),
// цвет цели на карте (R07: heat_states из categories_v2.json), карточка сотрудника (R07 встраивает форму R09),
// счётчик «Картины дня» (R08). Если «Сообщить жителям» через интерфейс не сработало, «исправлено» ставится через API,
// чтобы шаги жителя всё равно проверялись (строка сотрудника остаётся FAIL).
const resolutionOf = (rec) => (rec && ((rec.resolution && rec.resolution.state) || rec.resolution_state)) || null;
async function checkCentral(ctx) {
  const { browser, base, variants, staff } = ctx;
  const A = L.api(base);
  const login = staff && staff.user ? await A.login(staff.user, staff.pass) : { ok: false };
  if (!login.ok) { add("W2-1", "API", "вход сотрудника для подготовки", "FAIL", login); return; }
  let vi = 0;
  for (const [size, lang] of variants) {
    const tag = `${size[0]}-${lang}`;
    const stop = STOPS[vi++ % STOPS.length];
    const D = devId("d"), E = devId("e");
    const c = await fileComplaint(A, stop, D, "На остановке сломан павильон, нет крыши");
    if (!c || !c.id) { add("W2-1", tag, "подготовка: жалоба устройства D", "FAIL", c); continue; }
    await A.call("POST", `/api/civic/v2/complaints/${c.id}/metoo`, { device_id: E }, false, E);
    await A.call("POST", `/api/civic/v2/complaints/${c.id}/status`, { status: "in_progress" }, true);
    // 1. Сотрудник (IA_WAVE2 §2.3): карточка → «Отметить исправленным» → форма в той же карточке: «Что сделали
    //    (одна строка)», «Фото «после»», «Увидят N человек», главная «Сообщить жителям».
    const S = await openPage(browser, size, lang, { "birge.mode": "akimat" });
    try {
      await goto(S.page, base, lang);
      const logged = await staffLogin(S.page, lang, staff);
      const card = await openCard(S.page, stop);
      const fix = card ? await L.clickText(card, part(W(lang, ["target.mark_fixed", "heat.mark_fixed"], lang === "kk" ? "Түзетілді деп белгілеу" : "Отметить исправленным")), { wait: 1500 }) : false;
      const scope = card || S.page;
      const whatBox = await L.firstVisible(scope.getByRole("textbox", { name: part(W(lang, "fix.what_done")) }));
      if (whatBox) await whatBox.fill("Заменили крышу павильона").catch(() => null);
      const files = scope.locator("input[type=file]");
      let photo = false;
      if (await files.count().catch(() => 0)) {
        const img = path.join(OUT, "_after.jpg");
        if (!fs.existsSync(img)) await S.page.screenshot({ path: img, type: "jpeg", quality: 60, clip: { x: 0, y: 0, width: 320, height: 240 } });
        photo = await files.first().setInputFiles(img).then(() => true, () => false);
      }
      const willSee = await L.visibleText(scope, part(W(lang, "fix.will_see")));
      const prim = await primaries(scope);
      const send = await L.clickText(scope, exact(W(lang, "fix.send")), { wait: 2500 });
      add("W2-1", tag, "сотрудник (R07 + форма R09): «Отметить исправленным» → «Что сделали», «Фото «после»», «Увидят N человек» → «Сообщить жителям»",
        st(logged && !!card && fix && !!whatBox && photo && willSee && send), { logged, card: !!card, fix, whatBox: !!whatBox, photo, willSee, send, primary: prim },
        await shotOf(S.page, `${tag}-W2-1-1-staff`));
      let rec = await complaintById(A, c.id);
      let via = "интерфейс";
      if (resolutionOf(rec) !== "reported") { const fx = await staffFixApi(A, c.id); via = fx.ok ? "API (интерфейс сотрудника не сработал)" : "не удалось"; rec = await complaintById(A, c.id); }
      add("W2-1", tag, "запись (R09): «служба сообщила об устранении» — status fixed, этап reported, ещё не «проверено»",
        st(!!rec && rec.status === "fixed" && resolutionOf(rec) === "reported"), { via, status: rec && rec.status, resolution: resolutionOf(rec) });
      const hi = await heatItem(A, stop.id);
      const card2 = await openCard(S.page, stop);
      const word = card2 ? await L.visibleText(card2, part(W(lang, "status.reported_fixed"))) : false;
      add("W2-1", tag, `карта (R07): цель — «${W(lang, "status.reported_fixed")}» (светло-зелёный с пунктиром), не зелёный`,
        st(!!hi && hi.derived === "reported" && word), { heat: hi, card_text: word }, await shotOf(S.page, `${tag}-W2-1-2-reported`));
    } finally { await S.ctx.close(); }
    // 2. «Я тоже» (E) — тот же вопрос, что у автора (POLISH_WAVE_2 п. 1, IA §2.1, §2.4): до ответа автора.
    const M = await openPage(browser, size, lang, { "birge.mode": "resident", "birge.device": E });
    try {
      await goto(M.page, base, lang);
      const opened = await header(M.page, lang, mineRe(lang), 1800);
      const wait = await L.visibleText(M.page, part(W(lang, "verify.wait_title")));
      const yes = await L.firstVisible(M.page.getByRole("button", { name: exact(W(lang, "verify.yes")) }));
      add("W2-1", tag, `«Я тоже» (R09, другое устройство): в «Моих обращениях» блок «${W(lang, "verify.wait_title")}» и «${W(lang, "verify.yes")}»`, st(opened && wait && !!yes),
        { opened, wait, yes: !!yes }, await shotOf(M.page, `${tag}-W2-1-3-metoo`));
    } finally { await M.ctx.close(); }
    // 3. Автор (D): «Ждут вашей проверки» → «Да, исправлено» (главная) / «Проблема осталась» / «Не могу проверить» → «Да».
    const R = await openPage(browser, size, lang, { "birge.mode": "resident", "birge.device": D });
    try {
      await goto(R.page, base, lang);
      const opened = await header(R.page, lang, mineRe(lang), 1800);
      const btn = {};
      for (const k of ["yes", "no", "cant"]) btn[k] = await L.firstVisible(R.page.getByRole("button", { name: exact(W(lang, "verify." + k)) }));
      const yesPrimary = btn.yes ? await btn.yes.evaluate((e) => /primary/.test(e.className)).catch(() => null) : null;
      const prim = await primaries(R.page);
      add("W2-1", tag, `автор (R09): «${W(lang, "verify.question")}» — «${W(lang, "verify.yes")}» (одна главная) / «${W(lang, "verify.no")}» / «${W(lang, "verify.cant")}»`,
        st(opened && !!btn.yes && !!btn.no && !!btn.cant && yesPrimary === true && prim.length === 1), { opened, yes: !!btn.yes, no: !!btn.no, cant: !!btn.cant, yesPrimary, primary: prim },
        await shotOf(R.page, `${tag}-W2-1-4-verify`));
      if (btn.yes) { await btn.yes.click().catch(() => null); await L.sleep(2500); }
      const thanks = await L.visibleText(R.page, part(W(lang, "verify.thanks")));
      const rec = await complaintById(A, c.id);
      add("W2-1", tag, `«${W(lang, "verify.yes")}» (R09) → «${W(lang, "verify.thanks")}», запись — «проверено жителями»`, st(!!btn.yes && thanks && resolutionOf(rec) === "verified"),
        { thanks, status: rec && rec.status, resolution: resolutionOf(rec), history: historyOf(rec).slice(-4) }, await shotOf(R.page, `${tag}-W2-1-5-verified`));
    } finally { await R.ctx.close(); }
    // 4. Карта и акимат: зелёный «проверено жителями» (R07) и счётчик в «Картине дня» (R08).
    const hi = await heatItem(A, stop.id);
    const K = await openPage(browser, size, lang, { "birge.mode": "akimat" });
    try {
      await goto(K.page, base, lang);
      const card = await openCard(K.page, stop);
      const verified = card ? await L.visibleText(card, part(W(lang, "status.verified"))) : false;
      add("W2-1", tag, `карта (R07): цель зелёная — «${W(lang, "status.verified")}»`, st(!!hi && hi.derived === "verified" && verified), { heat: hi, card: !!card, verified },
        await shotOf(K.page, `${tag}-W2-1-6-akimat`));
      await K.page.keyboard.press("Escape").catch(() => null);
      const day = await header(K.page, lang, exact(W(lang, ["common.nav.day", "shell.section.day", "akim.title"], lang === "kk" ? "Күн қорытындысы" : "Картина дня")), 2500);
      const counter = await L.visibleText(K.page, /подтвердил|проверено жител|проверили жител|тексерді|растады/i);
      add("W2-1", tag, "«Картина дня» (R08): сколько исправлений проверили жители", st(day && counter), { day, counter }, await shotOf(K.page, `${tag}-W2-1-7-day`));
    } finally { await K.ctx.close(); }
  }
  // 5. «Проблема осталась» → та же карточка снова в работе («вернули жители»), история сохранена, объект снова красный.
  for (const lang of [...new Set(variants.map(([, l]) => l))]) {
    const stop = STOPS[lang === "ru" ? 3 : 2];
    const D = devId("r");
    const c = await fileComplaint(A, stop, D, "Павильон остановки сломан, крыши нет");
    if (!c || !c.id) { add("W2-1", `1366-${lang}`, "подготовка «Проблема осталась»", "FAIL", c); continue; }
    await A.call("POST", `/api/civic/v2/complaints/${c.id}/status`, { status: "in_progress" }, true);
    const fx = await staffFixApi(A, c.id);
    const R = await openPage(browser, [1366, 768], lang, { "birge.mode": "resident", "birge.device": D });
    try {
      await goto(R.page, base, lang);
      await header(R.page, lang, mineRe(lang), 1800);
      const no = await L.firstVisible(R.page.getByRole("button", { name: exact(W(lang, "verify.no")) }));
      if (no) { await no.click().catch(() => null); await L.sleep(2500); }
      const toast = await L.visibleText(R.page, part(W(lang, "verify.reopened_toast")));
      const rec = await complaintById(A, c.id);
      const hist = historyOf(rec);
      add("W2-1", `1366-${lang}`, `«${W(lang, "verify.no")}» (R09) → «${W(lang, "verify.reopened_toast")}»: та же запись снова «в работе», этап reopened, история сохранена`,
        st(fx.ok && !!no && toast && !!rec && rec.status === "in_progress" && resolutionOf(rec) === "reopened" && hist.length >= 3),
        { staff_fix: fx, button: !!no, toast, status: rec && rec.status, resolution: resolutionOf(rec), history: hist }, await shotOf(R.page, `1366-${lang}-W2-1-8-reopened`));
    } finally { await R.ctx.close(); }
    const hi = await heatItem(A, stop.id);
    const K = await openPage(browser, [1366, 768], lang, { "birge.mode": "akimat" });
    try {
      await goto(K.page, base, lang);
      const card = await openCard(K.page, stop);
      const mark = card ? await L.visibleText(card, part(W(lang, "heat.reopened_mark"))) : false;
      add("W2-1", `1366-${lang}`, `карта (R07): цель снова красная, в карточке «${W(lang, "heat.reopened_mark")}»`, st(!!hi && hi.derived === "open" && mark), { heat: hi, card: !!card, mark },
        await shotOf(K.page, `1366-${lang}-W2-1-9-reopened-card`));
    } finally { await K.ctx.close(); }
  }
}

// ------------------------------------------------------------------------------------------------ W2-2 паспорт решения
async function checkPassport(ctx) {
  const { browser, base, variants, staff } = ctx;
  const A = L.api(base);
  for (const [size, lang] of variants) {
    const tag = `${size[0]}-${lang}`;
    const D = devId("p");
    const c = await fileComplaint(A, STOPS[1], D, "Остановка: сломан павильон");
    const R = await openPage(browser, size, lang, { "birge.mode": "resident", "birge.device": D });
    try {
      await goto(R.page, base, lang);
      const opened = await header(R.page, lang, mineRe(lang), 1800);
      // IA §2.1: на карточке — «Передано: …» и «Ответ службы до …»; «Подробнее» раскрывает паспорт целиком и историю.
      const top = { service: await L.visibleText(R.page, part(W(lang, "service.assigned"))), due: await L.visibleText(R.page, part(W(lang, "passport.answer_due"))) };
      const more = await L.clickText(R.page, new RegExp("^(" + [W(lang, "qr.card.more", "Подробнее"), W(lang, "passport.title")].map(esc).join("|") + ")", "i"), { role: "button", wait: 800 })
        || !!(await R.page.locator("summary").first().click({ timeout: 2000 }).then(() => true, () => false));
      const full = { next: await L.visibleText(R.page, part(W(lang, "passport.next"))),
        fix: (await L.visibleText(R.page, part(W(lang, "passport.fix_eta")))) || (await L.visibleText(R.page, part(W(lang, "passport.fix_unknown")))),
        history: await L.visibleText(R.page, exact(W(lang, "passport.history"))) };
      add("W2-2", tag, "житель: «Передано: …», «Ответ службы до …»; «Подробнее» — «Следующий шаг», «Устранение: ориентир / пока не определено», «История»",
        st(opened && !!c && top.service && top.due && full.next && full.fix && full.history), { opened, complaint: c && c.id, top, more, full }, await shotOf(R.page, `${tag}-W2-2-passport`));
    } finally { await R.ctx.close(); }
  }
  // Сотрудник: «Изменить» → ровно 3 поля (служба, следующий шаг, ориентир устранения) — IA §2.3.
  const S = await openPage(browser, [1366, 768], "ru", { "birge.mode": "akimat" });
  try {
    await goto(S.page, base, "ru");
    const logged = await staffLogin(S.page, "ru", staff);
    const card = await openCard(S.page, STOPS[1]);
    const edit = card ? await L.clickText(card, exact(W("ru", "passport.edit")), { wait: 1200 }) : false;
    const fields = [];
    for (const k of ["passport.field.service", "passport.field.next", "passport.field.eta"]) fields.push(!!(await L.firstVisible(S.page.getByLabel(part(W("ru", k))))));
    const inputs = card ? await card.locator("input:not([type=hidden]):not([type=file]), select, textarea").evaluateAll((els) => els.filter((e) => e.getClientRects().length).length) : 0;
    add("W2-2", "1366-ru", "сотрудник: «Изменить» → 3 поля: «Кто отвечает», «Следующий шаг», «Когда устраним (ориентир)»", st(logged && edit && fields.every(Boolean) && inputs <= 4),
      { logged, card: !!card, edit, fields, inputs }, await shotOf(S.page, "1366-ru-W2-2-staff"));
  } finally { await S.ctx.close(); }
  add("W2-2", "API", "задержка: «Причина», «Временная мера», «Следующее обновление»; «Обновление просрочено» видит только акимат", "NOT_RUN",
    "дописать при поставке R09: нужна просроченная жалоба (сдвиг времени в базе, как demo_reset_check.cjs)");
}

// ------------------------------------------------------------------------------------------------ W2-4 «Рядом»
async function checkNearby(ctx) {
  const { browser, base, variants } = ctx;
  const tabClick = async (page, lang, k) => (await L.clickText(page, part(W(lang, "nearby.tab." + k)), { role: "tab", wait: 1000 })) || (await L.clickText(page, part(W(lang, "nearby.tab." + k)), { wait: 1000 }));
  for (const [size, lang] of variants) {
    const tag = `${size[0]}-${lang}`;
    const P = await openPage(browser, size, lang, { "birge.mode": "resident", "birge.device": devId("n") });
    try {
      const label = W(lang, ["common.nav.nearby", "shell.nav.nearby"]);
      let opened, hash;
      if (STAND.nearby) { await goto(P.page, STAND.nearby, lang); opened = true; hash = "#nearby (стенд)"; }
      else { await goto(P.page, base, lang); opened = await header(P.page, lang, exact(label), 2200); hash = await P.page.evaluate(() => location.hash); }
      const title = await L.visibleText(P.page, part(W(lang, "nearby.title")));
      const tabs = [];
      for (const k of ["now", "done", "planned", "outages"]) tabs.push(!!(await L.firstVisible(P.page.getByRole("tab", { name: part(W(lang, "nearby.tab." + k)) })))
        || !!(await L.firstVisible(P.page.getByRole("button", { name: part(W(lang, "nearby.tab." + k)) }))));
      // Своё окно, не шторка поверх карты (IA §0.3): экран раздела закрывает карту.
      const screen = await P.page.evaluate(() => { const c = document.querySelector(".maplibregl-canvas"); if (!c) return { map: false };
        const b = c.getBoundingClientRect(); const h = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
        return { map_on_top: h === c }; });
      const prim = await primaries(P.page);
      const mapClosed = STAND.nearby ? true : screen.map_on_top === false;  // на стенде карты нет
      add("W2-4", tag, `${STAND.nearby ? "стенд" : `меню «${label}»`} → свой экран «${W(lang, "nearby.title")}» (#nearby), 4 вкладки, карта закрыта, одна главная кнопка`,
        st(opened && /nearby/.test(hash) && title && tabs.every(Boolean) && mapClosed && prim.length === 1), { opened, hash, title, tabs, screen, primary: prim },
        await shotOf(P.page, `${tag}-W2-4-nearby`));
      // Отключения (IA §4): баннеров над вкладками ≤ 2; на вкладке «Отключения» у каждого — где, когда (подпись «Когда»
      // или само время «10:00–16:00»), источник, «обновлено …»; «Как обойти» — у перекрытия дороги (у воды обхода нет).
      const banners = await P.page.locator(".bk-banner").evaluateAll((els) => els.filter((e) => e.getClientRects().length).length).catch(() => null);
      await tabClick(P.page, lang, "outages");
      const lbl = (k) => esc(W(lang, "nearby.outage." + k).split("{")[0].trim());
      const out = await P.page.evaluate(([zone, time, detour, source, updated, closure]) => {
        const main = document.querySelector("main, [role=main], #nearby, .birge-screen") || document.body;
        const cards = [...main.querySelectorAll("article, li, .bk-card")].filter((e) => e.getClientRects().length && new RegExp(source).test(e.innerText) && !e.querySelector("article, li, .bk-card"));
        return cards.map((c) => { const t = c.innerText;
          return { zone: new RegExp(zone).test(t), time: new RegExp(time).test(t) || /\d{1,2}:\d{2}/.test(t), source: true, updated: new RegExp(updated).test(t),
            closure: new RegExp(closure, "i").test(t), detour: new RegExp(detour).test(t), text: t.replace(/\s+/g, " ").slice(0, 90) }; });
      }, [lbl("zone"), lbl("time"), lbl("detour"), lbl("source"), esc(W(lang, "nearby.updated").split("{")[0].trim()), "перекрыт|перекрыти|жабыл|road"]);
      const okOut = out.length > 0 && out.every((o) => o.zone && o.time && o.updated && (!o.closure || o.detour));
      add("W2-4", tag, "отключения: у каждого «Где», когда, «Источник», «обновлено …»; у перекрытия — «Как обойти»; баннеров ≤ 2",
        st(okOut && (banners === null || banners <= 2)), { banners, outages: out }, await shotOf(P.page, `${tag}-W2-4-outages`));
      // Задержки показываем («срок перенесён»); «Зачем?» раскрывает 4 строки.
      let delay = false, why = null;
      for (const k of ["now", "planned", "done"]) {
        await tabClick(P.page, lang, k);
        delay = delay || (await L.visibleText(P.page, part(W(lang, "works.shift_later"))));
        if (!why) {
          const w = W(lang, "nearby.why");
          const opened = (await L.clickText(P.page, exact(w), { wait: 800 })) || (await P.page.locator("summary").filter({ hasText: exact(w) }).first().click({ timeout: 2000 }).then(() => true, () => false));
          if (opened) { await L.sleep(600); why = []; for (const x of ["problem", "reason", "result", "inconvenience"]) why.push(await L.visibleText(P.page, part(W(lang, "nearby.why." + x)))); }
        }
      }
      add("W2-4", tag, `задержки видны («${W(lang, "works.shift_later")}»); «${W(lang, "nearby.why")}» — 4 строки: проблема → почему так → результат → неудобства и срок`,
        st(delay && !!why && why.every(Boolean)), { delay, why }, await shotOf(P.page, `${tag}-W2-4-why`));
      // Подписка: главная кнопка «Следить…» → «Вы следите / подписаны»; события — в «Мои обращения → Что изменилось» (R09).
      const subRe = new RegExp("^(" + [W(lang, "nearby.subscribe_yard"), "Следить за районом", "Ауданды бақылау", W(lang, "nearby.subscribe")].filter(Boolean).map(esc).join("|") + ")", "i");
      const sub = await L.clickText(P.page, subRe, { wait: 1800 });
      const subd = await L.visibleText(P.page, new RegExp([W(lang, "nearby.subscribed"), "Вы следите", "бақылап отырсыз"].map(esc).join("|"), "i"));
      add("W2-4", tag, "подписка: «Следить…» → «Вы подписаны / следите»", st(sub && subd), { sub, subd });
      if (STAND.nearby) { add("W2-4", tag, "«Карта» в меню возвращает к карте", "NOT_RUN", "стенд роли — без оболочки"); continue; }
      const toMap = await header(P.page, lang, exact(W(lang, "common.nav.map", "Карта")), 1500);
      const back = await P.page.evaluate(() => { const c = document.querySelector(".maplibregl-canvas"); if (!c) return false; const b = c.getBoundingClientRect();
        return document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2) === c; }).catch(() => false);
      add("W2-4", tag, "«Карта» в меню возвращает к карте", st(toMap && back), { toMap, back });
    } finally { await P.ctx.close(); }
  }
  add("W2-4", "R09", "события подписки «Рядом» — в «Мои обращения → Что изменилось»", "NOT_RUN", "дописать при поставке R09 (mine.changes) — R08 отдаёт /nearby/updates");
}

// ------------------------------------------------------------------------------------------------ W2-6 QR-паспорт объекта
async function checkQr(ctx) {
  const { browser, base, variants, parts } = ctx;
  // а) Оболочка R01 (§11.4): /?report=<id> — вид «Житель» на этот заход (выбор не запоминается), язык не меняется.
  if (parts.shellReport) {
    for (const [size, lang] of variants) {
      const tag = `${size[0]}-${lang}`;
      const P = await openPage(browser, size, lang, { "birge.mode": "akimat" });
      try {
        await goto(P.page, new URL(`/?report=${encodeURIComponent(KHAN.id)}`, base).href, lang, { fixLang: false });
        const s = await P.page.evaluate(() => ({ lang: document.documentElement.lang, saved_mode: localStorage.getItem("birge.mode"), saved_lang: localStorage.getItem("birge.lang") }));
        // Переключатель вида на телефоне — в «Меню» (не на экране): смотрим состояние кнопки, а не её видимость.
        const resident = await P.page.evaluate((src) => [...document.querySelectorAll("[aria-pressed=true]")].some((e) => new RegExp(src, "i").test(e.textContent.trim())), modeRe(lang, "resident").source);
        add("W2-6", tag, "/?report=<id>: язык не сменился, вид «Житель» на этот заход, сохранённый вид не перезаписан", st(s.lang === lang && resident && s.saved_mode === "akimat" && s.saved_lang === lang),
          { ...s, resident_pressed: resident }, await shotOf(P.page, `${tag}-W2-6-report-shell`));
      } finally { await P.ctx.close(); }
    }
    // Ссылка с ?lang= не меняет сохранённый выбор (IA §0.8).
    const P = await openPage(browser, [1366, 768], "kk");
    try {
      await goto(P.page, new URL("/?lang=ru", base).href, "kk", { fixLang: false });
      await goto(P.page, base, "kk", { fixLang: false });
      const s = await P.page.evaluate(() => ({ lang: document.documentElement.lang, saved: localStorage.getItem("birge.lang") }));
      add("W2-6", "1366-kk", "ссылка с ?lang=ru не меняет сохранённый ҚАЗ: следующий заход — снова ҚАЗ", st(s.lang === "kk" && s.saved === "kk"), s);
    } finally { await P.ctx.close(); }
  } else add("W2-6", "R01", "/?report=<id> в оболочке — ЖДЁТ поставки R01", "PENDING", "в web/civic/shell нет обработки ?report=");
  if (!parts.qrR12) { add("W2-6", "R12", "карточка объекта по QR и лист для печати — ЖДЁТ поставки R12", "PENDING", "в коде сборки нет: web/civic/qr/, qr.card.*"); return; }
  // б) R12 (IA §6.1): карточка открыта, одна главная «Я тоже», «Сообщить о другом», «Подробнее»; неизвестный id.
  for (const [size, lang] of variants) {
    const tag = `${size[0]}-${lang}`;
    const P = await openPage(browser, size, lang, { "birge.mode": "resident", "birge.device": devId("q") });
    try {
      await goto(P.page, new URL(`/?report=${encodeURIComponent(KHAN.id)}`, base).href, lang, { fixLang: false });
      const card = await L.firstVisible(P.page.locator("article, [role=dialog], section").filter({ hasText: new RegExp(esc(KHAN.name), "i") }));
      const prim = card ? await primaries(card) : [];
      const metoo = card ? await L.firstVisible(card.getByRole("button", { name: part(W(lang, "qr.card.metoo")) })) : null;
      const other = card ? await L.firstVisible(card.getByRole("button", { name: part(W(lang, "qr.card.report_other")) })) : null;
      const more = card ? await L.visibleText(card, exact(W(lang, "qr.card.more"))) : false;
      add("W2-6", tag, `/?report=<id> → карточка «${KHAN.name}»: одна главная «${W(lang, "qr.card.metoo")}», «${W(lang, "qr.card.report_other")}», «${W(lang, "qr.card.more")}»`,
        st(!!card && prim.length === 1 && !!metoo && !!other && more), { card: !!card, primary: prim, metoo: !!metoo, other: !!other, more }, await shotOf(P.page, `${tag}-W2-6-card`));
      if (other) {
        await other.click().catch(() => null); await L.sleep(2000);
        const box = await L.firstVisible(P.page.getByRole("dialog").getByRole("textbox"));
        add("W2-6", tag, "«Сообщить о другом» открывает мастер жалобы сразу на шаге текста с этим местом", st(!!box), { textbox: !!box });
      }
    } finally { await P.ctx.close(); }
  }
  const N = await openPage(browser, [375, 812], "ru");
  try {
    await goto(N.page, new URL("/?report=osm-node-1", base).href, "ru", { fixLang: false });
    const nf = await L.visibleText(N.page, part(W("ru", "qr.error.not_found")));
    add("W2-6", "375-ru", `неизвестный id → «${W("ru", "qr.error.not_found")}» и кнопка к карте (не пустая карта)`, st(nf), { not_found: nf }, await shotOf(N.page, "375-ru-W2-6-not-found"));
  } finally { await N.ctx.close(); }
  // в) Лист для печати (IA §6.2): QR ≥ 6 см (≥ 227 px), крупное название, «Объект № …», призыв kk и ru, домен; без чисел жалоб.
  const P = await openPage(browser, [1366, 768], "ru");
  try {
    let sheet = null;
    for (const u of [`/civic/qr/?target=${KHAN.id}`, `/civic/qr/?id=${KHAN.id}`, `/civic/qr/?targets=${KHAN.id}`, "/civic/qr/"]) {
      const r = await P.page.goto(new URL(u, base).href).catch(() => null);
      if (r && r.ok()) { sheet = u; break; }
    }
    if (!sheet) { add("W2-6", "лист", "лист для печати web/civic/qr/ открывается", "FAIL", "нет страницы /civic/qr/"); return; }
    await L.sleep(2500);
    const info = await P.page.evaluate(([callRu, callKk]) => {
      const qr = [...document.querySelectorAll("canvas, svg, img")].map((e) => e.getBoundingClientRect()).filter((b) => b.width >= 100 && Math.abs(b.width - b.height) < 6);
      const text = document.body.innerText;
      const big = [...document.querySelectorAll("body *")].filter((e) => !e.children.length && e.textContent.trim() && parseFloat(getComputedStyle(e).fontSize) >= 37).length;
      const print = [...document.styleSheets].some((s) => { try { return [...s.cssRules].some((r) => r.media && /print/.test(r.media.mediaText)); } catch (e) { return false; } });
      return { qr: qr.length, qr_px: qr[0] ? Math.round(qr[0].width) : 0, big_text: big, number: /№\s*\d+/.test(text), call_ru: text.includes(callRu.slice(0, 20)), call_kk: text.includes(callKk.slice(0, 20)),
        domain: /\b[a-z0-9-]+\.[a-z]{2,}\b/i.test(text) || /127\.0\.0\.1|localhost/.test(text), print, counts: /\d+\s*(человек|адам|жалоб|шағым)/i.test(text) };
    }, [W("ru", "qr.call"), W("kk", "qr.call")]);
    add("W2-6", "лист", "лист для печати: QR ≥ 6 см, крупное название, «Объект № …», призыв на kk и ru, домен, стиль печати; без чисел жалоб",
      st(info.qr > 0 && info.qr_px >= 227 && info.big_text > 0 && info.number && info.call_ru && info.call_kk && info.domain && info.print && !info.counts), { sheet, ...info }, await shotOf(P.page, "1366-ru-W2-6-sheet"));
    add("W2-6", "лист", "скан распечатки телефоном открывает карточку этой остановки; подмена ссылки", "NOT_RUN", "только на устройстве — Codex/владелец (камера телефона); подмена ссылки — R15");
  } finally { await P.ctx.close(); }
}

// ------------------------------------------------------------------------------------------------ W2-7 идеи
async function checkIdeas(ctx) {
  const { browser, base, variants } = ctx;
  const tabClick = async (page, lang, k) => (await L.clickText(page, part(W(lang, k)), { role: "tab", wait: 1000 })) || (await L.clickText(page, part(W(lang, k)), { wait: 1000 }));
  for (const [size, lang] of variants) {
    const tag = `${size[0]}-${lang}`;
    const P = await openPage(browser, size, lang, { "birge.mode": "resident", "birge.device": devId("i") });
    try {
      await goto(P.page, base, lang);
      const label = W(lang, ["common.nav.ideas", "shell.nav.ideas"]);
      const opened = await header(P.page, lang, exact(label), 2200);
      const honest = await L.visibleText(P.page, part(W(lang, "idea.honest")));
      const prim = await primaries(P.page);
      const tabs = [];
      for (const k of ["voting", "project", "rejected"]) tabs.push(!!(await L.firstVisible(P.page.getByRole("tab", { name: part(W(lang, "idea.status." + k)) })))
        || !!(await L.firstVisible(P.page.getByRole("button", { name: part(W(lang, "idea.status." + k)) }))));
      add("W2-7", tag, `меню «${label}» → «${W(lang, "idea.title")}»: «${W(lang, "idea.honest")}» видно сразу, одна главная «${W(lang, "idea.new")}», 3 вкладки`,
        st(opened && honest && prim.length === 1 && new RegExp(esc(W(lang, "idea.new")), "i").test(prim[0] || "") && tabs.every(Boolean)), { opened, honest, primary: prim, tabs },
        await shotOf(P.page, `${tag}-W2-7-ideas`));
      // Голос: «Поддержать» → «Вы поддержали», число +1; после перезагрузки не удваивается.
      const sup = await L.firstVisible(P.page.getByRole("button", { name: exact(W(lang, "idea.support")) }));
      const num = async () => P.page.evaluate((src) => { const m = document.body.innerText.match(new RegExp(src)); return m ? Number(m[1]) : null; }, "(\\d+)\\s*(голос|дауыс)");
      const before = await num();
      if (sup) { await sup.click().catch(() => null); await L.sleep(1800); }
      const after = await num(), done = await L.visibleText(P.page, exact(W(lang, "idea.supported")));
      await P.page.reload(); await L.sleep(2500); await header(P.page, lang, exact(label), 2000);
      const again = await num();
      add("W2-7", tag, `«${W(lang, "idea.support")}» → «${W(lang, "idea.supported")}», голосов +1; после перезагрузки не удваивается`,
        st(!!sup && done && before !== null && after === before + 1 && again === after), { support: !!sup, done, before, after, again });
      // Отклонённая — причина и «Можно доработать»; принятая — «По идее жителей · N голосов». 3D — только по кнопке.
      await tabClick(P.page, lang, "idea.status.rejected");
      const reason = await L.visibleText(P.page, part(W(lang, "idea.reason"))), improve = await L.visibleText(P.page, part(W(lang, "idea.can_improve")));
      await tabClick(P.page, lang, "idea.status.project");
      const byRes = await L.visibleText(P.page, part(W(lang, "idea.by_residents")));
      const auto3d = await P.page.evaluate(() => [...document.querySelectorAll("canvas")].filter((c) => !c.classList.contains("maplibregl-canvas") && c.getClientRects().length).length);
      add("W2-7", tag, `отказ: «${W(lang, "idea.reason")}» и «${W(lang, "idea.can_improve")}»; проект: «${W(lang, "idea.by_residents")}»; 3D само не открывается`,
        st(reason && improve && byRes && auto3d === 0), { reason, improve, byRes, auto3d }, await shotOf(P.page, `${tag}-W2-7-paths`));
    } finally { await P.ctx.close(); }
  }
  // Акимат: «Проекты и идеи» → проверка реализуемости (4 строки) → «Сделать проектом» (главная) / «Отклонить с причиной».
  const S = await openPage(browser, [1366, 768], "ru", { "birge.mode": "akimat" });
  try {
    await goto(S.page, base, "ru");
    const opened = await header(S.page, "ru", exact(W("ru", ["common.nav.projects", "shell.nav.projects"])), 2200);
    await tabClick(S.page, "ru", "idea.tab.review");
    const checks = [];
    for (const k of ["land", "networks", "access", "maintenance"]) checks.push(await L.visibleText(S.page, exact(W("ru", "idea.check." + k))));
    const make = await L.firstVisible(S.page.getByRole("button", { name: exact(W("ru", "idea.make_project")) }));
    const reject = await L.firstVisible(S.page.getByRole("button", { name: exact(W("ru", "idea.reject")) }));
    add("W2-7", "1366-ru", "акимат «Проекты и идеи»: проверка реализуемости (участок, сети, доступность, содержание), «Сделать проектом», «Отклонить с причиной»",
      st(opened && checks.every(Boolean) && !!make && !!reject), { opened, checks, make: !!make, reject: !!reject }, await shotOf(S.page, "1366-ru-W2-7-akimat"));
  } finally { await S.ctx.close(); }
  add("W2-7", "путь", "новая идея за 3 шага (место → название и описание → объект 3D) и превращение в проект в 3D", "NOT_RUN", "дописать при поставке R06/R05 (вход сотрудника, API идей)");
}

// ------------------------------------------------------------------------------------------------ P-12 защита от перегруза
async function checkClutter(ctx) {
  const { browser, base, variants, runtime } = ctx;
  const want = { resident: ["common.nav.map", "common.nav.mine", "common.nav.nearby|shell.nav.nearby", "common.nav.ideas|shell.nav.ideas", "common.nav.more|shell.nav.more"],
    akimat: ["common.nav.map", "common.nav.day", "common.nav.complaints|shell.nav.inbox", "common.nav.projects|shell.nav.projects", "common.nav.more|shell.nav.more"] };
  const navOf = async (page, lang, mobile) => {
    if (mobile) await L.clickText(page, menuRe(lang), { wait: 900 });
    const items = await page.evaluate(() => [...document.querySelectorAll(".birge-nav button, .birge-nav a")]
      .filter((e) => e.getClientRects().length && !e.hidden && getComputedStyle(e).visibility !== "hidden").map((e) => (e.innerText || e.getAttribute("aria-label") || "").trim().split("\n")[0]).filter(Boolean));
    if (mobile) await page.keyboard.press("Escape").catch(() => null);
    return [...new Set(items)];
  };
  for (const [size, lang] of variants) {
    const tag = `${size[0]}-${lang}`;
    for (const mode of ["resident", "akimat"]) {
      const expected = want[mode].map((k) => W(lang, k.split("|")));
      // По умолчанию: только разделы, чьи модули есть в сборке; не больше 5; у жителя нет «Картины дня».
      let P = await openPage(browser, size, lang, { "birge.mode": mode });
      try {
        await goto(P.page, base, lang);
        const nav = await navOf(P.page, lang, P.mobile);
        const dayInResident = mode === "resident" && nav.includes(W(lang, "common.nav.day"));
        add("P-12", `${tag} ${mode}`, "меню по умолчанию: ≤ 5 пунктов, только разделы с модулями" + (mode === "resident" ? ", без «Картины дня»" : ""),
          st(nav.length > 0 && nav.length <= 5 && !dayInResident && nav.every((x) => expected.includes(x))), { nav, expected, modules: runtime.nav && runtime.nav[mode] }, await shotOf(P.page, `${tag}-P-12-${mode}`));
      } finally { await P.ctx.close(); }
      // ?screens=all — все пункты (разбор R11/R10): ровно 5, в порядке POLISH_WAVE_2; «Ещё» ≤ 4 пунктов.
      P = await openPage(browser, size, lang, { "birge.mode": mode });
      try {
        await goto(P.page, new URL("/?screens=all", base).href, lang);
        const nav = await navOf(P.page, lang, P.mobile);
        add("P-12", `${tag} ${mode}`, `?screens=all: меню ровно «${expected.join(" · ")}»`, st(JSON.stringify(nav) === JSON.stringify(expected)), { nav, expected });
        if (P.mobile) await L.clickText(P.page, menuRe(lang), { wait: 900 });
        const more = await L.clickText(P.page, exact(expected[4]), { wait: 900 });
        // IA_WAVE2 §1: «Ещё» — маленький список-меню (role="menu"), не отдельная страница; в нём ≤ 4 пункта.
        const box = more ? await P.page.evaluate(() => {
          const vis = (e) => e.getClientRects().length && getComputedStyle(e).visibility !== "hidden";
          const menu = [...document.querySelectorAll("[role=menu]")].find(vis);
          if (menu) return { kind: "role=menu", items: [...menu.querySelectorAll("[role=menuitem], a, button")].filter(vis).map((e) => e.innerText.trim()) };
          const screen = document.querySelector("#birge-screen-title") ? document.querySelector("#birge-screen-title").closest("section, [role=dialog], main, div") : null;
          return { kind: screen ? "экран раздела #more" : "?", hash: location.hash, items: screen ? [...screen.querySelectorAll("a, button")].filter(vis).map((e) => e.innerText.trim()).filter(Boolean) : [] };
        }) : null;
        add("P-12", `${tag} ${mode}`, `«${expected[4]}»: маленький список (role=menu), не отдельная страница, 1–4 пункта`,
          st(more && !!box && box.kind === "role=menu" && box.items.length > 0 && box.items.length <= 4), { more, ...(box || {}) }, await shotOf(P.page, `${tag}-P-12-${mode}-more`));
      } finally { await P.ctx.close(); }
    }
  }
  // Дополнительный слой: по умолчанию «Только жалобы и работы», включён не больше одного (IA §0.2, R01 §11.3).
  if (!runtime.registerLayer) { add("P-12", "слои", "дополнительный слой — не больше одного сразу", "NOT_RUN", "нет BirgeShell.registerLayer"); return; }
  const P = await openPage(browser, [1366, 768], "ru", { "birge.mode": "resident" });
  try {
    await goto(P.page, base, "ru");
    const layers = await P.page.evaluate(() => [...document.querySelectorAll("[role=radio], input[type=radio]")].filter((e) => e.getClientRects().length || (e.labels && e.labels[0] && e.labels[0].getClientRects().length))
      .map((e) => ({ name: (e.getAttribute("aria-label") || (e.labels && e.labels[0] && e.labels[0].innerText) || e.innerText || "").trim(), on: e.checked || e.getAttribute("aria-checked") === "true" })));
    const none = W("ru", "shell.layers.none");
    const options = layers.filter((l) => /слой|жалоб|рядом|иде/i.test(l.name));
    add("P-12", "слои", `слои карты: по умолчанию «${none}», включено не больше одного`, options.length ? st(options.filter((l) => l.on).length <= 1 && options.some((l) => l.on && l.name.startsWith(none.slice(0, 10)))) : "NOT_RUN",
      options.length ? { options } : "переключатель слоёв не найден (слоёв ещё нет) — по умолчанию карту сторожит compare_baseline.cjs", await shotOf(P.page, "1366-ru-P-12-layers"));
  } finally { await P.ctx.close(); }
}

// ------------------------------------------------------------------------------------------------ main
const ITEMS = [
  { id: "W1-3", title: "Срочные случаи: газ 104, дым/пожар 112, провод 112", owner: "R09 (+R11)", run: checkEmergency, probe: (s) => s.emergency.length > 0,
    done: "Ни одна жалоба про газ или пожар не уходит без подсказки позвонить 104/112" },
  { id: "W2-1", title: "Центральная сцена: «Исправлено — проверьте» → житель подтвердил → зелёный «проверено»", owner: "R09, R07, R08", run: checkCentral, probe: (s) => s.central.length > 0,
    done: "исправили → житель подтвердил → объект зелёный «проверено»; при «осталось» — снова красный, история сохранена" },
  { id: "W2-2", title: "Паспорт решения", owner: "R09", run: checkPassport, probe: (s) => s.passport.length > 0, done: "Житель понимает, что происходит, без звонка" },
  { id: "W2-4", title: "«Что делают рядом»", owner: "R08 + R06", run: checkNearby, probe: (s, r) => !!r.globals.BirgeNearby || !!STAND.nearby, done: "Житель видит «Завтра 10–16 нет воды в вашем дворе» и «Зачем перекопали улицу»" },
  { id: "W2-6", title: "QR-паспорт объекта", owner: "R12 (+R01 ссылка)", run: checkQr, probe: (s) => s.shellReport.length > 0 || s.qrR12.length > 0, done: "Скан распечатки телефоном → карточка этой остановки" },
  { id: "W2-7", title: "Идеи → голосование → проект в 3D", owner: "R06 + R05", run: checkIdeas, probe: (s, r) => !!r.globals.BirgeIdeas, done: "Путь «идея → голоса → проект в 3D» или «отказ с причиной и доработка»" },
  { id: "P-12", title: "Защита от перегруза: меню ≤ 5, один доп. слой", owner: "R01, R11", run: checkClutter, probe: (s) => s.shellMenu.length > 0, done: "правила 1–2 POLISH_WAVE_2, IA_WAVE2 §0–1" },
];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const sha = L.buildSha(ROOT);
  DICTS = { ru: L.loadDict(ROOT, "ru") || {}, kk: L.loadDict(ROOT, "kk") || {} };
  const variants = SIZES.flatMap((s) => LANGS.map((l) => [s, l]));
  const todo = ITEMS.filter((i) => !ONLY || ONLY.includes(i.id));
  const stat = Object.fromEntries(Object.entries(STATIC).map(([k, f]) => [k, f()]));
  const server = await L.startServer(ROOT);
  const browser = await chromium.launch();
  const status = {};
  let runtime = { globals: {} };
  try {
    await L.api(server.base).call("GET", "/api/civic/v2/heat?days=30&zoom=12");  // подключает /similar (B-032)
    runtime = await runtimeProbe(browser, server.base);
    for (const it of todo) {
      const ok = it.probe(stat, runtime);
      status[it.id] = { ok: ok || !!args.force, forced: !ok && !!args.force };
      if (!status[it.id].ok) add(it.id, "сборка", `${it.title} — ЖДЁТ поставки (${it.owner})`, "PENDING", "в сборке нет: " + PROBE_TEXT[it.id]);
    }
    const parts = { shellReport: stat.shellReport.length > 0 || !!args.force, qrR12: stat.qrR12.length > 0 || !!args.force };
    for (const it of todo.filter((x) => status[x.id].ok)) {
      add(it.id, "сборка", `${it.title}: ${status[it.id].forced ? "кода нет, --force — проверяю механику" : "есть в сборке — проверяю"}`, "INFO", { static: stat, runtime: runtime.globals });
      try { await it.run({ browser, base: server.base, variants, staff: server.staff, runtime, parts }); }
      catch (e) { add(it.id, "!", "проверка прервалась", "FAIL", String(e.message || e).slice(0, 300)); }
    }
  } finally { await browser.close(); await server.stop(); }
  const counts = { PASS: 0, FAIL: 0, PENDING: 0, NOT_RUN: 0, INFO: 0 };
  results.forEach((r) => counts[r.status]++);
  const meta = { root: ROOT, sha, when: new Date().toISOString(), sizes: SIZES.map((s) => s.join("x")), langs: LANGS, node: process.version,
    runtime: runtime.globals, ...(args.force ? { force: "проверка механики, не приёмка" } : {}), ...(args.stand ? { stand: STAND } : {}) };
  fs.writeFileSync(path.join(OUT, "WAVE_RESULT.json"), JSON.stringify({ meta, counts, items: todo.map(({ run, probe, ...i }) => ({ ...i, delivered: status[i.id] })), results }, null, 1));
  const md = [`# R10 · новые пункты волн 1–2 · ${sha}${args.force ? " · --force (проверка механики, не приёмка)" : ""}`, "", "```", JSON.stringify(meta), "```", "",
    `Итого: PASS ${counts.PASS}, FAIL ${counts.FAIL}, ЖДЁТ ${counts.PENDING}, NOT_RUN ${counts.NOT_RUN}`, "",
    "| Пункт | Что | Владелец | Готово, когда | Состояние |", "|---|---|---|---|---|",
    ...todo.map((i) => { const rs = results.filter((r) => r.item === i.id && r.status !== "INFO");
      const s = !status[i.id] || !status[i.id].ok ? "ЖДЁТ" : rs.some((r) => r.status === "FAIL") ? "FAIL" : rs.length && rs.every((r) => r.status === "PASS") ? "PASS" : "частично";
      return `| ${i.id} | ${i.title} | ${i.owner} | ${i.done} | **${s}** |`; }),
    "", "| Пункт | Где | Проверка | Итог | Подробно | Кадр |", "|---|---|---|---|---|---|",
    ...results.map((r) => `| ${r.item} | ${r.scope} | ${r.name} | **${r.status === "PENDING" ? "ЖДЁТ" : r.status}** | ${r.detail ? JSON.stringify(r.detail).replace(/\|/g, "/").slice(0, 220) : ""} | ${r.shot || ""} |`)];
  fs.writeFileSync(path.join(OUT, "WAVE_RESULT.md"), md.join("\n") + "\n");
  console.log("ИТОГ:", counts, "→", OUT);
  process.exit(counts.FAIL ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
