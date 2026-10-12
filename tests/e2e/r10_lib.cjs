// R10 · раунд 14 · общие помощники новых проверок (map_baseline.cjs, wave_checks.cjs, compare_baseline.cjs):
// разбор флагов, сервер сборки с временной базой (как run-city.bat), HTTP API v2, словари R11, поиск по видимым словам.
// demo_flow.cjs и demo_reset_check.cjs держат свои копии — их не трогаем, чтобы не менять проверенные прогоны.
"use strict";
const { spawn, execFileSync } = require("child_process");
const fs = require("fs"), path = require("path"), os = require("os"), net = require("net");

const parseArgs = (argv) => Object.fromEntries(argv.reduce((acc, a, i, all) => {
  if (a.startsWith("--")) acc.push([a.slice(2), all[i + 1] && !all[i + 1].startsWith("--") ? all[i + 1] : true]);
  return acc;
}, []));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PY = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no);
  s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

// Сервер сборки: init → seed-demo → seed-r14-demo (если есть) → сотрудник; app.py с CIVIC_DEMO=1 (как run-city.bat).
// База — во временной папке, удаляется в stop(). Ничего не пишет в репозиторий.
async function startServer(root, { demo = true, staff = true } = {}) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r10-lib-"));
  const db = path.join(tmp, "civic.sqlite3");
  const env = { ...process.env, CIVIC_DB_PATH: db, PYTHONDONTWRITEBYTECODE: "1", CIVIC_DEMO: demo ? "1" : "" };
  const cli = (argv, input) => execFileSync(PY, ["-B", "-m", "ui.civic_store", "--db", db, ...argv],
    { cwd: root, env, input, stdio: [input ? "pipe" : "ignore", "pipe", "pipe"] }).toString();
  cli(["init"]);
  cli(["seed-demo", "--package", "data/civic/astana/demo_synthetic.json"]);
  const seeds = ["seed-demo"];
  if (/seed-r14-demo/.test(cli(["--help"]))) { cli(["seed-r14-demo"]); seeds.push("seed-r14-demo"); }
  let account = null;
  if (staff) {
    const user = "r10-operator", pass = "R10-lib-" + Math.random().toString(36).slice(2) + "-Aa1!";
    try { cli(["create-editor", user, "--password-stdin"], pass + "\n"); account = { user, pass }; }
    catch (e) { account = { error: String(e.stderr || e.message).slice(0, 300) }; }
  }
  const port = await freePort();
  const srv = spawn(PY, ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: root, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  const base = `http://127.0.0.1:${port}/`;
  for (let i = 0; i < 150; i++) {
    try { if ((await fetch(base + "api/health")).ok) {
      return { base, staff: account, seeds, db,
        stop: async () => { srv.kill(); await new Promise((r) => (srv.exitCode !== null ? r() : srv.once("exit", r))); fs.rmSync(tmp, { recursive: true, force: true }); } };
    } } catch {}
    await sleep(200);
  }
  srv.kill();
  throw new Error("сервер сборки не запустился: " + srv.log.slice(-1500));
}

// HTTP API v2 (CONTRACT §7). ms — время ответа (для замеров эталона).
function api(base) {
  let cookie = null, csrf = null;
  const origin = new URL(base).origin;
  // device — id устройства жителя (заголовок X-Birge-Device, как complaint.js R09): «Мои обращения», «Я тоже», голоса.
  const call = async (method, p, body, staff, device) => {
    const headers = { "Content-Type": "application/json", Origin: origin };
    if (staff && cookie) { headers.Cookie = cookie; headers["X-CSRF-Token"] = csrf; }
    if (device) headers["X-Birge-Device"] = device;
    const t = performance.now();
    let res;
    try { res = await fetch(origin + p, { method, headers, body: body ? JSON.stringify(body) : undefined }); }
    catch (e) { return { status: 0, body: { error: String(e) }, ms: performance.now() - t }; }
    const text = await res.text();
    const ms = performance.now() - t;
    let json = null; try { json = JSON.parse(text); } catch {}
    return { status: res.status, body: json, text: json ? null : text.slice(0, 200), res, ms, bytes: text.length };
  };
  return {
    call,
    data: (r) => (r.body && r.body.data !== undefined && r.body.ok !== undefined ? r.body.data : r.body),
    async login(user, pass) {
      const r = await call("POST", "/api/civic/v1/session/login", { username: user, password: pass });
      const set = r.res && r.res.headers.get("set-cookie");
      if (r.status !== 200 || !set) return { ok: false, status: r.status };
      cookie = set.split(";")[0];
      const d = r.body && (r.body.data || r.body);
      csrf = d && (d.csrf_token || (d.session && d.session.csrf_token));
      return { ok: !!csrf, status: r.status };
    },
    cookie: () => cookie,
  };
}

// Словари R11: плоские ключи «a.b.c» → строка (формы числа — объект {one, few, many}).
function loadDict(root, lang) {
  const file = path.join(root, "web/civic/i18n", lang + ".json");
  if (!fs.existsSync(file)) return null;
  const flat = {};
  const walk = (o, p) => { for (const [k, v] of Object.entries(o)) {
    if (v && typeof v === "object" && !Object.keys(v).every((x) => ["one", "few", "many", "other"].includes(x))) walk(v, p + k + ".");
    else flat[p + k] = v; } };
  walk(JSON.parse(fs.readFileSync(file, "utf8")), "");
  return flat;
}
const T = (dict, key, fallback) => {
  for (const k of [].concat(key)) {
    const v = dict && dict[k];
    if (typeof v === "string") return v;
    if (v && (v.other || v.many || v.one)) return v.other || v.many || v.one;
  }
  return fallback;
};
const esc = (s) => String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
// Текст ключа без параметров: «Звоните {phone} сейчас» → регулярка по неизменной части.
const textRe = (s) => new RegExp(String(s).split(/\{[a-z_]+\}/).map((x) => x.trim()).filter(Boolean)
  .map((x) => x.replace(/[.*+?^${}()|[\]\\«»]/g, (m) => (m === "«" || m === "»" ? "[«»\"]?" : "\\" + m))).join(".*"), "i");
// Любой из вариантов текста (ключи словаря + запасные слова из POLISH_WAVE*.md).
const anyRe = (...xs) => new RegExp(xs.flat().filter(Boolean).map((x) => textRe(x).source).join("|"), "i");

async function firstVisible(loc, max = 40) {
  const n = Math.min(await loc.count().catch(() => 0), max);
  for (let i = 0; i < n; i++) if (await loc.nth(i).isVisible().catch(() => false)) return loc.nth(i);
  return null;
}
const clickText = async (scope, re, opts = {}) => {
  const loc = await firstVisible(scope.getByRole(opts.role || "button", { name: re }));
  if (!loc) return false;
  await loc.click({ timeout: 4000 }).catch(() => null);
  await sleep(opts.wait ?? 900);
  return true;
};
const visibleText = async (scope, re) => !!(await firstVisible(scope.getByText(re)));
// Кнопка шапки: сама кнопка → «≡ Меню» (FINAL-2 и раньше) → меню аватара FINAL-3 (R01 INTEGRATION §14.1: .birge-avatar →
// #birge-account role=menu: разделы, «Чей вид» menuitemradio, «Для сотрудников», «Выйти»). Возвращает true, если нажато.
async function headerClick(page, re, { wait = 1200, menuRe = null } = {}) {
  // Сама кнопка — но не аватар: его имя «Меню: вид, вход для сотрудников» совпадает с поиском «Для сотрудников» (R01 §21.6а).
  const own = await firstVisible(page.getByRole("button", { name: re }).and(page.locator(":not(.birge-avatar)")));
  if (own) { await own.click({ timeout: 4000 }).catch(() => null); await sleep(wait); return true; }
  if (menuRe && (await clickText(page, menuRe))) {
    if (await clickText(page, re, { wait })) return true;
    await page.keyboard.press("Escape").catch(() => null);
  }
  // Меню могло остаться открытым после выбора вида (menuitemradio): тогда искать в нём, а не нажимать аватар (он его закроет).
  let menu = await firstVisible(page.locator("#birge-account"));
  if (!menu) {
    const avatar = await firstVisible(page.locator(".birge-avatar"));
    if (!avatar) return false;
    await avatar.click({ timeout: 3000 }).catch(() => null);
    await sleep(500);
    menu = await firstVisible(page.locator("#birge-account"));
    if (!menu) return false;
  }
  for (const role of ["menuitemradio", "menuitem", "button", "link"]) {
    const it = await firstVisible(menu.getByRole(role, { name: re }));
    if (it) { await it.click({ timeout: 3000 }).catch(() => null); await sleep(wait); return true; }
  }
  await page.keyboard.press("Escape").catch(() => null);
  return false;
}

const tap = async (page, x, y) => { if (page.viewportSize().width < 1024) await page.touchscreen.tap(x, y); else await page.mouse.click(x, y); };
// Показать точку на карте на свободной от панелей части холста и вернуть её место на экране (как demo_flow.cjs).
async function showPoint(page, point, zoom = 17) {
  return page.evaluate(async ([p, z]) => {
    // eslint-disable-next-line no-undef
    const m = typeof map !== "undefined" && map && map.project ? map : null;
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
    await wait(700);
    const q = m.project(p), x = c.left + q.x, y = c.top + q.y;
    const under = document.elementFromPoint(x, y);
    let near = null;
    for (let r = 14; r <= 70 && !near; r += 8)
      for (const [dx, dy] of [[r, 0], [-r, 0], [0, r], [0, -r], [r, r], [-r, -r], [r, -r], [-r, r]]) if (free(x + dx, y + dy)) { near = { x: x + dx, y: y + dy, r }; break; }
    return { x, y, onCanvas: under === canvas, under: under ? String(under.className || under.tagName).slice(0, 40) : null, near };
  }, [point, zoom]);
}
// Ключ словаря по русскому тексту (R11 ещё не дал ключ — ищем по слову из POLISH_WAVE*.md) → тот же ключ в kk.
function keyByText(dict, re) { for (const [k, v] of Object.entries(dict || {})) { const s = typeof v === "string" ? v : v && (v.many || v.other || v.one); if (s && re.test(s)) return k; } return null; }

// Ждать условие в странице, вернуть мс от начала ожидания (null — не дождались).
async function timeUntil(page, fn, arg, timeout = 15000) {
  const t = Date.now();
  try { await page.waitForFunction(fn, arg, { timeout, polling: 50 }); return Date.now() - t; } catch { return null; }
}

const median = (xs) => { const v = xs.filter((x) => typeof x === "number").sort((a, b) => a - b); if (!v.length) return null;
  const m = v.length >> 1; return v.length % 2 ? v[m] : Math.round((v[m - 1] + v[m]) / 2); };

function buildSha(root) {
  try { return execFileSync("git", ["rev-parse", "--short", "HEAD"], { cwd: root }).toString().trim(); } catch { return "unknown"; }
}
function machine() {
  const cpus = os.cpus();
  return { cpu: cpus[0] && cpus[0].model, cores: cpus.length, mem_gb: Math.round(os.totalmem() / 2 ** 30), platform: `${os.platform()} ${os.release()}`, node: process.version };
}

module.exports = { parseArgs, sleep, PY, startServer, api, loadDict, T, esc, textRe, anyRe, firstVisible, clickText, visibleText, headerClick,
  tap, showPoint, keyByText, timeUntil, median, buildSha, machine };
