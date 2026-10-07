/* R04 round 13 against the REAL R02 code (python3 tests/civic/R04/r02_stand.py, CivicService + CivicHttpAdapter of the
 * given checkout — R02's routes directly, NOT through the R01 gateway, which does not route /import-candidates).
 * Run:  R04_R02_ROOT=<checkout of R02, e.g. a detached worktree of bd7a911> node --test tests/civic/R04/e2e_r02_r13.test.cjs
 *   git worktree add --detach /tmp/r02-bd7a911 bd7a911ad23573ce0d168823199ecb3cc86557c9
 * The test package is synthetic (title «ТЕСТ R04 (синтетика)», example.org source) and lives only in the stand's temp DB;
 * it is labelled observed only to go through R02's import path, as R02's own tests do.
 * Without R04_R02_ROOT or Playwright the suite is skipped (NOT_RUN), never reported as passed.
 */
"use strict";
const { describe, it, before, after } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const fs = require("fs");
const readline = require("readline");
const { spawn } = require("child_process");
const { loadPlaywright, fk, sleep } = require("./e2e_helpers.cjs");

const PW = loadPlaywright();
const R02 = process.env.R04_R02_ROOT;
const SHOTS = path.resolve(__dirname, "../../../research/round-13-results/R04/screenshots");
const skip = !PW ? "playwright not installed" : !R02 ? "R04_R02_ROOT not set (path to an R02 checkout)" : false;

const ITEM = (over) => Object.assign({
  id: "ast-r04-r13-test", schema_version: "civic-v1", city: "astana", publication: "published", revision: 3, updated_at: "2026-10-05T00:00:00Z",
  kind: "roadworks", title: "ТЕСТ R04 (синтетика): ремонт тротуара", description: "Синтетическая запись стенда R04, не сведения о реальных работах.",
  status: "planned", geometry: { type: "Point", coordinates: [71.43, 51.13] }, geometry_precision: "approximate",
  schedule: { planned_start: "2026-10-14", original_planned_end: "2026-10-20", current_planned_end: "2026-10-20", actual_end: null },
  budget: { amount_kzt: null, basis: "unknown", source_id: null }, responsible: { organization: null, public_contact: null },
  evidence_type: "observed",
  source_refs: [{ id: "src-1", url: "https://example.org/r04/notice-1", publisher: "Тестовый источник", published_on: "2026-10-01",
    retrieved_at: "2026-10-05T10:00:00+05:00", access_status: "fetched", license: null, fields: ["schedule", "title"] }],
  evidence_notes: "Синтетическая тестовая запись.",
}, over || {});
const PACKAGE = (items, version) => ({ schema_version: "civic-v1", city: "astana", slice: { name: "r04-test", version, demo: false }, items });

describe("R04 round 13 against the real R02 service", { skip }, () => {
  let proc, base, info, browser;
  before(async () => {
    proc = spawn("python3", ["-B", path.join(__dirname, "r02_stand.py"), "--r02-root", R02], { stdio: ["ignore", "pipe", "inherit"], env: Object.assign({}, process.env, { PYTHONDONTWRITEBYTECODE: "1" }) });
    const line = await new Promise((resolve, reject) => {
      const rl = readline.createInterface({ input: proc.stdout });
      rl.once("line", resolve);
      proc.once("exit", (c) => reject(new Error("r02_stand exited " + c)));
    });
    info = JSON.parse(line);
    base = info.url;
    browser = await PW.chromium.launch({ args: ["--enable-unsafe-swiftshader"] });
    if (process.env.R04_SCREENSHOTS === "1") fs.mkdirSync(SHOTS, { recursive: true });
  });
  after(async () => {
    if (browser) await browser.close();
    if (proc) proc.kill();
  });
  const imp = async (pkg) => {
    const r = await fetch(base + "/__stand/import", { method: "POST", headers: { "Content-Type": "application/json", "X-Stand-Token": info.control }, body: JSON.stringify(pkg) });
    const j = await r.json();
    assert.equal(r.status, 200, JSON.stringify(j));
    return j;
  };
  const publicGet = async (p) => { const r = await fetch(base + "/api/civic/v1" + p); return { status: r.status, json: await r.json() }; };
  async function client(who) {  // Node-side session (another editor), same R02 API
    let cookie = "", csrf = null;
    const req = async (method, p, body) => {
      const headers = { "Content-Type": "application/json", Origin: base };
      if (cookie) headers.Cookie = cookie;
      if (csrf && method !== "GET") headers["X-CSRF-Token"] = csrf;
      const r = await fetch(base + "/api/civic/v1" + p, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
      const sc = r.headers.get("set-cookie");
      if (sc) cookie = sc.split(";")[0];
      const j = await r.json();
      if (!j.ok) throw Object.assign(new Error(j.error.code + ": " + j.error.message), { status: r.status });
      return j.data;
    };
    csrf = (await req("POST", "/session/login", who === 2 ? { username: info.username2, password: info.password2 } : { username: info.username, password: info.password })).csrf_token;
    return req;
  }
  async function page() {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const p = await ctx.newPage();
    p.errors = []; p.on("pageerror", (e) => p.errors.push(e.message));
    await p.goto(base + "/"); await p.waitForSelector(fk("login-user"));
    await p.fill(fk("login-user"), info.username); await p.fill(fk("login-pass"), info.password);
    await p.press(fk("login-pass"), "Enter"); await p.waitForSelector(fk("new"));
    return p;
  }
  const shot = async (p, name) => { if (process.env.R04_SCREENSHOTS === "1") await p.screenshot({ path: path.join(SHOTS, name + ".png") }); };
  const ok = (p, text) => p.waitForSelector(`.civic-r04-msg-ok:has-text("${text}")`);
  const errOf = async (p, k) => p.textContent("#" + (await p.getAttribute(fk(k), "aria-describedby")).split(" ").find((x) => x.endsWith("-err")));

  it("import -> publish -> the source moves the deadline -> compare -> accept -> public reason -> new public history -> archive", async () => {
    const id = ITEM().id;
    const r1 = await imp(PACKAGE([ITEM()], "v1"));
    assert.equal(r1.items[0].action, "create");
    const p = await page();
    await p.click(fk("row-" + id));
    await p.waitForSelector(fk("publish"));
    await p.click(fk("publish"));
    await p.click(fk("chip-0"));
    await p.click(fk("confirm"));
    await ok(p, "Опубликовано");
    // the source publishes a new deadline (version v2 of the package) -> R02 makes a candidate, the record is untouched
    const r2 = await imp(PACKAGE([ITEM({ schedule: { planned_start: "2026-10-14", original_planned_end: null, current_planned_end: "2026-11-30", actual_end: null } })], "v2"));
    assert.equal(r2.items[0].action, "editor_review", "a published record is never changed by the import itself: " + JSON.stringify(r2.items[0]));
    await p.click(fk("back"));
    await p.click(fk("filter-published"));
    await p.click(fk("row-" + id));
    await p.waitForSelector(fk("srcreview"));
    const box = await p.textContent(fk("srcreview"));
    assert.match(box, /Актуальный плановый срок окончания\s*20\.10\.2026\s*30\.11\.2026/);
    assert.match(box, /Тестовый источник · опубл\. 01\.10\.2026/);
    assert.match(box, /Первоначальный срок зафиксирован/);
    assert.doesNotMatch(box, /Первоначальный плановый срок окончания/, "R02 keeps the locked original out of the candidate diff");
    await shot(p, "r02-r13-01-source-review");
    // accept: reason required (published), stays in staff history; residents do not see it yet
    await p.click(fk("cand-apply-0"));
    await p.click(fk("chip-0"));
    await p.click(fk("confirm"));
    await ok(p, "Изменения источника приняты");
    assert.match(await p.textContent(".civic-r04-slot-msg"), /Жители их пока не видят/);
    let pub = await publicGet("/objects/" + id);
    assert.equal(pub.json.data.item.schedule.current_planned_end, "2026-10-20", "R02 pending model: public still old");
    // publish the move: a bare category is refused, a resident-readable reason passes
    await p.click(fk("publish"));
    assert.match(await p.textContent(".civic-r04-reason"), /новый срок окончания 30\.11\.2026 \(был 20\.10\.2026\)/);
    await p.fill(fk("reason"), "Уточнение по источнику");
    await p.click(fk("confirm"));
    assert.match(await errOf(p, "reason"), /почему срок перенесён/);
    await p.fill(fk("reason"), "Перенос срока: подрядчик сообщил о задержке поставки плитки");
    await shot(p, "r02-r13-02-publish-move");
    await p.click(fk("confirm"));
    await ok(p, "Изменения опубликованы");
    pub = await publicGet("/objects/" + id);
    assert.equal(pub.json.data.item.schedule.original_planned_end, "2026-10-20", "the original promise is not lost");
    assert.equal(pub.json.data.item.schedule.current_planned_end, "2026-11-30");
    assert.equal(pub.json.data.item.budget.amount_kzt, null, "unknown budget stays null, never 0");
    const last = pub.json.data.history[pub.json.data.history.length - 1];
    assert.match(last.reason, /задержке поставки плитки/);
    assert.ok(!JSON.stringify(pub.json.data.history).includes("Источник перенёс срок"), "the internal accept reason is not public");
    // archive: onPublished(archive); the record leaves the public API
    await p.click(fk("archive"));
    await p.click(fk("chip-0"));
    await p.click(fk("confirm"));
    await ok(p, "Запись в архиве");
    assert.equal((await publicGet("/objects/" + id)).status, 404);
    const evs = await p.evaluate(() => window.__published.map((x) => x.info.action));
    assert.deepEqual(evs.slice(-1), ["archive"]);
    assert.deepEqual(p.errors, []);
  });

  it("two editors at once on the real R02: 409 -> comparison -> my input kept -> merged save", async () => {
    const id = "ast-r04-r13-two";
    await imp(PACKAGE([ITEM({ id, title: "ТЕСТ R04 (синтетика): два редактора" })], "v1"));
    const p = await page();
    await p.click(fk("row-" + id));
    await p.waitForSelector(fk("title"));
    await p.fill(fk("title"), "ТЕСТ R04 (синтетика): моё название");
    const other = await client(2);
    const cur = (await other("GET", "/staff/objects/" + id)).item;
    await other("POST", "/staff/objects/" + id + "/update", { expected_revision: cur.revision, changes: { description: "Описание второго редактора (синтетика)." } });
    await p.click(fk("save"));
    await p.waitForSelector(`${fk("compare")}, .civic-r04-msg-error, .civic-r04-msg-ok`);
    assert.ok(await p.$(fk("compare")), "comparison expected; got: " + (await p.textContent(".civic-r04-slot-msg")) + " | " + (await p.textContent(".civic-r04-slot-conflict")));
    assert.match(await p.textContent(fk("compare")), /Описание второго редактора/);
    assert.equal(await p.inputValue(fk("title")), "ТЕСТ R04 (синтетика): моё название");
    await p.click(fk("rebase"));
    await p.click(fk("save"));
    await ok(p, "Сохранено");
    const fin = (await other("GET", "/staff/objects/" + id)).item;
    assert.equal(fin.title, "ТЕСТ R04 (синтетика): моё название");
    assert.equal(fin.description, "Описание второго редактора (синтетика).");
    assert.deepEqual(p.errors, []);
  });
});
