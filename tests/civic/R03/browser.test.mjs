// R03 browser tests on the verification stand (mock API, real MapLibre 5.6.2, real Chromium).
//   node --test tests/civic/R03/browser.test.mjs
//   R03_SHOTS=research/round-11-results/R03/screenshots node --test tests/civic/R03/browser.test.mjs
// External hosts are blocked on purpose: OpenFreeMap is unreachable in the sandbox and
// the stand must show its honest fallback. Results here are about the module, not R01/R02.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "./serve.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
function loadPlaywright() {
  try { return createRequire(import.meta.url)("playwright"); } catch (e) { /* fall through */ }
  try { return createRequire(path.join(execSync("npm root -g", { encoding: "utf8" }).trim(), "x.js"))("playwright"); } catch (e) { return null; }
}
const pw = loadPlaywright();
const SKIP = pw ? false : "playwright is not installed (NOT_RUN)";
const SHOTS = process.env.R03_SHOTS ? path.resolve(ROOT, process.env.R03_SHOTS) : null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
const DESKTOP = { width: 1440, height: 900 };
const MOBILE = { width: 390, height: 844 };
const TODAY = "2026-10-06";

let server, base, browser;
before(async () => {
  if (!pw) return;
  server = createServer();
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  base = "http://127.0.0.1:" + server.address().port;
  browser = await pw.chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"] });
});
after(async () => {
  if (browser) await browser.close();
  if (server) server.close();
});

const LISTENER_PROBE = () => {
  const net = (window.__r03net = {});
  const kind = (t) => (t === window ? "window" : t === document ? "document" : typeof MediaQueryList !== "undefined" && t instanceof MediaQueryList ? "mql" : null);
  const add = EventTarget.prototype.addEventListener, rem = EventTarget.prototype.removeEventListener;
  EventTarget.prototype.addEventListener = function (type, fn, o) { const k = kind(this); if (k) net[k + ":" + type] = (net[k + ":" + type] || 0) + 1; return add.call(this, type, fn, o); };
  EventTarget.prototype.removeEventListener = function (type, fn, o) { const k = kind(this); if (k) net[k + ":" + type] = (net[k + ":" + type] || 0) - 1; return rem.call(this, type, fn, o); };
};

async function open(params, o = {}) {
  const ctx = await browser.newContext({ viewport: o.viewport || DESKTOP, deviceScaleFactor: 1, reducedMotion: o.reducedMotion || "no-preference", hasTouch: !!o.touch });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource|ERR_FAILED/.test(m.text())) errors.push(m.text()); });
  if (o.probe) await page.addInitScript(LISTENER_PROBE);
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  const qs = new URLSearchParams(Object.assign({ today: TODAY }, params || {}));
  await page.goto(base + "/research/round-11-results/R03/stand/?" + qs + (o.hash || ""));
  await page.waitForFunction(() => window.__stand && window.__stand.instance && ["ready", "error"].includes(window.__stand.instance.getState().list), null, { timeout: 30000 });
  return { ctx, page, errors };
}
const state = (page) => page.evaluate(() => window.__stand.instance.getState());
const settle = (page) => page.waitForFunction(() => (!window.__stand.instance || !window.__stand.instance.getState().cameraPending) && (!window.__stand.map || !window.__stand.map.isMoving()), null, { timeout: 5000 });
async function shot(page, name) { if (SHOTS) await page.screenshot({ path: path.join(SHOTS, name + ".png") }); }
async function select(page, id) {
  await page.evaluate((x) => window.__stand.instance.selectObject(x), id);
  await page.waitForFunction(() => window.__stand.instance.getState().detail !== "loading", null, { timeout: 5000 });
  await settle(page);
}
async function noHorizontalOverflow(page) {
  return page.evaluate(() => {
    const bad = [];
    const root = document.getElementById("civic-public") || document.getElementById("civic-map-root");
    for (const el of [root, ...root.querySelectorAll(".civic-r03-scroll, .civic-r03-card, .civic-r03-item, .civic-r03-list-view, .civic-r03-sec, .civic-r03-dl")]) {
      if (el.offsetParent !== null && el.scrollWidth > el.clientWidth + 1) bad.push((el.className || el.id) + " " + el.scrollWidth + ">" + el.clientWidth);
    }
    if (document.documentElement.scrollWidth > innerWidth) bad.push("document " + document.documentElement.scrollWidth);
    const r = root.getBoundingClientRect();
    if (r.right > innerWidth + 0.5 || r.left < -0.5) bad.push("root outside viewport");
    return bad;
  });
}
// Is the visual centre of an element actually hit-testable (not covered by the panel)?
const reachable = (page, selector) => page.evaluate((sel) => {
  const el = document.querySelector(sel);
  if (!el) return "missing";
  const r = el.getBoundingClientRect();
  const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return hit && (hit === el || el.contains(hit)) ? true : "covered by " + (hit ? hit.className || hit.tagName : "nothing");
}, selector);
// Where is the selected object on screen relative to the panel?
const objectClearOfPanel = (page, lngLat, mobile) => page.evaluate(([ll, mob]) => {
  const map = window.__stand.map, c = map.getCanvas().getBoundingClientRect();
  const p = map.project(ll), x = c.left + p.x, y = c.top + p.y;
  const r = document.getElementById("civic-public").getBoundingClientRect();
  const inView = x > 0 && x < innerWidth && y > 0 && y < innerHeight;
  const clear = mob ? y < r.top - 8 : x > r.right + 8;
  return { inView, clear, x: Math.round(x), y: Math.round(y), panel: [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)] };
}, [lngLat, !!mobile]);

test("desktop 1440x900: list, layers, legend, no staff calls, no overflow", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await open();
  await settle(page);
  const s = await state(page);
  assert.equal(s.list, "ready");
  assert.equal(s.count, 12);
  const info = await page.evaluate(() => ({
    basemap: window.__stand.basemap,
    layers: window.__stand.map.getStyle().layers.map((l) => l.id).filter((id) => id.startsWith("civic-r03-")),
    sources: Object.keys(window.__stand.map.getStyle().sources).filter((id) => id.startsWith("civic-")),
    calls: window.__stand.api.calls.map((c) => c.method + " " + c.path),
    count: document.querySelector(".civic-r03-count").textContent,
    items: document.querySelectorAll(".civic-r03-item").length,
    rendered: window.__stand.map.queryRenderedFeatures({ layers: ["civic-r03-point", "civic-r03-line", "civic-r03-line-approx", "civic-r03-area-fill"] }).map((f) => f.properties.cid),
  }));
  assert.equal(info.basemap, "offline-fallback");
  assert.equal(info.layers.length, 12);
  assert.deepEqual(info.sources, ["civic-r03-objects"]);
  assert.ok(info.calls.every((c) => c.startsWith("GET /objects")), info.calls.join());
  assert.ok(!info.calls.some((c) => c.includes("staff")));
  assert.equal(info.count, "12 объектов");
  assert.equal(info.items, 12);
  assert.ok(!info.rendered.includes("r03-demo-nogeo"), "null geometry is never drawn");
  assert.ok(info.rendered.includes("r03-demo-area") && info.rendered.includes("r03-demo-line"), "polygon and line are drawn");
  assert.deepEqual(await noHorizontalOverflow(page), []);
  assert.equal(await reachable(page, "#toggle-3d"), true);
  assert.equal(await reachable(page, ".maplibregl-ctrl-attrib"), true);
  await shot(page, "desktop-1440-list");
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("card with data: shift + reason, money with basis, safe source link, history", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await open({ extra: "format" });
  await select(page, "r03-demo-shifted");
  const demo = await page.locator(".civic-r03-card").innerText();
  assert.match(demo, /Стоимость\s+нет данных/);
  assert.doesNotMatch(demo, /₸/, "no tenge on a synthetic record");
  assert.match(demo, /Демо\. Синтетическая демо-запись/);
  assert.match(demo, /запись обновлена 5 октября 2026, 16:40 \(время Астаны\)/);
  assert.doesNotMatch(demo, /по данным на/);
  await select(page, "r03-format-derived");
  const card = await page.evaluate(() => {
    const c = document.querySelector(".civic-r03-card");
    const a = c.querySelector("a.civic-r03-src-link");
    return { text: c.innerText, href: a && a.href, target: a && a.target, rel: a && a.rel, history: c.querySelectorAll(".civic-r03-history li").length };
  });
  assert.match(card.text, /Тест форматирования карточки \(fixture R03/);
  assert.match(card.text, /Срок перенесён на 16 дней позже/);
  assert.match(card.text, /20\.10\.2026 → 05\.11\.2026/);
  assert.match(card.text, /Причина: «Демо: перенос из-за поставки материалов/);
  assert.match(card.text, /48\u202f500\u202f000 ₸/);
  assert.match(card.text, /сумма договора · источник: Тестовый источник/);
  assert.match(card.text, /Тестовая организация \(fixture\)/);
  assert.match(card.text, /Выведено из источников/);
  assert.match(card.text, /статус по источнику от 15\.09\.2026 · запись обновлена 5 октября 2026, 16:40 \(время Астаны\)/);
  assert.match(card.text, /подтверждает: статус, текущий срок, стоимость, основание стоимости/);
  assert.equal(card.href, "https://example.org/civic-fixture/notice-1");
  assert.equal(card.target, "_blank");
  assert.match(card.rel, /noopener/);
  assert.equal(card.history, 3);
  const pos = await objectClearOfPanel(page, [71.4188, 51.1475]);
  assert.ok(pos.inView && pos.clear, JSON.stringify(pos));
  assert.deepEqual(await noHorizontalOverflow(page), []);
  await shot(page, "desktop-1440-card-format-fixture");
  await select(page, "r03-demo-shifted");
  await shot(page, "desktop-1440-card-data");
  await page.locator(".civic-r03-scroll").evaluate((el) => { el.scrollTop = el.scrollHeight; });
  await shot(page, "desktop-1440-card-history");
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("card without data: every missing value reads 'нет данных', no invented point or zero", { skip: SKIP }, async () => {
  const { ctx, page } = await open();
  await select(page, "r03-demo-nodata");
  const text = await page.locator(".civic-r03-card").innerText();
  assert.match(text, /Организация\s+нет данных/);
  assert.match(text, /Публичный контакт\s+нет данных/);
  assert.match(text, /Стоимость\s+нет данных/);
  assert.match(text, /Начало по плану\s+нет данных/);
  assert.match(text, /Текущий срок\s+нет данных/);
  assert.match(text, /Место примерное/);
  assert.match(text, /Плановый интервал неполный/);
  assert.doesNotMatch(text, /0 ₸/);
  assert.doesNotMatch(text, /перенесён/);
  await shot(page, "desktop-1440-card-nodata");
  await select(page, "r03-demo-nogeo");
  const t2 = await page.locator(".civic-r03-card").innerText();
  assert.match(t2, /Координаты не указаны — объект есть только в списке/);
  assert.equal(await page.locator('[data-r03-action="fly"]').count(), 0, "no 'show on map' for null geometry");
  await ctx.close();
});

test("historical plan and long ru/kk titles: visible marks, wrapping, no horizontal scroll", { skip: SKIP }, async () => {
  for (const vp of [DESKTOP, MOBILE]) {
    const { ctx, page } = await open({}, { viewport: vp });
    await select(page, "r03-demo-historical");
    assert.match(await page.locator(".civic-r03-card").innerText(), /Плановый срок окончания \(30\.09\.2024\) прошёл 736 дней назад/);
    for (const id of ["r03-demo-long-ru", "r03-demo-long-kk"]) {
      await select(page, id);
      assert.deepEqual(await noHorizontalOverflow(page), [], id + " " + vp.width);
    }
    if (vp === MOBILE) await shot(page, "mobile-390-card-long-kk");
    await page.evaluate(() => window.__stand.instance.selectObject(null));
    assert.deepEqual(await noHorizontalOverflow(page), []);
    await ctx.close();
  }
});

test("hostile data: no HTML execution, unsafe links hidden, drafts/other cities dropped, swapped coords not drawn", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await open({ hostile: "1", leak: "1" });
  await select(page, "r03-hostile-xss");
  const r = await page.evaluate(() => ({
    xss: window.__r03xss,
    imgs: document.querySelectorAll("#civic-public img, #civic-public script").length,
    title: document.querySelector(".civic-r03-card-title").textContent,
    links: [...document.querySelectorAll("#civic-public a")].map((a) => a.getAttribute("href")),
    text: document.querySelector(".civic-r03-card").innerText,
    ids: [...document.querySelectorAll(".civic-r03-item")].map((b) => b.dataset.id),
    rendered: window.__stand.map.queryRenderedFeatures().map((f) => f.properties && f.properties.cid).filter(Boolean),
    notes: document.querySelector(".civic-r03-list-notes").innerText,
  }));
  assert.equal(r.xss, undefined);
  assert.equal(r.imgs, 0);
  assert.match(r.title, /^<img src=x onerror/);
  assert.ok(r.links.every((h) => /^https?:/.test(h)), r.links.join());
  assert.match(r.text, /ссылка скрыта: небезопасный адрес/);
  await page.evaluate(() => window.__stand.instance.selectObject(null));
  const ids = await page.evaluate(() => [...document.querySelectorAll(".civic-r03-item")].map((b) => b.dataset.id));
  assert.ok(!ids.includes("r03-hostile-draft"), "draft leaked by the API is still not shown");
  assert.ok(!ids.includes("r03-hostile-othercity"));
  assert.ok(ids.includes("r03-hostile-swapped"));
  assert.ok(!r.rendered.includes("r03-hostile-swapped"));
  assert.match(await page.locator(".civic-r03-list-notes").innerText(), /Пропущено некорректных или неопубликованных записей: 2/);
  await select(page, "r03-hostile-swapped");
  assert.match(await page.locator(".civic-r03-card").innerText(), /вне области карты Астаны — похоже, перепутаны долгота и широта/);
  await select(page, "r03-hostile-negative");
  assert.match(await page.locator(".civic-r03-card").innerText(), /нет данных \(некорректное значение в записи\)/);
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("server 500 on list: error state, retry recovers", { skip: SKIP }, async () => {
  const { ctx, page } = await open({ fail: "list" });
  assert.equal((await state(page)).list, "error");
  const alert = await page.locator(".civic-r03-error").innerText();
  assert.match(alert, /Сервер не смог ответить \(500\)/);
  await shot(page, "desktop-1440-error-500");
  await page.click('[data-r03-action="retry-list"]');
  await page.waitForFunction(() => window.__stand.instance.getState().list === "ready");
  assert.equal((await state(page)).count, 12);
  await ctx.close();
});

test("server 500 on card: list data stays visible, history error has retry", { skip: SKIP }, async () => {
  const { ctx, page } = await open({ fail: "card" });
  await select(page, "r03-demo-shifted");
  assert.equal((await state(page)).detail, "error");
  const text = await page.locator(".civic-r03-card").innerText();
  assert.match(text, /Демо: ремонт пешеходного прохода/);
  assert.match(text, /Причина: история не загрузилась/);
  await page.click('[data-r03-action="retry-card"]');
  await page.waitForFunction(() => window.__stand.instance.getState().detail === "ready");
  assert.equal(await page.locator(".civic-r03-history li").count(), 3);
  await ctx.close();
});

test("empty server and empty filter result: clear messages and reset", { skip: SKIP }, async () => {
  const a = await open({ empty: "1" });
  assert.match(await a.page.locator(".civic-r03-empty").innerText(), /Опубликованных объектов пока нет/);
  await a.ctx.close();
  const { ctx, page } = await open({ persist: "0" });
  await page.click('[data-kind="event"]');
  await page.selectOption('[data-r03-filter="status"]', "completed");
  assert.match(await page.locator(".civic-r03-empty").innerText(), /По выбранным условиям ничего не найдено/);
  assert.equal(await page.locator(".civic-r03-item").count(), 0);
  await shot(page, "desktop-1440-empty-filter");
  await page.click('.civic-r03-empty [data-r03-action="reset-filters"]');
  assert.equal(await page.locator(".civic-r03-item").count(), 12);
  assert.equal(await page.getAttribute('[data-kind="event"]', "aria-pressed"), "false");
  await ctx.close();
});

test("period filter shows known planned intervals only and reports undated records", { skip: SKIP }, async () => {
  const { ctx, page } = await open({ persist: "0" });
  await page.selectOption('[data-r03-filter="period"]', "month");
  const ids = await page.evaluate(() => [...document.querySelectorAll(".civic-r03-item")].map((b) => b.dataset.id));
  assert.ok(!ids.includes("r03-demo-historical"));
  assert.ok(ids.includes("r03-demo-area"));
  assert.match(await page.locator(".civic-r03-list-notes").innerText(), /Без плановых дат: 2/);
  assert.match(await page.locator(".civic-r03-hint").first().innerText(), /01\.10\.2026 по 31\.10\.2026/);
  await ctx.close();
});

test("stale responses: a slow older card or list never replaces the newer choice", { skip: SKIP }, async () => {
  const { ctx, page } = await open({ persist: "0" });
  await page.evaluate(() => {
    window.__stand.api.options.slow["/objects/r03-demo-area"] = 1500;
    window.__stand.instance.selectObject("r03-demo-area");
    window.__stand.instance.selectObject("r03-demo-shifted");
  });
  await page.waitForTimeout(1900);
  const s = await state(page);
  assert.equal(s.selectedId, "r03-demo-shifted");
  assert.equal(s.detail, "ready");
  assert.equal(await page.locator(".civic-r03-card-title").textContent(), "Демо: ремонт пешеходного прохода у остановки");
  const count = await page.evaluate(async () => {
    const o = window.__stand.api.options;
    o.slow["/objects"] = 1200;
    const p1 = window.__stand.instance.refresh();
    o.slow["/objects"] = 5;
    o.items = o.items.filter((x) => x.id !== "r03-demo-line");
    const p2 = window.__stand.instance.refresh();
    await Promise.all([p1, p2]);
    await new Promise((r) => setTimeout(r, 50));
    return window.__stand.instance.getState().count;
  });
  assert.equal(count, 11);
  await ctx.close();
});

test("one map click = one selection and one request; hover tooltip; repeated clicks do not stack", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await open({ persist: "0" });
  await settle(page);
  const pt = await page.evaluate(() => { const m = window.__stand.map, c = m.getCanvas().getBoundingClientRect(), p = m.project([71.4304, 51.1282]); return { x: c.left + p.x, y: c.top + p.y }; });
  await page.mouse.move(pt.x, pt.y);
  await page.waitForSelector(".civic-r03-tip", { timeout: 3000 });
  assert.match(await page.locator(".civic-r03-tip").innerText(), /Демо-запись/);
  await page.mouse.click(pt.x, pt.y);
  await page.waitForFunction(() => window.__stand.instance.getState().detail === "ready");
  await page.waitForTimeout(150);
  let r = await page.evaluate(() => ({ calls: window.__stand.api.calls.filter((c) => c.path === "/objects/r03-demo-shifted").length, selects: window.__stand.selects.slice() }));
  assert.equal(r.calls, 1);
  assert.deepEqual(r.selects, [{ id: "r03-demo-shifted", source: "map" }]);
  // remount twice, then click again: still exactly one more selection
  await page.evaluate(() => { window.__stand.destroy(); window.__stand.mount(); window.__stand.destroy(); window.__stand.mount(); window.__stand.selects.length = 0; });
  await page.waitForFunction(() => window.__stand.instance.getState().list === "ready");
  await page.waitForTimeout(100);
  await page.mouse.click(pt.x, pt.y);
  await page.waitForFunction(() => window.__stand.instance.getState().detail === "ready");
  await page.waitForTimeout(150);
  r = await page.evaluate(() => ({ selects: window.__stand.selects.slice() }));
  assert.deepEqual(r.selects, [{ id: "r03-demo-shifted", source: "map" }]);
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("mount/destroy twice: layers, sources, popup, root, map and window listeners are all released", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await open({ permalink: "1" }, { probe: true });
  const snap = () => page.evaluate(() => {
    const m = window.__stand.map;
    const ml = {};
    for (const [k, v] of Object.entries(m._listeners || {})) if (v.length) ml[k] = v.length;
    const root = document.getElementById("civic-public");
    return {
      layers: m.getStyle().layers.filter((l) => l.id.startsWith("civic-r03")).length,
      sources: Object.keys(m.getStyle().sources).filter((k) => k.startsWith("civic-r03")).length,
      mapListeners: ml,
      net: Object.fromEntries(Object.entries(window.__r03net).filter(([, v]) => v !== 0)),
      rootChildren: root.childNodes.length,
      rootClass: root.className,
      rootAttrs: root.getAttributeNames().filter((a) => a !== "id"),
      popups: document.querySelectorAll(".civic-r03-tip").length,
      demoImage: m.hasImage("civic-r03-demo-ring"),
    };
  });
  // hover to create the popup, then destroy
  await settle(page);
  const pt = await page.evaluate(() => { const m = window.__stand.map, c = m.getCanvas().getBoundingClientRect(), p = m.project([71.4304, 51.1282]); return { x: c.left + p.x, y: c.top + p.y }; });
  await page.mouse.move(pt.x, pt.y);
  await page.waitForSelector(".civic-r03-tip");
  await page.evaluate(() => window.__stand.destroy());
  const s1 = await snap();
  assert.equal(s1.layers, 0);
  assert.equal(s1.sources, 0);
  assert.equal(s1.rootChildren, 0);
  assert.equal(s1.rootClass, "");
  assert.deepEqual(s1.rootAttrs, []);
  assert.equal(s1.popups, 0);
  assert.equal(s1.demoImage, false);
  for (let i = 0; i < 2; i++) {
    await page.evaluate(() => window.__stand.mount());
    await page.waitForFunction(() => window.__stand.instance.getState().list === "ready");
    const mid = await snap();
    assert.equal(mid.layers, 12);
    await page.evaluate(() => { window.__stand.instance.destroy(); window.__stand.instance.destroy(); window.__stand.instance.selectObject("r03-demo-area"); window.__stand.instance.refresh(); window.__stand.instance = null; });
    await page.waitForTimeout(200);
    const s2 = await snap();
    assert.deepEqual(s2, s1, "state after mount+destroy #" + (i + 2) + " equals state after the first destroy");
  }
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("keyboard: Enter opens a card with focus on its title, Escape returns focus to the list item", { skip: SKIP }, async () => {
  const { ctx, page } = await open({ persist: "0" });
  await page.focus('[data-id="r03-demo-line"]');
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => window.__stand.instance.getState().detail === "ready");
  assert.equal(await page.evaluate(() => document.activeElement.className), "civic-r03-card-title");
  await page.keyboard.press("Escape");
  assert.equal(await page.evaluate(() => document.activeElement.dataset.id), "r03-demo-line");
  assert.equal((await state(page)).view, "list");
  await ctx.close();
});

test("feedback button calls onFeedback with object id and geometry", { skip: SKIP }, async () => {
  const { ctx, page } = await open();
  await select(page, "r03-demo-area");
  await page.click('[data-r03-action="feedback"]');
  const fb = await page.evaluate(() => window.__stand.feedback);
  assert.equal(fb.length, 1);
  assert.equal(fb[0].objectId, "r03-demo-area");
  assert.equal(fb[0].geometry.type, "Polygon");
  await ctx.close();
});

test("mobile 390x844: bottom sheet states keep 3D toggle and attribution reachable; card clear of the sheet", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await open({ persist: "0" }, { viewport: MOBILE, touch: true });
  await shot(page, "mobile-390-peek");
  const heights = {};
  for (const want of ["peek", "half", "full"]) {
    const s = await state(page);
    if (s.sheet !== want) {
      await page.click(".civic-r03-handle");
      await page.waitForTimeout(350);
    }
    assert.equal((await state(page)).sheet, want);
    heights[want] = await page.evaluate(() => Math.round(document.getElementById("civic-public").getBoundingClientRect().height));
    assert.equal(await reachable(page, "#toggle-3d"), true, "3D toggle in " + want);
    assert.equal(await reachable(page, ".maplibregl-ctrl-attrib"), true, "attribution in " + want);
    assert.equal(await reachable(page, ".civic-r03-handle"), true);
    assert.deepEqual(await noHorizontalOverflow(page), []);
    if (want !== "peek") await shot(page, "mobile-390-" + want);
  }
  assert.ok(heights.peek < heights.half && heights.half < heights.full, JSON.stringify(heights));
  const targets = await page.evaluate(() => [...document.querySelectorAll("#civic-public button, #civic-public select, #civic-public input:not([type=checkbox])")]
    .filter((e) => e.offsetParent !== null).map((e) => [e.className || e.tagName, Math.round(e.getBoundingClientRect().height)]).filter(([, h]) => h < 44));
  assert.deepEqual(targets, [], "touch targets >= 44px");
  await page.click(".civic-r03-handle"); // full -> peek
  await page.waitForTimeout(300);
  await select(page, "r03-demo-shifted");
  assert.equal((await state(page)).sheet, "half", "selecting opens the sheet to half");
  const pos = await objectClearOfPanel(page, [71.4304, 51.1282], true);
  assert.ok(pos.inView && pos.clear, JSON.stringify(pos));
  await shot(page, "mobile-390-card");
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("offline basemap: honest fallback message; 3D tilts the camera only; objects still drawn", { skip: SKIP }, async () => {
  const { ctx, page } = await open();
  assert.match(await page.locator("#stand-status").innerText(), /OpenFreeMap недоступна/);
  await page.click("#toggle-3d");
  await page.waitForTimeout(900);
  const r = await page.evaluate(() => ({ pitch: window.__stand.map.getPitch(), status: document.getElementById("stand-status").innerText, drawn: window.__stand.map.queryRenderedFeatures({ layers: ["civic-r03-point"] }).length }));
  assert.ok(r.pitch > 30);
  assert.match(r.status, /3D-здания появятся, когда загрузится подложка/);
  assert.ok(r.drawn > 0);
  await select(page, "r03-demo-area");
  const pitch = await page.evaluate(() => window.__stand.map.getPitch());
  assert.ok(pitch > 30, "selecting an object keeps the user's 3D tilt");
  await shot(page, "desktop-1440-3d-tilt-offline");
  await ctx.close();
});

test("reduced motion: camera jumps without animation and keeps the object clear of the panel", { skip: SKIP }, async () => {
  const { ctx, page } = await open({ persist: "0" }, { reducedMotion: "reduce" });
  await page.evaluate(() => window.__stand.instance.selectObject("r03-demo-line"));
  await page.waitForTimeout(60);
  assert.equal(await page.evaluate(() => window.__stand.map.isMoving()), false);
  const pos = await objectClearOfPanel(page, [71.4452, 51.1421]);
  assert.ok(pos.inView && pos.clear, JSON.stringify(pos));
  await ctx.close();
});

test("permalink: hash opens the card, unknown id is an honest not-found, back clears the hash", { skip: SKIP }, async () => {
  const { ctx, page } = await open({ permalink: "1" }, { hash: "#civic-object=r03-demo-area" });
  await page.waitForFunction(() => window.__stand.instance.getState().detail === "ready");
  assert.equal((await state(page)).selectedId, "r03-demo-area");
  await page.click('[data-r03-action="back"]');
  assert.equal(await page.evaluate(() => location.hash), "");
  await page.evaluate(() => { location.hash = "civic-object=missing-id"; });
  await page.waitForFunction(() => window.__stand.instance.getState().detail === "notfound");
  assert.match(await page.locator(".civic-r03-card").innerText(), /Объект не найден/);
  await ctx.close();
});

test("filters persist across reload without private data", { skip: SKIP }, async () => {
  const { ctx, page } = await open();
  await page.click('[data-kind="roadworks"]');
  await page.selectOption('[data-r03-filter="period"]', "year");
  await page.reload();
  await page.waitForFunction(() => window.__stand && window.__stand.instance && window.__stand.instance.getState().list === "ready");
  assert.equal(await page.getAttribute('[data-kind="roadworks"]', "aria-pressed"), "true");
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("civic-r03:filters:v1")));
  assert.deepEqual(Object.keys(stored).sort(), ["area", "from", "kinds", "period", "statuses", "to"]);
  assert.deepEqual(stored.kinds, ["roadworks"]);
  await ctx.close();
});

test("area filter counts objects in the visible part and reports records without a place", { skip: SKIP }, async () => {
  const { ctx, page } = await open({ persist: "0" });
  await page.evaluate(() => window.__stand.map.jumpTo({ center: [71.4304, 51.1282], zoom: 15.5 }));
  await page.check('[data-r03-filter="area"]');
  await page.waitForTimeout(300);
  const t = await page.locator(".civic-r03-count").innerText();
  assert.match(t, /^Показано \d+ из 12$/);
  assert.match(await page.locator(".civic-r03-list-notes").innerText(), /Без места на карте \(не входят в «видимую часть»\): 1/);
  await ctx.close();
});

test("embedded in an R01-like host panel: no own positioning, camera avoids the host panel", { skip: SKIP }, async () => {
  for (const vp of [DESKTOP, MOBILE]) {
    const { ctx, page, errors } = await open({ host: "r01", persist: "0" }, { viewport: vp });
    const info = await page.evaluate(() => {
      const r = document.getElementById("civic-map-root");
      return { cls: r.className, pos: getComputedStyle(r).position, handle: getComputedStyle(r.querySelector(".civic-r03-handle")).display, title: getComputedStyle(r.querySelector(".civic-r03-head-row")).display };
    });
    assert.match(info.cls, /civic-r03-layout-embedded/);
    assert.equal(info.pos, "relative");
    assert.equal(info.handle, "none");
    assert.equal(info.title, "none", "host shows its own heading");
    await select(page, "r03-demo-shifted");
    const pos = await page.evaluate((mob) => {
      const map = window.__stand.map, c = map.getCanvas().getBoundingClientRect(), p = map.project([71.4304, 51.1282]);
      const x = c.left + p.x, y = c.top + p.y, r = document.querySelector(".stand-host-panel").getBoundingClientRect();
      return { ok: mob ? y < r.top - 8 : x > r.right + 8, x, y, r: [r.left, r.top, r.right, r.bottom] };
    }, vp === MOBILE);
    assert.ok(pos.ok, JSON.stringify(pos));
    assert.deepEqual(await noHorizontalOverflow(page), []);
    if (vp === DESKTOP) await shot(page, "desktop-1440-embedded-r01-like-host");
    assert.deepEqual(errors, []);
    await ctx.close();
  }
});

// ---------- regressions for the adversarial review (wf_a5038205-b19) ----------
const srcIds = (page) => page.evaluate(async () => (await window.__stand.map.getSource("civic-r03-objects").getData()).features.map((f) => f.properties.cid));

test("review: a second mount on the same root/map replaces the first cleanly", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await open({ persist: "0" });
  const r = await page.evaluate(async () => {
    const first = window.__stand.instance;
    const second = window.CivicMap.mount({ root: document.getElementById("civic-public"), map: window.__stand.map, api: window.__stand.api });
    await new Promise((res) => setTimeout(res, 400));
    const root = document.getElementById("civic-public");
    const mid = { children: root.childNodes.length, items: root.querySelectorAll(".civic-r03-item").length, layers: window.__stand.map.getStyle().layers.filter((l) => l.id.startsWith("civic-r03")).length };
    first.destroy(); // already destroyed by the second mount: must be a no-op
    const still = root.querySelectorAll(".civic-r03-item").length;
    second.destroy();
    return { mid, still, after: { children: root.childNodes.length, cls: root.getAttribute("class"), layers: window.__stand.map.getStyle().layers.filter((l) => l.id.startsWith("civic-r03")).length } };
  });
  assert.equal(r.mid.items, 12);
  assert.equal(r.mid.layers, 12);
  assert.equal(r.still, 12, "destroying the stale handle does not wipe the live UI");
  assert.deepEqual(r.after, { children: 0, cls: null, layers: 0 });
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("review: search filters the map too, counts it as an active filter, and reset restores it", { skip: SKIP }, async () => {
  const { ctx, page } = await open({ persist: "0" });
  assert.equal((await srcIds(page)).length, 11);
  await page.fill('[data-r03-filter="q"]', "сквер");
  await page.waitForFunction(() => window.__stand.instance.getState().q === "сквер");
  assert.deepEqual(await srcIds(page), ["r03-demo-nodata"]);
  assert.equal(await page.locator(".civic-r03-item").count(), 1);
  assert.match(await page.locator(".civic-r03-filters-active").innerText(), /активно: 1/);
  await page.click('.civic-r03-filters-body [data-r03-action="reset-filters"]');
  assert.equal((await srcIds(page)).length, 11);
  await ctx.close();
});

test("review: refresh after an object left the public list turns its open card into 'не найден'", { skip: SKIP }, async () => {
  const { ctx, page } = await open({ persist: "0" });
  await select(page, "r03-demo-shifted");
  await page.evaluate(async () => {
    const o = window.__stand.api.options;
    o.items = o.items.filter((x) => x.id !== "r03-demo-shifted");
    await window.__stand.instance.refresh();
  });
  await page.waitForFunction(() => window.__stand.instance.getState().detail === "notfound");
  assert.match(await page.locator(".civic-r03-card").innerText(), /Объект не найден/);
  assert.equal(await page.locator('[data-r03-action="feedback"]').count(), 0);
  await ctx.close();
});

test("review: a small polygon inside a big one is selectable on the map", { skip: SKIP }, async () => {
  const { ctx, page } = await open({ persist: "0" });
  await page.evaluate(async () => {
    const poly = (id, w, s, e, n) => ({ schema_version: "civic-v1", id, city: "astana", kind: "construction", title: id, status: "planned", publication: "published",
      geometry: { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] }, geometry_precision: "source", schedule: {}, budget: {}, responsible: {}, evidence_type: "synthetic", source_refs: [], revision: 1 });
    // the big one comes later in API order (drawn later = on top before the fix)
    window.__stand.api.options.items.push(poly("small", 71.370, 51.170, 71.374, 51.172), poly("big", 71.360, 51.165, 71.390, 51.180));
    await window.__stand.instance.refresh();
    window.__stand.map.jumpTo({ center: [71.372, 51.171], zoom: 15 });
  });
  await page.waitForTimeout(400);
  const pt = await page.evaluate(() => { const m = window.__stand.map, c = m.getCanvas().getBoundingClientRect(), p = m.project([71.372, 51.171]); return { x: c.left + p.x, y: c.top + p.y }; });
  await page.mouse.click(pt.x, pt.y);
  await page.waitForFunction(() => window.__stand.instance.getState().selectedId !== null);
  assert.equal((await state(page)).selectedId, "small");
  await ctx.close();
});

test("review: keyboard focus survives reset, show-undated and retry", { skip: SKIP }, async () => {
  const { ctx, page } = await open({ persist: "0" });
  const active = () => page.evaluate(() => { const a = document.activeElement; return a === document.body ? "BODY" : (a.getAttribute("data-r03-filter") || a.className); });
  await page.fill('[data-r03-filter="q"]', "zzzzqqq");
  await page.waitForFunction(() => window.__stand.instance.getState().q === "zzzzqqq");
  await page.focus('.civic-r03-empty [data-r03-action="reset-filters"]');
  await page.keyboard.press("Enter");
  assert.notEqual(await active(), "BODY");
  await page.selectOption('[data-r03-filter="period"]', "next30");
  await page.focus('[data-r03-action="show-undated"]');
  await page.keyboard.press("Enter");
  assert.notEqual(await active(), "BODY");
  await page.evaluate(async () => { window.__stand.api.options.failList = 1; await window.__stand.instance.refresh(); });
  await page.focus('[data-r03-action="retry-list"]');
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => window.__stand.instance.getState().list === "ready");
  assert.notEqual(await active(), "BODY");
  await ctx.close();
});

test("review: the error message is not re-inserted on every keystroke", { skip: SKIP }, async () => {
  const { ctx, page } = await open({ persist: "0" });
  await page.evaluate(async () => { window.__stand.api.options.failList = 1; await window.__stand.instance.refresh(); });
  await page.evaluate(() => {
    window.__ins = 0;
    new MutationObserver((ms) => { for (const m of ms) window.__ins += m.addedNodes.length; }).observe(document.querySelector(".civic-r03-state"), { childList: true, subtree: true });
  });
  await page.type('[data-r03-filter="q"]', "ремонт", { delay: 40 });
  await page.waitForTimeout(300);
  assert.equal(await page.evaluate(() => window.__ins), 0);
  assert.equal(await page.locator("#civic-public [role=alert]").count(), 0, "no assertive alert inside the polite region");
  await ctx.close();
});

test("review: landscape phone 667x375 keeps 3D toggle and attribution reachable in every sheet state", { skip: SKIP }, async () => {
  const { ctx, page } = await open({ persist: "0" }, { viewport: { width: 667, height: 375 }, touch: true });
  for (let i = 0; i < 3; i++) {
    assert.equal(await reachable(page, "#toggle-3d"), true, (await state(page)).sheet);
    assert.equal(await reachable(page, "#zoom-in"), true);
    assert.equal(await reachable(page, ".maplibregl-ctrl-attrib"), true);
    await page.click(".civic-r03-handle");
    await page.waitForTimeout(320);
  }
  await shot(page, "mobile-667x375-landscape");
  await ctx.close();
});

test("review: on a phone, an object tapped low on the map ends up above the opened sheet", { skip: SKIP }, async () => {
  const { ctx, page } = await open({ persist: "0", fit: "0" }, { viewport: MOBILE, touch: true });
  await page.evaluate(() => window.__stand.map.jumpTo({ center: [71.4511, 51.1255], zoom: 13 }));
  await page.waitForTimeout(300);
  const pt = await page.evaluate(() => { const m = window.__stand.map, c = m.getCanvas().getBoundingClientRect(), p = m.project([71.4511, 51.1209]); return { x: c.left + p.x, y: c.top + p.y }; });
  assert.ok(pt.y > 418 && pt.y < 640, "object starts where the half sheet will cover it: " + JSON.stringify(pt));
  await page.touchscreen.tap(pt.x, pt.y);
  await page.waitForFunction(() => window.__stand.instance.getState().selectedId === "r03-demo-completed");
  await settle(page);
  const pos = await objectClearOfPanel(page, [71.4511, 51.1209], true);
  assert.ok(pos.inView && pos.clear, JSON.stringify(pos));
  await ctx.close();
});

test("review: tapping the open object again does not re-fire onSelect or refetch", { skip: SKIP }, async () => {
  const { ctx, page } = await open({ persist: "0" });
  await settle(page);
  const pt = await page.evaluate(() => { const m = window.__stand.map, c = m.getCanvas().getBoundingClientRect(), p = m.project([71.4304, 51.1282]); return { x: c.left + p.x, y: c.top + p.y }; });
  await page.mouse.click(pt.x, pt.y);
  await page.waitForFunction(() => window.__stand.instance.getState().detail === "ready");
  await page.mouse.click(pt.x, pt.y);
  await page.waitForTimeout(300);
  const r = await page.evaluate(() => ({ calls: window.__stand.api.calls.filter((c) => c.path === "/objects/r03-demo-shifted").length, selects: window.__stand.selects.length }));
  assert.deepEqual(r, { calls: 1, selects: 1 });
  await ctx.close();
});

test("review: a custom period with only an end date works and survives reload", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await open();
  await page.selectOption('[data-r03-filter="period"]', "custom");
  await page.fill('[data-r03-filter="to"]', "2026-10-31");
  await page.dispatchEvent('[data-r03-filter="to"]', "change");
  await page.waitForTimeout(200);
  const n = await page.locator(".civic-r03-item").count();
  assert.ok(n > 0 && n < 12, String(n));
  await page.reload();
  await page.waitForFunction(() => window.__stand && window.__stand.instance && window.__stand.instance.getState().list === "ready", null, { timeout: 15000 });
  assert.equal(await page.locator(".civic-r03-item").count(), n);
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("review: synthetic points carry a dashed ring symbol that the legend describes", { skip: SKIP }, async () => {
  const { ctx, page } = await open({ persist: "0" });
  const r = await page.evaluate(() => {
    const m = window.__stand.map, l = m.getStyle().layers.find((x) => x.id === "civic-r03-point-synthetic");
    return { type: l && l.type, icon: l && l.layout && l.layout["icon-image"], image: m.hasImage("civic-r03-demo-ring"), legend: document.querySelector(".civic-r03-legend").textContent };
  });
  assert.deepEqual([r.type, r.icon, r.image], ["symbol", "civic-r03-demo-ring", true]);
  assert.match(r.legend, /Серое пунктирное кольцо/);
  await ctx.close();
});
