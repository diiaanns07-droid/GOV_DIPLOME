/* R04 round 12 acceptance in the REAL application: app.py (R01 shell + R02 API + R03 map) with this editor.
 * Run (from the repo root):  R04_APP=1 node --test tests/civic/R12/editor/app_acceptance.test.cjs
 *   screenshots of the real interface: add R04_SCREENSHOTS=1 -> research/round-12-results/R04/screenshots/app-*.png
 * The SQLite file is created in a fresh temporary directory OUTSIDE the repository (never the working DB) with
 * `python -m ui.civic_store init` + the synthetic demo package; one test editor gets a random password via
 * --password-stdin (never printed). The server listens on 127.0.0.1 only and is stopped at the end.
 * Without R04_APP=1 or Playwright the suite is skipped (NOT_RUN), never reported as passed.
 */
"use strict";
const { describe, it, before, after } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const fs = require("fs");
const os = require("os");
const net = require("net");
const crypto = require("crypto");
const { spawn, spawnSync, execSync } = require("child_process");

function loadPlaywright() {
  for (const p of ["playwright", "/opt/node-tools/node_modules/playwright"]) { try { return require(p); } catch (e) { /* next */ } }
  try { return require(path.join(execSync("npm root -g").toString().trim(), "playwright")); } catch (e) { return null; }
}
const PW = loadPlaywright();
const REPO = path.resolve(__dirname, "../../../..");
const SHOTS = path.join(REPO, "research/round-12-results/R04/screenshots");
const PY = process.env.PYTHON || "python3";
const skip = !PW ? "playwright not installed" : process.env.R04_APP !== "1" ? "set R04_APP=1 to start app.py with a temporary DB" : false;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const ed = (s) => "#civic-editor-root " + s;
const fk = (k) => ed(`[data-fk="${k}"]`);
const TITLE = "Тест R04 (синтетика): ремонт тротуара у остановки";

function freePort() {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.once("error", reject);
    s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => resolve(p)); });
  });
}

describe("R04 cabinet in the real app (app.py + R02 + R01 shell)", { skip }, () => {
  let tmp, env, server, base, browser, user, pass;
  const log = [];
  before(async () => {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), "civic-r04-app-"));
    env = Object.assign({}, process.env, { CIVIC_DB_PATH: path.join(tmp, "civic.sqlite3"), PYTHONDONTWRITEBYTECODE: "1" });
    const cli = (args, input) => {
      const r = spawnSync(PY, ["-B", "-m", "ui.civic_store"].concat(args), { cwd: REPO, env, input, encoding: "utf8" });
      if (r.status !== 0) throw new Error("civic_store " + args[0] + " failed: " + (r.stderr || r.stdout).slice(0, 400));
    };
    cli(["init"]);
    cli(["seed-demo", "--package", "data/civic/astana/demo_synthetic.json"]);
    user = "r04acc";
    pass = crypto.randomBytes(15).toString("base64url");
    cli(["create-editor", user, "--password-stdin"], pass + "\n");
    const port = await freePort();
    base = "http://127.0.0.1:" + port;
    server = spawn(PY, ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"], detached: true });
    server.stdout.on("data", (d) => log.push(String(d)));
    server.stderr.on("data", (d) => log.push(String(d)));
    for (let i = 0; i < 120; i++) {
      try { const r = await fetch(base + "/api/civic/v1/session"); if (r.ok) break; } catch (e) { /* not up yet */ }
      await sleep(500);
    }
    browser = await PW.chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-gl=swiftshader", "--ignore-gpu-blocklist"] });
    if (process.env.R04_SCREENSHOTS === "1") fs.mkdirSync(SHOTS, { recursive: true });
  });
  after(async () => {
    if (browser) await browser.close();
    if (server) { try { process.kill(-server.pid, "SIGTERM"); } catch (e) { try { server.kill("SIGTERM"); } catch (x) { /* gone */ } } }
    await sleep(300);
    if (tmp) fs.rmSync(tmp, { recursive: true, force: true });
    if (log.some((l) => /Traceback/.test(l))) console.log(log.join("").slice(-3000));
  });

  const shot = async (p, name) => { if (process.env.R04_SCREENSHOTS === "1") await p.screenshot({ path: path.join(SHOTS, "app-" + name + ".jpg"), type: "jpeg", quality: 80 }); };
  async function page(viewport) {
    const ctx = await browser.newContext({ viewport: viewport || { width: 1440, height: 900 }, locale: "ru-RU", timezoneId: "Asia/Almaty" });
    const p = await ctx.newPage();
    p.errors = []; p.posts = [];
    p.on("pageerror", (e) => p.errors.push(e.message));
    p.on("request", (r) => { if (r.method() === "POST" && r.url().includes("/api/civic/v1/staff/")) p.posts.push(new URL(r.url()).pathname.replace("/api/civic/v1", "")); });
    p.on("dialog", (d) => d.dismiss());
    await p.goto(base + "/", { waitUntil: "domcontentloaded" });
    await p.waitForSelector("#civic-staff-button:not([hidden])", { timeout: 30000 });
    // the cabinet works without the map too, but drawing needs it: wait (basemap tiles may be blocked offline)
    await p.waitForFunction(() => typeof mapReady !== "undefined" && !!mapReady, null, { timeout: 30000 }).catch(() => {});
    await p.click("#civic-staff-button");
    await p.waitForSelector(fk("login-user"));
    await p.fill(fk("login-user"), user);
    await p.fill(fk("login-pass"), pass);
    await p.press(fk("login-pass"), "Enter");
    await p.waitForSelector(fk("new"));
    return p;
  }
  const staff = (p) => p.evaluate(async () => {
    const r = await fetch("/api/civic/v1/staff/objects?limit=100", { credentials: "same-origin" });
    return (await r.json()).data.items;
  });
  const publicObj = async (id) => { const r = await fetch(base + "/api/civic/v1/objects/" + encodeURIComponent(id)); return { status: r.status, json: await r.json() }; };
  const errText = (p, k) => p.$eval(fk(k), (x) => { const id = (x.getAttribute("aria-describedby") || "").split(" ").find((s) => s.endsWith("-err")); return id ? document.getElementById(id).textContent : ""; });
  let id = null;

  it("create a draft: an error is shown at its field and the form survives; a double click creates exactly one record", async () => {
    const p = await page();
    await shot(p, "01-cabinet-list");
    await p.click(fk("new"));
    await p.fill(fk("title"), TITLE);
    await p.selectOption(fk("kind"), "roadworks");
    await p.selectOption(fk("status"), "planned");
    await p.fill(fk("description"), "Синтетическая запись приёмки R04. Не сведения о реальных работах.");
    await p.check(ed("input[type=radio][value=synthetic]"));
    // a real mistake: an amount on a synthetic record (R02 rejects it) and no basis/source
    await p.fill(fk("amount"), "15000000");
    await p.click(fk("save"));
    assert.match(await errText(p, "amount"), /синтетической/);
    assert.equal(p.posts.length, 0, "nothing is sent while the form has errors");
    assert.equal(await p.inputValue(fk("description")), "Синтетическая запись приёмки R04. Не сведения о реальных работах.");
    await p.$eval(fk("amount"), (x) => x.scrollIntoView({ block: "center" }));
    await shot(p, "02-error-at-field");
    await p.fill(fk("amount"), "");
    // place: approximately known, a point on the real map
    await p.check(fk("place-approximate"));
    if (await p.isDisabled(fk("tool-point"))) throw new Error("map not ready in the cabinet: drawing disabled");
    await p.click(fk("tool-point"));
    const box = await p.locator("#map").boundingBox();
    await p.mouse.click(box.x + Math.min(320, box.width / 3), box.y + box.height / 2);
    await p.waitForSelector(fk("geometry_confirmed"));
    await p.check(fk("geometry_confirmed"));
    await p.fill(fk("planned_start"), "2026-10-14");
    await p.fill(fk("original_planned_end"), "2026-10-20");
    assert.equal(await p.inputValue(fk("current_planned_end")), "2026-10-20");
    assert.match(await p.textContent(fk("sched-note")), /Жители увидят: окончание 20\.10\.2026/);
    await shot(p, "03-filled-draft");
    await p.dblclick(fk("save"));
    await p.waitForSelector(ed('.civic-r04-msg-ok:has-text("Черновик создан")'));
    await sleep(800);
    const mine = (await staff(p)).filter((x) => x.title === TITLE);
    assert.equal(mine.length, 1, "double click -> one record");
    assert.equal(p.posts.filter((x) => x === "/staff/objects").length >= 1, true);
    id = mine[0].id;
    assert.equal(mine[0].geometry.type, "Point");
    assert.equal(mine[0].geometry_precision, "approximate");
    assert.equal(mine[0].budget.amount_kzt, null, "unknown cost stays null");
    assert.equal((await publicObj(id)).status, 404, "a draft is not public");
    await shot(p, "04-draft-created");
    assert.deepEqual(p.errors, []);
    await p.context().close();
  });

  it("preview, then explicit publication with a reason", async () => {
    assert.ok(id, "previous step created the record");
    const p = await page();
    await p.click(fk("filter-draft")).catch(() => {});
    await p.click(fk("row-" + id));
    await p.waitForSelector(fk("preview"));
    await p.click(fk("preview"));
    assert.match(await p.textContent(ed(".civic-r04-preview")), /Черновик: жители не видят/);
    await shot(p, "05-preview");
    await p.click(fk("publish"));
    await p.click(fk("confirm"));
    assert.match(await errText(p, "reason").catch(() => p.textContent(ed(".civic-r04-reason"))), /причин/i);
    assert.equal(p.posts.filter((x) => x.endsWith("/publish")).length, 0, "no publication without a reason");
    await p.click(fk("chip-0"));
    await shot(p, "06-publish-step");
    await p.click(fk("confirm"));
    await p.waitForSelector(ed('.civic-r04-msg-ok:has-text("Опубликовано")'));
    const pub = await publicObj(id);
    assert.equal(pub.status, 200);
    assert.equal(pub.json.data.item.schedule.original_planned_end, "2026-10-20");
    assert.ok(!JSON.stringify(pub.json).includes("internal_notes"));
    assert.deepEqual(p.errors, []);
    await p.context().close();
  });

  it("move the deadline: the note explains original vs current, a reason is required, history shows было → стало", async () => {
    const p = await page();
    await p.click(fk("filter-published"));
    await p.click(fk("row-" + id));
    await p.waitForSelector(fk("current_planned_end"));
    assert.equal(await p.getAttribute(fk("original_planned_end"), "readonly"), "");
    await p.fill(fk("current_planned_end"), "2026-11-05");
    assert.match(await p.textContent(fk("sched-note")), /окончание 05\.11\.2026; первоначально обещали 20\.10\.2026 \(перенос на 16 дн\.\)/);
    assert.match(await p.textContent(fk("sched-change")), /сохранено 20\.10\.2026 → станет 05\.11\.2026/);
    await p.click(fk("save"));
    assert.equal(p.posts.filter((x) => x.endsWith("/update")).length, 0, "no save without a reason");
    await p.click(fk("chip-0"));
    await p.type(fk("reason"), "подрядчик сообщил о задержке поставки плитки");
    await p.$eval(fk("current_planned_end"), (x) => x.scrollIntoView({ block: "center" }));
    await shot(p, "07-reschedule-reason");
    await p.click(fk("save"));
    await p.waitForSelector(ed('.civic-r04-msg-ok:has-text("Сохранено")'));
    // R02 keeps edits of a published record pending until «Опубликовать изменения…»
    if (await p.$(fk("publish"))) {
      await p.click(fk("publish"));
      await p.fill(fk("reason"), "Перенос срока: подрядчик сообщил о задержке поставки плитки");
      await p.click(fk("confirm"));
      await p.waitForSelector(ed('.civic-r04-msg-ok:has-text("Изменения опубликованы")'));
    }
    const pub = await publicObj(id);
    assert.equal(pub.json.data.item.schedule.original_planned_end, "2026-10-20", "the original promise stays");
    assert.equal(pub.json.data.item.schedule.current_planned_end, "2026-11-05");
    assert.ok((pub.json.data.history || []).some((h) => /задержке поставки/.test(h.reason || "")), "public history carries the reason");
    await p.click(ed(".civic-r04-history summary"));
    const hist = await p.textContent(ed(".civic-r04-history"));
    assert.match(hist, /было 20\.10\.2026 → стало 05\.11\.2026/);
    await p.locator(ed(".civic-r04-history")).scrollIntoViewIfNeeded();
    await shot(p, "08-history");
    assert.deepEqual(p.errors, []);
    await p.context().close();
  });

  it("a network drop on save keeps the text; retry saves once; 390 px phone form", async () => {
    const p = await page();
    await p.click(fk("filter-published"));
    await p.click(fk("row-" + id));
    await p.waitForSelector(fk("description"));
    await p.fill(fk("description"), "Уточнение: проход для пешеходов сохраняется по временному настилу.");
    await p.route("**/api/civic/v1/staff/objects/*/update", (r) => r.abort("failed"));
    await p.click(fk("chip-1"));
    await p.click(fk("save"));
    await p.waitForSelector(ed('.civic-r04-msg-error:has-text("Нет связи")'));
    assert.equal(await p.inputValue(fk("description")), "Уточнение: проход для пешеходов сохраняется по временному настилу.");
    await shot(p, "09-network-error");
    await p.unroute("**/api/civic/v1/staff/objects/*/update");
    await p.click(fk("retry"));
    await p.waitForSelector(ed('.civic-r04-msg-ok:has-text("Сохранено")'));
    const rec = (await staff(p)).find((x) => x.id === id);
    assert.match(rec.description, /временному настилу/);
    await p.context().close();

    const m = await page({ width: 390, height: 844 });
    await m.click(fk("filter-published"));
    await m.click(fk("row-" + id));
    await m.waitForSelector(fk("title"));
    const w = await m.evaluate(() => ({ doc: document.documentElement.scrollWidth, body: (() => { const b = document.querySelector("#civic-editor-root .civic-r04-body"); return b ? b.scrollWidth - b.clientWidth : 0; })() }));
    assert.ok(w.doc <= 390 && w.body <= 0, "no horizontal scroll on a phone: " + JSON.stringify(w));
    await shot(m, "10-phone-form");
    await m.locator(fk("place-approximate")).scrollIntoViewIfNeeded();
    await shot(m, "11-phone-place");
    assert.deepEqual(m.errors, []);
    await m.context().close();
  });
});
