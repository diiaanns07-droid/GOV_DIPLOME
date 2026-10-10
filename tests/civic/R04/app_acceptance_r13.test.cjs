/* R04 round 13 acceptance in a REAL application tree: app.py (R01 shell + gateway, R02 store, R03 map) with this editor.
 * Run on this branch (base 56538a3 + editor):      R04_APP=1 node --test tests/civic/R04/app_acceptance_r13.test.cjs
 * Run on another tree (e.g. a temporary assembly):  R04_APP=1 R04_APP_ROOT=<tree> R04_APP_LABEL=<name> [R04_APP_PATCHED=1] node --test ...
 *   R04_APP_PATCHED=1 also runs the checks that need R01 to apply research/round-13-results/R04/r01_editor_integration.patch
 *   (map getter, /staff/meta and /import-candidates through the gateway, archive not opened on the public map).
 * Screenshots of the real interface: R04_SCREENSHOTS=1 -> research/round-13-results/R04/screenshots/app13-<label>-*.jpg
 * Each run: a fresh SQLite in a temporary directory OUTSIDE the repository (never the working DB), the synthetic demo
 * package, two test editors with random passwords via --password-stdin; app.py on 127.0.0.1 only; all removed after.
 * Test records are titled «ТЕСТ R04 (синтетика)» and marked synthetic, except the import test (labelled observed only to
 * pass through R02's import path, with an example.org source, as R02's own tests do). Without R04_APP=1 or Playwright: NOT_RUN.
 */
"use strict";
const { describe, it, before, after } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const fs = require("fs");
const os = require("os");
const net = require("net");
const crypto = require("crypto");
const { spawn, spawnSync } = require("child_process");
const { loadPlaywright, sleep } = require("./e2e_helpers.cjs");

const PW = loadPlaywright();
const REPO = path.resolve(__dirname, "../../..");
const ROOT = process.env.R04_APP_ROOT ? path.resolve(process.env.R04_APP_ROOT) : REPO;
const LABEL = (process.env.R04_APP_LABEL || "branch").replace(/[^a-z0-9-]/gi, "");
const PATCHED = process.env.R04_APP_PATCHED === "1";
const SHOTS = path.join(REPO, "research/round-13-results/R04/screenshots");
const PY = process.env.PYTHON || "python3";
const skip = !PW ? "playwright not installed" : process.env.R04_APP !== "1" ? "set R04_APP=1 to start app.py with a temporary DB" : false;
const ed = (s) => "#civic-editor-root " + s;
const fk = (k) => ed(`[data-fk="${k}"]`);
const freePort = () => new Promise((resolve, reject) => { const s = net.createServer(); s.once("error", reject); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => resolve(p)); }); });

describe("R04 round 13 in the real app (" + LABEL + (PATCHED ? ", R01 patch applied" : "") + ")", { skip }, () => {
  let tmp, env, server, base, browser;
  const users = {}, log = [], notes = {};
  const cli = (args, input) => {
    const r = spawnSync(PY, ["-B", "-m", "ui.civic_store"].concat(args), { cwd: ROOT, env, input, encoding: "utf8" });
    if (r.status !== 0) throw new Error("civic_store " + args[0] + " failed: " + (r.stderr || r.stdout).slice(0, 400));
    return r.stdout;
  };
  before(async () => {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), "civic-r04-app13-"));
    env = Object.assign({}, process.env, { CIVIC_DB_PATH: path.join(tmp, "civic.sqlite3"), PYTHONDONTWRITEBYTECODE: "1" });
    cli(["init"]);
    cli(["seed-demo", "--package", "data/civic/astana/demo_synthetic.json"]);
    for (const u of ["r04a", "r04b"]) { users[u] = crypto.randomBytes(15).toString("base64url"); cli(["create-editor", u, "--password-stdin"], users[u] + "\n"); }
    const port = await freePort();
    base = "http://127.0.0.1:" + port;
    server = spawn(PY, ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"], detached: true });
    server.stdout.on("data", (d) => log.push(String(d)));
    server.stderr.on("data", (d) => log.push(String(d)));
    for (let i = 0; i < 120; i++) { try { const r = await fetch(base + "/api/civic/v1/session"); if (r.ok) break; } catch (e) { /* starting */ } await sleep(500); }
    browser = await PW.chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-gl=swiftshader", "--ignore-gpu-blocklist"] });
    if (process.env.R04_SCREENSHOTS === "1") fs.mkdirSync(SHOTS, { recursive: true });
  });
  after(async () => {
    if (process.env.R04_EVIDENCE === "1") {
      const dir = path.join(REPO, "research/round-13-results/R04/evidence");
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, "app13-" + LABEL + ".json"), JSON.stringify({ root: path.relative(REPO, ROOT) || ".", patched: PATCHED, notes }, null, 1) + "\n");
    }
    if (browser) await browser.close();
    if (server) { try { process.kill(-server.pid, "SIGTERM"); } catch (e) { try { server.kill("SIGTERM"); } catch (x) { /* gone */ } } }
    await sleep(300);
    if (tmp) fs.rmSync(tmp, { recursive: true, force: true });
    if (log.some((l) => /Traceback/.test(l))) console.log(log.join("").slice(-3000));
  });

  const shot = async (p, name) => { if (process.env.R04_SCREENSHOTS === "1") await p.screenshot({ path: path.join(SHOTS, "app13-" + LABEL + "-" + name + ".jpg"), type: "jpeg", quality: 80 }); };
  async function newPage(viewport) {
    const ctx = await browser.newContext({ viewport: viewport || { width: 1440, height: 900 }, locale: "ru-RU", timezoneId: "Asia/Almaty" });
    const p = await ctx.newPage();
    p.errors = []; p.on("pageerror", (e) => p.errors.push(e.message)); p.on("dialog", (d) => d.accept());
    return p;
  }
  async function openApp(p, opts) {
    await p.goto(base + "/", { waitUntil: "domcontentloaded" });
    await p.waitForSelector("#civic-staff-button:not([hidden])", { timeout: 30000 });
    if (!(opts && opts.early)) await p.waitForFunction(() => typeof mapReady !== "undefined" && !!mapReady, null, { timeout: 30000 }).catch(() => {});
    await p.click("#civic-staff-button");
    await p.waitForSelector(ed(".civic-r04"));
  }
  async function login(p, u) {
    await p.waitForSelector(fk("login-user"));
    await p.fill(fk("login-user"), u); await p.fill(fk("login-pass"), users[u]);
    await p.press(fk("login-pass"), "Enter");
    await p.waitForSelector(fk("new"));
  }
  const ok = (p, t) => p.waitForSelector(ed(`.civic-r04-msg-ok:has-text("${t}")`));
  const errOf = async (p, k) => p.textContent("#" + (await p.getAttribute(fk(k), "aria-describedby")).split(" ").find((x) => x.endsWith("-err")));
  const publicGet = async (id) => { const r = await fetch(base + "/api/civic/v1/objects/" + encodeURIComponent(id)); return { status: r.status, json: await r.json() }; };
  const staffList = (p) => p.evaluate(async () => (await (await fetch("/api/civic/v1/staff/objects?limit=100", { credentials: "same-origin" })).json()).data.items);
  let chainId = null;

  it("create -> reload (local copy) -> draft -> publish -> deadline move with a public reason -> new public history -> archive", async () => {
    const p = await newPage();
    await openApp(p);
    await login(p, "r04a");
    notes.rules = await p.textContent(fk("rules")).catch(() => null);
    await p.click(fk("new"));
    await p.fill(fk("title"), "ТЕСТ R04 (синтетика): ремонт тротуара, раунд 13");
    await p.selectOption(fk("kind"), "roadworks");
    await p.selectOption(fk("status"), "planned");
    await p.fill(fk("description"), "Синтетическая запись приёмки R04, не сведения о реальных работах.");
    await p.check(ed("input[type=radio][value=synthetic]"));
    await p.fill(fk("planned_start"), "2026-10-14");
    await p.fill(fk("original_planned_end"), "2026-10-20");
    await p.waitForFunction(() => (sessionStorage.getItem("civic-r04-unsaved:v1") || "").includes("раунд 13"));
    // reload before saving: the per-tab copy brings the form back (server session cookie stays)
    await p.reload({ waitUntil: "domcontentloaded" });
    await openApp(p);
    await p.waitForSelector(fk("rec-new"));
    assert.match(await p.textContent(ed(".civic-r04-listview")), /локальная копия, не на сервере/);
    await p.click(fk("rec-new"));
    await p.click(fk("restore"));
    assert.equal(await p.inputValue(fk("title")), "ТЕСТ R04 (синтетика): ремонт тротуара, раунд 13");
    assert.equal(await p.inputValue(fk("original_planned_end")), "2026-10-20");
    await p.click(fk("tool-point"));
    const box = await p.locator("#map").boundingBox();
    await p.mouse.click(box.x + Math.min(320, box.width / 3), box.y + box.height / 2);
    await p.waitForSelector(fk("geometry_confirmed"));
    await p.check(fk("geometry_confirmed"));
    await shot(p, "01-restored-draft");
    await p.click(fk("save"));
    await ok(p, "Черновик создан");
    const mine = (await staffList(p)).filter((x) => x.title === "ТЕСТ R04 (синтетика): ремонт тротуара, раунд 13");
    assert.equal(mine.length, 1);
    chainId = mine[0].id;
    assert.equal(mine[0].budget.amount_kzt, null, "unknown cost stays null, never 0");
    assert.equal((await publicGet(chainId)).status, 404, "a draft is not public");
    // preview = R03's rules in the app (window.CivicMapCore is loaded before the editor)
    await p.click(fk("preview"));
    // R03's CivicMapCore exports costView/responsibleView only from its round-12 delivery; the base app (56538a3) has an older core
    const hasR03 = await p.evaluate(() => !!(window.CivicMapCore && typeof window.CivicMapCore.costView === "function"));
    notes.preview_engine = await p.getAttribute(ed(".civic-r04-card"), "data-engine");
    assert.equal(notes.preview_engine, hasR03 ? "r03" : "fallback", "the preview uses R03's own rules when the page has them");
    assert.match(await p.textContent(ed(".civic-r04-preview")), /Демо\. Синтетическая демо-запись/);
    await p.click(fk("publish"));
    await p.click(fk("chip-0"));
    await p.click(fk("confirm"));
    await ok(p, "Опубликовано");
    // move the deadline: a bare category is refused for residents, a real explanation passes
    await p.fill(fk("current_planned_end"), "2026-11-05");
    await p.click(fk("chip-0"));
    await p.type(fk("reason"), "подрядчик сообщил о задержке поставки плитки");
    await p.click(fk("save"));
    await ok(p, "Сохранено");
    await p.click(fk("publish"));
    await p.fill(fk("reason"), "Уточнение по источнику");
    await p.click(fk("confirm"));
    assert.match(await errOf(p, "reason"), /почему срок перенесён/);
    await p.fill(fk("reason"), "Перенос срока: подрядчик сообщил о задержке поставки плитки");
    await shot(p, "02-publish-move");
    await p.click(fk("confirm"));
    await ok(p, "Изменения опубликованы");
    const pub = await publicGet(chainId);
    assert.equal(pub.json.data.item.schedule.original_planned_end, "2026-10-20", "the original promise is kept");
    assert.equal(pub.json.data.item.schedule.current_planned_end, "2026-11-05");
    assert.match(pub.json.data.history[pub.json.data.history.length - 1].reason, /задержке поставки плитки/);
    await p.click(ed(".civic-r04-history summary"));
    assert.match(await p.textContent(ed(".civic-r04-history")), /было 20\.10\.2026 → стало 05\.11\.2026/);
    // archive: leaves the public API; what does the public map show afterwards?
    await p.click(fk("archive"));
    await p.click(fk("chip-0"));
    await p.click(fk("confirm"));
    await ok(p, "Запись в архиве");
    assert.equal((await publicGet(chainId)).status, 404);
    await sleep(1200);
    const after = await p.evaluate(() => ({ hash: location.hash, notFound: /Объект не найден/.test(document.body.innerText) }));
    notes.after_archive = after;
    // the R03 panel is hidden behind the cabinet drawer, so the page text cannot show its card: check the shell's selection/link instead
    if (PATCHED) assert.ok(!after.hash.includes(encodeURIComponent(chainId)), "with the R01 patch the archived record is not the selected object / link: " + after.hash);
    await shot(p, "03-after-archive");
    assert.deepEqual(p.errors, []);
    await p.context().close();
  });

  it("two editors at once (two accounts, two browsers): 409 -> per-field comparison -> both changes kept", async () => {
    const a = await newPage(), b = await newPage();
    await openApp(a); await login(a, "r04a");
    await openApp(b); await login(b, "r04b");
    const demo = (await staffList(a)).find((x) => x.publication === "published");
    for (const p of [a, b]) { await p.click(fk("filter-published")); await p.click(fk("row-" + demo.id)); await p.waitForSelector(fk("title")); }
    await b.fill(fk("description"), "Описание второго редактора (синтетика).");
    await b.click(fk("chip-1"));
    await b.click(fk("save"));
    await ok(b, "Сохранено");
    await a.fill(fk("title"), demo.title + " — правка первого редактора");
    await a.click(fk("chip-1"));
    await a.click(fk("save"));
    await a.waitForSelector(fk("compare"));
    assert.match(await a.textContent(fk("compare")), /Описание второго редактора/);
    assert.equal(await a.inputValue(fk("title")), demo.title + " — правка первого редактора", "my input stays");
    await shot(a, "04-two-editors-compare");
    await a.click(fk("rebase"));
    await a.click(fk("chip-1"));
    await a.click(fk("save"));
    await ok(a, "Сохранено");
    const fin = (await staffList(a)).find((x) => x.id === demo.id);
    assert.equal(fin.title, demo.title + " — правка первого редактора");
    assert.equal(fin.description, "Описание второго редактора (синтетика).");
    assert.deepEqual(a.errors.concat(b.errors), []);
    await a.context().close(); await b.context().close();
  });

  it("rules of validation and changed-source review as this tree's gateway serves them", async () => {
    const p = await newPage();
    await openApp(p);
    await login(p, "r04a");
    const rules = await p.textContent(fk("rules"));
    notes.rules = rules;
    if (PATCHED) assert.match(rules, /с сервера \(\/staff\/meta\)/);
    else assert.match(rules, /локальная копия правил R02 \(сервер не отдаёт \/staff\/meta\)/, "the base gateway does not route /staff/meta and the editor says so");
    // a changed source for a published imported record (R02 importer CLI on this tree's store)
    const item = { id: "ast-r04-r13-app", schema_version: "civic-v1", city: "astana", publication: "published", revision: 1, updated_at: "2026-10-05T00:00:00Z",
      kind: "roadworks", title: "ТЕСТ R04 (синтетика): импорт", description: "Синтетическая запись стенда R04.", status: "planned",
      geometry: { type: "Point", coordinates: [71.43, 51.13] }, geometry_precision: "approximate",
      schedule: { planned_start: "2026-10-14", original_planned_end: "2026-10-20", current_planned_end: "2026-10-20", actual_end: null },
      budget: { amount_kzt: null, basis: "unknown", source_id: null }, responsible: { organization: null, public_contact: null }, evidence_type: "observed",
      source_refs: [{ id: "src-1", url: "https://example.org/r04/notice", publisher: "Тестовый источник", published_on: "2026-10-01", retrieved_at: "2026-10-05T10:00:00+05:00", access_status: "fetched", license: null, fields: ["schedule", "title"] }],
      evidence_notes: "Синтетическая тестовая запись." };
    const pkg = (it, v) => ({ schema_version: "civic-v1", city: "astana", slice: { name: "r04-app-test", version: v, demo: false }, items: [it] });
    const f1 = path.join(tmp, "pkg1.json"), f2 = path.join(tmp, "pkg2.json");
    fs.writeFileSync(f1, JSON.stringify(pkg(item, "v1")));
    cli(["import", f1]);
    await p.click(fk("refresh"));
    await p.click(fk("row-ast-r04-r13-app"));
    await p.waitForSelector(fk("publish"));
    await p.click(fk("publish")); await p.click(fk("chip-0")); await p.click(fk("confirm"));
    await ok(p, "Опубликовано");
    fs.writeFileSync(f2, JSON.stringify(pkg(Object.assign({}, item, { schedule: { planned_start: "2026-10-14", original_planned_end: null, current_planned_end: "2026-11-30", actual_end: null } }), "v2")));
    cli(["import", f2]);
    await p.click(fk("back"));
    await p.click(fk("filter-published"));
    await p.click(fk("row-ast-r04-r13-app"));
    await p.waitForSelector(fk("srcreview"));
    const box = await p.textContent(fk("srcreview"));
    notes.source_review = box.slice(0, 300);
    await shot(p, "05-source-review");
    if (PATCHED) {
      assert.match(box, /Актуальный плановый срок окончания\s*20\.10\.2026\s*30\.11\.2026/);
      await p.click(fk("cand-apply-0")); await p.click(fk("chip-0")); await p.click(fk("confirm"));
      await ok(p, "Изменения источника приняты");
    } else {
      assert.match(box, /маршрут \/import-candidates не подключён/, "honest note on the base gateway");
    }
    assert.deepEqual(p.errors, []);
    await p.context().close();
  });

  it("cabinet opened before the map is ready: drawing becomes available (needs R01's map getter)", { skip: PATCHED ? false : "needs the R01 patch (map: () => currentMap()); on the base shell the editor gets map=null — see INTEGRATION.txt" }, async () => {
    const p = await newPage();
    await openApp(p, { early: true });
    await login(p, "r04a");
    await p.click(fk("new"));
    await p.waitForFunction(() => typeof mapReady !== "undefined" && !!mapReady, null, { timeout: 30000 });
    await p.waitForFunction(() => !document.querySelector('#civic-editor-root [data-fk="map-wait"]'), null, { timeout: 20000 });
    await p.click(fk("tool-point"));
    const box = await p.locator("#map").boundingBox();
    await p.mouse.click(box.x + Math.min(320, box.width / 3), box.y + box.height / 2);
    await p.waitForSelector(fk("geometry_confirmed"));
    assert.deepEqual(p.errors, []);
    await p.context().close();
  });
});
