/* R04 round 13 browser tests: the real editor in headless Chromium against the civic-v1 CONTRACT MOCK
 * (tests/civic/R12/editor/contract_mock.cjs — not R02, not the R01 shell). Races of session/map/navigation, drawing
 * lifecycle, source review, preview/publish/archive, vertex editing and street search.
 * Run:  node --test tests/civic/R12/editor/e2e_r13.test.cjs     (screenshots: R04_SCREENSHOTS=1 -> research/round-13-results/R04/screenshots/)
 */
"use strict";
const { describe, it, before, after } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const fs = require("fs");
const { startStand } = require("./stand.cjs");
const { loadPlaywright, makeKit, fk, sleep } = require("./e2e_helpers.cjs");

const PW = loadPlaywright();
const SHOTS = path.resolve(__dirname, "../../../../research/round-13-results/R04/screenshots");

describe("R04 round 13 (contract mock)", { skip: PW ? false : "playwright not installed" }, () => {
  let stand, browser, K;
  const pages = [];
  before(async () => {
    stand = await startStand();
    browser = await PW.chromium.launch({ args: ["--enable-unsafe-swiftshader"] });
    if (process.env.R04_SCREENSHOTS === "1") fs.mkdirSync(SHOTS, { recursive: true });
    K = makeKit({ stand, browser, pages, shotsDir: SHOTS });
  });
  after(async () => {
    for (const p of pages) for (const e of p.errors) console.error("pageerror:", e);
    if (browser) await browser.close();
    if (stand) await stand.close();
  });

  it("openObject before the mount's session check: signed out -> asks to sign in, opens the record after login; a refusal shows no fields", async () => {
    K.H().reset();
    const rec = await K.seedDraft({ title: "Запись, открытая по ссылке" });
    K.H().failNext({ method: "GET", pathPrefix: "/session", mode: "delay:1200" });
    const p = await K.newPage();
    await p.goto(stand.url + "/?open=" + encodeURIComponent(rec.id));
    await p.waitForSelector(fk("login-user"));
    assert.match(await p.textContent(".civic-r04-topmsg"), /Войдите, чтобы открыть запись/);
    await p.waitForFunction(() => window.__openDone === false);  // contract: false while not signed in (no hanging promise)
    await K.login(p);
    await p.waitForSelector(fk("title"));
    assert.equal(await K.value(p, "title"), "Запись, открытая по ссылке", "the requested record still opens after login, not the list");
    // a refused record (unknown id): back to the list with an error; nothing of the previous record stays on screen
    const r = await p.evaluate(() => window.__editor.openObject("obj-nope"));
    assert.equal(r, false);
    await p.waitForSelector(fk("new"));
    assert.equal(await p.$(fk("title")), null);
    assert.match(await p.textContent(".civic-r04-topmsg"), /не найдена|недоступна/);
    assert.ok(!(await p.textContent(".civic-r04")).includes("Запись, открытая по ссылке") || (await p.$$(fk("row-" + rec.id))).length === 1,
      "the record may appear only as a list row, never as an open form");
    // already signed in + slow session check: the record opens directly (no list in between)
    K.H().failNext({ method: "GET", pathPrefix: "/session", mode: "delay:900" });
    await p.goto(stand.url + "/?open=" + encodeURIComponent(rec.id));
    await p.waitForSelector(fk("title"));
    assert.equal(await K.value(p, "title"), "Запись, открытая по ссылке");
    await p.waitForFunction(() => window.__openDone === true);  // signed in: the promise waits for the session check, then reports success
    assert.deepEqual(p.errors, []);
  });

  it("a late answer does not open an older record over the newer one", async () => {
    K.H().reset();
    const a = await K.seedDraft({ title: "Старый запрос" });
    const b = await K.seedDraft({ title: "Новый запрос" });
    const p = await K.open(null, "", { keepState: true });
    await K.loginToList(p);
    K.H().failNext({ method: "GET", pathPrefix: "/staff/objects/" + a.id, mode: "delay:1200" });
    const first = p.evaluate((id) => window.__editor.openObject(id), a.id);
    await sleep(100);
    assert.equal(await p.evaluate((id) => window.__editor.openObject(id), b.id), true);
    assert.equal(await first, false, "the slower, older request reports it was superseded");
    await sleep(1300);
    assert.equal(await K.value(p, "title"), "Новый запрос");
  });

  it("session switched to another user in this tab: nothing is sent as him, the form is closed, the first user's copy comes back to him", async () => {
    const p = await K.open();
    await K.loginToList(p);
    await K.fillDraft(p, { title: "Черновик первого редактора", description: "Текст, который нельзя потерять" });
    await p.waitForFunction(() => (sessionStorage.getItem("civic-r04-unsaved:v1") || "").includes("Черновик первого редактора"));
    // another tab of the same browser signs in as the second editor: the cookie of this tab now belongs to him
    await p.evaluate(async (c) => {
      await fetch("/api/civic/v1/session/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(c), credentials: "same-origin" });
    }, stand.creds2);
    await p.click(fk("save"));
    await p.waitForSelector('.civic-r04-msg-warn:has-text("сессия сменилась")');
    assert.equal(K.objects().filter((o) => o.title === "Черновик первого редактора").length, 0, "nothing was created under the second editor");
    assert.equal(await p.$(fk("title")), null, "the first editor's form is not shown to the second");
    assert.match(await p.textContent(".civic-r04-head"), /Второй редактор/);
    assert.ok(!(await p.textContent(".civic-r04-listview")).includes("Черновик первого редактора"), "the second editor does not see the first one's local copy");
    const stored = await p.evaluate(() => sessionStorage.getItem("civic-r04-unsaved:v1"));
    assert.ok(!stored.includes(stand.creds.password) && !stored.includes(stand.creds2.password) && !/csrf/i.test(stored));
    // the second editor leaves; the first one signs in again in this tab and gets his copy back
    await p.click(fk("logout"));
    await p.waitForSelector(fk("login-user"));
    await K.loginToList(p);
    assert.match(await p.textContent(".civic-r04-listview"), /Черновик первого редактора/);
    await p.click(fk("rec-new"));
    await p.click(fk("restore"));
    assert.equal(await K.value(p, "description"), "Текст, который нельзя потерять");
    await K.saveOk(p, "Черновик создан");
    assert.equal(K.objects().filter((o) => o.title === "Черновик первого редактора")[0].created_by.name, "Тестовый редактор");
    assert.deepEqual(p.errors, []);
  });

  it("rules of validation: the mock has no /staff/meta -> the head says «local copy», nothing claims the endpoint works", async () => {
    const p = await K.open();
    await K.loginToList(p);
    await p.waitForSelector(fk("rules"));
    assert.match(await p.textContent(fk("rules")), /локальная копия правил R02 \(сервер не отдаёт \/staff\/meta\)/);
    assert.ok(K.H().requests.some((r) => r.method === "GET" && r.apiPath === "/staff/meta"), "asked once");
    assert.equal(K.H().requests.filter((r) => r.apiPath === "/staff/meta").length, 1);
  });

  it("map never ready (getter returns null): buttons explain, no endless polling, no tool started", async () => {
    K.H().reset();
    const p = await K.newPage();
    await p.clock.install();
    await K.open(null, "?latemap=never", { page: p });
    await K.loginToList(p);
    await K.fillDraft(p, { title: "Карта не пришла" });
    await p.check(fk("place-approximate"));
    assert.match(await p.textContent(fk("map-wait")), /Карта ещё загружается/);
    await p.click(fk("tool-point"));
    assert.equal(await p.evaluate(() => window.__toolEvents.filter((e) => e.active).length), 0, "no drawing without a map");
    await p.clock.runFor(10 * 60 * 1000);
    const calls = await p.evaluate(() => window.__getterCalls);
    await p.clock.runFor(10 * 60 * 1000);
    assert.equal(await p.evaluate(() => window.__getterCalls), calls, "no more look-ups after the bounded back-off");
    assert.ok(calls >= 3 && calls < 40, "bounded look-ups (the back-off did run): " + calls);
    // typed coordinates still work without a map
    await p.fill(fk("geometry"), "51.1282");
    await p.fill(fk("geo-lon"), "71.4304");
    await p.click(fk("geo-apply"));
    await p.check(fk("geometry_confirmed"));
    await K.saveOk(p, "Черновик создан");
    assert.deepEqual(K.objects()[0].geometry.coordinates, [71.4304, 51.1282]);
  });

  it("logout with an open drawing and a dirty form: the tool is released, nothing is sent, the copy is removed", async () => {
    const p = await K.open();
    await K.loginToList(p);
    await K.fillDraft(p, { title: "Выход во время рисования" });
    await p.check(fk("place-approximate"));
    await p.click(fk("tool-segment"));
    const b = await p.locator("#map").boundingBox();
    await p.mouse.click(b.x + b.width / 2 - 60, b.y + b.height / 2);
    await p.click(fk("logout"));
    await p.click(fk("logout-confirm"));
    await p.waitForSelector(fk("login-user"));
    const ev = await p.evaluate(() => window.__toolEvents);
    assert.deepEqual(ev.at(-1), { active: false });
    assert.equal(ev.filter((e) => e.active).length, ev.filter((e) => !e.active).length, "every start has its end");
    assert.equal(K.posts("/staff/objects").length, 0);
    assert.equal(await p.evaluate(() => sessionStorage.getItem("civic-r04-unsaved:v1")), null);
    assert.equal(await p.evaluate(() => window.__map.getStyle().layers.filter((l) => l.id.startsWith("civic-r04-")).length), 0);
  });

  const SRC = { id: "src-1", url: "https://www.gov.kz/memleket/entities/astana/press/news/details/1", publisher: "Акимат (тестовый источник)",
    published_on: "2026-10-01", retrieved_at: "2026-10-02", access_status: "fetched", license: null, fields: ["schedule"] };

  it("changed source: comparison with revision and provenance; 409 refreshes it and applies nothing; accept with a reason; dismiss", async () => {
    K.H().reset();
    const rec = await K.seedPublished({ source_refs: [SRC] });
    K.H().addCandidate(rec.id, { schedule: { current_planned_end: "2026-11-30" }, source_refs: [Object.assign({}, SRC, { published_on: "2026-10-05" })] },
      { source: "r05-astana-real", external_id: "ast-r05-trotuar" });
    const p = await K.open(null, "", { keepState: true });
    await K.loginToList(p);
    await p.click(fk("filter-published"));
    await p.click(fk("row-" + rec.id));
    await p.waitForSelector(fk("srcreview"));
    const box = await p.textContent(fk("srcreview"));
    assert.match(box, /Источник изменился/);
    assert.match(box, /ред\. 2/, "the comparison names the record revision");
    assert.match(box, /Актуальный плановый срок окончания\s*20\.10\.2026\s*30\.11\.2026/);
    assert.match(box, /Акимат \(тестовый источник\) · опубл\. 05\.10\.2026/, "provenance of the changed field");
    assert.match(box, /Первоначальный срок зафиксирован/);
    await K.shot(p, "r13-01-source-review");
    // a local edit blocks accepting (it would be overwritten)
    await p.fill(fk("description"), "Моя несохранённая правка");
    assert.equal(await p.isDisabled(fk("cand-apply-0")), true);
    await p.fill(fk("description"), rec.description);
    assert.equal(await p.isDisabled(fk("cand-apply-0")), false);
    // another editor saves first -> 409: comparison refreshed, nothing applied
    K.H().mutate(rec.id, { description: "Другой редактор уточнил описание." });
    await p.click(fk("cand-apply-0"));
    await p.click(fk("chip-0"));
    await p.click(fk("confirm"));
    await p.waitForSelector('.civic-r04-msg-error:has-text("ничего не применено")');
    assert.equal(K.objects()[0].schedule.current_planned_end, "2026-10-20");
    const refreshed = await p.textContent(fk("srcreview"));
    assert.match(refreshed, /ред\. 3/);
    // R02 applies the source content as a whole: the refreshed comparison shows that the other editor's description would be replaced
    assert.match(refreshed, /Описание\s*Другой редактор уточнил описание\.\s*Синтетическая запись для проверки интерфейса\./);
    // accept: a published record needs a reason
    await p.click(fk("cand-apply-0"));
    await p.click(fk("confirm"));
    assert.match(await p.textContent("#" + (await p.getAttribute(fk("reason"), "aria-describedby"))), /причину/);
    await p.click(fk("chip-0"));
    await p.click(fk("confirm"));
    await p.waitForSelector('.civic-r04-msg-ok:has-text("Изменения источника приняты")');
    const after = K.objects()[0];
    assert.equal(after.schedule.current_planned_end, "2026-11-30");
    assert.equal(after.schedule.original_planned_end, "2026-10-20", "the original promise stays");
    assert.equal(after.description, "Синтетическая запись для проверки интерфейса.", "applied as shown in the comparison (whole source content, R02 semantics)");
    assert.equal(await p.$(fk("srcreview")), null, "no pending candidate any more");
    // a second change of the source is dismissed: the record stays as it is
    K.H().addCandidate(rec.id, { title: "Название из источника" });
    await p.click(fk("back"));
    await p.click(fk("filter-published"));
    await p.click(fk("row-" + rec.id));
    await p.waitForSelector(fk("cand-dismiss-0"));
    await p.click(fk("cand-dismiss-0"));
    await p.click(fk("confirm"));
    await p.waitForSelector('.civic-r04-msg-ok:has-text("отклонено")');
    assert.equal(K.objects()[0].title, rec.title);
    assert.deepEqual(p.errors, []);
  });

  it("changed source on a server that does not route /import-candidates: an honest note, nothing pretends to work", async () => {
    K.H().reset();
    const rec = await K.seedPublished();
    K.H().addCandidate(rec.id, { schedule: { current_planned_end: "2026-12-01" } });
    K.H().routeCandidates(false);
    const p = await K.open(null, "", { keepState: true });
    await K.loginToList(p);
    await p.click(fk("filter-published"));
    await p.click(fk("row-" + rec.id));
    await p.waitForSelector(fk("srcreview"));
    const box = await p.textContent(fk("srcreview"));
    assert.match(box, /1 непросмотренное изменение/);
    assert.match(box, /маршрут \/import-candidates не подключён/);
    assert.equal(await p.$(fk("cand-apply-0")), null);
  });

  it("409 on save: a per-field comparison (opened / server / mine), my input stays, nothing overwritten until I choose", async () => {
    K.H().reset();
    const rec = await K.seedPublished();
    const p = await K.open(null, "", { keepState: true });
    await K.loginToList(p);
    await p.click(fk("filter-published"));
    await p.click(fk("row-" + rec.id));
    await p.waitForSelector(fk("title"));
    await p.fill(fk("title"), "Моё название");
    K.H().mutate(rec.id, { title: "Название другого редактора", description: "Описание другого редактора." });
    await p.click(fk("chip-1"));
    await p.click(fk("save"));
    await p.waitForSelector(fk("compare"));
    const t = await p.textContent(fk("compare"));
    assert.match(t, /Название — изменено обеими сторонами\s*Демонстрационный ремонт прохода\s*Название другого редактора\s*Моё название/);
    assert.match(t, /Описание\s*Синтетическая запись для проверки интерфейса\.\s*Описание другого редактора\.\s*без изменений/);
    assert.equal(await K.value(p, "title"), "Моё название", "my input stays in the form");
    assert.equal(K.objects()[0].title, "Название другого редактора", "nothing was overwritten on the server");
    await K.shot(p, "r13-02-conflict-compare");
    await p.click(fk("rebase"));
    await p.click(fk("chip-1"));
    await K.saveOk(p, "Сохранено");
    assert.equal(K.objects()[0].title, "Моё название");
    assert.equal(K.objects()[0].description, "Описание другого редактора.", "the other editor's description is kept");
  });

  it("a deadline move residents see needs a reason they understand: a bare category is refused", async () => {
    K.H().reset();
    const rec = await K.seedPublished();
    const p = await K.open(null, "", { keepState: true });
    await K.loginToList(p);
    await p.click(fk("filter-published"));
    await p.click(fk("row-" + rec.id));
    await p.waitForSelector(fk("current_planned_end"));
    await p.fill(fk("current_planned_end"), "2026-11-15");
    assert.match(await p.textContent(".civic-r04-reason label"), /видна жителям/);
    await p.fill(fk("reason"), "Уточнение по источнику");
    await p.click(fk("save"));
    assert.match(await p.textContent("#" + (await p.getAttribute(fk("reason"), "aria-describedby"))), /почему срок перенесён/);
    assert.equal(K.posts("/staff/objects/" + rec.id + "/update").length, 0);
    await p.fill(fk("reason"), "Перенос срока: подрядчик сообщил о задержке поставки плитки");
    await K.saveOk(p, "Сохранено");
    const pub = await K.publicGet("/objects/" + rec.id);
    assert.equal(pub.json.data.item.schedule.original_planned_end, "2026-10-20");
    assert.equal(pub.json.data.item.schedule.current_planned_end, "2026-11-15");
    assert.ok(pub.json.data.history.some((h) => /задержке поставки плитки/.test(h.reason || "")));
  });

  it("a local copy made on an older revision: the comparison is shown before restoring", async () => {
    K.H().reset();
    const rec = await K.seedDraft();
    const p = await K.open(null, "", { keepState: true });
    await K.loginToList(p);
    await p.click(fk("row-" + rec.id));
    await p.waitForSelector(fk("description"));
    await p.fill(fk("description"), "Моё описание из копии");
    await p.click(fk("back"));
    K.H().mutate(rec.id, { description: "Описание, сохранённое другим редактором." });
    await p.click(fk("row-" + rec.id));
    await p.waitForSelector(fk("restore"));
    const t = await p.textContent(fk("compare"));
    assert.match(t, /Описание — изменено обеими сторонами/);
    assert.match(t, /Описание, сохранённое другим редактором\./);
    assert.match(t, /Моё описание из копии/);
    assert.equal(await K.value(p, "description"), "Описание, сохранённое другим редактором.", "nothing restored before the user chooses");
    await p.click(fk("restore"));
    assert.equal(await K.value(p, "description"), "Моё описание из копии");
  });

  it("vertex editing of the record's own area: select, move (click and arrows), self-crossing refused, undo, Esc restores, Done needs re-confirmation", async () => {
    const p = await K.open();
    await K.loginToList(p);
    await K.fillDraft(p, { title: "Двор с правкой вершин" });
    await p.check(fk("place-approximate"));
    await p.click(fk("tool-area"));
    const b = await p.locator("#map").boundingBox();
    const at = (dx, dy) => p.mouse.click(b.x + b.width / 2 + dx, b.y + b.height / 2 + dy);
    for (const [dx, dy] of [[-80, -60], [80, -60], [80, 60], [-80, 60]]) await at(dx, dy);
    await p.click(fk("tool-done"));
    await p.check(fk("geometry_confirmed"));
    await K.saveOk(p, "Черновик создан");
    const ring0 = K.objects()[0].geometry.coordinates[0];
    // Esc after a move: nothing changes
    await p.click(fk("tool-edit"));
    assert.deepEqual(await p.evaluate(() => window.__toolEvents.at(-1)), { active: true, mode: "edit" });
    await p.click(fk("vx-0"));
    await at(0, 0);
    await p.keyboard.press("Escape");
    assert.equal(await p.$(fk("tool-done")), null);
    assert.equal(await p.isChecked(fk("geometry_confirmed")), true, "cancel keeps the confirmed mark as it was");
    // a move that makes the outline cross itself is refused at «Готово»; undo fixes it
    await p.click(fk("tool-edit"));
    await p.click(fk("vx-0"));
    // move corner 1 just outside the edge between corners 2 and 3: the edge from corner 4 to it then crosses that edge
    const cross = await p.evaluate((ring) => {
      const m = window.__map, r = m.getCanvas().getBoundingClientRect(), v = ring.slice(0, -1).map((c) => m.project(c));
      const mid = { x: (v[1].x + v[2].x) / 2, y: (v[1].y + v[2].y) / 2 }, cen = { x: v.reduce((a, q) => a + q.x, 0) / v.length, y: v.reduce((a, q) => a + q.y, 0) / v.length };
      const d = Math.hypot(mid.x - cen.x, mid.y - cen.y);
      return { x: r.left + mid.x + (mid.x - cen.x) / d * 25, y: r.top + mid.y + (mid.y - cen.y) / d * 25 };
    }, ring0);
    await p.mouse.click(cross.x, cross.y);
    assert.match(await p.textContent(".civic-r04-slot-geom [role=alert]"), /пересекает сам себя/);
    await p.click(fk("tool-done"));
    assert.ok(await p.$(fk("tool-done")), "the tool stays open with the problem");
    await p.click(fk("tool-undo"));
    assert.equal(await p.$(".civic-r04-slot-geom [role=alert]"), null);
    // keyboard: select corner 3 in the list, nudge it up twice (~10 m), Enter
    await p.click(fk("vx-2"));
    await p.keyboard.press("ArrowUp");
    await p.keyboard.press("ArrowUp");
    await K.shot(p, "r13-03-vertex-edit");
    await p.keyboard.press("Enter");
    await p.waitForSelector(fk("geometry_confirmed"));
    assert.equal(await p.isChecked(fk("geometry_confirmed")), false, "a changed mark must be confirmed again");
    await p.check(fk("geometry_confirmed"));
    await K.saveOk(p, "Сохранено");
    const ring1 = K.objects()[0].geometry.coordinates[0];
    assert.equal(ring1.length, ring0.length, "same number of corners");
    const moved = ring1.filter((q) => !ring0.some((r) => r[0] === q[0] && r[1] === q[1]));
    assert.equal(moved.length, 1, "exactly one corner moved: " + JSON.stringify(moved));
    const prev = ring0.find((r) => Math.abs(r[0] - moved[0][0]) < 1e-9);
    assert.ok(prev && Math.abs(moved[0][1] - prev[1] - 2 * 0.000045) < 1e-6, "moved north by two nudges");
    assert.deepEqual(ring1[0], ring1[ring1.length - 1], "the ring stays closed");
    const ev = await p.evaluate(() => window.__toolEvents);
    assert.equal(ev.filter((e) => e.active).length, ev.filter((e) => !e.active).length);
    assert.deepEqual(p.errors, []);
  });

  it("street search: OSM names, approximate frame on the map, no point is invented; not found and unavailable are said plainly", async () => {
    const p = await K.open();
    await K.loginToList(p);
    await K.fillDraft(p, { title: "Поиск улицы" });
    const c0 = await p.evaluate(() => window.__map.getCenter().toArray());
    await p.fill(fk("street-q"), "Кенесары");
    await p.waitForSelector(fk("street-0"));
    const label = await p.textContent(fk("street-0"));
    assert.match(label, /Кенесары/);
    await p.click(fk("street-0"));
    const note = await p.textContent(fk("street-note"));
    assert.match(note, /Это не адрес и не точка работ/);
    assert.match(note, /© участники OpenStreetMap, ODbL-1\.0; снимок 06\.05\.2026/);
    // Перелёт к улице анимирован (600 мс): ждём, пока камера сдвинется, а не читаем центр в тот же миг (R12: было нестабильно под нагрузкой).
    const moved = await p.waitForFunction((c) => { const x = window.__map.getCenter().toArray(); return Math.abs(x[0] - c[0]) + Math.abs(x[1] - c[1]) > 1e-4; }, c0, { timeout: 5000 }).then(() => true, () => false);
    assert.ok(moved, "the map moved to the street");
    assert.equal(await p.isChecked(fk("place-unknown")), true, "choosing a street does not set a place");
    assert.equal(await p.$(fk("geometry_confirmed")), null, "no point was created");
    assert.ok(await p.evaluate(() => window.__map.getStyle().layers.some((l) => l.id.endsWith("street-box"))), "dashed frame of the street on the map");
    await K.shot(p, "r13-04-street-search");
    await p.fill(fk("street-q"), "Несуществующая улица Ыыы");
    await p.waitForSelector('[data-fk="street-note"]:has-text("Улица не найдена в снимке OSM")', { timeout: 5000 });
    // a server without streets.json
    const q = await K.newPage();
    await q.route("**/civic/map/streets.json", (r) => r.fulfill({ status: 404, body: "" }));
    await K.open(null, "", { page: q, keepState: true });
    await K.loginToList(q);
    await q.click(fk("new"));
    await q.fill(fk("street-q"), "Кенесары");
    await q.waitForSelector('[data-fk="street-note"]:has-text("Поиск улиц недоступен")');
  });

  it("390 px and keyboard only: source review, 409 comparison and street search fit the phone and are reachable without a mouse", async () => {
    K.H().reset();
    const rec = await K.seedPublished({ source_refs: [SRC] });
    K.H().addCandidate(rec.id, { schedule: { current_planned_end: "2026-11-30" }, title: "Длинное название из источника, которое переносится по словам на узком экране телефона" });
    const p = await K.newPage({ width: 390, height: 844 });
    await K.open(null, "", { page: p, keepState: true });
    await K.loginToList(p);
    await p.click(fk("filter-published"));
    await p.click(fk("row-" + rec.id));
    await p.waitForSelector(fk("srcreview"));
    const fit = () => p.evaluate(() => ({ doc: document.documentElement.scrollWidth, body: (() => { const b = document.querySelector(".civic-r04-body"); return b.scrollWidth - b.clientWidth; })() }));
    let w = await fit();
    assert.ok(w.doc <= 390 && w.body <= 0, "source review fits 390 px: " + JSON.stringify(w));
    await K.shot(p, "r13-05-review-390");
    // keyboard: Tab reaches «Принять изменения источника…» and Enter opens the step
    await p.focus(fk("srcreview"));
    let found = false;
    for (let i = 0; i < 40 && !found; i++) { await p.keyboard.press("Tab"); found = await p.evaluate(() => document.activeElement && document.activeElement.dataset.fk === "cand-apply-0"); }
    assert.ok(found, "Tab reaches the accept button");
    await p.keyboard.press("Enter");
    await p.waitForSelector(fk("confirm"));
    await p.keyboard.press("Escape");
    assert.equal(await p.$(fk("confirm")), null, "Esc closes the step");
    // 409 comparison at 390 px
    await p.fill(fk("description"), "Моё описание на телефоне");
    K.H().mutate(rec.id, { description: "Чужое описание" });
    await p.click(fk("chip-1"));
    await p.click(fk("save"));
    await p.waitForSelector(fk("compare"));
    w = await fit();
    assert.ok(w.doc <= 390 && w.body <= 0, "comparison fits 390 px: " + JSON.stringify(w));
    await K.shot(p, "r13-06-conflict-390");
    await p.click(fk("rebase"));
    // street search by keyboard
    await p.focus(fk("street-q"));
    await p.keyboard.type("Кенесары");
    await p.waitForSelector(fk("street-0"));
    await p.keyboard.press("Tab");
    assert.equal(await p.evaluate(() => document.activeElement.dataset.fk), "street-0");
    await p.keyboard.press("Enter");
    await p.waitForSelector('[data-fk="street-note"]:has-text("Это не адрес")');
    w = await fit();
    assert.ok(w.doc <= 390 && w.body <= 0, "street search fits 390 px: " + JSON.stringify(w));
    assert.deepEqual(p.errors, []);
  });
});
