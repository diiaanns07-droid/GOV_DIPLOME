/* R04 round 13 browser tests: the real editor in headless Chromium against the civic-v1 CONTRACT MOCK
 * (tests/civic/R04/contract_mock.cjs — not R02, not the R01 shell). Races of session/map/navigation, drawing
 * lifecycle, source review, preview/publish/archive, vertex editing and street search.
 * Run:  node --test tests/civic/R04/e2e_r13.test.cjs     (screenshots: R04_SCREENSHOTS=1 -> research/round-13-results/R04/screenshots/)
 */
"use strict";
const { describe, it, before, after } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const fs = require("fs");
const { startStand } = require("./stand.cjs");
const { loadPlaywright, makeKit, fk, sleep } = require("./e2e_helpers.cjs");

const PW = loadPlaywright();
const SHOTS = path.resolve(__dirname, "../../../research/round-13-results/R04/screenshots");

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
    await p.click(fk("tool-line"));
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
});
