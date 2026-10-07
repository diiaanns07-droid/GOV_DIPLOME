/* R04 editor against the REAL R02 CivicService (python3 tests/civic/R04/r02_stand.py), not the contract mock.
 * Run:  R04_R02_ROOT=<checkout of the R02 branch> node --test tests/civic/R04/e2e_r02.test.cjs
 *   e.g. git worktree add --detach /tmp/r02 92f7abae8184516c9bf6bd89367a63692402cc1b
 * Screenshots: add R04_SCREENSHOTS=1 -> research/round-12-results/R04/screenshots/r02-*.png
 * Without R04_R02_ROOT or Playwright the suite is skipped (NOT_RUN), never reported as passed.
 */
"use strict";
const { describe, it, before, after } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const fs = require("fs");
const readline = require("readline");
const { spawn, execSync } = require("child_process");

function loadPlaywright() {
  try { return require("playwright"); } catch (e) { /* fall through */ }
  try { return require(path.join(execSync("npm root -g").toString().trim(), "playwright")); } catch (e) { return null; }
}
const PW = loadPlaywright();
const R02 = process.env.R04_R02_ROOT;
const SHOTS = path.resolve(__dirname, "../../../research/round-12-results/R04/screenshots");
const fk = (k) => `[data-fk="${k}"]`;
const skip = !PW ? "playwright not installed" : !R02 ? "R04_R02_ROOT not set (path to an R02 checkout)" : false;

describe("R04 editor against the real R02 service", { skip }, () => {
  let proc, base, creds, browser;
  before(async () => {
    proc = spawn("python3", [path.join(__dirname, "r02_stand.py"), "--r02-root", R02], { stdio: ["ignore", "pipe", "inherit"] });
    const line = await new Promise((resolve, reject) => {
      const rl = readline.createInterface({ input: proc.stdout });
      rl.once("line", resolve);
      proc.once("exit", (c) => reject(new Error("r02_stand exited " + c)));
    });
    const info = JSON.parse(line);
    base = info.url;
    creds = { username: info.username, password: info.password };
    browser = await PW.chromium.launch({ args: ["--enable-unsafe-swiftshader"] });
    if (process.env.R04_SCREENSHOTS === "1") fs.mkdirSync(SHOTS, { recursive: true });
  });
  after(async () => {
    if (browser) await browser.close();
    if (proc) proc.kill();
  });
  const shot = async (p, name) => { if (process.env.R04_SCREENSHOTS === "1") await p.screenshot({ path: path.join(SHOTS, "r02-" + name + ".png") }); };
  const value = (p, k) => p.$eval(fk(k), (x) => x.value);
  async function apiClient() {
    let cookie = "", csrf = null;
    const req = async (method, p, body, extra) => {
      const headers = Object.assign({ "Content-Type": "application/json", Origin: base, "Sec-Fetch-Site": "same-origin" }, extra || {});
      if (cookie) headers.Cookie = cookie;
      if (csrf && method !== "GET") headers["X-CSRF-Token"] = csrf;
      const r = await fetch(base + "/api/civic/v1" + p, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
      const sc = r.headers.get("set-cookie");
      if (sc) cookie = sc.split(";")[0];
      const j = await r.json();
      if (!j.ok) throw Object.assign(new Error(j.error.code + ": " + j.error.message), { status: r.status, body: j });
      return Object.assign({ status: r.status }, j.data);
    };
    csrf = (await req("POST", "/session/login", creds)).csrf_token;
    return req;
  }
  const publicGet = async (p) => { const r = await fetch(base + "/api/civic/v1" + p); return { status: r.status, json: await r.json() }; };
  async function page(viewport) {
    const ctx = await browser.newContext({ viewport: viewport || { width: 1280, height: 860 } });
    const p = await ctx.newPage();
    p.errors = []; p.reqs = [];
    p.on("pageerror", (e) => p.errors.push(e.message));
    p.on("request", (r) => { if (r.url().includes("/api/civic/v1/")) p.reqs.push({ method: r.method(), path: new URL(r.url()).pathname.replace("/api/civic/v1", ""), headers: r.headers(), body: r.postData() }); });
    await p.goto(base + "/");
    await p.waitForFunction(() => window.__mapState);
    await p.fill(fk("login-user"), creds.username);
    await p.fill(fk("login-pass"), creds.password);
    await p.press(fk("login-pass"), "Enter");
    await p.waitForSelector(fk("new"));
    return p;
  }
  const ok = (p, text) => p.waitForSelector(`.civic-r04-msg-ok:has-text("${text}")`);

  let draftId = null;
  it("walkthrough: draft without dates/cost, point on the map, internal note, preview, publish with reason", async () => {
    const p = await page();
    await shot(p, "01-list");
    await p.click(fk("new"));
    await p.fill(fk("title"), "Демонстрационный ремонт тротуара (синтетика R04)");
    await p.selectOption(fk("kind"), "roadworks");
    await p.selectOption(fk("status"), "planned");
    await p.fill(fk("description"), "Синтетическая запись стенда R04. Не сведения о реальных работах.");
    await p.check("input[type=radio][value=synthetic]");
    await p.fill(fk("planned_start"), "2026-10-14");
    await p.fill(fk("original_planned_end"), "2026-10-20");
    assert.equal(await value(p, "current_planned_end"), "2026-10-20", "current end follows the original while they match (visible)");
    await p.check(fk("place-approximate"));
    await p.click(fk("tool-point"));
    const b = await p.locator("#map").boundingBox();
    await p.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
    await p.check(fk("geometry_confirmed"));
    await shot(p, "02-new-draft-form");
    await p.click(fk("save"));
    await ok(p, "Черновик создан");
    const createReq = p.reqs.find((r) => r.method === "POST" && r.path === "/staff/objects");
    assert.match(createReq.headers["idempotency-key"] || "", /^[A-Za-z0-9._:-]{8,64}$/, "UI sends a key R02 accepts");
    const body = JSON.parse(createReq.body);
    assert.deepEqual(body.budget, { amount_kzt: null, basis: "unknown", source_id: null });
    draftId = (await p.textContent(".civic-r04-meta")).match(/ID (\S+)/)[1];
    // R02 recognises a replay of the same key: no second object
    const req = await apiClient();
    const replay = await req("POST", "/staff/objects", body, { "Idempotency-Key": createReq.headers["idempotency-key"] });
    assert.equal(replay.item.id, draftId);
    assert.equal(replay.status, 200, "replay answered 200, not 201 Created");
    assert.equal((await publicGet("/objects/" + encodeURIComponent(draftId))).status, 404, "draft hidden from the public API");
    // R02 staff DTO carries internal_notes -> the field appears
    await p.waitForSelector(fk("internal_notes"));
    await p.fill(fk("internal_notes"), "СЛУЖЕБНО: не для жителей");
    await p.click(fk("save"));
    await ok(p, "Сохранено");
    await p.click(fk("preview"));
    const card = await p.textContent(".civic-r04-preview");
    assert.ok(!card.includes("СЛУЖЕБНО"));
    assert.match(card, /Синтетические данные/);
    await p.click(fk("publish"));
    await p.click(fk("confirm"));
    assert.equal(p.reqs.filter((r) => r.path.endsWith("/publish")).length, 0, "no publish without a reason");
    await p.click(fk("chip-0"));
    await shot(p, "03-publish-confirm");
    await p.click(fk("confirm"));
    await ok(p, "Опубликовано");
    const pub = await publicGet("/objects/" + encodeURIComponent(draftId));
    assert.equal(pub.status, 200);
    assert.ok(!JSON.stringify(pub.json).includes("СЛУЖЕБНО"), "R02 public DTO has no internal notes");
    assert.equal(pub.json.data.item.schedule.original_planned_end, "2026-10-20");
    assert.equal((await p.evaluate(() => window.__published)).length, 1);
    await shot(p, "04-published");
    assert.deepEqual(p.errors, []);
  });

  it("walkthrough: move the deadline with a reason; original stays; history and public history show the reason", async () => {
    assert.ok(draftId, "depends on the previous scenario");
    const p = await page();
    await p.evaluate((id) => window.__editor.openObject(id), draftId);
    await p.waitForSelector(fk("current_planned_end"));
    assert.equal(await p.getAttribute(fk("original_planned_end"), "readonly"), "");
    await p.fill(fk("current_planned_end"), "2026-11-05");
    await p.click(fk("save"));
    assert.equal(p.reqs.filter((r) => r.path.endsWith("/update")).length, 0, "no update without a reason");
    await p.click(fk("chip-0"));
    await p.type(fk("reason"), "подрядчик сообщил о задержке поставки (синтетика)");
    await shot(p, "05-reschedule-diff");
    await p.click(fk("save"));
    await ok(p, "Жители пока видят опубликованную версию");
    // R02 keeps edits of a published record pending: the public version is unchanged until published again
    let pub = await publicGet("/objects/" + encodeURIComponent(draftId));
    assert.equal(pub.json.data.item.schedule.current_planned_end, "2026-10-20");
    assert.equal((await p.evaluate(() => window.__published)).length, 0, "no onPublished while nothing public changed");
    assert.match(await p.textContent(".civic-r04-edit"), /не опубликованные изменения/);
    await p.click(fk("publish"));
    const table = await p.textContent(".civic-r04-preview");
    assert.match(table, /Было у жителей \/ станет после публикации/);
    assert.match(table, /Актуальный плановый срок окончания\s*20\.10\.2026\s*05\.11\.2026/);
    await p.click(fk("chip-0"));
    await p.type(fk("reason"), ": подрядчик сообщил о задержке");
    await shot(p, "06-publish-changes-before-after");
    await p.click(fk("confirm"));
    await ok(p, "Изменения опубликованы");
    assert.equal((await p.evaluate(() => window.__published)).at(-1).info.action, "publish");
    await p.click(".civic-r04-history summary");
    assert.match(await p.textContent(".civic-r04-history"), /задержке поставки/);
    await shot(p, "07-history");
    pub = await publicGet("/objects/" + encodeURIComponent(draftId));
    assert.equal(pub.json.data.item.schedule.original_planned_end, "2026-10-20");
    assert.equal(pub.json.data.item.schedule.current_planned_end, "2026-11-05");
    assert.ok(pub.json.data.history.some((h) => (h.reason || "").includes("задержке")), "public history carries the reason");
    assert.ok(!JSON.stringify(pub.json.data.history).includes("editor-test"), "no login names in the public history");
  });

  it("409 from R02: concurrent edit, my text kept, rebase and save", async () => {
    const p = await page();
    await p.evaluate((id) => window.__editor.openObject(id), draftId);
    await p.waitForSelector(fk("description"));
    await p.fill(fk("description"), "Мой текст во время чужой правки");
    const req = await apiClient();
    const cur = (await req("GET", "/staff/objects/" + encodeURIComponent(draftId))).item;
    await req("POST", "/staff/objects/" + encodeURIComponent(draftId) + "/update", { expected_revision: cur.revision, changes: { title: "Название от коллеги (синтетика)" }, reason: "Уточнение названия" });
    await p.fill(fk("reason"), "Уточнение описания");
    await p.click(fk("save"));
    await p.waitForSelector(fk("rebase"));
    assert.equal(await value(p, "description"), "Мой текст во время чужой правки");
    await shot(p, "08-conflict");
    await p.click(fk("rebase"));
    await p.click(fk("save"));
    await ok(p, "Сохранено");
    const after = (await req("GET", "/staff/objects/" + encodeURIComponent(draftId))).item;
    assert.equal(after.title, "Название от коллеги (синтетика)");
    assert.equal(after.description, "Мой текст во время чужой правки");
  });

  it("lost session (cookie gone) -> re-login in place; double click saves once; logout ends the R02 session", async () => {
    const p = await page();
    await p.click(fk("new"));
    await p.fill(fk("title"), "Проверка сессии (синтетика)");
    await p.selectOption(fk("kind"), "event");
    await p.check("input[type=radio][value=synthetic]");
    await p.context().clearCookies();
    await p.click(fk("save"));
    await p.waitForSelector(fk("relogin-user"));
    assert.equal(await value(p, "title"), "Проверка сессии (синтетика)");
    await p.fill(fk("relogin-user"), creds.username);
    await p.fill(fk("relogin-pass"), creds.password);
    await p.press(fk("relogin-pass"), "Enter");
    await ok(p, "Вы снова вошли");
    const before = p.reqs.filter((r) => r.method === "POST" && r.path === "/staff/objects").length;
    await p.dblclick(fk("save"));
    await ok(p, "Черновик создан");
    assert.equal(p.reqs.filter((r) => r.method === "POST" && r.path === "/staff/objects").length, before + 1);
    await p.click(fk("logout"));
    await p.waitForSelector(fk("login-user"));
    const s = await p.evaluate(() => fetch("/api/civic/v1/session").then((r) => r.json()));
    assert.equal(s.data.authenticated, false);
    const denied = await p.evaluate(() => fetch("/api/civic/v1/staff/objects").then((r) => r.status));
    assert.equal(denied, 401, "server refuses staff data after logout");
    await shot(p, "09-after-logout");
  });

  it("390 px with R02: form, publish step and history fit the phone width", async () => {
    const p = await page({ width: 390, height: 844 });
    await p.evaluate((id) => window.__editor.openObject(id), draftId);
    await p.waitForSelector(fk("title"));
    const w = await p.evaluate(() => ({ doc: document.documentElement.scrollWidth, body: (() => { const b = document.querySelector(".civic-r04-body"); return b.scrollWidth - b.clientWidth; })() }));
    assert.ok(w.doc <= 390 && w.body <= 0, JSON.stringify(w));
    await shot(p, "10-published-record-390");
    await p.click(fk("preview"));
    await p.locator(".civic-r04-preview").scrollIntoViewIfNeeded();
    await shot(p, "11-preview-390");
  });
});
