// R03 round 13: the public map against R02's REAL CivicService (not the mock) — paging beyond one page,
// slow answers, a filter changed during loading, a superseded request, an object archived while open,
// identical points, deep link + reload.
//   node --test --test-concurrency=1 tests/civic/R03/r02_contract.test.mjs
// R02 code comes from a pinned commit via `git archive` into a temp dir (R03_R02_SHA, default: R02's round-12
// code bd7a911; falls back to round 11 6a28de2). 241 published records = 11 R03 fixtures + 230 EXPLICITLY
// SYNTHETIC test records created in a temporary SQLite only. Not available -> skipped, reported as NOT_RUN.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { spawn, execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { mkdtempSync, mkdirSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import readline from "node:readline";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const CANDIDATES = process.env.R03_R02_SHA ? [process.env.R03_R02_SHA] : ["bd7a911ad23573ce0d168823199ecb3cc86557c9", "6a28de2"];
const BULK = 230, SAME = 60, FIXTURES = 11;
function loadPlaywright() {
  try { return createRequire(import.meta.url)("playwright"); } catch (e) { /* fall through */ }
  try { return createRequire(path.join(execFileSync("npm", ["root", "-g"], { encoding: "utf8" }).trim(), "x.js"))("playwright"); } catch (e) { return null; }
}
function r02Root() {
  for (const sha of CANDIDATES) {
    try {
      execFileSync("git", ["cat-file", "-e", sha + "^{commit}"], { cwd: ROOT, stdio: "ignore" });
      const dir = mkdtempSync(path.join(os.tmpdir(), "r03-r02src-"));
      const tar = execFileSync("git", ["archive", sha, "ui/civic_store"], { cwd: ROOT, maxBuffer: 64 << 20 });
      execFileSync("tar", ["x", "-C", dir], { input: tar });
      return { dir, sha };
    } catch (e) { /* next */ }
  }
  return null;
}
const pw = loadPlaywright();
const src = pw ? r02Root() : null;
const SKIP = !pw ? "playwright is not installed (NOT_RUN)" : !src ? "R02 source not available locally (NOT_RUN)" : false;
const SHOTS = process.env.R03_SHOTS ? path.resolve(ROOT, process.env.R03_SHOTS) : null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

let proc, info, browser, base;
before(async () => {
  if (SKIP) return;
  proc = spawn("python3", ["-I", path.join(ROOT, "tests/civic/R03/r02_readonly_server.py"), "--r02-root", src.dir, "--bulk", String(BULK), "--same-spot", String(SAME)],
    { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"], env: Object.assign({}, process.env, { PYTHONDONTWRITEBYTECODE: "1" }) });
  let stderr = "";
  proc.stderr.on("data", (d) => { stderr += d; });
  const line = await new Promise((resolve, reject) => {
    const rl = readline.createInterface({ input: proc.stdout });
    rl.once("line", resolve);
    proc.once("exit", (code) => reject(new Error("harness exited " + code + ": " + stderr)));
    setTimeout(() => reject(new Error("harness timeout: " + stderr)), 120000);
  });
  info = JSON.parse(line);
  base = "http://127.0.0.1:" + info.port;
  browser = await pw.chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"] });
});
after(async () => {
  if (browser) await browser.close();
  if (proc) proc.kill();
  if (src) rmSync(src.dir, { recursive: true, force: true });
});

const control = (what, body) => fetch(base + "/__r03/" + what, { method: "POST", body: JSON.stringify(body) }).then((r) => r.json());
const apiLog = () => fetch(base + "/__r03/log").then((r) => r.json());
async function open(o = {}) {
  const ctx = await browser.newContext({ viewport: o.viewport || { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await page.goto(base + "/tests/civic/R03/stand/?api=real&persist=0&fit=0&today=2026-10-06" + (o.query || "") + (o.hash || ""));
  await page.waitForFunction(() => window.__stand && window.__stand.instance && ["ready", "error"].includes(window.__stand.instance.getState().list), null, { timeout: 60000 });
  return { ctx, page, errors };
}
const state = (page) => page.evaluate(() => window.__stand.instance.getState());

test("R02 paging: 241 published records come in pages of 100 by cursor; map moves never refetch", { skip: SKIP }, async () => {
  const n0 = (await apiLog()).length;
  const { ctx, page, errors } = await open();
  const s = await state(page);
  assert.equal(s.count, FIXTURES + BULK, "every published record, none dropped at a page edge");
  const lists = (await apiLog()).slice(n0).filter((r) => r.path === "/api/civic/v1/objects");
  assert.equal(lists.length, 3, JSON.stringify(lists));
  assert.ok(lists.every((r) => /(^|&)limit=100(&|$)/.test(r.query)), "limit=100 on every page");
  assert.ok(lists.slice(1).every((r) => /cursor=/.test(r.query)), "next pages by R02's cursor");
  const ids = await page.evaluate(() => [...document.querySelectorAll(".civic-r03-item")].map((b) => b.dataset.id));
  assert.equal(new Set(ids).size, ids.length, "no duplicates across pages");
  assert.match(await page.locator(".civic-r03-list-notes").innerText(), /Показаны первые 200 из 241/);
  // panning/zooming and the visible-part filter work on the loaded list only
  const n1 = (await apiLog()).length;
  await page.evaluate(async () => {
    const m = window.__stand.map;
    window.__stand.instance.setFilters({ area: true });
    for (let i = 0; i < 10; i++) { m.jumpTo({ center: [71.36 + i * 0.01, 51.12], zoom: 13 + (i % 3) }); await new Promise((r) => setTimeout(r, 60)); }
  });
  await page.waitForTimeout(600);
  assert.equal((await apiLog()).length, n1, "no request per map move");
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("R02 slow network: a filter chosen during loading applies to the late answer; a superseded refresh never mixes in", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await open();
  await control("delay", { ms: 700 });
  try {
    await page.evaluate(() => { window.__stand.instance.refresh(); window.__stand.instance.setFilters({ kinds: ["event"] }); });
    assert.equal((await state(page)).list, "loading");
    await page.waitForFunction(() => window.__stand.instance.getState().list === "ready", null, { timeout: 20000 });
    const kinds = await page.evaluate(() => [...document.querySelectorAll(".civic-r03-item .civic-r03-item-kind")].map((e) => e.textContent));
    assert.ok(kinds.length > 0 && kinds.every((t) => /Событие/.test(t)), kinds.slice(0, 5).join("|"));
    // two refreshes in a row: the first is aborted/ignored, the list is the second one's, exactly once
    await page.evaluate(() => { window.__stand.instance.setFilters({ kinds: [] }); window.__stand.instance.refresh(); setTimeout(() => window.__stand.instance.refresh(), 150); });
    await page.waitForTimeout(300);
    await page.waitForFunction(() => window.__stand.instance.getState().list === "ready", null, { timeout: 20000 });
    assert.equal((await state(page)).count, FIXTURES + BULK);
    const ids = await page.evaluate(() => [...document.querySelectorAll(".civic-r03-item")].map((b) => b.dataset.id));
    assert.equal(new Set(ids).size, ids.length);
  } finally { await control("delay", { ms: 0 }); }
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("R02 identical points: one tap lists them; the overflow note does not promise that zooming separates them", { skip: SKIP }, async () => {
  const { ctx, page } = await open();
  await page.evaluate(() => window.__stand.map.jumpTo({ center: [71.40, 51.15], zoom: 17 }));
  await page.waitForTimeout(600);
  const pt = await page.evaluate(() => { const m = window.__stand.map, c = m.getCanvas().getBoundingClientRect(), p = m.project([71.40, 51.15]); return { x: c.left + p.x, y: c.top + p.y }; });
  await page.mouse.click(pt.x, pt.y);
  await page.waitForFunction(() => window.__stand.instance.getState().view === "pick");
  const t = await page.locator(".civic-r03-card").innerText();
  assert.match(t, /Здесь 50 объектов рядом/);
  assert.match(t, /Ещё 10 в этой же точке — они есть в общем списке/);
  assert.doesNotMatch(t, /приблизьте карту/);
  await ctx.close();
});

test("R02 object archived while open + deep link and reload: same card, then an honest 'no longer published'", { skip: SKIP }, async () => {
  const id = info.ids["r03-bulk-0100"];
  const { ctx, page, errors } = await open({ query: "&permalink=1", hash: "#civic-object=" + encodeURIComponent(id) });
  await page.waitForFunction(() => window.__stand.instance.getState().detail === "ready");
  assert.equal((await state(page)).selectedId, id);
  await page.reload();
  await page.waitForFunction(() => window.__stand && window.__stand.instance && window.__stand.instance.getState().detail === "ready", null, { timeout: 60000 });
  assert.equal((await state(page)).selectedId, id, "reload opens the same object");
  assert.match(await page.locator(".civic-r03-card-title").first().innerText(), /Тест R03 №101/);
  // an editor archives it while the resident looks at it; the next refresh says so in plain words
  assert.deepEqual(await control("archive", { id }), { ok: true });
  await page.evaluate(() => window.__stand.instance.refresh());
  await page.waitForFunction(() => window.__stand.instance.getState().detail === "notfound", null, { timeout: 20000 });
  const card = await page.locator(".civic-r03-card").innerText();
  assert.match(card, /Объект не найден/);
  assert.match(card, /сняли с публикации или ссылка устарела/);
  assert.equal((await state(page)).count, FIXTURES + BULK - 1);
  // the same link after a reload: not found, not a blank page or an invented card
  await page.reload();
  await page.waitForFunction(() => window.__stand && window.__stand.instance && window.__stand.instance.getState().detail === "notfound", null, { timeout: 60000 });
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "r13-r02-deeplink-unpublished-1440.png") });
  assert.deepEqual(errors, []);
  await ctx.close();
});
