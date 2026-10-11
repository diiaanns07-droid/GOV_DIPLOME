// R10 · раунд 14 · приёмка новых пунктов POLISH_WAVE.md и POLISH_WAVE_2.md — написана ДО поставок ролей.
//
//   node tests/e2e/wave_checks.cjs --root <папка сборки> --out <папка> [--sizes 1366x768,375x812] [--langs ru,kk]
//        [--only W2-1,W1-3]   — только эти пункты
//        [--force]            — проверять и без кода роли (проверка самой проверки: на 8e67c65 ждём FAIL без падений, не приёмка)
//
// Каждый пункт сначала спрашивает сборку, есть ли он вообще (код роли в web/ и ui/, маршрут API, раздел меню).
// Нет — статус ЖДЁТ с причиной («нет кода R09: complaint.emergency»): это не дефект, роль ещё не сдала.
// Есть — настоящая проверка критерия «готово, когда» из POLISH_WAVE*.md → PASS / FAIL, кадры 1366/375 × ru/kk.
// Слова интерфейса — из словарей R11; если ключа ещё нет, по русскому слову из POLISH_WAVE*.md ищется ключ
// с таким текстом (keyByText) и берётся его kk. При первой поставке роли сверить маршруты и слова (README).
//
// Пункты:
//   W1-3  срочные случаи: газ → 104, дым/пожар → 112, оборванный провод → 112 — баннер и tel: до отправки (R09, R11)
//   W2-1  центральная сцена (и W1-4, W2-3): «Исправлено — проверьте» → житель «Да, исправлено» → зелёный «проверено»;
//         «Проблема осталась» → снова в работе и красный, история сохранена; «Я тоже» видят тот же вопрос (R09, R07, R08)
//   W2-2  паспорт решения: «Отвечает», «Следующий шаг», два срока, задержка с причиной (R09)
//   W2-4  «Рядом»: 4 группы, «Зачем» из 4 строк, отключения, подписка; слой выключен по умолчанию (R06, R08)
//   W2-6  QR-паспорт объекта: /?report=<id> → карточка объекта; лист для печати web/civic/qr/; язык не меняется (R12)
//   W2-7  идеи → голосование → проект в 3D или отказ с причиной (R06, R05)
//   P-12  перегруз: меню жителя и акимата ≤ 5 пунктов; доп. слой — не больше одного сразу (R01, R11)
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
const T = L.T, esc = L.esc;
const NURA_BBOX = "71.375,51.115,71.420,51.140";
// Реальные остановки Нуры из OSM (data/civic/astana/geo/objects.json R12), которые не трогает demo_flow.cjs на шаге 2.
const STOPS = [
  { id: "osm-node-5756851369", name: "Центр материнства и детства", point: [71.40432, 51.1251454] },
  { id: "osm-node-5756882393", name: "Жилой комплекс Зелёный Квартал", point: [71.3966837, 51.1278101] },
  { id: "osm-node-2716977767", name: "Национальный кардиологический центр", point: [71.4131502, 51.1276695] },
  { id: "osm-node-13394597038", name: "Республиканский диагностический центр", point: [71.4060541, 51.1266034] },
  { id: "osm-node-4109037549", name: "Хан Шатыр", point: [71.406553, 51.131155] },
];

const results = [];
const add = (item, scope, name, status, detail, shot) => {
  results.push({ item, scope, name, status, detail: detail ?? null, shot: shot || null });
  console.log(`${status.padEnd(7)} ${item} ${scope} ${name}` + (detail ? " — " + JSON.stringify(detail).slice(0, 240) : ""));
};
const st = (ok) => (ok === null ? "NOT_RUN" : ok ? "PASS" : "FAIL");

// ------------------------------------------------------------------------------------------------ есть ли пункт в сборке
// Поиск по исходникам сборки (без tests/ и research/): какой роль дала код. Регулярки — по именам из POLISH_WAVE*.md,
// categories_v2.json (heat_states, emergency_phone) и словарей R11. Совпадение только в ui-kit/i18n (тексты R11) — не поставка.
// heat.reported_fixed — старый ключ R07 («Сообщали N человек», есть в 8e67c65), не состояние волны 2 — не считается.
function grepBuild(dirs, re, exclude = /(^|\/)(ui-kit|i18n|vendor|tests?|research)\//) {
  const hits = [];
  const walk = (d) => {
    let list = [];
    try { list = fs.readdirSync(path.join(ROOT, d), { withFileTypes: true }); } catch { return; }
    for (const e of list) {
      const rel = path.join(d, e.name);
      if (exclude.test(rel + (e.isDirectory() ? "/" : ""))) continue;
      if (e.isDirectory()) walk(rel);
      else if (/\.(js|mjs|py|html)$/.test(e.name)) {
        const text = fs.readFileSync(path.join(ROOT, rel), "utf8");
        const m = text.match(re);
        if (m) hits.push(`${rel}: ${m[0].slice(0, 40)}`);
      }
      if (hits.length > 5) return;
    }
  };
  for (const d of dirs) walk(d);
  return hits;
}
// Что ищется (для отчёта «ЖДЁТ»).
const PROBE_TEXT = {
  "W1-3": "R09: complaint.emergency / emergency_phone / tel:104|112 в web/civic/feedback, ui/civic_feedback",
  "W2-1": "R09/R07: verified_fixed / reported_fixed / проверка жителем в feedback и heat",
  "W2-2": "R09: поля паспорта (next_step, response_due, fix_eta, temporary_measure, next_update)",
  "W2-4": "R06/R08: раздел или маршрут nearby, отключения (outage)",
  "W2-6": "R12: web/civic/qr/ или обработка ?report=<id>",
  "W2-7": "R06/R05: маршрут или раздел ideas",
  "P-12": "R01: новое меню с пунктом «Ещё» (common.nav.more)",
};
const PROBES = {
  "W1-3": () => grepBuild(["web/civic/feedback", "web/civic/shell", "ui/civic_feedback"], /complaint\.emergency|emergency_phone|tel:(104|112)/),
  "W2-1": () => grepBuild(["web/civic/feedback", "web/civic/heat", "ui/civic_feedback", "ui/civic_heat"], /verified_fixed|(?<!heat\.)reported_fixed|resident_verif|verify_(yes|no)|still_there|not_fixed/),
  "W2-2": () => grepBuild(["web/civic/feedback", "ui/civic_feedback"], /passport|next_step|response_due|fix_eta|temporary_measure|next_update/),
  "W2-4": () => grepBuild(["web/civic", "ui"], /\/nearby\b|["']nearby["']|\bnearby\.[a-z_]+|\boutages?\b/),
  "W2-6": () => [...(fs.existsSync(path.join(ROOT, "web/civic/qr")) ? ["web/civic/qr/"] : []), ...grepBuild(["web/civic/shell", "web"], /[?&]report=|get\(["']report["']\)/, /(^|\/)(vendor|tests?|research|labeling|govtech)\//)],
  "W2-7": () => grepBuild(["web/civic", "ui"], /\/ideas\b|["']ideas?["']|idea_|ideas\./),
  "P-12": () => grepBuild(["web/civic/shell"], /common\.nav\.more|nav\.more|["']Ещё["']|["']Тағы["']/),
};
function delivered(id) {
  const hits = PROBES[id] ? PROBES[id]() : [];
  return { ok: hits.length > 0, hits };
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
async function goto(page, url, lang) {
  await page.goto(url);
  await page.waitForFunction(() => document.readyState === "complete" && document.body.innerText.length > 50, null, { timeout: 40000 }).catch(() => null);
  await L.sleep(2500);
  if ((await page.evaluate(() => document.documentElement.lang)) !== lang) {
    const b = await L.firstVisible(page.getByRole("button", { name: lang === "kk" ? /^ҚАЗ$/ : /^РУС$/ }));
    if (b) { await b.click().catch(() => null); await L.sleep(1000); }
  }
}
const words = (dict, lang) => ({
  menu: new RegExp("^" + esc(T(dict, ["common.nav.menu", "shell.menu"], lang === "kk" ? "Мәзір" : "Меню")) + "$", "i"),
  resident: new RegExp("^" + esc(T(dict, ["common.role.resident", "shell.mode.resident"], lang === "kk" ? "Тұрғын" : "Житель")) + "$", "i"),
  akimat: new RegExp("^" + esc(T(dict, ["common.role.akimat", "shell.mode.akimat"], lang === "kk" ? "Әкімдік" : "Акимат")) + "$", "i"),
  mine: L.textRe(T(dict, ["common.nav.mine", "mine.title"], lang === "kk" ? "Менің өтініштерім" : "Мои обращения")),
  day: new RegExp("^" + esc(T(dict, ["common.nav.day", "shell.section.day", "akim.title"], lang === "kk" ? "Күн қорытындысы" : "Картина дня")) + "$", "i"),
});
// Кнопка в шапке или в «Меню» (телефон и экраны уже 1024).
async function header(page, dict, lang, re, wait = 1500) {
  let ok = await L.clickText(page, re, { wait });
  if (!ok && (await L.clickText(page, words(dict, lang).menu))) { ok = await L.clickText(page, re, { wait }); if (!ok) await page.keyboard.press("Escape").catch(() => null); }
  return ok;
}
// Слово интерфейса: ключ словаря → по русскому тексту из POLISH_WAVE*.md ищется ключ R11 → kk этого ключа.
function word(dicts, lang, keys, ru) {
  const d = dicts[lang];
  let v = T(d, keys, null);
  // Короткое слово — только точное совпадение («Рядом» ≠ «Рядом есть объект на карте OSM:»), фраза — по началу.
  if (!v && ru) { const k = L.keyByText(dicts.ru, new RegExp("^" + esc(ru) + (ru.length < 14 ? "$" : ""), "i")); if (k) v = T(d, k, null); }
  return v || (lang === "ru" ? ru : null);
}
const shotOf = (page, name) => { const f = path.join(OUT, name + ".jpg"); return page.screenshot({ path: f, type: "jpeg", quality: 70 }).then(() => path.basename(f), () => null); };

// Вход сотрудника через «Для сотрудников» (как demo_flow шаг 5).
async function staffLogin(page, dict, lang, staff) {
  if (!staff || !staff.user) return false;
  await header(page, dict, lang, words(dict, lang).akimat, 1200);
  if (!(await header(page, dict, lang, L.textRe(lang === "kk" ? "Қызметкерлерге" : "Для сотрудников"), 1800))) return false;
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
// Мастер жалобы до шага текста: «Сообщить о проблеме» → нажать на карту у точки → первое место из списка.
async function wizardToText(page, dict, lang, point) {
  await header(page, dict, lang, words(dict, lang).resident, 1200);
  const start = T(dict, "complaint.start.button", lang === "kk" ? "Мәселе туралы хабарлау" : "Сообщить о проблеме");
  if (!(await L.clickText(page, L.textRe(start), { wait: 1500 }))) return { ok: false, why: "нет кнопки «" + start + "»" };
  const formRe = L.textRe(T(dict, "complaint.step2.title", lang === "kk" ? "Мәселе қай жерде?" : "Где проблема?"));
  const form = await L.firstVisible(page.getByRole("dialog").filter({ hasText: formRe }));
  if (!form) return { ok: false, why: "форма «Где проблема?» не открылась" };
  const pt = await L.showPoint(page, point, 17);
  if (pt) { const at = pt.onCanvas || !pt.near ? pt : pt.near; await L.tap(page, at.x, at.y); }
  await L.sleep(3000);
  const approx = L.textRe(T(dict, "complaint.step2.approximate", lang === "kk" ? "Шамамен орны" : "Примерное место"));
  const choice = (await L.firstVisible(form.getByRole("button", { name: approx }))) || (await L.firstVisible(form.getByRole("button").filter({ hasNotText: /назад|артқа|закрыть|жабу/i })));
  if (!choice) return { ok: false, why: "после нажатия на карту нет вариантов места" };
  await choice.click().catch(() => null); await L.sleep(1500);
  const dlg = (await L.firstVisible(page.getByRole("dialog"))) || page;
  const box = await L.firstVisible(dlg.getByRole("textbox"));
  return box ? { ok: true, dlg, box } : { ok: false, why: "нет поля текста" };
}

// ------------------------------------------------------------------------------------------------ W1-3 срочные случаи
async function checkEmergency(ctx) {
  const { browser, base, dicts, variants } = ctx;
  const cases = [
    { name: "газ (текст)", text: { ru: "Сильно пахнет газом в подъезде", kk: "Подъездде газ иісі қатты шығып тұр" }, phone: "104" },
    { name: "пожар (текст)", text: { ru: "Во дворе что-то горит, идёт дым", kk: "Аулада бірдеңе жанып жатыр, түтін шығып тұр" }, phone: "112" },
    { name: "оборванный провод (уточнение)", text: { ru: "Фонарь не горит, провод висит до земли", kk: "Шам жанбайды, сым жерге дейін салбырап тұр" }, phone: "112",
      chip: { keys: ["subtopic.wire_down"], ru: "Оборван провод" } },
  ];
  for (const [size, lang] of variants) {
    const dict = dicts[lang], tag = `${size[0]}-${lang}`;
    for (const c of cases) {
      const P = await openPage(browser, size, lang);
      try {
        await goto(P.page, base, lang);
        const wz = await wizardToText(P.page, dict, lang, STOPS[0].point);
        if (!wz.ok) { add("W1-3", tag, `${c.name}: мастер жалобы до шага текста`, "FAIL", wz.why); continue; }
        await wz.box.fill(c.text[lang]).catch(() => null);
        await L.sleep(3000);
        let chip = null;
        if (c.chip) {
          const chipText = word(dicts, lang, c.chip.keys, c.chip.ru);
          chip = chipText ? await L.clickText(wz.dlg, new RegExp("^" + esc(chipText) + "$", "i"), { wait: 1200 }) : false;
          add("W1-3", tag, `${c.name}: чип уточнения «${chipText}» есть и нажимается`, st(chip), { chip: chipText });
        }
        const title = T(dict, "complaint.emergency.title", lang === "kk" ? null : "Это может быть опасно");
        const banner = title ? await L.visibleText(P.page, L.textRe(title)) : false;
        const link = await L.firstVisible(P.page.locator(`a[href^="tel:${c.phone}"]`));
        const linkText = link ? (await link.innerText().catch(() => "")).trim() : null;
        // Одна главная кнопка (UX_SPEC §10): ссылка «Позвонить N» — главная, «Отправить» — второстепенная, но доступна.
        const sendRe = L.textRe(T(dict, ["complaint.step3.send", "complaint.send"], lang === "kk" ? "Жіберу" : "Отправить"));
        const send = await L.firstVisible(wz.dlg.getByRole("button", { name: sendRe }));
        const sendEnabled = send ? await send.isEnabled().catch(() => false) : false;
        const sendPrimary = send ? await send.evaluate((e) => /primary/.test(e.className)).catch(() => null) : null;
        const shot = await shotOf(P.page, `${tag}-W1-3-${c.phone}-${c.chip ? "chip" : c.name.split(" ")[0]}`);
        add("W1-3", tag, `${c.name}: до отправки баннер «${title || "?"}» и ссылка tel:${c.phone}`, st(banner && !!link), { banner, tel: !!link, linkText }, shot);
        add("W1-3", tag, `${c.name}: обращение всё равно можно отправить, «Отправить» не главная кнопка`, st(sendEnabled && sendPrimary === false), { send: !!send, sendEnabled, sendPrimary });
      } finally { await P.ctx.close(); }
    }
  }
}

// ------------------------------------------------------------------------------------------------ W2-1 центральная сцена
// Подготовка через API (быстро и одинаково): жалоба устройства D на остановку, «Я тоже» устройства E, сотрудник
// «в работу». «Отметить исправленным» — через интерфейс акимата (новое: фото «после» и строка «что сделали»).
const VERIFY = {
  yes: { keys: ["mine.verify.yes", "complaint.verify.yes", "verify.yes"], ru: "Да, исправлено" },
  no: { keys: ["mine.verify.no", "complaint.verify.no", "verify.no"], ru: "Проблема осталась" },
  cant: { keys: ["mine.verify.cant", "complaint.verify.cant", "verify.cant"], ru: "Не могу проверить" },
  reported: { keys: ["heat.state.reported_fixed", "heat.reported_fixed_state"], ru: "служба сообщила об устранении" },
  verified: { keys: ["heat.state.verified_fixed", "heat.verified_fixed"], ru: "проверено жителями" },
  reopened: { keys: ["heat.state.reopened", "heat.reopened"], ru: "проблема осталась — снова в работе" },
  whatDone: { keys: ["target.fix.what_done", "heat.fix.what_done", "complaint.fix.what_done"], ru: "Что сделали" },
  photoAfter: { keys: ["target.fix.photo_after", "heat.fix.photo_after", "complaint.photo.after"], ru: "Фото «после»" },
};
const devId = (p) => `r10${p}${Math.random().toString(36).slice(2, 14)}${Date.now().toString(36)}`.slice(0, 40);
async function heatItem(A, id) {
  const h = await A.call("GET", `/api/civic/v2/heat?bbox=${NURA_BBOX}&days=30&zoom=16`);
  const it = ((A.data(h) || {}).items || []).find((i) => i.target && i.target.id === id);
  return it ? { level: it.level, weight: it.weight, count: it.count, fixed_until: it.fixed_until, state: it.state || it.heat_state || it.fixed_state || null } : null;
}
async function fileComplaint(A, stop, device, text) {
  const body = { text, lang: "ru", category: "transport", category_source: "resident", point: stop.point,
    target: { kind: "object", id: stop.id, label_ru: `Остановка «${stop.name}»` }, device_id: device, demo: true };
  const r = await A.call("POST", "/api/civic/v2/complaints", body, false, device);
  return (A.data(r) || {}).complaint || A.data(r) || null;
}
async function checkCentral(ctx) {
  const { browser, base, dicts, variants, staff } = ctx;
  const A = L.api(base);
  const login = staff && staff.user ? await A.login(staff.user, staff.pass) : { ok: false };
  if (!login.ok) { add("W2-1", "API", "вход сотрудника для подготовки", "FAIL", login); return; }
  let vi = 0;
  for (const [size, lang] of variants) {
    const dict = dicts[lang], tag = `${size[0]}-${lang}`;
    const stop = STOPS[vi++ % 4];
    const D = devId("d"), E = devId("e");
    const c = await fileComplaint(A, stop, D, "На остановке сломан павильон, нет крыши");
    if (!c || !c.id) { add("W2-1", tag, "подготовка: жалоба устройства D", "FAIL", c); continue; }
    await A.call("POST", `/api/civic/v2/complaints/${c.id}/metoo`, { device_id: E }, false, E);
    await A.call("POST", `/api/civic/v2/complaints/${c.id}/status`, { status: "in_progress" }, true);
    // 1. Сотрудник: карточка остановки → «Отметить исправленным» → фото «после» + «что сделали» → сохранить.
    const S = await openPage(browser, size, lang, { "birge.mode": "akimat" });
    let reportedShot = null;
    try {
      await goto(S.page, base, lang);
      const logged = await staffLogin(S.page, dict, lang, staff);
      const p = await L.showPoint(S.page, stop.point, 17);
      if (p) await L.tap(S.page, p.x, p.y);
      await L.sleep(2500);
      const fix = await L.clickText(S.page, L.textRe(T(dict, ["target.mark_fixed", "heat.mark_fixed"], lang === "kk" ? "Түзетілді деп белгілеу" : "Отметить исправленным")), { wait: 1500 });
      const what = word(dicts, lang, VERIFY.whatDone.keys, VERIFY.whatDone.ru);
      const whatBox = await L.firstVisible(S.page.getByRole("textbox", { name: what ? L.textRe(what) : /./ }));
      // Поле файла обычно скрыто за кнопкой «Добавить фото» — берём само поле, видимость не важна.
      const files = S.page.locator("input[type=file]");
      const file = (await files.count().catch(() => 0)) ? files.first() : null;
      let photo = false;
      if (whatBox) await whatBox.fill("Заменили крышу павильона").catch(() => null);
      if (file) {
        const img = path.join(OUT, "_after.jpg");
        if (!fs.existsSync(img)) await S.page.screenshot({ path: img, type: "jpeg", quality: 60, clip: { x: 0, y: 0, width: 320, height: 240 } });
        photo = await file.setInputFiles(img).then(() => true, () => false);
      }
      const save = await L.clickText(S.page, /^(Сохранить|Подтвердить|Готово|Отметить исправленным|Сақтау|Растау|Дайын)$/i, { wait: 2500 });
      reportedShot = await shotOf(S.page, `${tag}-W2-1-1-reported`);
      add("W2-1", tag, "сотрудник: «Отметить исправленным» → строка «что сделали» и фото «после»", st(logged && fix && !!whatBox && photo),
        { logged, fix, whatBox: !!whatBox, photo, save }, reportedShot);
      const hi = await heatItem(A, stop.id);
      const reportedWord = word(dicts, lang, VERIFY.reported.keys, VERIFY.reported.ru);
      const reportedSeen = reportedWord ? await L.visibleText(S.page, L.textRe(reportedWord)) : false;
      add("W2-1", tag, "после «исправлено» объект — «служба сообщила об устранении» (светло-зелёный, ещё не «проверено»)",
        st(!!hi && hi.state === "reported_fixed" && reportedSeen), { heat: hi, card_text: reportedSeen, word: reportedWord });
    } finally { await S.ctx.close(); }
    // 2. Житель D: «Мои обращения» → «Да, исправлено» / «Проблема осталась» / «Не могу проверить» → «Да».
    //    Вариант 1366-ru — путь «Проблема осталась» на второй остановке (тот же экран).
    const R = await openPage(browser, size, lang, { "birge.mode": "resident", "birge.device": D });
    try {
      await goto(R.page, base, lang);
      const opened = await header(R.page, dict, lang, words(dict, lang).mine, 1800);
      const btn = {};
      for (const k of ["yes", "no", "cant"]) { const w = word(dicts, lang, VERIFY[k].keys, VERIFY[k].ru); btn[k] = w ? await L.firstVisible(R.page.getByRole("button", { name: L.textRe(w) })) : null; }
      const shot = await shotOf(R.page, `${tag}-W2-1-2-verify`);
      add("W2-1", tag, "житель: в «Моих обращениях» вопрос «Да, исправлено / Проблема осталась / Не могу проверить»", st(opened && !!btn.yes && !!btn.no && !!btn.cant),
        { opened, yes: !!btn.yes, no: !!btn.no, cant: !!btn.cant }, shot);
      if (btn.yes) { await btn.yes.click().catch(() => null); await L.sleep(2500); }
      const after = await A.call("GET", `/api/civic/v2/complaints?bbox=${NURA_BBOX}`, null, true);
      const rec = ((A.data(after) || {}).items || []).find((x) => x.id === c.id) || {};
      const hi = await heatItem(A, stop.id);
      add("W2-1", tag, "«Да, исправлено» → объект зелёный «проверено жителями», в истории есть отметка жителя", st(!!btn.yes && !!hi && hi.state === "verified_fixed"),
        { heat: hi, status: rec.status, history: (rec.status_history || []).map((h) => h.status || h.to || h).slice(-4) }, await shotOf(R.page, `${tag}-W2-1-3-verified`));
    } finally { await R.ctx.close(); }
    // 3. W2-3: «Я тоже» (устройство E) видит то же обновление и тот же вопрос.
    const M = await openPage(browser, size, lang, { "birge.mode": "resident", "birge.device": E });
    try {
      await goto(M.page, base, lang);
      await header(M.page, dict, lang, words(dict, lang).mine, 1800);
      const verified = word(dicts, lang, VERIFY.verified.keys, VERIFY.verified.ru);
      const seen = verified ? await L.visibleText(M.page, L.textRe(verified)) : false;
      add("W2-1", tag, "«Я тоже» (другое устройство): в «Моих обращениях» то же обновление — «проверено жителями»", st(seen), { word: verified }, await shotOf(M.page, `${tag}-W2-1-4-metoo`));
    } finally { await M.ctx.close(); }
    // 4. Акимат: карточка и «Картина дня» — сколько исправлений подтвердили жители (R08).
    const K = await openPage(browser, size, lang, { "birge.mode": "akimat" });
    try {
      await goto(K.page, base, lang);
      const day = await header(K.page, dict, lang, words(dict, lang).day, 2500);
      const counter = await L.visibleText(K.page, /подтвердил|проверено жител|тексерді|растады/i);
      add("W2-1", tag, "«Картина дня»: сколько исправлений подтвердили жители", st(day && counter), { day, counter }, await shotOf(K.page, `${tag}-W2-1-5-day`));
    } finally { await K.ctx.close(); }
  }
  // 5. «Проблема осталась» → та же карточка снова в работе, история сохранена, объект снова красный (API + 1366 ru).
  const D = devId("r");
  const c = await fileComplaint(A, STOPS[3], D, "Павильон остановки сломан, крыши нет");
  if (c && c.id) {
    await A.call("POST", `/api/civic/v2/complaints/${c.id}/status`, { status: "in_progress" }, true);
    await A.call("POST", `/api/civic/v2/complaints/${c.id}/status`, { status: "fixed", note: "Заменили крышу", what_done: "Заменили крышу" }, true);
    const lang = variants.some(([, l]) => l === "ru") ? "ru" : variants[0][1];
    const R = await openPage(browser, [1366, 768], lang, { "birge.mode": "resident", "birge.device": D });
    try {
      await goto(R.page, base, lang);
      await header(R.page, dicts[lang], lang, words(dicts[lang], lang).mine, 1800);
      const w = word(dicts, lang, VERIFY.no.keys, VERIFY.no.ru);
      const no = w ? await L.firstVisible(R.page.getByRole("button", { name: L.textRe(w) })) : null;
      if (no) { await no.click().catch(() => null); await L.sleep(2500); }
      const after = await A.call("GET", `/api/civic/v2/complaints?bbox=${NURA_BBOX}`, null, true);
      const rec = ((A.data(after) || {}).items || []).find((x) => x.id === c.id) || {};
      const hist = (rec.status_history || []).map((h) => h.status || h.to || h);
      const hi = await heatItem(A, STOPS[3].id);
      add("W2-1", `1366-${lang}`, "«Проблема осталась» → та же карточка снова «в работе», история сохранена, объект снова красный",
        st(!!no && rec.status === "in_progress" && hist.includes("fixed") && !!hi && hi.level >= 1 && !hi.fixed_until && hi.state !== "verified_fixed"),
        { button: !!no, status: rec.status, history: hist, heat: hi }, await shotOf(R.page, `1366-${lang}-W2-1-6-reopened`));
    } finally { await R.ctx.close(); }
  } else add("W2-1", "API", "подготовка «Проблема осталась»", "FAIL", c);
}

// ------------------------------------------------------------------------------------------------ W2-2 паспорт решения
async function checkPassport(ctx) {
  const { browser, base, dicts, variants } = ctx;
  const A = L.api(base);
  for (const [size, lang] of variants) {
    const dict = dicts[lang], tag = `${size[0]}-${lang}`;
    const D = devId("p");
    const c = await fileComplaint(A, STOPS[1], D, "Остановка: сломан павильон");
    const R = await openPage(browser, size, lang, { "birge.mode": "resident", "birge.device": D });
    try {
      await goto(R.page, base, lang);
      const opened = await header(R.page, dict, lang, words(dict, lang).mine, 1800);
      const lines = {
        responsible: word(dicts, lang, ["passport.responsible", "complaint.passport.responsible"], "Отвечает") || T(dict, "service.assigned", null),
        next: word(dicts, lang, ["passport.next_step", "complaint.passport.next_step"], "Следующий шаг"),
        due: word(dicts, lang, ["passport.response_due", "complaint.passport.response_due"], "Ответ службы до"),
        fix: word(dicts, lang, ["passport.fix_eta", "complaint.passport.fix_eta"], "Устранение"),
      };
      const seen = {};
      for (const [k, w] of Object.entries(lines)) seen[k] = w ? await L.visibleText(R.page, L.textRe(w)) : false;
      add("W2-2", tag, "карточка обращения жителя: «Отвечает», «Следующий шаг», «Ответ службы до …», «Устранение: ориентир / пока не определено»",
        st(opened && !!c && Object.values(seen).every(Boolean)), { opened, complaint: c && c.id, seen, words: lines }, await shotOf(R.page, `${tag}-W2-2-passport`));
    } finally { await R.ctx.close(); }
  }
  // Задержка: «Причина · Временная мера · Следующее обновление» — сотрудник задаёт 3 поля; просроченное обновление видно руководителю.
  add("W2-2", "API", "задержка: причина, временная мера, дата следующего обновления; просроченное обновление — в «Картине дня»", "NOT_RUN",
    "дописать по маршруту R09 при поставке (поля паспорта в API пока неизвестны) — экран сотрудника: ровно 3 поля");
}

// ------------------------------------------------------------------------------------------------ W2-4 «Рядом»
async function checkNearby(ctx) {
  const { browser, base, dicts, variants } = ctx;
  for (const [size, lang] of variants) {
    const dict = dicts[lang], tag = `${size[0]}-${lang}`;
    const P = await openPage(browser, size, lang, { "birge.mode": "resident" });
    try {
      await goto(P.page, base, lang);
      const near = word(dicts, lang, ["common.nav.nearby", "nearby.title"], "Рядом");
      const opened = near ? await header(P.page, dict, lang, new RegExp("^" + esc(near) + "$", "i"), 2000) : false;
      const groups = ["Ремонтируют сейчас", "Завершили", "Запланировано", "Отключения и перекрытия"]
        .map((ru, i) => word(dicts, lang, [["nearby.group.now", "nearby.group.done", "nearby.group.planned", "nearby.group.outages"][i]], ru));
      const g = [];
      for (const w of groups) g.push(w ? await L.visibleText(P.page, L.textRe(w)) : false);
      const why = word(dicts, lang, ["nearby.why", "nearby.card.why"], "Зачем");
      const whySeen = why ? await L.visibleText(P.page, L.textRe(why)) : false;
      const updated = await L.visibleText(P.page, /обновлено .*назад|жаңартылды/i);
      const delay = await L.visibleText(P.page, /задерж|перенес|кешік|ауыстырыл/i);
      const map = await P.page.evaluate(() => { const m = document.querySelector(".maplibregl-canvas"); if (!m) return null; const b = m.getBoundingClientRect();
        const h = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2); return h === m; }).catch(() => null);
      add("W2-4", tag, `«${near || "Рядом"}» в меню жителя → свой экран: 4 группы, «Зачем», «обновлено N минут назад», задержки тоже`,
        st(opened && g.every(Boolean) && whySeen && updated && delay), { opened, groups: g, why: whySeen, updated, delay, map_on_top_after_open: map }, await shotOf(P.page, `${tag}-W2-4-nearby`));
      const sub = await L.clickText(P.page, /^(Подписаться|Жазылу)/i, { wait: 1500 });
      const notif = sub ? await header(P.page, dict, lang, /^(Мои уведомления|Менің хабарламаларым)$/i, 1500) : false;
      add("W2-4", tag, "подписка на двор/улицу/объект → «Мои уведомления»", st(sub && notif), { sub, notif });
    } finally { await P.ctx.close(); }
  }
}

// ------------------------------------------------------------------------------------------------ W2-6 QR-паспорт объекта
async function checkQr(ctx) {
  const { browser, base, dicts, variants } = ctx;
  const stop = STOPS[4];  // «Хан Шатыр»: у него демо-жалобы (CIVIC_DEMO=1) — есть история и «Я тоже»
  for (const [size, lang] of variants) {
    const dict = dicts[lang], tag = `${size[0]}-${lang}`;
    const P = await openPage(browser, size, lang, { "birge.mode": "resident" });
    try {
      await goto(P.page, new URL(`/?report=${encodeURIComponent(stop.id)}`, base).href, lang);
      const title = await L.visibleText(P.page, new RegExp(esc(stop.name), "i"));
      const metoo = await L.firstVisible(P.page.getByRole("button", { name: new RegExp("^" + esc(T(dict, "complaint.step4.metoo", lang === "kk" ? "Мен де" : "Я тоже")), "i") }));
      const other = word(dicts, lang, ["target.report_other", "qr.report_other"], "Сообщить о другом");
      const otherBtn = other ? await L.firstVisible(P.page.getByRole("button", { name: L.textRe(other) })) : null;
      const hist = word(dicts, lang, ["target.history", "qr.history"], "История");
      const histSeen = hist ? await L.visibleText(P.page, L.textRe(hist)) : false;
      const keptLang = (await P.page.evaluate(() => document.documentElement.lang)) === lang;
      add("W2-6", tag, `/?report=<id> → карточка «${stop.name}»: история, обращения, «Я тоже», «Сообщить о другом»; язык не сменился`,
        st(title && !!metoo && !!otherBtn && histSeen && keptLang), { title, metoo: !!metoo, other: !!otherBtn, history: histSeen, keptLang }, await shotOf(P.page, `${tag}-W2-6-report`));
    } finally { await P.ctx.close(); }
  }
  // Лист для печати (web/civic/qr/): QR + короткий адрес + номер объекта + домен; печать на A4.
  const P = await openPage(browser, [1366, 768], "ru");
  try {
    const urls = [`/civic/qr/?target=${stop.id}`, `/civic/qr/?id=${stop.id}`, `/civic/qr/index.html?target=${stop.id}`];
    let sheet = null;
    for (const u of urls) { const r = await P.page.goto(new URL(u, base).href).catch(() => null); if (r && r.ok()) { sheet = u; break; } }
    if (!sheet) { add("W2-6", "лист", "лист для печати web/civic/qr/ открывается", "FAIL", { tried: urls }); return; }
    await L.sleep(2000);
    const info = await P.page.evaluate((id) => {
      const qr = [...document.querySelectorAll("canvas, svg, img")].map((e) => e.getBoundingClientRect()).filter((b) => b.width >= 113 && Math.abs(b.width - b.height) < 4);
      const text = document.body.innerText;
      const html = document.documentElement.outerHTML;
      const print = [...document.styleSheets].some((s) => { try { return [...s.cssRules].some((r) => r.media && /print/.test(r.media.mediaText)); } catch (e) { return false; } });
      return { qr: qr.length, qr_px: qr[0] ? Math.round(qr[0].width) : 0, id: text.includes(id.replace(/^osm-node-/, "")) || text.includes(id), report_link: html.includes("report=" + id) || html.includes("report=" + encodeURIComponent(id)), print, text: text.slice(0, 200) };
    }, stop.id);
    add("W2-6", "лист", "лист для печати: QR ≥ 3 см, номер объекта, ссылка ?report=<id>, стиль для печати", st(info.qr > 0 && info.id && info.report_link && info.print),
      { sheet, ...info }, await shotOf(P.page, "1366-ru-W2-6-sheet"));
    add("W2-6", "лист", "скан распечатки телефоном открывает карточку этой остановки", "NOT_RUN", "только на устройстве — Codex/владелец (камера телефона); подмена ссылки — R15");
  } finally { await P.ctx.close(); }
}

// ------------------------------------------------------------------------------------------------ W2-7 идеи
async function checkIdeas(ctx) {
  const { browser, base, dicts, variants } = ctx;
  for (const [size, lang] of variants) {
    const dict = dicts[lang], tag = `${size[0]}-${lang}`;
    const P = await openPage(browser, size, lang, { "birge.mode": "resident", "birge.device": devId("i") });
    try {
      await goto(P.page, base, lang);
      const ideas = word(dicts, lang, ["common.nav.ideas", "ideas.title"], "Идеи");
      const opened = ideas ? await header(P.page, dict, lang, new RegExp("^" + esc(ideas) + "$", "i"), 2000) : false;
      const honest = word(dicts, lang, ["ideas.disclaimer", "idea.disclaimer"], "Это опрос для выбора концепции");
      const honestSeen = honest ? await L.visibleText(P.page, L.textRe(honest)) : false;
      const propose = word(dicts, lang, ["ideas.propose", "idea.propose"], "Предложить идею");
      const proposeBtn = propose ? await L.firstVisible(P.page.getByRole("button", { name: L.textRe(propose) })) : null;
      add("W2-7", tag, `«${ideas || "Идеи"}»: раздел открывается, до голосования честно «${honest || "Это опрос…"}», кнопка «Предложить идею»`,
        st(opened && honestSeen && !!proposeBtn), { opened, honest: honestSeen, propose: !!proposeBtn }, await shotOf(P.page, `${tag}-W2-7-ideas`));
      const fromIdea = await L.visibleText(P.page, /По идее жителей|Тұрғындар идеясы/i);
      const rework = await L.visibleText(P.page, /Можно доработать|Пысықтауға болады/i);
      add("W2-7", tag, "есть путь «проект по идее жителей, N голосов» или «отказ с причиной и „Можно доработать“»", st(fromIdea || rework), { fromIdea, rework });
    } finally { await P.ctx.close(); }
  }
  add("W2-7", "API", "голос соседа +1, повтор с того же устройства не удваивает; акимат: чек-лист (участок, сети, доступность, содержание) → проект в 3D или отказ", "NOT_RUN",
    "дописать по маршруту R06 при поставке (API идей пока неизвестен)");
}

// ------------------------------------------------------------------------------------------------ P-12 защита от перегруза
async function checkClutter(ctx) {
  const { browser, base, dicts, variants } = ctx;
  const want = { resident: ["Карта", "Мои обращения", "Рядом", "Идеи", "Ещё"], akimat: ["Карта", "Картина дня", "Обращения", "Проекты и идеи", "Ещё"] };
  for (const [size, lang] of variants) {
    const dict = dicts[lang], tag = `${size[0]}-${lang}`;
    for (const mode of ["resident", "akimat"]) {
      const P = await openPage(browser, size, lang, { "birge.mode": mode });
      try {
        await goto(P.page, base, lang);
        const nav = await P.page.evaluate(() => [...document.querySelectorAll("nav button, nav a, [role=navigation] button, [role=navigation] a, [role=tablist] [role=tab]")]
          .filter((e) => e.getBoundingClientRect().width > 0).map((e) => (e.innerText || e.getAttribute("aria-label") || "").trim()).filter(Boolean));
        const names = want[mode].map((ru) => word(dicts, lang, [], ru)).filter(Boolean);
        const found = names.filter((n) => nav.some((x) => x.startsWith(n)));
        add("P-12", `${tag} ${mode}`, `меню ${mode === "resident" ? "жителя" : "акимата"}: не больше 5 пунктов (${want[mode].join(" · ")})`, st(nav.length > 0 && nav.length <= 5 && found.length === names.length),
          { nav, expected: names }, await shotOf(P.page, `${tag}-P-12-${mode}`));
      } finally { await P.ctx.close(); }
    }
  }
  add("P-12", "карта", "дополнительный слой («Рядом», «Идеи», «Объявления») — не больше одного сразу, по умолчанию выключены", "NOT_RUN",
    "по умолчанию — map_baseline.cjs + compare_baseline.cjs (слои и значки как в 8e67c65); переключатели слоёв — дописать при поставке R01");
}

// ------------------------------------------------------------------------------------------------ main
const ITEMS = [
  { id: "W1-3", title: "Срочные случаи: газ 104, дым/пожар 112, провод 112", owner: "R09 (+R11)", run: checkEmergency,
    done: "Ни одна жалоба про газ или пожар не уходит без подсказки позвонить 104/112" },
  { id: "W2-1", title: "Центральная сцена: «Исправлено — проверьте» → житель подтвердил → зелёный «проверено»", owner: "R09, R07, R08", run: checkCentral,
    done: "исправили → житель подтвердил → объект зелёный «проверено»; при «осталось» — снова красный, история сохранена" },
  { id: "W2-2", title: "Паспорт решения", owner: "R09", run: checkPassport, done: "Житель понимает, что происходит, без звонка" },
  { id: "W2-4", title: "«Что делают рядом»", owner: "R06 + R08", run: checkNearby, done: "Житель видит «Завтра 10–16 нет воды в вашем дворе» и «Зачем перекопали улицу»" },
  { id: "W2-6", title: "QR-паспорт объекта", owner: "R12", run: checkQr, done: "Скан распечатки телефоном → карточка этой остановки" },
  { id: "W2-7", title: "Идеи → голосование → проект в 3D", owner: "R06 + R05", run: checkIdeas, done: "Путь «идея → голоса → проект в 3D» или «отказ с причиной и доработка»" },
  { id: "P-12", title: "Защита от перегруза: меню ≤ 5, один доп. слой", owner: "R01, R11", run: checkClutter, done: "правила 1–2 POLISH_WAVE_2" },
];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const sha = L.buildSha(ROOT);
  const dicts = { ru: L.loadDict(ROOT, "ru"), kk: L.loadDict(ROOT, "kk") };
  const variants = SIZES.flatMap((s) => LANGS.map((l) => [s, l]));
  const todo = ITEMS.filter((i) => !ONLY || ONLY.includes(i.id));
  const status = {};
  for (const it of todo) { status[it.id] = delivered(it.id); if (args.force && !status[it.id].ok) status[it.id] = { ok: true, forced: true, hits: [] }; }
  const need = todo.filter((it) => status[it.id].ok);
  for (const it of todo.filter((x) => !status[x.id].ok))
    add(it.id, "сборка", `${it.title} — ЖДЁТ поставки (${it.owner})`, "PENDING", "в коде сборки нет: " + PROBE_TEXT[it.id]);
  let server = null;
  if (need.length) {
    server = await L.startServer(ROOT);
    await L.api(server.base).call("GET", "/api/civic/v2/heat?days=30&zoom=12");  // подключает /similar (B-032)
    const browser = await chromium.launch();
    try {
      for (const it of need) {
        add(it.id, "сборка", `${it.title}: ${status[it.id].forced ? "кода нет, --force — проверяю механику" : "код есть — проверяю"}`, "INFO", status[it.id].hits);
        try { await it.run({ browser, base: server.base, dicts, variants, staff: server.staff }); }
        catch (e) { add(it.id, "!", "проверка прервалась", "FAIL", String(e.message || e).slice(0, 300)); }
      }
    } finally { await browser.close(); await server.stop(); }
  }
  const counts = { PASS: 0, FAIL: 0, PENDING: 0, NOT_RUN: 0, INFO: 0 };
  results.forEach((r) => counts[r.status]++);
  const meta = { root: ROOT, sha, when: new Date().toISOString(), sizes: SIZES.map((s) => s.join("x")), langs: LANGS, node: process.version, ...(args.force ? { force: "проверка механики, не приёмка" } : {}) };
  fs.writeFileSync(path.join(OUT, "WAVE_RESULT.json"), JSON.stringify({ meta, counts, items: todo.map(({ run, ...i }) => ({ ...i, delivered: status[i.id] })), results }, null, 1));
  const md = [`# R10 · новые пункты волн 1–2 · ${sha}${args.force ? " · --force (проверка механики, не приёмка)" : ""}`, "", "```", JSON.stringify(meta), "```", "",
    `Итого: PASS ${counts.PASS}, FAIL ${counts.FAIL}, ЖДЁТ ${counts.PENDING}, NOT_RUN ${counts.NOT_RUN}`, "",
    "| Пункт | Что | Владелец | Готово, когда | Состояние |", "|---|---|---|---|---|",
    ...todo.map((i) => { const rs = results.filter((r) => r.item === i.id && r.status !== "INFO");
      const s = !status[i.id].ok ? "ЖДЁТ" : rs.some((r) => r.status === "FAIL") ? "FAIL" : rs.every((r) => r.status === "PASS") ? "PASS" : "частично";
      return `| ${i.id} | ${i.title} | ${i.owner} | ${i.done} | **${s}** |`; }),
    "", "| Пункт | Где | Проверка | Итог | Подробно | Кадр |", "|---|---|---|---|---|---|",
    ...results.map((r) => `| ${r.item} | ${r.scope} | ${r.name} | **${r.status === "PENDING" ? "ЖДЁТ" : r.status}** | ${r.detail ? JSON.stringify(r.detail).replace(/\|/g, "/").slice(0, 220) : ""} | ${r.shot || ""} |`)];
  fs.writeFileSync(path.join(OUT, "WAVE_RESULT.md"), md.join("\n") + "\n");
  console.log("ИТОГ:", counts, "→", OUT);
  process.exit(counts.FAIL ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
