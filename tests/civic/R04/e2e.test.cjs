/* R04 browser acceptance: the real editor (web/civic/editor/*) in headless Chromium against the civic-v1 CONTRACT MOCK
 * (tests/civic/R04/contract_mock.cjs — not R02). One MapLibre map without a basemap (software WebGL).
 * Run:  node --test tests/civic/R04/e2e.test.cjs
 * Screenshots (real, from this run): R04_SCREENSHOTS=1 node --test tests/civic/R04/e2e.test.cjs
 *   -> research/round-12-results/R04/screenshots/
 * Playwright is resolved locally or from the global npm root; without it the suite is skipped (NOT_RUN).
 */
"use strict";
const { describe, it, before, after } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const fs = require("fs");
const { execSync } = require("child_process");
const { startStand } = require("./stand.cjs");

function loadPlaywright() {
  try { return require("playwright"); } catch (e) { /* fall through */ }
  try { return require(path.join(execSync("npm root -g").toString().trim(), "playwright")); } catch (e) { return null; }
}
const PW = loadPlaywright();
const SHOTS = path.resolve(__dirname, "../../../research/round-12-results/R04/screenshots");
const fk = (k) => `[data-fk="${k}"]`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitFor(cond, what, ms = 5000) {
  const t0 = Date.now();
  for (;;) {
    const v = await cond();
    if (v) return v;
    if (Date.now() - t0 > ms) throw new Error("timeout: " + what);
    await sleep(40);
  }
}

describe("R04 editor in the browser (contract mock)", { skip: PW ? false : "playwright not installed" }, () => {
  let stand, browser;
  const pages = [];
  before(async () => {
    stand = await startStand();
    browser = await PW.chromium.launch({ args: ["--enable-unsafe-swiftshader"] });
    if (process.env.R04_SCREENSHOTS === "1") fs.mkdirSync(SHOTS, { recursive: true });
  });
  after(async () => {
    for (const p of pages) for (const e of p.errors) console.error("pageerror:", e);
    if (browser) await browser.close();
    if (stand) await stand.close();
  });
  const H = () => stand.mock.hooks;
  const objects = () => [...stand.mock.state.objects.values()];
  const posts = (apiPath) => H().requests.filter((r) => r.method === "POST" && r.apiPath === apiPath);
  async function open(viewport, query, keepAlive) {
    H().reset();
    if (keepAlive === false) H().keepAlive(false);
    const ctx = await browser.newContext({ viewport: viewport || { width: 1280, height: 860 } });
    const p = await ctx.newPage();
    p.errors = []; p.reqs = [];
    p.on("pageerror", (e) => p.errors.push(e.message));
    p.on("request", (r) => { if (r.url().includes("/api/civic/v1/")) p.reqs.push({ method: r.method(), path: new URL(r.url()).pathname.replace("/api/civic/v1", ""), body: r.postData() }); });
    pages.push(p);
    await p.goto(stand.url + "/" + (query || ""));
    await p.waitForFunction(() => window.__mapState);
    await p.waitForSelector(fk("login-user"));
    return p;
  }
  async function login(p) {
    await p.fill(fk("login-user"), stand.creds.username);
    await p.fill(fk("login-pass"), stand.creds.password);
    await p.press(fk("login-pass"), "Enter");
    await p.waitForSelector(fk("new"));
  }
  async function fillDraft(p, o) {
    await p.click(fk("new"));
    await p.waitForSelector(fk("title"));
    await p.fill(fk("title"), o.title);
    await p.selectOption(fk("kind"), o.kind || "roadworks");
    await p.check(`input[type=radio][value=${o.evidence || "synthetic"}]`);
    if (o.description) await p.fill(fk("description"), o.description);
  }
  async function saveOk(p, text) {
    await p.click(fk("save"));
    await p.waitForSelector(`.civic-r04-msg-ok:has-text("${text || "ред."}")`);
  }
  const shot = async (p, name) => { if (process.env.R04_SCREENSHOTS === "1") await p.screenshot({ path: path.join(SHOTS, name + ".png") }); };
  const value = (p, k) => p.$eval(fk(k), (x) => x.value);
  const errorText = (p, k) => p.$eval(fk(k), (x) => { const id = (x.getAttribute("aria-describedby") || "").split(" ").find((s) => s.endsWith("-err")); return id ? document.getElementById(id).textContent : ""; });
  // Node-side API client for seeding (separate session, same contract).
  async function apiClient() {
    let cookie = "", csrf = null;
    const req = async (method, p, body) => {
      const headers = { "Content-Type": "application/json", Origin: stand.url };
      if (cookie) headers.Cookie = cookie;
      if (csrf && method !== "GET") headers["X-CSRF-Token"] = csrf;
      const r = await fetch(stand.url + "/api/civic/v1" + p, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
      const sc = r.headers.get("set-cookie");
      if (sc) cookie = sc.split(";")[0];
      const j = await r.json();
      if (!j.ok) throw Object.assign(new Error(j.error.code), { status: r.status });
      return j.data;
    };
    csrf = (await req("POST", "/session/login", stand.creds)).csrf_token;
    return req;
  }
  async function seedPublished(over) {
    const req = await apiClient();
    const body = Object.assign({ title: "Демонстрационный ремонт прохода", kind: "roadworks", evidence_type: "synthetic", status: "planned",
      description: "Синтетическая запись для проверки интерфейса.", geometry: { type: "Point", coordinates: [71.43, 51.17] }, geometry_precision: "approximate",
      schedule: { planned_start: "2026-10-14", original_planned_end: "2026-10-20", current_planned_end: "2026-10-20", actual_end: null } }, over || {});
    const c = await req("POST", "/staff/objects", body);
    const pub = await req("POST", "/staff/objects/" + c.item.id + "/publish", { expected_revision: c.item.revision, reason: "Первая публикация (тест)" });
    return pub.item;
  }
  const publicGet = async (p) => { const r = await fetch(stand.url + "/api/civic/v1" + p); return { status: r.status, json: await r.json() }; };

  it("creates a draft: unknown dates/cost stay null, server fields not sent, draft hidden from the public API", async () => {
    const p = await open();
    await login(p);
    await shot(p, "01-list-empty-desktop");
    await fillDraft(p, { title: "Тестовый ремонт тротуара", description: "Синтетическая запись стенда." });
    await saveOk(p, "Черновик создан");
    assert.equal(posts("/staff/objects").length, 1);
    const body = JSON.parse(p.reqs.find((r) => r.method === "POST" && r.path === "/staff/objects").body);
    for (const k of ["id", "revision", "publication", "updated_at", "created_by", "city"]) assert.ok(!(k in body), "client must not send " + k);
    assert.deepEqual(body.schedule, { planned_start: null, original_planned_end: null, current_planned_end: null, actual_end: null });
    assert.deepEqual(body.budget, { amount_kzt: null, basis: "unknown", source_id: null });
    const [rec] = objects();
    assert.equal(rec.publication, "draft");
    assert.equal(rec.budget.amount_kzt, null);
    const list = await publicGet("/objects");
    assert.equal(list.json.data.items.length, 0, "draft must not be in the public list");
    assert.equal((await publicGet("/objects/" + rec.id)).status, 404);
    assert.match(await p.textContent(".civic-r04-meta"), /Черновик/);
    await shot(p, "02-draft-created-desktop");
    assert.deepEqual(p.errors, []);
  });

  it("validation: the error sits at its field, typed text stays, nothing is sent", async () => {
    const p = await open();
    await login(p);
    await p.click(fk("new"));
    await p.fill(fk("description"), "Длинное описание, которое нельзя потерять при ошибке.");
    await p.fill(fk("amount"), "125 000 000");
    await p.click(fk("save"));
    assert.match(await errorText(p, "title"), /Обязательное/);
    assert.equal(await p.getAttribute(fk("title"), "aria-invalid"), "true");
    assert.match(await errorText(p, "budget_source_id"), /без источника/);
    assert.match(await errorText(p, "basis"), /сумма/);
    assert.equal(await p.evaluate(() => document.activeElement.getAttribute("data-fk")), "title", "focus goes to the first invalid field");
    assert.equal(await value(p, "description"), "Длинное описание, которое нельзя потерять при ошибке.");
    assert.equal(await value(p, "amount"), "125 000 000");
    assert.equal(posts("/staff/objects").length, 0);
    await p.fill(fk("title"), "Исправлено");
    assert.equal(await errorText(p, "title"), "", "error clears once the field is fixed");
  });

  it("place: point on the map needs confirmation; coordinates by keyboard; geometry can be removed; Esc closes the tool", async () => {
    const p = await open();
    await login(p);
    await fillDraft(p, { title: "Точка на карте" });
    const base = await p.evaluate(() => Object.assign({}, window.__mapCounts));
    assert.equal(await p.$(fk("tool-point")), null, "a new record starts as «место неизвестно»: no drawing tools until the user says the place is known");
    await p.check(fk("place-approximate"));
    await p.click(fk("tool-point"));
    assert.equal(await p.evaluate(() => window.__mapCounts.click), (base.click || 0) + 1);
    const box = await p.locator("#map").boundingBox();
    await p.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await p.waitForSelector(fk("geometry_confirmed"));
    assert.equal(await p.evaluate(() => window.__mapCounts.click), base.click || 0, "map click listener removed after the point is set");
    await p.click(fk("save"));
    assert.match(await errorText(p, "geometry"), /Подтвердите/);
    assert.equal(posts("/staff/objects").length, 0);
    await p.check(fk("geometry_confirmed"));
    await shot(p, "03-point-on-map-desktop");
    await saveOk(p, "Черновик создан");
    let [rec] = objects();
    assert.equal(rec.geometry.type, "Point");
    assert.ok(Math.abs(rec.geometry.coordinates[0] - 71.43) < 0.02 && Math.abs(rec.geometry.coordinates[1] - 51.13) < 0.02, "map centre ≈ [71.43, 51.13]: " + rec.geometry.coordinates);
    assert.equal(rec.geometry_precision, "approximate");
    assert.ok(await p.evaluate(() => window.__map.getStyle().layers.some((l) => l.id.startsWith("civic-r04-"))));
    // keyboard: type coordinates (comma decimal), Enter applies; the specialist panel stays open after redraws
    await p.click(fk("coords-open"));
    await p.fill(fk("geometry"), "51,128");
    await p.fill(fk("geo-lon"), "71.4301");
    await p.press(fk("geo-lon"), "Enter");
    await p.check(fk("geometry_confirmed"));
    await saveOk(p, "Сохранено");
    rec = objects()[0];
    assert.deepEqual(rec.geometry.coordinates, [71.4301, 51.128]);
    assert.equal(await p.isVisible(fk("geometry")), true, "coordinates panel still open after save");
    // remove the mark: «приблизительно» without a mark is an error at the place, nothing is sent
    await p.click(fk("geo-remove"));
    await p.click(fk("save"));
    assert.match(await p.textContent("[id$=\"-geo-err\"]"), /Отметьте место на карте/);
    assert.equal(await p.evaluate(() => document.activeElement.dataset.fk), "geometry", "the coordinates panel is open, so focus goes to the latitude field");
    // the user says the place is unknown -> the record stays valid without coordinates
    await p.check(fk("place-unknown"));
    await saveOk(p, "Сохранено");
    rec = objects()[0];
    assert.equal(rec.geometry, null);
    assert.equal(rec.geometry_precision, "unknown");
    // Esc cancels an active tool and removes its listener
    await p.check(fk("place-approximate"));
    await p.click(fk("tool-point"));
    await p.keyboard.press("Escape");
    assert.equal(await p.evaluate(() => window.__mapCounts.click), base.click || 0);
    assert.deepEqual(await p.evaluate(() => window.__toolEvents.at(-1)), { active: false });
    assert.equal(await p.evaluate(() => window.__map.getCanvas().style.cursor), "");
  });

  it("place: a line section (LineString) from map clicks", async () => {
    const p = await open();
    await login(p);
    await fillDraft(p, { title: "Участок работ" });
    await p.check(fk("place-approximate"));
    await p.click(fk("tool-line"));
    const b = await p.locator("#map").boundingBox();
    for (const [dx, dy] of [[-120, 0], [0, 30], [140, 10]]) await p.mouse.click(b.x + b.width / 2 + dx, b.y + b.height / 2 + dy);
    await p.click(fk("tool-done"));
    await p.check(fk("geometry_confirmed"));
    await saveOk(p, "Черновик создан");
    const [rec] = objects();
    assert.equal(rec.geometry.type, "LineString");
    assert.equal(rec.geometry.coordinates.length, 3);
  });

  it("publish: reason required, preview hides internal notes, onPublished gets the public projection", async () => {
    const p = await open();
    await login(p);
    await fillDraft(p, { title: "Публикация с причиной", description: "Описание для жителей." });
    assert.equal(await p.$(fk("internal_notes")), null, "empty DB: the editor does not know yet whether the server keeps internal notes");
    await saveOk(p, "Черновик создан");
    // the staff item carries internal_notes -> the field appears (feature detection, no browser-side assumption)
    await p.fill(fk("internal_notes"), "СЛУЖЕБНО: телефон прораба");
    await saveOk(p, "Сохранено");
    assert.equal(objects()[0].internal_notes, "СЛУЖЕБНО: телефон прораба");
    await p.click(fk("preview"));
    const card = await p.textContent(".civic-r04-preview");
    assert.ok(!card.includes("СЛУЖЕБНО"), "preview must not show internal notes");
    assert.match(card, /Черновик: жители не видят/);
    assert.match(card, /Синтетические данные/);
    await p.click(fk("publish"));
    await p.click(fk("confirm"));
    assert.match(await p.textContent(`#${await p.getAttribute(fk("reason"), "aria-describedby")}`), /причину/);
    assert.equal(posts("/staff/objects/obj-1/publish").length, 0);
    await p.click(fk("chip-0"));
    await shot(p, "04-publish-confirm-desktop");
    await p.click(fk("confirm"));
    await p.waitForSelector('.civic-r04-msg-ok:has-text("Опубликовано")');
    const pub = await p.evaluate(() => window.__published);
    assert.equal(pub.length, 1);
    assert.equal(pub[0].info.action, "publish");
    assert.ok(!JSON.stringify(pub[0].item).includes("СЛУЖЕБНО") && !("internal_notes" in pub[0].item) && !("created_by" in pub[0].item));
    const list = await publicGet("/objects");
    assert.equal(list.json.data.items.length, 1);
    assert.ok(!JSON.stringify(list.json).includes("СЛУЖЕБНО"));
    assert.equal(objects()[0].publication, "published");
    assert.equal(objects()[0].evidence_type, "synthetic", "the editor never upgrades evidence on publish");
  });

  it("reschedule: original end is read-only, current end moves only with a reason, history shows it", async () => {
    const seeded = await (async () => { H().reset(); return seedPublished(); })();
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } });
    const p = await ctx.newPage(); p.errors = []; p.reqs = []; pages.push(p);
    p.on("pageerror", (e) => p.errors.push(e.message));
    await p.goto(stand.url + "/"); await p.waitForSelector(fk("login-user"));
    await login(p);
    await p.click(fk("filter-published"));
    await p.click(fk("row-" + seeded.id));
    await p.waitForSelector(fk("current_planned_end"));
    assert.equal(await p.getAttribute(fk("original_planned_end"), "readonly"), "");
    assert.equal(await p.$(fk("publish")), null, "no publish button for a published record");
    await p.fill(fk("current_planned_end"), "2026-11-05");
    const diff = await p.textContent(".civic-r04-diff");
    assert.match(diff, /Актуальный плановый срок окончания\s*20\.10\.2026\s*05\.11\.2026/);
    await p.click(fk("save"));
    assert.match(await p.textContent("#" + (await p.getAttribute(fk("reason"), "aria-describedby"))), /причину/);
    assert.equal(posts("/staff/objects/" + seeded.id + "/update").length, 0);
    await p.click(fk("chip-0"));
    await p.type(fk("reason"), "подрядчик сообщил о задержке поставки");
    await shot(p, "05-reschedule-diff-reason-desktop");
    await saveOk(p, "Сохранено");
    const rec = stand.mock.state.objects.get(seeded.id);
    assert.equal(rec.schedule.original_planned_end, "2026-10-20");
    assert.equal(rec.schedule.current_planned_end, "2026-11-05");
    assert.equal(rec.revision, seeded.revision + 1);
    await p.click(".civic-r04-history summary");
    assert.match(await p.textContent(".civic-r04-history"), /Перенос срока: подрядчик сообщил о задержке поставки/);
    const pubDetail = await publicGet("/objects/" + seeded.id);
    assert.ok(pubDetail.json.data.history.some((h) => (h.reason || "").includes("задержке")), "public history carries the reason");
    const pub = await p.evaluate(() => window.__published);
    assert.equal(pub.at(-1).info.action, "update");
    await p.click(fk("preview"));
    assert.match(await p.textContent(".civic-r04-preview"), /было 20\.10\.2026, стало 05\.11\.2026/);
    await shot(p, "06-history-preview-desktop");
  });

  it("409: another editor changed the record — my text survives, rebase keeps both changes", async () => {
    H().reset();
    const seeded = await seedPublished();
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } });
    const p = await ctx.newPage(); p.errors = []; pages.push(p);
    p.on("pageerror", (e) => p.errors.push(e.message));
    await p.goto(stand.url + "/"); await p.waitForSelector(fk("login-user"));
    await login(p);
    await p.click(fk("filter-published"));
    await p.click(fk("row-" + seeded.id));
    await p.waitForSelector(fk("description"));
    await p.fill(fk("description"), "Мой текст, набранный во время чужой правки");
    H().mutate(seeded.id, { title: "Название от коллеги" });
    await p.fill(fk("reason"), "Уточнение описания для жителей");
    await p.click(fk("save"));
    await p.waitForSelector(fk("rebase"));
    assert.equal(await value(p, "description"), "Мой текст, набранный во время чужой правки");
    assert.match(await p.textContent(".civic-r04-slot-conflict"), /Изменено на сервере: Название/);
    await shot(p, "07-conflict-409-desktop");
    await p.click(fk("rebase"));
    assert.equal(await value(p, "title"), "Название от коллеги");
    assert.equal(await value(p, "description"), "Мой текст, набранный во время чужой правки");
    assert.equal(await value(p, "reason"), "Уточнение описания для жителей", "reason text survives the rebase");
    await saveOk(p, "Сохранено");
    const rec = stand.mock.state.objects.get(seeded.id);
    assert.equal(rec.title, "Название от коллеги");
    assert.equal(rec.description, "Мой текст, набранный во время чужой правки");
    assert.equal(rec.revision, seeded.revision + 2);
  });

  it("session expires mid-edit: re-login in place, text kept, save goes through once", async () => {
    const p = await open();
    await login(p);
    await fillDraft(p, { title: "Сессия истекает" });
    await saveOk(p, "Черновик создан");
    await p.fill(fk("description"), "Текст, набранный до истечения сессии");
    H().expireSessions();
    await p.click(fk("save"));
    await p.waitForSelector(fk("relogin-user"));
    assert.equal(await value(p, "description"), "Текст, набранный до истечения сессии");
    assert.equal(await p.isDisabled(fk("save")), true, "save waits for re-login");
    await shot(p, "08-session-expired-desktop");
    await p.fill(fk("relogin-user"), stand.creds.username);
    await p.fill(fk("relogin-pass"), stand.creds.password);
    await p.press(fk("relogin-pass"), "Enter");
    await p.waitForSelector('.civic-r04-msg-ok:has-text("Вы снова вошли")');
    assert.equal(await p.$(fk("relogin-user")), null);
    await saveOk(p, "Сохранено");
    assert.equal(objects()[0].description, "Текст, набранный до истечения сессии");
    assert.equal(objects().length, 1);
  });

  it("double click / repeated Enter on save creates exactly one object", async () => {
    const p = await open();
    await login(p);
    await fillDraft(p, { title: "Двойное нажатие" });
    H().failNext({ method: "POST", pathPrefix: "/staff/objects", mode: "delay:500" });
    await p.dblclick(fk("save"));
    await p.press(fk("title"), "Enter").catch(() => {});
    await p.waitForSelector('.civic-r04-msg-ok:has-text("Черновик создан")');
    await sleep(200);
    assert.equal(posts("/staff/objects").length, 1);
    assert.equal(objects().length, 1);
    assert.equal(await p.isDisabled(fk("save")), true, "clean form: save is disabled");
    assert.equal(posts("/staff/objects").length, 1);
    assert.equal(await p.getAttribute(".civic-r04", "aria-busy"), "false");
  });

  it("browser transport retry after a lost answer: the Idempotency-Key replay returns the same draft (proposed delta)", async () => {
    const p = await open();
    await login(p);
    await fillDraft(p, { title: "Повтор на уровне браузера" });
    H().failNext({ method: "POST", pathPrefix: "/staff/objects", mode: "drop", afterCommit: true });
    await p.click(fk("save"));
    await p.waitForSelector('.civic-r04-msg-ok:has-text("Черновик создан")');
    const creates = p.reqs.filter((r) => r.method === "POST" && r.path === "/staff/objects");
    assert.equal(posts("/staff/objects").length, 2, "Chromium silently re-sent the POST on the reused keep-alive socket");
    assert.equal(objects().length, 1, "the replay was recognised by Idempotency-Key, no copy");
    assert.ok(creates.length >= 1);
  });

  it("connection lost after the server created the draft (no transport retry): retry finds it instead of creating a copy", async () => {
    const p = await open(null, "", false);  // fresh socket per request: the browser cannot retry by itself, the page sees the error
    await login(p);
    await fillDraft(p, { title: "Обрыв связи", description: "Текст при обрыве" });
    H().failNext({ method: "POST", pathPrefix: "/staff/objects", mode: "drop", afterCommit: true });
    await p.click(fk("save"));
    await p.waitForSelector('.civic-r04-msg-error:has-text("Нет связи")');
    assert.equal(objects().length, 1, "server committed");
    assert.equal(await value(p, "description"), "Текст при обрыве");
    await shot(p, "09-network-lost-desktop");
    await p.click(fk("retry"));
    await p.waitForSelector(fk("dup-open"));
    await p.click(fk("dup-open"));
    await p.waitForSelector('.civic-r04-msg-info:has-text("найденный черновик")');
    assert.equal(objects().length, 1);
    assert.equal(posts("/staff/objects").length, 1, "the retry did not POST a second create");
    assert.match(await p.textContent(".civic-r04-meta"), /ID obj-1/);
    // drop BEFORE the server acted: retry finds nothing and creates once
    await p.click(fk("back"));
    await fillDraft(p, { title: "Обрыв до сервера" });
    H().failNext({ method: "POST", pathPrefix: "/staff/objects", mode: "drop" });
    await p.click(fk("save"));
    await p.waitForSelector('.civic-r04-msg-error:has-text("Нет связи")');
    assert.equal(objects().length, 1);
    await p.click(fk("retry"));
    await p.waitForSelector('.civic-r04-msg-ok:has-text("Черновик создан")');
    assert.equal(objects().length, 2);
  });

  it("unsaved text: kept in memory only, restorable; page close asks; nothing in web storage or JS cookies", async () => {
    const p = await open();
    await login(p);
    await p.click(fk("new"));
    await p.fill(fk("title"), "Несохранённый черновик");
    await p.click(fk("back"));
    await p.waitForSelector(fk("rec-new"));
    await p.click(fk("rec-new"));
    await p.waitForSelector(fk("restore"));
    await p.click(fk("restore"));
    assert.equal(await value(p, "title"), "Несохранённый черновик");
    const storage = await p.evaluate(() => ({ ls: localStorage.length, ss: sessionStorage.length, cookie: document.cookie }));
    assert.deepEqual(storage, { ls: 0, ss: 0, cookie: "" }, "session/form never in web storage; session cookie is HttpOnly");
    let dialog = null;
    p.on("dialog", (d) => { dialog = d.type(); d.accept(); });
    await p.close({ runBeforeUnload: true });
    await waitFor(() => dialog, "beforeunload dialog");
    assert.equal(dialog, "beforeunload");
  });

  it("logout closes editor actions, wipes in-memory drafts and ends the server session", async () => {
    const p = await open();
    await login(p);
    await p.click(fk("new"));
    await p.fill(fk("title"), "Правка перед выходом");
    await p.click(fk("logout"));
    await p.click(fk("logout-confirm"));
    await p.waitForSelector(fk("login-user"));
    for (const k of ["save", "new", "publish", "archive", "logout", "tool-point"]) assert.equal(await p.$(fk(k)), null, k + " must be gone");
    assert.equal(await p.$(".civic-r04-edit"), null);
    assert.equal(await p.evaluate(() => window.__editor.openObject("obj-1")), false);
    assert.equal(await p.$(fk("save")), null);
    const s = await p.evaluate(() => fetch("/api/civic/v1/session").then((r) => r.json()));
    assert.equal(s.data.authenticated, false);
    assert.ok(posts("/session/logout").length === 1);
    await shot(p, "10-after-logout-desktop");
    await login(p);
    assert.equal(await p.$(fk("rec-new")), null, "in-memory drafts are wiped on logout");
  });

  it("archive: reason required; record leaves the public list; onPublished(archive); read-only afterwards", async () => {
    H().reset();
    const seeded = await seedPublished();
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } });
    const p = await ctx.newPage(); p.errors = []; pages.push(p);
    p.on("pageerror", (e) => p.errors.push(e.message));
    await p.goto(stand.url + "/"); await p.waitForSelector(fk("login-user"));
    await login(p);
    await p.evaluate((id) => window.__editor.openObject(id), seeded.id);
    await p.waitForSelector(fk("archive"));
    await p.click(fk("archive"));
    await p.click(fk("confirm"));
    assert.equal(posts("/staff/objects/" + seeded.id + "/archive").length, 0);
    await p.fill(fk("reason"), "Работы завершены, запись больше не актуальна");
    await p.click(fk("confirm"));
    await p.waitForSelector('.civic-r04-msg-ok:has-text("архиве")');
    assert.equal((await publicGet("/objects")).json.data.items.length, 0);
    assert.equal((await p.evaluate(() => window.__published)).at(-1).info.action, "archive");
    assert.equal(await p.$(fk("save")), null);
    assert.equal(await p.isDisabled(fk("title")), true);
  });

  it("destroy removes map listeners, layers, the active tool and the DOM; remount works", async () => {
    const p = await open();
    await login(p);
    const base = await p.evaluate(() => Object.assign({}, window.__mapCounts));
    await p.click(fk("new"));
    await p.check(fk("place-approximate"));
    await p.click(fk("tool-line"));
    const during = await p.evaluate(() => Object.assign({}, window.__mapCounts));
    assert.ok(during.click > (base.click || 0) && during.styledata > (base.styledata || 0));
    await p.evaluate(() => window.__editor.destroy());
    await p.evaluate(() => window.__editor.destroy());  // idempotent
    const afterCounts = await p.evaluate(() => Object.assign({}, window.__mapCounts));
    for (const k of new Set(Object.keys(during))) assert.equal(afterCounts[k] || 0, base[k] || 0, "listener leak: " + k);
    assert.equal(await p.evaluate(() => window.__map.getStyle().layers.filter((l) => l.id.startsWith("civic-r04-")).length), 0);
    assert.equal(await p.evaluate(() => Object.keys(window.__map.getStyle().sources).filter((s) => s.startsWith("civic-r04-")).length), 0);
    assert.equal(await p.evaluate(() => document.getElementById("panel").children.length), 0);
    assert.equal(await p.evaluate(() => window.__map.getCanvas().style.cursor), "");
    await p.evaluate(() => window.__remount());
    await p.waitForSelector(fk("new"));  // the server session is still valid
  });

  it("keyboard only: login, create, choose type and evidence, save; Esc closes the publish step", async () => {
    const p = await open();
    const tabTo = async (k, max = 160) => {
      for (let i = 0; i < max; i++) {
        if ((await p.evaluate(() => document.activeElement && document.activeElement.getAttribute("data-fk"))) === k) return;
        await p.keyboard.press("Tab");
      }
      throw new Error("not reachable by Tab: " + k);
    };
    await tabTo("login-user");
    await p.keyboard.type(stand.creds.username);
    await p.keyboard.press("Tab");
    await p.keyboard.type(stand.creds.password);
    await p.keyboard.press("Enter");
    await p.waitForSelector(fk("new"));
    await tabTo("new");
    await p.keyboard.press("Enter");
    await p.waitForSelector(fk("title"));
    await tabTo("title");
    await p.keyboard.type("Создано с клавиатуры");
    await p.keyboard.press("Tab");
    await p.keyboard.press("ArrowDown");
    assert.notEqual(await value(p, "kind"), "", "type chosen with arrow keys");
    await tabTo("evidence_type");
    for (let i = 0; i < 3; i++) await p.keyboard.press("ArrowDown");
    assert.equal(await p.evaluate(() => document.activeElement.value), "synthetic");
    await tabTo("save");
    await p.keyboard.press("Enter");
    await p.waitForSelector('.civic-r04-msg-ok:has-text("Черновик создан")');
    const rec = objects()[0];
    assert.equal(rec.evidence_type, "synthetic");
    assert.ok(rec.kind);
    await tabTo("publish");
    await p.keyboard.press("Enter");
    assert.equal(await p.evaluate(() => document.activeElement.getAttribute("data-fk")), "reason");
    await p.keyboard.press("Escape");
    assert.equal(await p.$(fk("confirm")), null);
    assert.equal(await p.evaluate(() => document.activeElement.getAttribute("data-fk")), "publish");
  });

  it("390 px: no horizontal overflow, 16px inputs, 44px buttons, action bar on screen", async () => {
    const p = await open({ width: 390, height: 844 });
    await shot(p, "11-login-390");
    await login(p);
    await fillDraft(p, { title: "Мобильная форма с достаточно длинным названием объекта для проверки переноса строк", description: "Описание" });
    await p.click(fk("src-add"));
    await p.fill(fk("sources.0.url"), "https://www.gov.kz/memleket/entities/astana/press/news/details/1193903?lang=ru");
    const m = await p.evaluate(() => {
      const body = document.querySelector(".civic-r04-body");
      const save = document.querySelector('[data-fk="save"]').getBoundingClientRect();
      return { docW: document.documentElement.scrollWidth, bodyOverflow: body.scrollWidth - body.clientWidth,
        inputFont: parseFloat(getComputedStyle(document.querySelector('[data-fk="title"]')).fontSize),
        saveH: save.height, saveBottom: save.bottom, vh: innerHeight };
    });
    assert.ok(m.docW <= 390, "page wider than 390: " + m.docW);
    assert.ok(m.bodyOverflow <= 0, "editor body overflows horizontally by " + m.bodyOverflow);
    assert.ok(m.inputFont >= 16);
    assert.ok(m.saveH >= 44);
    assert.ok(m.saveBottom <= m.vh, "sticky save button visible");
    await shot(p, "12-form-390");
    await p.check(fk("place-approximate"));
    await p.locator(fk("tool-point")).scrollIntoViewIfNeeded();
    await shot(p, "13-place-section-390");
    await p.check(fk("place-unknown"));
    await p.click(fk("save"));
    await p.waitForSelector('.civic-r04-msg-ok:has-text("Черновик создан")');
    await p.click(fk("publish"));
    await p.click(fk("chip-0"));
    await shot(p, "14-publish-confirm-390");
  });

  it("untrusted text is rendered as text; a map-less mount still accepts typed coordinates", async () => {
    H().reset();
    const p = await open(null, "?nomap=1");
    const req = await apiClient();
    const c = await req("POST", "/staff/objects", { title: "Проверка экранирования", kind: "event", evidence_type: "hypothesis",
      description: '<img src=x onerror="window.__xss=1">описание' });
    await login(p);
    await p.evaluate((id) => window.__editor.openObject(id), c.item.id);
    await p.waitForSelector(fk("preview"));
    await p.click(fk("preview"));
    await sleep(200);
    assert.equal(await p.evaluate(() => window.__xss), undefined);
    assert.match(await p.textContent(".civic-r04-preview"), /<img src=x/);
    await p.check(fk("place-approximate"));
    assert.equal(await p.isDisabled(fk("tool-point")), true);
    await p.fill(fk("description"), "Безопасное описание");
    await p.fill(fk("geometry"), "51.1694");
    await p.fill(fk("geo-lon"), "71.4491");
    await p.click(fk("geo-apply"));
    await p.check(fk("geometry_confirmed"));
    await saveOk(p, "Сохранено");
    assert.deepEqual(stand.mock.state.objects.get(c.item.id).geometry.coordinates, [71.4491, 51.1694]);
  });

  it("round 12: a filled form survives a page reload in the same tab; the copy holds no secrets and logout clears it", async () => {
    const p = await open();
    await login(p);
    await fillDraft(p, { title: "Перезагрузка не теряет форму", description: "Длинное описание, которое нельзя потерять." });
    await p.fill(fk("organization"), "ГУ «Тестовое управление»");
    await p.waitForFunction(() => (sessionStorage.getItem("civic-r04-unsaved:v1") || "").includes("Перезагрузка не теряет форму"));
    const stored = await p.evaluate(() => sessionStorage.getItem("civic-r04-unsaved:v1"));
    assert.ok(!stored.includes(stand.creds.password), "password must never be stored");
    assert.ok(!/csrf/i.test(stored), "no CSRF token in the tab copy");
    await p.reload();
    await p.waitForSelector(fk("rec-new"));  // the list offers the local copy after reload
    assert.match(await p.textContent(".civic-r04-listview"), /локальная копия, не на сервере/);
    await p.click(fk("rec-new"));
    await p.waitForSelector(fk("restore"));
    await p.click(fk("restore"));
    assert.equal(await value(p, "title"), "Перезагрузка не теряет форму");
    assert.equal(await value(p, "description"), "Длинное описание, которое нельзя потерять.");
    assert.equal(await value(p, "organization"), "ГУ «Тестовое управление»");
    assert.equal(posts("/staff/objects").length, 0, "restoring is local; nothing was sent");
    await saveOk(p, "Черновик создан");
    await p.waitForFunction(() => !sessionStorage.getItem("civic-r04-unsaved:v1"));
    await p.click(fk("back"));
    await p.click(fk("new"));
    await p.fill(fk("title"), "Будет удалено при выходе");
    await p.waitForFunction(() => !!sessionStorage.getItem("civic-r04-unsaved:v1"));
    await p.click(fk("back"));
    await p.click(fk("logout"));
    const confirm = await p.$(fk("logout-confirm"));
    if (confirm) await confirm.click();
    await p.waitForSelector(fk("login-user"));
    assert.equal(await p.evaluate(() => sessionStorage.getItem("civic-r04-unsaved:v1")), null, "logout clears the tab copy");
    assert.deepEqual(p.errors, []);
  });

  it("round 12: drawing — Esc cancels and returns to the form; a flat area is refused; Backspace fixes it; Save waits for an unfinished drawing", async () => {
    const p = await open();
    await login(p);
    await fillDraft(p, { title: "Благоустройство двора" });
    await p.check(fk("place-approximate"));
    const base = await p.evaluate(() => Object.assign({}, window.__mapCounts));
    const b = await p.locator("#map").boundingBox();
    const at = (dx, dy) => p.mouse.click(b.x + b.width / 2 + dx, b.y + b.height / 2 + dy);
    // Esc on an unfinished line: nothing is kept, focus is back on the form, the map listener is gone
    await p.click(fk("tool-line"));
    await at(-80, 0);
    await at(80, 0);
    await p.keyboard.press("Escape");
    assert.equal(await p.$(fk("tool-done")), null);
    assert.equal(await p.evaluate(() => document.activeElement.dataset.fk), "tool-point");
    assert.equal(await p.evaluate(() => window.__mapCounts.click), base.click || 0);
    assert.match(await p.textContent(".civic-r04-slot-geom"), /Выберите, как отметить место/);
    assert.doesNotMatch(await p.textContent(".civic-r04-slot-geom"), /"type"|coordinates/, "no raw GeoJSON in the form");
    // area: three points on one line have no area -> refused, the tool stays open with the points
    await p.click(fk("tool-area"));
    await at(-100, 0);
    await at(0, 0);
    assert.equal(await p.isDisabled(fk("tool-done")), true, "«Готово» needs three points");
    await at(100, 0);
    await p.click(fk("tool-done"));
    assert.match(await p.textContent(".civic-r04-slot-geom [role=alert]"), /Уберите лишнюю точку/);
    assert.match(await p.textContent(".civic-r04-tool"), /Точек: 3/);
    // Save while drawing sends nothing and says why
    await p.click(fk("save"));
    await p.waitForSelector('.civic-r04-msg-error:has-text("Рисование не завершено")');
    assert.equal(posts("/staff/objects").length, 0);
    // Backspace removes the last point; a real corner makes an area; the outline closes itself
    await p.keyboard.press("Backspace");
    assert.match(await p.textContent(".civic-r04-tool"), /Точек: 2/);
    await at(0, 90);
    await shot(p, "15-area-drawing-desktop");
    await p.click(fk("tool-done"));
    await p.waitForSelector(fk("geometry_confirmed"));
    assert.match(await p.textContent(".civic-r04-slot-geom"), /Отмечено: площадь, вершин: 3, ≈ \d/);
    assert.equal(await p.evaluate(() => window.__mapCounts.click), base.click || 0, "map click listener removed after «Готово»");
    await p.check(fk("geometry_confirmed"));
    await saveOk(p, "Черновик создан");
    const [rec] = objects();
    assert.equal(rec.geometry.type, "Polygon");
    const ring = rec.geometry.coordinates[0];
    assert.equal(ring.length, 4, "three corners + closing point");
    assert.deepEqual(ring[0], ring[3]);
    assert.equal(rec.geometry_precision, "approximate");
    assert.ok(await p.evaluate(() => window.__map.getStyle().layers.some((l) => l.id.endsWith("geom-fill"))));
    assert.deepEqual(p.errors, []);
  });

  it("round 12: «точно по источнику» needs a source marked «Место»; «место неизвестно» keeps the drawing out of the request", async () => {
    const p = await open();
    await login(p);
    await fillDraft(p, { title: "Место по схеме из извещения" });
    await p.check(fk("place-exact"));
    await p.click(fk("tool-point"));
    const b = await p.locator("#map").boundingBox();
    await p.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
    await p.check(fk("geometry_confirmed"));
    await p.click(fk("save"));
    assert.match(await p.textContent('[id$="-f-place-err"]'), /источник, у которого отмечено «Место»/);
    assert.equal(posts("/staff/objects").length, 0);
    await p.click(fk("src-add"));
    await p.fill(fk("sources.0.url"), "https://www.gov.kz/memleket/entities/astana/press/news/details/1193903?lang=ru");
    await p.check(fk("sources.0.fields.geometry"));
    await saveOk(p, "Черновик создан");
    let [rec] = objects();
    assert.equal(rec.geometry_precision, "source");
    assert.equal(rec.geometry.type, "Point");
    // the place turns out to be unknown: the mark stays in the form, with a warning, but is not sent
    await p.check(fk("place-unknown"));
    assert.equal(await p.$(fk("tool-point")), null);
    assert.match(await p.textContent(".civic-r04-slot-geom"), /осталось в форме, но не будет отправлено/);
    await saveOk(p, "Сохранено");
    rec = objects()[0];
    assert.equal(rec.geometry, null);
    assert.equal(rec.geometry_precision, "unknown");
    assert.deepEqual(p.errors, []);
  });
});
