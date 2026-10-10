// R10 · раунд 14 · сквозная приёмка сценария демо Birge (CONTRACT §0, 6 шагов) на сборке R01.
//
//   node tests/e2e/demo_flow.cjs --root <папка сборки> --out <папка отчёта>
//        [--sizes 1366x768,375x812] [--langs ru,kk] [--url http://127.0.0.1:8611/ --user U --pass P]
//        [--stop "lon,lat,osm-node-…,Имя"]
//
// Без --url тест сам поднимает сервер сборки (python3 app.py) на свободном порту с ВРЕМЕННОЙ базой:
// init → seed-demo (синтетика R02) → seed-r14-demo (если есть у R06) → сотрудник «r10-operator».
// Ничего не пишет в репозиторий. Нужен Playwright: NODE_PATH="$(npm root -g)".
//
// Два слоя проверок:
//   API — шаги сценария через HTTP API v2 (CONTRACT §7): отделяет «нет модуля» от «нет кнопки».
//   UI  — то же глазами жителя и акимата: элементы ищутся по ВИДИМЫМ словам из словарей R11
//         (web/civic/i18n/ru.json, kk.json), а не по внутренним классам — тест не зависит от вёрстки.
// Итог: <out>/RESULT.json и RESULT.md; скриншоты <out>/<размер>-<язык>-<шаг>.jpg.
// Статусы: PASS, FAIL (с причиной), NOT_RUN (нечего проверять: модуль не подключён и это уже FAIL шага API).
// UI-шаги 5–6 меняют данные временной базы так же, как ведущий демо: вход сотрудника («Для сотрудников»),
// проект сквера (в конце удаляется), «Взять в работу» → «Отметить исправленным» по остановке варианта (UI_STOPS).
"use strict";
const { chromium } = require("playwright");
const { spawn, execFileSync } = require("child_process");
const fs = require("fs"), path = require("path"), os = require("os"), net = require("net");

// ------------------------------------------------------------------------------------------------ параметры
const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => {
  if (a.startsWith("--")) acc.push([a.slice(2), all[i + 1] && !all[i + 1].startsWith("--") ? all[i + 1] : true]);
  return acc;
}, []));
const ROOT = path.resolve(args.root || path.join(__dirname, "../.."));
const OUT = path.resolve(args.out || path.join(os.tmpdir(), "r10-e2e"));
const SIZES = String(args.sizes || "1366x768,375x812").split(",").map((s) => s.split("x").map(Number));
const LANGS = String(args.langs || "ru,kk").split(",");
// Реальная остановка Нуры из OSM (есть в целях R07 и в geo/objects.json R12).
// --stop "lon,lat,id,Имя" — другая остановка (например, для стенда роли с узкой областью данных).
const STOP = args.stop ? (([lon, lat, id, ...name]) => ({ id, name: name.join(","), point: [Number(lon), Number(lat)] }))(String(args.stop).split(","))
  : { id: "osm-node-4109037549", name: "Хан Шатыр", point: [71.406553, 51.131155] };
// Остановки — реальные OSM (data/civic/astana/geo/objects.json R12), все в Нуре.
// STOP — остановка DEMO_SCRIPT: на ней при CIVIC_DEMO=1 есть демо-жалобы «Освещение» (путь «Я тоже»), её API-шаг не трогает.
// API_STOP — для API-шага (подать → «Я тоже» → «исправлено»), чтобы не менять состояние остановки сценария.
// UI_STOPS — у каждого варианта экрана своя остановка: вариант 1 повторяет DEMO_SCRIPT («Хан Шатыр», «Я тоже»),
// остальные начинают с чистой остановки (новая жалоба → «Взять в работу» → «Исправлено»).
const API_STOP = args.stop ? STOP : { id: "osm-node-13394597038", name: "Республиканский диагностический центр", point: [71.4060541, 51.1266034] };
const UI_STOPS = args.stop ? [STOP] : [STOP,
  { id: "osm-node-5756851369", name: "Центр материнства и детства", point: [71.40432, 51.1251454] },
  { id: "osm-node-5756882393", name: "Жилой комплекс Зелёный Квартал", point: [71.3966837, 51.1278101] },
  { id: "osm-node-2716977767", name: "Национальный кардиологический центр", name_kk: "Ұлттық кардиохирургиялық орталық", point: [71.4131502, 51.1276695] }];
const NURA_BBOX = "71.375,51.115,71.420,51.140";
const DEVICE = "r10-e2e-device-" + Date.now();
const { NOISE, TAB_LIMIT, uiScreen, cyrLines, untranslated, focusToPrimary } = require("./ux_lib.cjs");

// Python: переменная PYTHON (например .venv\Scripts\python на Windows), иначе python3 / python.
const PY = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");

const results = [];
const add = (layer, step, name, status, detail, shot) => {
  results.push({ layer, step, name, status, detail: detail ?? null, shot: shot || null });
  console.log(`${status.padEnd(7)} ${layer} ${step} ${name}` + (detail ? " — " + JSON.stringify(detail).slice(0, 300) : ""));
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ------------------------------------------------------------------------------------------------ сервер
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no);
  s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r10-e2e-"));
  const db = path.join(tmp, "civic.sqlite3");
  // CIVIC_DEMO=1 — как run-city.bat на демо (синтетический набор R07 на карте); --no-demo — без него.
  const env = { ...process.env, CIVIC_DB_PATH: db, PYTHONDONTWRITEBYTECODE: "1", CIVIC_DEMO: args["no-demo"] ? "" : "1" };
  const cli = (argv, input) => execFileSync(PY, ["-B", "-m", "ui.civic_store", "--db", db, ...argv],
    { cwd: ROOT, env, input, stdio: [input ? "pipe" : "ignore", "pipe", "pipe"] }).toString();
  cli(["init"]);
  cli(["seed-demo", "--package", "data/civic/astana/demo_synthetic.json"]);
  const help = cli(["--help"]);
  const seeds = ["seed-demo"];
  if (/seed-r14-demo/.test(help)) { cli(["seed-r14-demo"]); seeds.push("seed-r14-demo"); }
  const user = "r10-operator", pass = "R10-e2e-" + Math.random().toString(36).slice(2) + "-Aa1!";
  let staff = null;
  try { cli(["create-editor", user, "--password-stdin"], pass + "\n"); staff = { user, pass }; }
  catch (e) { staff = { error: String(e.stderr || e.message).slice(0, 300) }; }
  const port = await freePort();
  const srv = spawn(PY, ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)],
    { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) {
    try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return { srv, base: `http://127.0.0.1:${port}/`, staff, seeds, tmp }; } catch {}
    await sleep(200);
  }
  throw new Error("сервер сборки не запустился: " + srv.log.slice(-1500));
}

// ------------------------------------------------------------------------------------------------ HTTP
function api(base) {
  let cookie = null, csrf = null;
  const origin = new URL(base).origin;  // API всегда от корня сервера, даже если страница по пути /stand/
  const call = async (method, p, body, staff) => {
    const headers = { "Content-Type": "application/json", Origin: origin };
    if (staff && cookie) { headers.Cookie = cookie; headers["X-CSRF-Token"] = csrf; }
    let res;
    try { res = await fetch(origin + p, { method, headers, body: body ? JSON.stringify(body) : undefined }); }
    catch (e) { return { status: 0, body: { error: String(e) } }; }
    const text = await res.text();
    let json = null; try { json = JSON.parse(text); } catch {}
    return { status: res.status, body: json, text: json ? null : text.slice(0, 200), res };
  };
  return {
    call,
    data: (r) => (r.body && r.body.data !== undefined && r.body.ok !== undefined ? r.body.data : r.body),
    async login(user, pass) {
      const r = await call("POST", "/api/civic/v1/session/login", { username: user, password: pass });
      const set = r.res && r.res.headers.get("set-cookie");
      if (r.status !== 200 || !set) return { ok: false, status: r.status, body: r.body };
      cookie = set.split(";")[0];
      const d = r.body && (r.body.data || r.body);
      csrf = d && (d.csrf_token || (d.session && d.session.csrf_token));
      return { ok: !!csrf, status: r.status };
    },
  };
}

// ------------------------------------------------------------------------------------------------ словари
function loadDict(lang) {
  const file = path.join(ROOT, "web/civic/i18n", lang + ".json");
  if (!fs.existsSync(file)) return null;
  const flat = {};
  const walk = (o, p) => { for (const [k, v] of Object.entries(o)) {
    if (v && typeof v === "object" && !Object.keys(v).every((x) => ["one", "few", "many", "other"].includes(x))) walk(v, p + k + ".");
    else flat[p + k] = v; } };
  walk(JSON.parse(fs.readFileSync(file, "utf8")), "");
  return flat;
}
// Текст ключа без параметров: «Остановка «{name}»» → регулярка по неизменной части.
// key — строка или список ключей-синонимов (словари ролей и R11 ещё сходятся): берём первый найденный.
const T = (dict, key, fallback) => {
  for (const k of [].concat(key)) {
    const v = dict && dict[k];
    if (typeof v === "string") return v;
    if (v && (v.other || v.many || v.one)) return v.other || v.many || v.one;
  }
  return fallback;
};
const textRe = (s) => new RegExp(s.split(/\{[a-z_]+\}/).map((x) => x.trim()).filter(Boolean)
  .map((x) => x.replace(/[.*+?^${}()|[\]\\«»]/g, (m) => (m === "«" || m === "»" ? "[«»\"]?" : "\\" + m))).join(".*"), "i");

// ------------------------------------------------------------------------------------------------ слой API
async function apiFlow(A, staffInfo) {
  const ctx = {};
  // 0. Какие модули подключены (шлюз R01).
  const m = await A.call("GET", "/api/civic/v2/modules");
  const modules = (A.data(m) || {}).modules || {};
  const notReady = Object.entries(modules).filter(([, v]) => v.status !== "ready").map(([k, v]) => `${k}:${v.role}:${v.status}`);
  add("API", "0", "шлюз v2: все маршруты ready", m.status === 200 && notReady.length === 0 ? "PASS" : "FAIL",
    m.status === 200 ? { not_ready: notReady } : { status: m.status });
  ctx.modules = modules;

  // 0б. Шаг 2 DEMO_SCRIPT на ЧИСТОЙ базе (как run-city.bat): ведущий пишет «Аялдамада жарық жоқ, вечером на остановке
  //     темно» и ждёт «Освещение» и похожие обращения с «Я тоже». Проверяем ДО того, как тест сам создаст жалобы:
  //     если похожих нет — на показе «Я тоже» не появится (с --url на уже использованном сервере проверка мягче).
  const demoText = "Аялдамада жарық жоқ, вечером на остановке темно";
  const c0 = await A.call("POST", "/api/civic/v2/classify", { text: demoText });
  const d0 = A.data(c0) || {};
  add("API", "2", "текст DEMO_SCRIPT (смесь kk/ru) → «Освещение» с подсказкой", c0.status === 200 && d0.category === "lighting" && d0.suggest !== false ? "PASS" : "FAIL",
    { status: c0.status, category: d0.category, score: d0.score, suggest: d0.suggest, model: d0.model_version });
  // Страница при загрузке запрашивает /heat — только после этого шлюз подключает /similar к жалобам R09 (B-032).
  const sCold = await A.call("POST", "/api/civic/v2/similar", { text: demoText, point: STOP.point, days: 30 });
  add("API", "2", "/similar сразу после запуска сервера (до первой загрузки страницы) отвечает 200", sCold.status === 200 ? "PASS" : "FAIL",
    { status: sCold.status, error: sCold.body && sCold.body.error });
  await A.call("GET", "/api/civic/v2/heat?days=30&zoom=12");
  const s0 = await A.call("POST", "/api/civic/v2/similar", { text: demoText, point: STOP.point, days: 30 });
  const m0 = (A.data(s0) || {}).matches || [];
  add("API", "2", "чистая база демо: /similar по тексту DEMO_SCRIPT у остановки находит похожие (иначе «Я тоже» не будет)",
    s0.status === 200 && m0.length > 0 ? "PASS" : "FAIL", { status: s0.status, n: m0.length, stop: STOP.name });

  // 1. Место на карте → «Это остановка «…»?» (R12 /targets).
  const [lon, lat] = API_STOP.point;
  const t = await A.call("GET", `/api/civic/v2/targets?lon=${lon}&lat=${lat}&category=transport`);
  const cands = (A.data(t) || {}).candidates || [];
  const first = cands[0];
  const okT = t.status === 200 && first && first.target && first.target.kind === "object" && /^osm-(node|way|relation)-\d+$/.test(first.target.id)
    && typeof first.distance_m === "number" && first.distance_m <= 60;
  add("API", "1", "/targets у остановки: первый кандидат — реальный объект OSM ≤ 60 м с подписью", okT ? "PASS" : "FAIL",
    { status: t.status, first: first ? { id: first.target && first.target.id, label: first.target && (first.target.label_ru || first.label_ru), d: first.distance_m } : null, n: cands.length });
  ctx.target = okT ? first.target : { kind: "object", id: API_STOP.id, label_ru: `Остановка «${API_STOP.name}»` };

  // 2. Категория и похожие (R04).
  const texts = { ru: "На остановке сломан павильон, нет крыши", kk: "Аялдамада павильон сынған, шатыры жоқ", mixed: "Бекетте павильон сынған, крыши нет" };
  for (const [lang, text] of Object.entries(texts)) {
    const c = await A.call("POST", "/api/civic/v2/classify", { text });
    const d = A.data(c) || {};
    const ok = c.status === 200 && d.category === "transport" && typeof d.score === "number" && Array.isArray(d.top3) && "needs_review" in d && d.model_version;
    add("API", "2", `/classify (${lang}) → «Остановки и транспорт», ответ по §7`, ok ? "PASS" : "FAIL",
      { status: c.status, category: d.category, score: d.score, needs_review: d.needs_review, model: d.model_version });
  }

  // 1б. Жалоба на цель (R09), затем «Я тоже» другим устройством.
  const body = { text: texts.mixed, lang: "mixed", category: "transport", category_source: "resident", point: API_STOP.point,
    target: ctx.target, device_id: DEVICE, demo: true };
  const cr = await A.call("POST", "/api/civic/v2/complaints", body);
  const rec = (A.data(cr) || {}).complaint || A.data(cr) || {};
  const okC = [200, 201].includes(cr.status) && /^c-/.test(rec.id || "") && rec.status === "new" && rec.target && rec.target.id === ctx.target.id;
  add("API", "1", "POST /complaints: запись §5 (id c-…, status new, target сохранён)", okC ? "PASS" : "FAIL",
    { status: cr.status, id: rec.id, st: rec.status, err: cr.body && cr.body.error });
  ctx.complaint = okC ? rec : null;

  const sim = await A.call("POST", "/api/civic/v2/similar", { text: "Павильон на остановке сломан", point: API_STOP.point, days: 30 });
  const matches = (A.data(sim) || {}).matches || [];
  const okS = sim.status === 200 && Array.isArray(matches) && (!ctx.complaint || matches.some((x) => x.complaint_id === ctx.complaint.id));
  add("API", "2", "/similar находит только что поданную жалобу на ту же остановку", okS ? "PASS" : "FAIL",
    { status: sim.status, n: matches.length, top: matches[0] || null });
  if (ctx.complaint) {
    const mt = await A.call("POST", `/api/civic/v2/complaints/${ctx.complaint.id}/metoo`, { device_id: DEVICE + "-2" });
    const after = (A.data(mt) || {}).complaint || A.data(mt) || {};
    add("API", "2", "«Я тоже» другим устройством: metoo +1", [200, 201].includes(mt.status) && after.metoo >= 1 ? "PASS" : "FAIL",
      { status: mt.status, metoo: after.metoo, err: mt.body && mt.body.error });
    const again = await A.call("POST", `/api/civic/v2/complaints/${ctx.complaint.id}/metoo`, { device_id: DEVICE + "-2" });
    const again2 = (A.data(again) || {}).complaint || A.data(again) || {};
    add("API", "2", "повторное «Я тоже» с того же устройства не увеличивает счёт", again2.metoo === after.metoo || [409, 429].includes(again.status) ? "PASS" : "FAIL",
      { status: again.status, metoo: again2.metoo });
  }

  // 3. Тепловая карта (R07): цель есть, уровень и цвет по categories_v2.
  const h = await A.call("GET", `/api/civic/v2/heat?bbox=${NURA_BBOX}&days=30&zoom=16`);
  const items = (A.data(h) || {}).items || [];
  const mine = items.find((i) => i.target && i.target.id === ctx.target.id);
  add("API", "3", "/heat (Нура, 30 дней, z16): цель жалобы есть, level ≥ 1, count ≥ 1, форма есть", h.status === 200 && mine && mine.level >= 1 && mine.count >= 1 && mine.geometry ? "PASS" : "FAIL",
    { status: h.status, items: items.length, target: mine ? { level: mine.level, count: mine.count, weight: mine.weight, kind: mine.target.kind } : null });
  const zoomCity = await A.call("GET", `/api/civic/v2/heat?days=30&zoom=10`);
  const cityItems = (A.data(zoomCity) || {}).items || [];
  add("API", "3", "смысловой зум: z10 отдаёт районы, а не отдельные остановки", zoomCity.status === 200 && cityItems.length > 0 && cityItems.every((i) => !i.target || i.target.kind !== "object") ? "PASS" : "FAIL",
    { status: zoomCity.status, n: cityItems.length, kinds: [...new Set(cityItems.map((i) => i.target && i.target.kind))] });

  // 4. «Картина дня» (R08).
  const s = await A.call("GET", "/api/civic/v2/akim/summary");
  const sd = A.data(s) || {};
  const hot = sd.hot && (sd.hot.items || sd.hot.top || []);
  add("API", "4", "/akim/summary: KPI, темы, районы, горячие места, просрочки, отставание, текст ru/kk",
    s.status === 200 && sd.kpi && sd.topics && sd.districts && sd.hot && sd.deadlines && sd.objects && sd.text && sd.text.ru && sd.text.kk ? "PASS" : "FAIL",
    { status: s.status, complaints_available: sd.complaints_available, sources: sd.sources, hot: Array.isArray(hot) ? hot.length : null });

  // 5. Предложение акимата + голос жителя (R06).
  const login = staffInfo && staffInfo.user ? await A.login(staffInfo.user, staffInfo.pass) : { ok: false, why: staffInfo && staffInfo.error };
  add("API", "5", "вход сотрудника акимата (сессия + CSRF)", login.ok ? "PASS" : "FAIL", login);
  const pl = await A.call("GET", "/api/civic/v2/proposals");
  const plist = (A.data(pl) || {}).items || (A.data(pl) || {}).proposals || [];
  add("API", "5", "GET /proposals: демо-предложения (seed-r14-demo) со статусом", pl.status === 200 && plist.length > 0 && plist.every((p) => p.status) ? "PASS" : "FAIL",
    { status: pl.status, n: plist.length, statuses: [...new Set(plist.map((p) => p.status))] });
  // Демо-проект с точкой — для голоса жителя на экране, где акимат не может поставить свой (телефон).
  const seeded = plist.find((p) => p.geometry && p.geometry.type === "Point" && p.status === "proposal");
  ctx.seededPoint = seeded ? seeded.geometry.coordinates : null;
  let prop = null;
  if (login.ok) {
    const pc = await A.call("POST", "/api/civic/v2/proposals", { kind: "square", geometry: { type: "Point", coordinates: [71.4021, 51.1288] },
      title_ru: "Сквер (приёмка R10)", title_kk: "Гүлзар (R10 қабылдау)", demo: true }, true);
    const pd = A.data(pc) || {};
    prop = pd.item || pd.proposal || pd;  // R06 отвечает {item: …}
    add("API", "5", "POST /proposals (сквер) от сотрудника", [200, 201].includes(pc.status) && prop && prop.id && prop.status === "proposal" ? "PASS" : "FAIL",
      { status: pc.status, id: prop && prop.id, st: prop && prop.status, err: pc.body && pc.body.error });
  }
  const pid = (prop && prop.id) || (plist[0] && plist[0].id);
  if (pid) {
    const v1 = await A.call("POST", `/api/civic/v2/proposals/${pid}/vote`, { value: 1, device_id: DEVICE });
    const v2 = await A.call("POST", `/api/civic/v2/proposals/${pid}/vote`, { value: 1, device_id: DEVICE });
    const one = (r) => { const d = A.data(r) || {}; return d.item || d.proposal || d; };
    const a = one(v1), b = one(v2);
    add("API", "5", "голос «За» +1, повтор с того же устройства не удваивает", [200, 201].includes(v1.status) && a.votes_up >= 1 && (b.votes_up === a.votes_up || [409, 429].includes(v2.status)) ? "PASS" : "FAIL",
      { first: [v1.status, a.votes_up], second: [v2.status, b.votes_up] });
  } else add("API", "5", "голос «За» по предложению", "NOT_RUN", "нет ни одного предложения");

  // 6. «Исправлено» → зелёная цель на карте и статус у жителя.
  if (ctx.complaint && login.ok) {
    const st1 = await A.call("POST", `/api/civic/v2/complaints/${ctx.complaint.id}/status`, { status: "in_progress" }, true);
    const st2 = await A.call("POST", `/api/civic/v2/complaints/${ctx.complaint.id}/status`, { status: "fixed" }, true);
    add("API", "6", "сотрудник: «Взять в работу» → «Исправлено»", [200, 201].includes(st1.status) && [200, 201].includes(st2.status) ? "PASS" : "FAIL",
      { in_progress: st1.status, fixed: st2.status, err: (st2.body && st2.body.error) || (st1.body && st1.body.error) });
    const h2 = await A.call("GET", `/api/civic/v2/heat?bbox=${NURA_BBOX}&days=30&zoom=16`);
    const it2 = ((A.data(h2) || {}).items || []).find((i) => i.target && i.target.id === ctx.target.id);
    add("API", "6", "после «исправлено» цель зелёная (fixed_until задан, вес обнулён)", it2 && it2.fixed_until && (it2.weight === 0 || it2.level === 0 || it2.level === "fixed") ? "PASS" : "FAIL",
      { item: it2 ? { level: it2.level, weight: it2.weight, fixed_until: it2.fixed_until } : null });
    const l = await A.call("GET", `/api/civic/v2/complaints?bbox=${NURA_BBOX}`);
    const got = ((A.data(l) || {}).items || (A.data(l) || {}).complaints || []).find((c) => c.id === ctx.complaint.id);
    add("API", "6", "GET /complaints: статус fixed и история статусов", got && got.status === "fixed" && Array.isArray(got.status_history) && got.status_history.length >= 3 ? "PASS" : "FAIL",
      { status: l.status, st: got && got.status, history: got && got.status_history && got.status_history.length });
  } else add("API", "6", "статус «исправлено»", "NOT_RUN", "нет жалобы из шага 1 или входа сотрудника");
  return ctx;
}

// ------------------------------------------------------------------------------------------------ слой UI
// Место для проекта сквера (шаг 5): левый берег, в стороне от демо-проектов seed-r14-demo (Жагалау).
// Каждый вариант экрана ставит свой проект на ~130 м севернее предыдущего и в конце удаляет его.
const PLACE = [71.4148, 51.1131];
const esc = (s) => String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// Первый ВИДИМЫЙ из найденных элементов: getByText/getByRole находят и скрытые копии (свёрнутая панель, другой вид).
async function firstVisible(loc, max = 40) {
  const n = Math.min(await loc.count().catch(() => 0), max);
  for (let i = 0; i < n; i++) if (await loc.nth(i).isVisible().catch(() => false)) return loc.nth(i);
  return null;
}
// Видимый элемент, ближайший к точке экрана (табличка «своего» проекта среди нескольких).
async function nearestVisible(loc, xy, max = 40) {
  const n = Math.min(await loc.count().catch(() => 0), max);
  let best = null, bestD = Infinity;
  for (let i = 0; i < n; i++) {
    const it = loc.nth(i);
    if (!(await it.isVisible().catch(() => false))) continue;
    const b = await it.boundingBox().catch(() => null);
    if (!b) continue;
    const d = Math.hypot(b.x + b.width / 2 - xy.x, b.y + b.height / 2 - xy.y);
    if (d < bestD) { best = it; bestD = d; }
  }
  return best ? { loc: best, d: Math.round(bestD) } : null;
}
const clickText = async (scope, re, opts = {}) => {
  const loc = await firstVisible(scope.getByRole(opts.role || "button", { name: re }));
  if (!loc) return false;
  await loc.click({ timeout: 4000 }).catch(() => null);
  await sleep(opts.wait || 900);
  return true;
};
const visibleText = async (scope, re) => !!(await firstVisible(scope.getByText(re)));
const tap = async (page, x, y) => { if (page.viewportSize().width < 1024) await page.touchscreen.tap(x, y); else await page.mouse.click(x, y); };
// Нажать на найденный элемент по центру его рамки (касание на телефоне): так нажимает человек, а таблички
// 3D-проектов двигаются вместе с картой — обычный click Playwright ждёт «неподвижности» и не срабатывает.
const tapEl = async (page, loc) => { const b = await loc.boundingBox().catch(() => null); if (!b) return false; await tap(page, b.x + b.width / 2, b.y + b.height / 2); return true; };

// Значок выбранного места (R07 помечает его, пока открыта карточка): на экране и ничем не закрыт — ни шторкой,
// ни шапкой, ни кнопкой поверх карты (R11 ночь, круг 16: на телефоне «Что построить?» вставала ровно на него).
async function selectedPlace(page) {
  return page.evaluate(() => {
    const el = document.querySelector(".r07-badge--selected");
    if (!el || !el.getClientRects().length) return { badge: false };
    const b = el.getBoundingClientRect(), cx = b.left + b.width / 2, cy = b.top + b.height / 2;
    const inView = cx >= 0 && cy >= 0 && cx <= innerWidth && cy <= innerHeight;
    const over = inView ? document.elementFromPoint(cx, cy) : null;
    const who = (n) => ((n.closest("button, [role=button], a") || n).textContent || "").trim().slice(0, 40) || n.getAttribute("class") || n.tagName;
    return { badge: true, inView, at: [Math.round(cx), Math.round(cy)], covered: over && !el.contains(over) ? who(over) : null };
  });
}

// Показать точку на карте и вернуть её место на экране: что лежит поверх (холст или значок) и ближайшую
// свободную точку холста рядом. Панель (ноутбук) или шторка (телефон) может закрывать точку — тогда карта
// сдвигается так, чтобы точка оказалась на открытой части карты.
async function showPoint(page, point, zoom = 17) {
  return page.evaluate(async ([p, z]) => {
    // eslint-disable-next-line no-undef
    const m = typeof map !== "undefined" && map && map.project ? map : (window.standMap || null);
    if (!m) return null;
    const wait = (ms) => new Promise((ok) => setTimeout(ok, ms));
    m.jumpTo({ center: p, zoom: z, pitch: 0, bearing: 0 });
    await wait(500);
    const canvas = m.getCanvas(), c = canvas.getBoundingClientRect();
    const free = (x, y) => document.elementFromPoint(x, y) === canvas;
    let want = null;
    for (const fx of [0.5, 0.3, 0.15, 0.7]) {
      for (let y = c.top + c.height * 0.45; y > c.top + 60 && !want; y -= 20) if (free(c.left + c.width * fx, y)) want = { x: c.left + c.width * fx, y };
      if (want) break;
    }
    if (want) for (let i = 0; i < 3; i++) { const q = m.project(p); m.panBy([c.left + q.x - want.x, c.top + q.y - want.y], { duration: 0 }); await wait(150); }
    await wait(700);  // значки тепловой карты переставляются после сдвига
    const q = m.project(p), x = c.left + q.x, y = c.top + q.y;
    const under = document.elementFromPoint(x, y);
    let near = null;
    for (let r = 14; r <= 70 && !near; r += 8)
      for (const [dx, dy] of [[r, 0], [-r, 0], [0, r], [0, -r], [r, r], [-r, -r], [r, -r], [-r, r]]) if (free(x + dx, y + dy)) { near = { x: x + dx, y: y + dy, r }; break; }
    return { x, y, onCanvas: under === canvas, under: under ? String(under.className || under.tagName).slice(0, 40) : null, near };
  }, [point, zoom]);
}

async function uiFlow(browser, base, [w, h], lang, apiCtx, staff, vi) {
  const dict = loadDict(lang);
  const tag = `${w}-${lang}`;
  const mobile = w < 761;
  const st = UI_STOPS[vi % UI_STOPS.length];  // остановка этого варианта (шаги 1–2 и 6)
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1,
    locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (["error", "warning"].includes(m.type()) && !NOISE.test(m.text())) errors.push(m.type() + ": " + m.text().slice(0, 200)); });
  // JPEG 70 %: кадр ~60 КБ вместо ~350 КБ PNG — отчёты лежат в Git.
  const shot = async (s) => { const f = path.join(OUT, `${tag}-${s}.jpg`); await page.screenshot({ path: f, type: "jpeg", quality: 70 }).catch(() => null); return path.basename(f); };
  const step = (s, name, ok, detail, file) => add(`UI ${tag}`, s, name, ok === null ? "NOT_RUN" : ok ? "PASS" : "FAIL", detail, file);

  const langRe = lang === "kk" ? /^ҚАЗ$/ : /^РУС$/;
  const menuRe = new RegExp("^" + T(dict, ["common.nav.menu", "shell.menu"], lang === "kk" ? "Мәзір" : "Меню") + "$", "i");
  const setLang = async () => { const b = await firstVisible(page.getByRole("button", { name: langRe })); if (b) { await b.click().catch(() => null); await sleep(1000); } return !!b; };
  // Кнопка из шапки; на телефоне — через «≡ Меню».
  const header = async (re, wait = 1200) => {
    let ok = await clickText(page, re, { wait });
    if (!ok && mobile && (await clickText(page, menuRe))) { ok = await clickText(page, re, { wait }); if (!ok) await page.keyboard.press("Escape").catch(() => null); }
    return ok;
  };
  const words = {
    resident: T(dict, ["common.role.resident", "shell.mode.resident"], lang === "kk" ? "Тұрғын" : "Житель"),
    akimat: T(dict, ["common.role.akimat", "shell.mode.akimat"], lang === "kk" ? "Әкімдік" : "Акимат"),
  };
  const setMode = (mode) => header(new RegExp("^" + esc(words[mode]) + "$", "i"));
  const fresh = async () => { await page.goto(base); await sleep(2500); await setLang(); };

  await page.goto(base);
  await page.waitForFunction(() => document.readyState === "complete" && document.body.innerText.length > 50, null, { timeout: 40000 }).catch(() => null);
  await sleep(2500);

  // 0. Язык: переключатель ҚАЗ/РУС в шапке.
  const hasLang = await setLang();
  let scr = await uiScreen(page);
  step("0", "шапка: ҚАЗ/РУС на виду, язык страницы переключился", hasLang && scr.lang === lang, { lang: scr.lang }, await shot("0-start"));
  step("0", "нет горизонтальной прокрутки", scr.scrollW <= scr.innerW, { scrollW: scr.scrollW, w: scr.innerW });
  step("0", "надписи не закрыты другими панелями (частично)", scr.clippedN === 0, { n: scr.clippedN, ex: scr.clipped });
  step("0", "нет ключей перевода и технических слов", scr.raw.length === 0 && scr.tech.length === 0, { raw: scr.raw, tech: scr.tech });
  step("0", "шрифт: нет текста мельче 14 px (основной ≥ 16 px)", scr.tinyN === 0, { tiny: scr.tinyN, ex: scr.tiny, under16: scr.smallN, ex16: scr.small });
  step("0", "зоны нажатия ≥ 40 px (цель — 48 px)", scr.under40.length === 0, { under40N: scr.under40N, under40: scr.under40, under48: `${scr.under48N}/${scr.targetsN}` });

  // 0а. Выбор языка запоминается: после перезагрузки страница остаётся на выбранном языке.
  if (hasLang) {
    await page.reload(); await sleep(3000);
    const kept = (await page.evaluate(() => document.documentElement.lang)) === lang;
    step("0", "выбор ҚАЗ/РУС сохраняется после перезагрузки страницы", kept);
    if (!kept) await setLang();  // дальше проверяем на нужном языке
  }

  // 0б. Казахский полный: на экране kk не должно остаться русских строк из экрана ru (кроме имён и чисел).
  if (lang === "kk") {
    const kkLines = await cyrLines(page), kkAll = await cyrLines(page, { all: true });
    if (await clickText(page, /^РУС$/, { wait: 1000 })) {
      const same = untranslated(kkLines, await cyrLines(page)), sameAll = untranslated(kkAll, await cyrLines(page, { all: true }));
      await setLang();
      step("0", "ҚАЗ: на экране нет строк, оставшихся по-русски", same.length === 0, { n: same.length, ex: same.slice(0, 8) });
      step("0", "ҚАЗ: во всей странице (с прокруткой панелей) нет строк по-русски", sameAll.length === 0, { n: sameAll.length, ex: sameAll.slice(0, 8) });
    }
  }

  // 1. Житель: «Сообщить о проблеме» → нажать на остановку → «Это здесь? Остановка «…»».
  const toResident = await setMode("resident");
  const startLabel = T(dict, "complaint.start.button", lang === "kk" ? "Мәселе туралы хабарлау" : "Сообщить о проблеме");
  if (!mobile) {
    const f = await focusToPrimary(page, textRe(startLabel));
    step("1", `клавиатура: Tab доходит до главной кнопки (≤ ${TAB_LIMIT}), рамка фокуса видна`, f.primary && f.ring && f.tabs <= TAB_LIMIT, f);
  }
  const started = await clickText(page, textRe(startLabel), { wait: 1500 });
  // Форма жалобы — диалог с заголовком шага «Где проблема?»; всё дальше ищем только внутри него
  // (на экране есть и другие поля и подписи: поиск улицы, панель «Карта жалоб»).
  const formRe = textRe(T(dict, "complaint.step2.title", lang === "kk" ? "Мәселе қай жерде?" : "Где проблема?"));
  const form = started ? await firstVisible(page.getByRole("dialog").filter({ hasText: formRe })) : null;
  step("1", `главная кнопка «${startLabel}» есть и открывает шаг «Где проблема?»`, started && !!form, { resident_view: toResident }, await shot("1-start"));
  let picked = false;
  if (form) {
    const names = [st.name, st.name_kk].filter(Boolean).map((x) => esc(x));
    const nameRe = new RegExp(names.join("|"), "i");
    const offered = async () => { await sleep(2500); return !!(await firstVisible(form.getByRole("button", { name: nameRe }))); };
    const pt = await showPoint(page, st.point, 17);
    let q = false;
    if (pt && !pt.onCanvas) {
      // Над остановкой — значок тепловой карты. Житель нажмёт именно на него: форма должна это принять.
      await tap(page, pt.x, pt.y);
      q = await offered();
      step("1", "нажатие по значку на остановке выбирает место (значок не перехватывает нажатие)", q, { under: pt.under });
      if (!q && pt.near) { await tap(page, pt.near.x, pt.near.y); q = await offered(); }  // обход для демо: нажать рядом
    } else if (pt) { await tap(page, pt.x, pt.y); q = await offered(); }
    step("1", `после нажатия на карту в форме предложена остановка «${st.name}»`, q, { point: pt, names }, await shot("1-target"));
    if (q) picked = await clickText(form, nameRe, { wait: 1500 });
    else {
      // Остановки в списке нет (например, R12 /targets не подключён) — берём «Примерное место», чтобы проверить шаг 2.
      picked = await clickText(form, textRe(T(dict, "complaint.step2.approximate", lang === "kk" ? "Шамамен орны" : "Примерное место")), { wait: 1500 });
      if (picked) add(`UI ${tag}`, "1", "обход: выбрано «Примерное место», шаг 2 проверяется дальше", "NOT_RUN", null);
    }
  } else step("1", `предложена остановка «${st.name}»`, null, "форма жалобы не открылась");

  // 2. Текст → категория от модели → «Отправить» → «Я тоже» (если уже сообщали) или «Обращение отправлено».
  if (picked) {
    const dlg = (await firstVisible(page.getByRole("dialog"))) || page;
    const box = await firstVisible(dlg.getByRole("textbox"));
    // Текст ведущего из DEMO_SCRIPT (смесь kk/ru) — ждём «Освещение», как обещает сценарий.
    if (box) await box.fill("Аялдамада жарық жоқ, вечером на остановке темно").catch(() => null);
    await sleep(3000);
    const cat = T(dict, "cat.lighting", lang === "kk" ? "Жарықтандыру" : "Освещение");
    const sugg = T(dict, "complaint.step3.suggested", lang === "kk" ? "Ұқсайды:" : "Похоже на:");
    const suggested = await visibleText(dlg, textRe(sugg));
    const catShown = await visibleText(dlg, new RegExp(esc(cat), "i"));
    step("2", `модель предложила категорию «${cat}» («${sugg}»)`, !!box && suggested && catShown, { textbox: !!box, suggested, catShown }, await shot("2-category"));
    const sent = await clickText(dlg, textRe(T(dict, ["complaint.step3.send", "complaint.send"], lang === "kk" ? "Жіберу" : "Отправить")), { wait: 3000 });
    const metooRe = new RegExp("^" + esc(T(dict, "complaint.step4.metoo", lang === "kk" ? "Мен де" : "Я тоже")) + "$", "i");
    const metoo = !!(await firstVisible(page.getByRole("button", { name: metooRe })));
    if (metoo) await clickText(page, metooRe, { wait: 2500 });  // DEMO_SCRIPT: «Я тоже» на существующем
    const done = await visibleText(page, textRe(T(dict, "complaint.step5.title", "Обращение отправлено")))
      || await visibleText(page, textRe(T(dict, "complaint.step5.metoo_title", "Ваш голос учтён")));
    step("2", "после отправки: «Я тоже» (если уже сообщали) → «Ваш голос учтён», иначе «Обращение отправлено»", sent && done, { sent, metoo, done }, await shot("2-sent"));
  } else step("2", "категория и «Я тоже»", null, "место на шаге 1 не выбрано");

  // 3. Акимат: тепловая карта у остановки — цвет и число рядом, легенда с числами.
  await fresh();
  await setMode("akimat");
  const heat = await page.evaluate(async (p) => {
    // eslint-disable-next-line no-undef
    const m = typeof map !== "undefined" && map && map.getStyle ? map : null;
    if (!m) return { map: false };
    m.jumpTo({ center: p, zoom: 15 }); await new Promise((ok) => setTimeout(ok, 1800));
    const layers = (m.getStyle().layers || []).filter((l) => /heat|^r07-/i.test(l.id)).map((l) => l.id);
    let rendered = 0; try { rendered = layers.length ? m.queryRenderedFeatures({ layers }).length : 0; } catch {}
    // Значки поверх карты (маркеры), на которых есть число людей. После перемещения карты R07 перерисовывает их не сразу —
    // ждём до 5 с, иначе на загруженной машине тест видит 0 значков при полной карте (так было в прогоне e6d9d80).
    let badges = 0;
    for (let i = 0; i < 25 && !badges; i++) {
      badges = [...document.querySelectorAll(".maplibregl-marker")].filter((e) => e.getBoundingClientRect().width > 0 && /\d/.test(e.innerText)).length;
      if (!badges) await new Promise((ok) => setTimeout(ok, 200));
    }
    return { map: true, layers: layers.length, rendered, badges };
  }, STOP.point);
  // Легенда: подпись из словаря R11 или запасная R07 (в ранних словарях ключа heat.legend ещё нет).
  // На телефоне R07 показывает компактную легенду без заголовка — тогда достаточно видимых ступеней «1–2» и «10+».
  let legend = false;
  for (const txt of [T(dict, "heat.legend", null), T(dict, "heat.legend.title", null), lang === "kk" ? "Қанша адам хабарлады" : "Сколько человек сообщили"])
    if (txt && !legend) legend = await visibleText(page, textRe(txt));
  if (!legend) legend = (await visibleText(page, /^1[–-]2$/)) && (await visibleText(page, /^10\+$/));
  step("3", "тепловая карта у остановки: цвет нарисован, рядом число людей, легенда с числами видна", heat.map && heat.rendered > 0 && heat.badges > 0 && legend, { ...heat, legend }, await shot("3-heat"));

  // 3б. DEMO_SCRIPT шаг 3.3: «Фильтры: Освещение, 30 дней → Сбросить». Пункт категории ищем вне табличек 3D-проектов.
  const allCatRe = new RegExp("^" + esc(T(dict, ["heat.category_all", "heat.filter.all_categories"], lang === "kk" ? "Барлық санаттар" : "Все категории")), "i");
  const opened = await clickText(page, allCatRe, { wait: 800 });
  const lightRe = new RegExp("^" + esc(T(dict, "cat.lighting", lang === "kk" ? "Жарықтандыру" : "Освещение")) + "$", "i");
  let chip = null;
  if (opened) { const l = page.getByRole("button", { name: lightRe });
    for (let i = 0; i < Math.min(await l.count(), 20) && !chip; i++) { const it = l.nth(i);
      if (await it.isVisible().catch(() => false) && !(await it.evaluate((e) => !!e.closest(".b3d-labels")).catch(() => true))) chip = it; } }
  if (chip) { await chip.click().catch(() => null); await sleep(1000); }
  await clickText(page, new RegExp("^30 " + (lang === "kk" ? "күн" : "дней") + "$", "i"), { wait: 800 });
  const resetRe = new RegExp("^" + esc(T(dict, ["heat.reset", "common.action.reset"], lang === "kk" ? "Тазарту" : "Сбросить")) + "$", "i");
  const reset = await clickText(page, resetRe, { wait: 1000 });
  const back = !!(await firstVisible(page.getByRole("button", { name: allCatRe })));
  step("3", "фильтры: «Освещение» + «30 дней» → «Сбросить» → снова «Все категории»", opened && !!chip && reset && back, { opened, chip: !!chip, reset, back });

  // 3в. «Горячие места» → место из списка: камера летит к нему, открывается карточка — значок места остаётся видно
  //     (так ведущий открывает место в шаге 3; R11 ночь, круг 16 — на телефоне его закрывала «Что построить?»).
  const hotRe = new RegExp("^" + esc(T(dict, "heat.hot_title", lang === "kk" ? "Шағымы көп орындар" : "Горячие места")), "i");
  const hotItems = page.locator("section").filter({ has: page.getByRole("heading", { name: hotRe }) }).getByRole("listitem").getByRole("button");
  const hot = [];
  let hotShot;
  // Число пунктов — до первого нажатия: пока открыта карточка, списка на экране нет.
  const nHot = Math.min(await hotItems.count().catch(() => 0), 3);
  for (let i = 0; i < nHot; i++) {
    await page.keyboard.press("Escape"); await sleep(700);
    const it = hotItems.nth(i);
    const title = ((await it.innerText().catch(() => "")) || "").replace(/\s+/g, " ").trim().slice(0, 50);
    if (!(await it.click({ timeout: 3000 }).then(() => true, () => false))) { hot.push({ title, clicked: false }); continue; }
    await sleep(2500);
    hot.push({ title, ...(await selectedPlace(page)) });
    if (i === 0) hotShot = await shot("3-hot");
  }
  const hotSeen = hot.filter((h) => h.badge);  // район в списке — без значка, его не считаем
  step("3", "«Горячие места» → место из списка: значок выбранного места виден на карте и ничем не закрыт",
    hotSeen.length ? hotSeen.every((h) => h.inView && !h.covered) : null, hot.length ? hot : "список «Горячие места» не найден", hotShot);
  await page.keyboard.press("Escape"); await sleep(700);

  // 4. «Картина дня».
  const dayRe = new RegExp("^" + esc(T(dict, ["common.nav.day", "shell.section.day", "akim.title"], lang === "kk" ? "Күн қорытындысы" : "Картина дня")) + "$", "i");
  const day = await header(dayRe, 2500);
  const soon = day ? await visibleText(page, textRe(T(dict, "shell.day.soon_title", "скоро появится"))) : false;
  const kpis = day ? await page.locator(".bk-kpi, .akim-kpi").filter({ visible: true }).count() : 0;
  const kpiText = day ? await visibleText(page, textRe(T(dict, "akim.kpi.in_progress", "В работе"))) : false;
  const overdue = day ? await visibleText(page, textRe(T(dict, "akim.kpi.overdue", "Просрочено"))) : false;
  step("4", "«Картина дня»: открылась, 4 крупных числа, «В работе», «Просрочено»", day && !soon && kpis >= 4 && kpiText && overdue, { day, placeholder_soon: soon, kpis, kpiText, overdue }, await shot("4-day"));

  // 5. Акимат: вход сотрудника → «Что построить?» → «Сквер» → место → «Поставить»; житель «За»; акимат «Удалить».
  await fresh();
  await setMode("akimat");
  const login = { opened: false, ok: false };
  if (staff && staff.user) {
    login.opened = await header(textRe(lang === "kk" ? "Қызметкерлерге" : "Для сотрудников"), 1800);
    const user = login.opened ? await firstVisible(page.locator("input[autocomplete=username], input[name=username]")) : null;
    const pass = login.opened ? await firstVisible(page.locator("input[type=password]")) : null;
    if (user && pass) {
      // Что видит сотрудник на форме входа: в ҚАЗ русских подписей быть не должно.
      if (lang === "kk") login.ru_in_kk = (await page.evaluate(() => document.body.innerText)).match(/Вход для сотрудника|Имя пользователя|Пароль|Войти\b|Учётную запись создаёт/g) || [];
      await user.fill(staff.user); await pass.fill(staff.pass); await pass.press("Enter");
      await sleep(2500);
      login.ok = !!(await firstVisible(page.getByRole("button", { name: /^(Выйти|Шығу)$/i })));
      login.tech = (await uiScreen(page)).tech;
      if (lang === "kk" && login.ok) login.ru_in_kk = [...new Set([...(login.ru_in_kk || []),
        ...((await page.evaluate(() => document.body.innerText)).match(/Кабинет редактора|Вы вошли|Новый объект|Обновить список|Черновики|Опубликованные|Архив|Выйти\b/g) || [])])];
    } else login.why = "нет полей имени и пароля";
  } else login.why = "нет учётной записи сотрудника";
  step("5", "вход сотрудника: «Для сотрудников» → имя и пароль → кабинет открыт", login.ok, login, await shot("5-login"));
  if (login.ok) {
    step("5", "кабинет сотрудника: нет технических слов (адреса API, роли сервера)", login.tech.length === 0, { tech: login.tech });
    if (lang === "kk") step("5", "ҚАЗ: форма входа и кабинет сотрудника по-казахски", login.ru_in_kk.length === 0, { ru: login.ru_in_kk });
    if (!(await clickText(page, /^(Закрыть кабинет|Кабинетті жабу)$/i))) await page.keyboard.press("Escape").catch(() => null);
    await sleep(800);
  }
  const catalog = await visibleText(page, textRe(T(dict, "proposal.catalog.title", "Что построить?")));
  // Карточка каталога: «Сквер» или «Сквер: поставить на карту» — не путать с табличкой «Сквер: проект 2027…».
  const kindRe = (k) => { const name = T(dict, "proposal.kind." + k, k);
    const aria = T(dict, "build3d.catalog.place", "{kind}: поставить на карту").replace("{kind}", name);
    return new RegExp("^(" + esc(name) + "|" + esc(aria) + ")$", "i"); };
  const kindsShown = async () => { const out = [];
    for (const k of ["square", "playground", "sports", "stop", "lighting"]) if (await firstVisible(page.getByRole("button", { name: kindRe(k) }))) out.push(k);
    return out; };
  let kinds = await kindsShown();
  // С B3 каталог свёрнут в одну кнопку «Что построить?» — человек сначала нажимает её.
  let unfolded = false;
  if (catalog && kinds.length === 0) {
    unfolded = await clickText(page, new RegExp("^" + esc(T(dict, "proposal.catalog.title", "Что построить?")) + "$", "i"), { wait: 1000 });
    kinds = await kindsShown();
  }
  step("5", "каталог «Что построить?»: сквер, площадка, спортплощадка, остановка, освещение", catalog && kinds.length === 5, { catalog, unfolded, kinds }, await shot("5-catalog"));
  if (catalog && kinds.includes("square") && login.ok) {
    const place = [PLACE[0], PLACE[1] + 0.0012 * vi];
    const kindName = T(dict, "proposal.kind.square", lang === "kk" ? "Гүлзар" : "Сквер");
    await showPoint(page, place, 17);
    await clickText(page, kindRe("square"), { wait: 1200 });
    const hint = await visibleText(page, textRe(T(dict, "proposal.place_hint", "Нажмите на карту, где поставить")));
    let pt = await showPoint(page, place, 17);
    if (pt && !pt.onCanvas && pt.near) pt = { ...pt, x: pt.near.x, y: pt.near.y };
    if (pt) { if (!mobile) await page.mouse.move(pt.x, pt.y); await tap(page, pt.x, pt.y); await sleep(1200); }
    // DEMO_SCRIPT 5.2: «повернуть ↺ ↻ при желании» — кнопки поворота есть, пока объект не поставлен.
    const rotR = await clickText(page, new RegExp("^" + esc(T(dict, "proposal.rotate_right", lang === "kk" ? "Оңға бұру" : "Повернуть вправо")) + "$", "i"), { wait: 500 });
    const rotL = await clickText(page, new RegExp("^" + esc(T(dict, "proposal.rotate_left", lang === "kk" ? "Солға бұру" : "Повернуть влево")) + "$", "i"), { wait: 500 });
    const placeRe = new RegExp("^" + esc(T(dict, "proposal.place", lang === "kk" ? "Орнату" : "Поставить")) + "$", "i");
    const placedClick = await clickText(page, placeRe, { wait: 4000 });
    const placedMsg = await visibleText(page, textRe(T(dict, "build3d.placed", "Проект поставлен")));
    const projRe = new RegExp("^" + esc(kindName) + ":.*2027", "i");
    const near = pt ? await nearestVisible(page.getByRole("button", { name: projRe }), pt) : null;
    step("5", `«${kindName}» → нажать на карту → ↺ ↻ → «Поставить»: «Проект поставлен», на карте табличка проекта 2027`, placedClick && placedMsg && !!near && near.d < 80 && rotR && rotL,
      { hint, rotate: [rotL, rotR], placedClick, placedMsg, label_px_from_place: near && near.d }, await shot("5-placed"));
    // DEMO_SCRIPT 5.2: «кнопка 3D справа — наклон».
    const pitch0 = await page.evaluate(() => (typeof map !== "undefined" && map.getPitch ? map.getPitch() : null));
    // У кнопки видимый текст «3D», а имя для экранного диктора — «Объёмный вид» (ключ common.map.view3d).
    const view3dRe = new RegExp("^(3D|" + esc(T(dict, ["common.map.view3d", "shell.map.view3d"], lang === "kk" ? "Көлемді көрініс" : "Объёмный вид")) + ")$", "i");
    const b3d = await clickText(page, view3dRe, { wait: 1500 });
    const pitch1 = await page.evaluate(() => (typeof map !== "undefined" && map.getPitch ? map.getPitch() : null));
    step("5", "кнопка «3D» наклоняет карту", b3d && pitch1 !== null && pitch1 > 20 && pitch1 > pitch0, { b3d, pitch0, pitch1 }, await shot("5-3d"));
    if (b3d && pitch1 > 20) { await clickText(page, view3dRe, { wait: 800 }); }  // вернуть плоский вид для следующих шагов

    // Житель: карточка проекта → «За».
    await setMode("resident");
    await sleep(1200);
    const p2 = await showPoint(page, place, 17);
    const lbl = p2 ? await nearestVisible(page.getByRole("button", { name: projRe }), p2) : null;
    if (lbl) { await tapEl(page, lbl.loc); await sleep(1500); }
    const upRe = new RegExp("^" + esc(T(dict, "proposal.vote_up", lang === "kk" ? "Жақтаймын" : "За")) + "(\\s|:|\\d|$)", "i");
    const voted = await clickText(page, upRe, { wait: 1800 });
    const saved = (await visibleText(page, textRe(T(dict, "proposal.vote_saved", "Голос учтён"))))
      || (await visibleText(page, textRe(T(dict, "build3d.card.your_vote_up", "Ваш голос: за"))));
    step("5", "житель: табличка проекта → карточка → «За» → «Голос учтён» / «Ваш голос: за»", !!lbl && voted && saved, { label: !!lbl, voted, saved }, await shot("5-vote"));

    // Акимат: «Удалить» — заодно уборка, чтобы следующий прогон начинал с тех же демо-данных.
    await setMode("akimat");
    await sleep(1200);
    const p3 = await showPoint(page, place, 17);
    const lbl2 = p3 ? await nearestVisible(page.getByRole("button", { name: projRe }), p3) : null;
    if (lbl2) { await tapEl(page, lbl2.loc); await sleep(1500); }
    const delClick = await clickText(page, new RegExp("^" + esc(T(dict, "proposal.delete", lang === "kk" ? "Жою" : "Удалить")) + "$", "i"), { wait: 2500 });
    const deleted = await visibleText(page, textRe(T(dict, "build3d.deleted", "Проект удалён")));
    step("5", "акимат: карточка проекта → «Удалить» → «Проект удалён»", delClick && deleted, { label: !!lbl2, delClick, deleted });
  } else {
    step("5", "постановка проекта и удаление", null, { catalog, kinds, login: login.ok });
    // Голос жителя всё равно проверяем — по демо-проекту seed-r14-demo (DEMO_SCRIPT: житель голосует с телефона).
    const sp = apiCtx && apiCtx.seededPoint;
    if (sp) {
      await setMode("resident");
      await sleep(1200);
      const p2 = await showPoint(page, sp, 17);
      const anyProj = textRe(T(dict, "build3d.card.open", "{kind}: проект {year}, открыть карточку"));
      const lbl = p2 ? await nearestVisible(page.getByRole("button", { name: anyProj }), p2) : null;
      if (lbl) { await tapEl(page, lbl.loc); await sleep(1500); }
      const upRe = new RegExp("^" + esc(T(dict, "proposal.vote_up", lang === "kk" ? "Жақтаймын" : "За")) + "(\\s|:|\\d|$)", "i");
      const voted = await clickText(page, upRe, { wait: 1800 });
      const saved = (await visibleText(page, textRe(T(dict, "proposal.vote_saved", "Голос учтён"))))
        || (await visibleText(page, textRe(T(dict, "build3d.card.your_vote_up", "Ваш голос: за"))));
      step("5", "житель: табличка демо-проекта → карточка → «За» → «Голос учтён» / «Ваш голос: за»", !!lbl && voted && saved, { label: !!lbl, voted, saved }, await shot("5-vote"));
    }
  }

  // 6. Акимат: карточка остановки → «Взять в работу» → «Отметить исправленным» → «Исправлено» (зелёный);
  //    житель: «Мои обращения» → статус «Исправлено».
  const fixedWord = T(dict, ["heat.fixed_word", "status.fixed"], lang === "kk" ? "Түзетілді" : "Исправлено");
  if (login.ok) {
    await setMode("akimat");
    const s = await showPoint(page, st.point, 17);
    if (s) await tap(page, s.x, s.y);  // в виде «Акимат» нажатие по значку остановки открывает её карточку
    await sleep(2500);
    const sel = await selectedPlace(page);
    step("6", "карточка места открыта: значок выбранного места виден на карте и ничем не закрыт (шторка, шапка, кнопки)",
      sel.badge ? sel.inView && !sel.covered : null, sel.badge ? sel : "значок выбранного места не найден (.r07-badge--selected)");
    const take =await clickText(page, textRe(T(dict, ["target.take", "heat.take"], lang === "kk" ? "Жұмысқа алу" : "Взять в работу")), { wait: 2000 });
    const fix = await clickText(page, textRe(T(dict, ["target.mark_fixed", "heat.mark_fixed"], "Отметить исправленным")), { wait: 2500 });
    // С заглавной буквы и без флага i: в легенде карты то же слово строчными («исправлено») — его не считаем.
    const fixedShown = await visibleText(page, new RegExp(esc(fixedWord)));
    const green = await visibleText(page, textRe(T(dict, "heat.fixed_until", "На карте зелёным до {date}")));
    // Нет ни «Взять в работу», ни «Отметить исправленным», а цель уже «Исправлено» — новых жалоб нет: проверять нечего.
    // Нет «Взять в работу», но есть «Отметить исправленным» — место уже «В работе» (так бывает в демо-наборе R07): верно.
    const nothingNew = !take && !fix && fixedShown;
    step("6", `акимат: карточка остановки → «Взять в работу» (если место ещё не в работе) → «Отметить исправленным» → «${fixedWord}», зелёным на карте`,
      nothingNew ? null : fix && fixedShown && green,
      { under: s && s.under, take, fix, fixedShown, green,
        note: nothingNew ? "у остановки нет новых жалоб — шаг 2 не отправил жалобу" : (!take && fix ? "место уже «В работе» — кнопки «Взять в работу» нет" : undefined) }, await shot("6-fixed"));
    if (!mobile && fixedShown) {
      await page.keyboard.press("Escape"); await sleep(800);
      const stillOpen = await visibleText(page, textRe(T(dict, "heat.fixed_until", "На карте зелёным до {date}")));
      step("6", "клавиатура: Esc закрывает карточку остановки", !stillOpen, { stillOpen });
    }
  } else step("6", "акимат отмечает исправленным", null, "нет входа сотрудника");
  const mineLabel = T(dict, ["common.nav.mine", "mine.title", "complaint.step5.to_mine"], lang === "kk" ? "Менің өтініштерім" : "Мои обращения");
  await setMode("resident");
  const mineOpen = await header(textRe(mineLabel), 1800);
  // Статус — в окне «Мои обращения»: шкала этапов обращения — список, его имя для экранного диктора = текущий статус
  // (у новой жалобы на шкале тоже написано «Исправлено», но имя списка — «Новое»; легенда карты не в счёт).
  const mineBox = mineOpen ? (await firstVisible(page.getByRole("dialog").filter({ hasText: textRe(mineLabel) }))) || page : null;
  const mineFixed = mineBox ? !!(await firstVisible(mineBox.getByRole("list", { name: new RegExp("^" + esc(T(dict, "status.fixed", fixedWord)) + "$") }))) : false;
  step("6", `житель: «${mineLabel}» → у обращения статус «${T(dict, "status.fixed", fixedWord)}»`, mineOpen && mineFixed, { mineOpen, mineFixed }, await shot("6-mine"));

  step("*", "консоль без ошибок (кроме шума среды: подложка, WebGL)", errors.length === 0, errors.slice(0, 6));
  await ctx.close();
}


// ------------------------------------------------------------------------------------------------ «нет связи»
// UX_BRIEF правило 7 и COMMON «ошибки сети»: при обрыве запросов API экран показывает понятное сообщение и
// «Повторить», а не пустое место; после восстановления связи «Повторить» возвращает данные.
// Отдельное окно браузера: оборванные запросы не попадают в проверку консоли основного прогона.
async function networkErrors(browser, base, [w, h], lang) {
  const dict = loadDict(lang);
  const tag = `${w}-${lang}`;
  const mobile = w < 761;
  const step = (name, ok, detail, file) => add(`UI ${tag}`, "E", name, ok === null ? "NOT_RUN" : ok ? "PASS" : "FAIL", detail, file);
  const netRe = new RegExp([T(dict, ["heat.error_title", "common.state.network_title"], lang === "kk" ? "Сервермен байланыс жоқ" : "Нет связи с сервером"),
    T(dict, "common.state.error_title", "Не получилось загрузить"), T(dict, "shell.day.error_title", "Картину дня не удалось открыть")]
    .filter(Boolean).map(esc).join("|"), "i");
  const retryRe = new RegExp("^" + esc(T(dict, ["heat.retry", "common.action.retry"], lang === "kk" ? "Қайталау" : "Повторить")) + "$", "i");
  const menuRe = new RegExp("^" + esc(T(dict, ["common.nav.menu", "shell.menu"], lang === "kk" ? "Мәзір" : "Меню")) + "$", "i");
  const header = async (page, re) => { let ok = await clickText(page, re, { wait: 2000 });
    if (!ok && mobile && (await clickText(page, menuRe))) ok = await clickText(page, re, { wait: 2000 }); return ok; };
  const cases = [
    { name: "тепловая карта", route: "**/api/civic/v2/heat**", mode: "akimat" },
    { name: "«Мои обращения»", route: "**/api/civic/v2/complaints/mine**", mode: "resident",
      open: (page) => header(page, textRe(T(dict, ["common.nav.mine", "mine.title"], lang === "kk" ? "Менің өтініштерім" : "Мои обращения"))) },
    { name: "«Картина дня»", route: "**/api/civic/v2/akim/summary**", mode: "akimat",
      open: (page) => header(page, new RegExp("^" + esc(T(dict, ["common.nav.day", "akim.title"], lang === "kk" ? "Күн қорытындысы" : "Картина дня")) + "$", "i")) },
  ];
  for (const c of cases) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    await page.addInitScript(([m, l]) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); } catch (e) { /* пусто */ } }, [c.mode, lang]);
    let broken = true;
    await page.route(c.route, (r) => (broken ? r.abort("internetdisconnected") : r.continue()));
    try {
      await page.goto(base); await sleep(3500);
      const lb = await firstVisible(page.getByRole("button", { name: lang === "kk" ? /^ҚАЗ$/ : /^РУС$/ }));
      if (lb) { await lb.click().catch(() => null); await sleep(800); }
      const opened = c.open ? await c.open(page) : true;
      await sleep(1500);
      const msg = await visibleText(page, netRe);
      const retry = await firstVisible(page.getByRole("button", { name: retryRe }));
      const f = path.join(OUT, `${tag}-E-${c.route.split("/").filter(Boolean).slice(-1)[0].replace(/\W+/g, "")}.jpg`);
      await page.screenshot({ path: f, type: "jpeg", quality: 70 }).catch(() => null);
      broken = false;
      let recovered = null;
      if (retry) { await retry.click().catch(() => null); await sleep(2500); recovered = !(await visibleText(page, netRe)); }
      step(`нет связи · ${c.name}: понятное сообщение и «Повторить»; после связи «Повторить» возвращает данные`,
        opened && msg && !!retry && recovered === true, { opened, message: msg, retry: !!retry, recovered }, path.basename(f));
    } catch (e) { step(`нет связи · ${c.name}`, false, String(e.message || e).slice(0, 200)); }
    await ctx.close();
  }
}

// ------------------------------------------------------------------------------------------------ main
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  let server = null, base = args.url, staff = args.user ? { user: args.user, pass: args.pass } : null, seeds = [];
  if (!base) { server = await startServer(); base = server.base; staff = server.staff; seeds = server.seeds; }
  let sha = "unknown";
  try { sha = execFileSync("git", ["rev-parse", "--short", "HEAD"], { cwd: ROOT }).toString().trim(); } catch {}
  console.log(`R10 e2e: сборка ${ROOT} @ ${sha}, сервер ${base}`);
  const browser = await chromium.launch();
  try {
    const apiCtx = await apiFlow(api(base), staff);
    let vi = 0;  // номер варианта экрана: у каждого своё место для проекта на шаге 5
    for (const size of SIZES) for (const lang of LANGS) {
      try { await uiFlow(browser, base, size, lang, apiCtx, staff, vi++); }
      catch (e) { add(`UI ${size[0]}-${lang}`, "!", "прогон экрана прервался", "FAIL", String(e.message || e).slice(0, 300)); }
      try { await networkErrors(browser, base, size, lang); }
      catch (e) { add(`UI ${size[0]}-${lang}`, "!", "прогон экрана прервался", "FAIL", String(e.message || e).slice(0, 300)); }
    }
  } finally {
    await browser.close();
    if (server) { server.srv.kill(); fs.rmSync(server.tmp, { recursive: true, force: true }); }
  }
  const counts = { PASS: 0, FAIL: 0, NOT_RUN: 0 };
  results.forEach((r) => counts[r.status]++);
  const meta = { root: ROOT, sha, base: args.url || "(свой сервер)", seeds, sizes: SIZES.map((s) => s.join("x")), langs: LANGS,
    when: new Date().toISOString(), node: process.version };
  fs.writeFileSync(path.join(OUT, "RESULT.json"), JSON.stringify({ meta, counts, results }, null, 1));
  const md = [`# R10 e2e · сценарий демо · ${sha}`, "", "```", JSON.stringify(meta), "```", "",
    `Итого: PASS ${counts.PASS}, FAIL ${counts.FAIL}, NOT_RUN ${counts.NOT_RUN}`, "", "| Слой | Шаг | Проверка | Итог | Подробно | Кадр |", "|---|---|---|---|---|---|",
    ...results.map((r) => `| ${r.layer} | ${r.step} | ${r.name} | **${r.status}** | ${r.detail ? JSON.stringify(r.detail).replace(/\|/g, "/").slice(0, 220) : ""} | ${r.shot || ""} |`)];
  fs.writeFileSync(path.join(OUT, "RESULT.md"), md.join("\n") + "\n");
  console.log("ИТОГ:", counts, "→", OUT);
  process.exit(counts.FAIL ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
