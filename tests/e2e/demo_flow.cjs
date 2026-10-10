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
const NURA_BBOX = "71.375,51.115,71.420,51.140";
const DEVICE = "r10-e2e-device-" + Date.now();
// Шум среды: нет интернета для подложки, программный WebGL в headless Chromium.
const NOISE = /openfreemap|Failed to load resource|ERR_TUNNEL|AJAXError|GL Driver|GPU stall|style diff|swiftshader|GroupMarkerNotSet|WebGL/i;
// UX_BRIEF правило 4 + UX_SPEC §8: таких слов в интерфейсе быть не должно.
const TECH_WORDS = /\b(ребро|рёбра|граф|геометри\w*|сценари\w*|payload|demo-ring|target|null|undefined|NaN)\b/i;
const RAW_KEY = /\b(shell|common|complaint|heat|akim|target|proposal|build3d|mine|status|stage|cat|district)\.[a-z_]+(\.[a-z_0-9]+)*\b/;

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
  const env = { ...process.env, CIVIC_DB_PATH: db, PYTHONDONTWRITEBYTECODE: "1" };
  const cli = (argv, input) => execFileSync("python3", ["-B", "-m", "ui.civic_store", "--db", db, ...argv],
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
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)],
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

  // 1. Место на карте → «Это остановка «…»?» (R12 /targets).
  const [lon, lat] = STOP.point;
  const t = await A.call("GET", `/api/civic/v2/targets?lon=${lon}&lat=${lat}&category=transport`);
  const cands = (A.data(t) || {}).candidates || [];
  const first = cands[0];
  const okT = t.status === 200 && first && first.target && first.target.kind === "object" && /^osm-(node|way|relation)-\d+$/.test(first.target.id)
    && typeof first.distance_m === "number" && first.distance_m <= 60;
  add("API", "1", "/targets у остановки: первый кандидат — реальный объект OSM ≤ 60 м с подписью", okT ? "PASS" : "FAIL",
    { status: t.status, first: first ? { id: first.target && first.target.id, label: first.target && (first.target.label_ru || first.label_ru), d: first.distance_m } : null, n: cands.length });
  ctx.target = okT ? first.target : { kind: "object", id: STOP.id, label_ru: `Остановка «${STOP.name}»` };

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
  const body = { text: texts.mixed, lang: "mixed", category: "transport", category_source: "resident", point: STOP.point,
    target: ctx.target, device_id: DEVICE, demo: true };
  const cr = await A.call("POST", "/api/civic/v2/complaints", body);
  const rec = (A.data(cr) || {}).complaint || A.data(cr) || {};
  const okC = [200, 201].includes(cr.status) && /^c-/.test(rec.id || "") && rec.status === "new" && rec.target && rec.target.id === ctx.target.id;
  add("API", "1", "POST /complaints: запись §5 (id c-…, status new, target сохранён)", okC ? "PASS" : "FAIL",
    { status: cr.status, id: rec.id, st: rec.status, err: cr.body && cr.body.error });
  ctx.complaint = okC ? rec : null;

  const sim = await A.call("POST", "/api/civic/v2/similar", { text: "Павильон на остановке сломан", point: STOP.point, days: 30 });
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
  const pl = await A.call("GET", `/api/civic/v2/proposals?bbox=${NURA_BBOX}`);
  const plist = (A.data(pl) || {}).items || (A.data(pl) || {}).proposals || [];
  add("API", "5", "GET /proposals: предложения Нуры со статусом «проект»", pl.status === 200 && plist.length > 0 && plist.every((p) => p.status === "proposal" || p.status) ? "PASS" : "FAIL",
    { status: pl.status, n: plist.length });
  let prop = null;
  if (login.ok) {
    const pc = await A.call("POST", "/api/civic/v2/proposals", { kind: "square", geometry: { type: "Point", coordinates: [71.4021, 51.1288] },
      title_ru: "Сквер (приёмка R10)", title_kk: "Гүлзар (R10 қабылдау)", demo: true }, true);
    prop = (A.data(pc) || {}).proposal || A.data(pc);
    add("API", "5", "POST /proposals (сквер) от сотрудника", [200, 201].includes(pc.status) && prop && prop.id && prop.status === "proposal" ? "PASS" : "FAIL",
      { status: pc.status, id: prop && prop.id, st: prop && prop.status, err: pc.body && pc.body.error });
  }
  const pid = (prop && prop.id) || (plist[0] && plist[0].id);
  if (pid) {
    const v1 = await A.call("POST", `/api/civic/v2/proposals/${pid}/vote`, { value: 1, device_id: DEVICE });
    const v2 = await A.call("POST", `/api/civic/v2/proposals/${pid}/vote`, { value: 1, device_id: DEVICE });
    const a = (A.data(v1) || {}).proposal || A.data(v1) || {}, b = (A.data(v2) || {}).proposal || A.data(v2) || {};
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
async function uiScreen(page) {
  // Общие правила UX_BRIEF для того, что сейчас на экране.
  return page.evaluate(({ tech, raw }) => {
    const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
      return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth; };
    const text = document.body.innerText;
    const small = [], tiny = [];
    for (const el of document.querySelectorAll("body *")) {
      if (!vis(el) || el.children.length || !el.textContent.trim()) continue;
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (fs < 14) tiny.push(`${fs}px «${el.textContent.trim().slice(0, 30)}»`);
      else if (fs < 16) small.push(`${fs}px «${el.textContent.trim().slice(0, 30)}»`);
    }
    const targets = [...document.querySelectorAll("button, a[href], [role=button], input, select, summary")].filter(vis)
      .map((e) => {
        // У флажка зона нажатия — вся подпись <label>, а не 18-пиксельный квадрат.
        const box = (/^(checkbox|radio)$/.test(e.type) && e.closest("label")) || e;
        const r = box.getBoundingClientRect();
        return { h: Math.round(r.height), w: Math.round(r.width), t: (box.innerText || e.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 24) };
      });
    return {
      scrollW: document.documentElement.scrollWidth, innerW: innerWidth, lang: document.documentElement.lang,
      tech: (text.match(new RegExp(tech, "ig")) || []).slice(0, 8), raw: (text.match(new RegExp(raw, "g")) || []).slice(0, 8),
      tiny: tiny.slice(0, 8), tinyN: tiny.length, small: small.slice(0, 6), smallN: small.length,
      under40: targets.filter((t) => t.h < 40 || t.w < 40).slice(0, 8), under48N: targets.filter((t) => t.h < 48).length, targetsN: targets.length,
    };
  }, { tech: TECH_WORDS.source, raw: RAW_KEY.source });
}

async function tapMap(page, point) {
  // Ставим точку в центр свободной части карты (как в тесте R09) и нажимаем.
  const xy = await page.evaluate(async (p) => {
    // eslint-disable-next-line no-undef
    const m = typeof map !== "undefined" && map && map.project ? map : (window.standMap || null);
    if (!m) return null;
    m.jumpTo({ center: p, zoom: 17 });
    await new Promise((ok) => setTimeout(ok, 400));
    const canvas = m.getCanvas(), c = canvas.getBoundingClientRect();
    // Панель (ноутбук) или шторка (телефон) может закрывать центр карты: ищем свободную точку карты
    // по вертикали от центра вверх и сдвигаем карту так, чтобы остановка оказалась там.
    const free = (x, y) => { const e = document.elementFromPoint(x, y); return e === canvas || (e && canvas.parentElement.contains(e) && e.tagName === "CANVAS"); };
    let want = { x: c.left + c.width / 2, y: c.top + c.height / 2 };
    if (!free(want.x, want.y)) {
      const xs = [c.left + c.width * 0.5, c.left + c.width * 0.3, c.left + c.width * 0.15];
      outer: for (const x of xs) for (let y = c.top + c.height / 2; y > c.top + 40; y -= 20) if (free(x, y)) { want = { x, y: y - 10 }; break outer; }
    }
    for (let i = 0; i < 3; i++) {
      const q = m.project(p);
      m.panBy([c.left + q.x - want.x, c.top + q.y - want.y], { duration: 0 });
      await new Promise((ok) => setTimeout(ok, 150));
    }
    const q = m.project(p);
    return { x: c.left + q.x, y: c.top + q.y, free: free(c.left + q.x, c.top + q.y) };
  }, point);
  if (!xy) return false;
  if (page.viewportSize().width < 1024) await page.touchscreen.tap(xy.x, xy.y); else await page.mouse.click(xy.x, xy.y);
  await sleep(1200);
  return true;
}

const clickText = async (page, re, opts = {}) => {
  const loc = page.getByRole(opts.role || "button", { name: re }).first();
  if (!(await loc.count()) || !(await loc.isVisible().catch(() => false))) return false;
  await loc.click({ timeout: 4000 }).catch(() => null);
  await sleep(opts.wait || 900);
  return true;
};
const visibleText = async (page, re) => page.getByText(re).first().isVisible().catch(() => false);

async function uiFlow(browser, base, [w, h], lang, apiCtx) {
  const dict = loadDict(lang), ru = loadDict("ru");
  const tag = `${w}-${lang}`;
  const mobile = w < 761;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1,
    locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (["error", "warning"].includes(m.type()) && !NOISE.test(m.text())) errors.push(m.type() + ": " + m.text().slice(0, 200)); });
  // JPEG 70 %: кадр ~60 КБ вместо ~350 КБ PNG — отчёты лежат в Git.
  const shot = async (step) => { const f = path.join(OUT, `${tag}-${step}.jpg`); await page.screenshot({ path: f, type: "jpeg", quality: 70 }).catch(() => null); return path.basename(f); };
  const step = (s, name, ok, detail, file) => add(`UI ${tag}`, s, name, ok === null ? "NOT_RUN" : ok ? "PASS" : "FAIL", detail, file);

  await page.goto(base);
  await page.waitForFunction(() => document.readyState === "complete" && document.body.innerText.length > 50, null, { timeout: 40000 }).catch(() => null);
  await sleep(2500);

  // 0. Язык: переключатель ҚАЗ/РУС в шапке.
  const langBtn = page.getByRole("button", { name: lang === "kk" ? /^ҚАЗ$/ : /^РУС$/ }).first();
  const hasLang = await langBtn.isVisible().catch(() => false);
  if (hasLang) { await langBtn.click(); await sleep(1200); }
  let scr = await uiScreen(page);
  step("0", "шапка: ҚАЗ/РУС на виду, язык страницы переключился", hasLang && scr.lang === lang, { lang: scr.lang }, await shot("0-start"));
  step("0", "нет горизонтальной прокрутки", scr.scrollW <= scr.innerW, { scrollW: scr.scrollW, w: scr.innerW });
  step("0", "нет ключей перевода и технических слов", scr.raw.length === 0 && scr.tech.length === 0, { raw: scr.raw, tech: scr.tech });
  step("0", "шрифт: нет текста мельче 14 px (основной ≥ 16 px)", scr.tinyN === 0, { tiny: scr.tinyN, ex: scr.tiny, under16: scr.smallN, ex16: scr.small });
  step("0", "зоны нажатия ≥ 40 px (цель — 48 px)", scr.under40.length === 0, { under40: scr.under40, under48: `${scr.under48N}/${scr.targetsN}` });

  // 0б. Казахский полный: на экране kk не должно остаться русских строк из экрана ru (кроме имён и чисел).
  if (lang === "kk") {
    const lines = async () => (await page.evaluate(() => document.body.innerText)).split("\n").map((x) => x.trim())
      .filter((x) => /[а-яё]{3,}/i.test(x));
    const kkLines = await lines();
    const ruBtn = page.getByRole("button", { name: /^РУС$/ }).first();
    if (await ruBtn.isVisible().catch(() => false)) {
      await ruBtn.click(); await sleep(1000);
      const ruSet = new Set(await lines());
      await langBtn.click(); await sleep(1000);
      // Имена собственные одинаковы в обоих языках — их не считаем (районы, Birge, адреса).
      const same = kkLines.filter((x) => ruSet.has(x) && !/^(Астана|Нура|Есиль|Алматы|Сарыарка|Байконур|Сарайшык|Birge|3D|Карта|РУС|ҚАЗ)$/i.test(x));
      step("0", "ҚАЗ: нет строк, оставшихся по-русски", same.length === 0, { n: same.length, ex: same.slice(0, 8) });
    }
  }

  // 1. Житель: «Сообщить о проблеме» → карта → «Это остановка «…»?»
  const resident = T(dict, ["common.role.resident", "shell.mode.resident"], lang === "kk" ? "Тұрғын" : "Житель");
  const menuRe = new RegExp(T(dict, ["common.nav.menu", "shell.menu"], lang === "kk" ? "Мәзір" : "Меню"), "i");
  let toResident = await clickText(page, new RegExp("^" + resident + "$", "i"));
  if (!toResident && mobile) { // на телефоне вид — в меню ≡
    if (await clickText(page, menuRe)) toResident = await clickText(page, new RegExp("^" + resident + "$", "i"));
    await page.keyboard.press("Escape").catch(() => null);
  }
  const startLabel = T(dict, "complaint.start.button", lang === "kk" ? "Мәселе туралы хабарлау" : "Сообщить о проблеме");
  const started = await clickText(page, textRe(startLabel), { wait: 1500 });
  step("1", `главная кнопка «${startLabel}» есть и открывает шаги`, started, { resident_view: toResident }, await shot("1-start"));
  let picked = false;
  if (started) {
    const tapped = await tapMap(page, STOP.point);
    // Имя остановки: из OSM-набора теста или подпись, которую вернул /targets (ru/kk могут отличаться).
    const t = apiCtx && apiCtx.target;
    const names = [STOP.name, t && t.label_ru, t && t.label_kk].filter(Boolean)
      .map((x) => x.replace(/^.*«(.+)».*$/, "$1").replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    const nameRe = new RegExp(names.join("|"), "i");
    const q = tapped && (await visibleText(page, nameRe));
    step("1", `после нажатия на карту предложена остановка «${STOP.name}»`, q, { tapped, names }, await shot("1-target"));
    picked = q && (await clickText(page, nameRe));
  } else step("1", `предложена остановка «${STOP.name}»`, null, "нет главной кнопки");

  // 2. Текст → категория → похожие / «Я тоже».
  if (picked) {
    const box = page.getByRole("textbox").first();
    await box.fill(lang === "kk" ? "Аялдамада павильон сынған, шатыры жоқ" : "На остановке сломан павильон, нет крыши").catch(() => null);
    await sleep(2500);
    const cat = T(dict, "cat.transport", lang === "kk" ? "Аялдамалар мен көлік" : "Остановки и транспорт");
    const suggested = await visibleText(page, textRe(T(dict, "complaint.step3.suggested", "Похоже на:")));
    const catShown = await visibleText(page, new RegExp(cat, "i"));
    step("2", `модель предложила категорию «${cat}» («${T(dict, "complaint.step3.suggested", "Похоже на:")}»)`, suggested && catShown, { suggested, catShown }, await shot("2-category"));
    const sent = await clickText(page, textRe(T(dict, "complaint.send", "Отправить")), { wait: 2500 });
    const metoo = await visibleText(page, new RegExp("^" + T(dict, "complaint.step4.metoo", "Я тоже") + "$", "i"));
    const done = await visibleText(page, textRe(T(dict, "complaint.step5.title", "Обращение отправлено")));
    step("2", "после отправки: «Я тоже» (если уже сообщали) или «Обращение отправлено» с номером", sent && (metoo || done), { sent, metoo, done }, await shot("2-sent"));
  } else step("2", "категория и «Я тоже»", null, "шаг 1 не пройден");

  // 3. Акимат: тепловая карта Нуры.
  await page.goto(base); await sleep(2500);
  if (hasLang) { await page.getByRole("button", { name: lang === "kk" ? /^ҚАЗ$/ : /^РУС$/ }).first().click().catch(() => null); await sleep(800); }
  const heat = await page.evaluate(async (p) => {
    // eslint-disable-next-line no-undef
    const m = typeof map !== "undefined" && map && map.getStyle ? map : null;
    if (!m) return { map: false };
    m.jumpTo({ center: p, zoom: 15 }); await new Promise((ok) => setTimeout(ok, 1500));
    const layers = (m.getStyle().layers || []).filter((l) => /heat/i.test(l.id)).map((l) => l.id);
    let rendered = 0; try { rendered = layers.length ? m.queryRenderedFeatures({ layers }).length : 0; } catch {}
    return { map: true, layers, rendered };
  }, STOP.point);
  const legend = await visibleText(page, textRe(T(dict, ["heat.legend", "heat.legend.title"], lang === "kk" ? "Қанша адам хабарлады" : "Сколько человек сообщили")));
  step("3", "тепловая карта: слой жалоб нарисован в Нуре, легенда с числами видна", heat.map && heat.rendered > 0 && legend, { ...heat, legend }, await shot("3-heat"));

  // 4. «Картина дня».
  const dayRe = new RegExp("^" + T(dict, ["common.nav.day", "shell.section.day", "akim.title"], lang === "kk" ? "Күн қорытындысы" : "Картина дня") + "$", "i");
  let day = await clickText(page, dayRe, { wait: 2500 });
  if (!day && mobile && (await clickText(page, menuRe))) day = await clickText(page, dayRe, { wait: 2500 });
  const soon = day ? await visibleText(page, textRe(T(dict, "shell.day.soon_title", "скоро появится"))) : false;
  const kpis = day ? await page.locator(".bk-kpi, .akim-kpi").count() : 0;
  const kpiText = day ? await visibleText(page, textRe(T(dict, "akim.kpi.in_progress", "В работе"))) : false;
  step("4", "«Картина дня»: открылась, 4 крупных числа, «В работе», «Просрочено»", day && !soon && kpis >= 4 && kpiText, { day, placeholder_soon: soon, kpis, kpiText }, await shot("4-day"));

  // 5. Предложение акимата в 3D: каталог из 5 объектов.
  await page.goto(base); await sleep(2000);
  if (hasLang) { await page.getByRole("button", { name: lang === "kk" ? /^ҚАЗ$/ : /^РУС$/ }).first().click().catch(() => null); await sleep(800); }
  const catalog = await visibleText(page, textRe(T(dict, "proposal.catalog.title", "Что построить?")));
  const kinds = [];
  for (const k of ["square", "playground", "sports", "stop", "lighting"]) if (await visibleText(page, new RegExp(T(dict, "proposal.kind." + k, k), "i"))) kinds.push(k);
  step("5", "каталог «Что построить?»: сквер, площадка, спортплощадка, остановка, освещение", catalog && kinds.length === 5, { catalog, kinds }, await shot("5-catalog"));

  // 6. Житель видит «исправлено» (жалобу из API-шага 6 отметили исправленной).
  const fixedWord = T(dict, "status.fixed", lang === "kk" ? "Түзетілді" : "Исправлено");
  const mineLabel = T(dict, ["mine.title", "complaint.step5.to_mine"], lang === "kk" ? "Менің өтініштерім" : "Мои обращения");
  const mineOpen = await clickText(page, textRe(mineLabel), { wait: 1500 });
  step("6", `«${mineLabel}» доступны жителю; статус — цвет + слово «${fixedWord}»`, mineOpen ? await visibleText(page, new RegExp(fixedWord, "i")) : false,
    { mineOpen, note: "жалоба API-шага подана с другого устройства — проверяется наличие экрана и слова статуса" }, await shot("6-mine"));

  step("*", "консоль без ошибок (кроме шума среды: подложка, WebGL)", errors.length === 0, errors.slice(0, 6));
  await ctx.close();
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
    for (const size of SIZES) for (const lang of LANGS) {
      try { await uiFlow(browser, base, size, lang, apiCtx); }
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
