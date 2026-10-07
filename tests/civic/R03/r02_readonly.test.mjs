// R03 read-only run against R02's real CivicService (round 11).
//   node --test tests/civic/R03/r02_readonly.test.mjs
// R02 code is NOT copied into R03 paths: it is extracted from the pinned commit with
// `git archive` into a temp dir (or taken from R03_R02_ROOT). If neither is available the
// test is skipped and must be reported as NOT_RUN, never as PASS.
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
export const R02_SHA = process.env.R03_R02_SHA || "6a28de2";
function loadPlaywright() {
  try { return createRequire(import.meta.url)("playwright"); } catch (e) { /* fall through */ }
  try { return createRequire(path.join(execFileSync("npm", ["root", "-g"], { encoding: "utf8" }).trim(), "x.js"))("playwright"); } catch (e) { return null; }
}
function r02Root() {
  if (process.env.R03_R02_ROOT) return { dir: process.env.R03_R02_ROOT, temp: false };
  try {
    execFileSync("git", ["cat-file", "-e", R02_SHA + "^{commit}"], { cwd: ROOT, stdio: "ignore" });
    const dir = mkdtempSync(path.join(os.tmpdir(), "r03-r02src-"));
    const tar = execFileSync("git", ["archive", R02_SHA, "ui/civic_store"], { cwd: ROOT, maxBuffer: 64 << 20 });
    execFileSync("tar", ["x", "-C", dir], { input: tar });
    return { dir, temp: true };
  } catch (e) { return null; }
}
const pw = loadPlaywright();
const src = pw ? r02Root() : null;
const SKIP = !pw ? "playwright is not installed (NOT_RUN)" : !src ? "R02 source " + R02_SHA + " not available locally (NOT_RUN)" : false;
const SHOTS = process.env.R03_SHOTS ? path.resolve(ROOT, process.env.R03_SHOTS) : null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

let proc, info, browser, base;
before(async () => {
  if (SKIP) return;
  proc = spawn("python3", ["-I", path.join(ROOT, "tests/civic/R03/r02_readonly_server.py"), "--r02-root", src.dir], { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"] });
  let stderr = "";
  proc.stderr.on("data", (d) => { stderr += d; });
  const line = await new Promise((resolve, reject) => {
    const rl = readline.createInterface({ input: proc.stdout });
    rl.once("line", resolve);
    proc.once("exit", (code) => reject(new Error("harness exited " + code + ": " + stderr)));
    setTimeout(() => reject(new Error("harness timeout: " + stderr)), 60000);
  });
  info = JSON.parse(line);
  base = "http://127.0.0.1:" + info.port;
  browser = await pw.chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"] });
});
after(async () => {
  if (browser) await browser.close();
  if (proc) proc.kill();
  if (src && src.temp) rmSync(src.dir, { recursive: true, force: true });
});

async function open(viewport) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await page.goto(base + "/research/round-11-results/R03/stand/?api=real&persist=0&today=2026-10-06");
  await page.waitForFunction(() => window.__stand && window.__stand.instance && ["ready", "error"].includes(window.__stand.instance.getState().list), null, { timeout: 30000 });
  return { ctx, page, errors };
}

test("R02 read-only: public list = published only; card shows R02 history reason; no staff/POST from the browser", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await open({ width: 1440, height: 900 });
  const s = await page.evaluate(() => window.__stand.instance.getState());
  assert.equal(s.list, "ready");
  assert.equal(s.count, 11, "13 seeded - 1 draft - 1 archived");
  const titles = await page.evaluate(() => [...document.querySelectorAll(".civic-r03-item-title")].map((e) => e.textContent));
  assert.ok(!titles.some((t) => /Черновик R03|Снятая с публикации/.test(t)));
  const id = info.ids["r03-demo-shifted"];
  await page.evaluate((x) => window.__stand.instance.selectObject(x), id);
  await page.waitForFunction(() => window.__stand.instance.getState().detail === "ready");
  await page.waitForFunction(() => !window.__stand.map || !window.__stand.map.isMoving());
  const text = await page.locator(".civic-r03-card").innerText();
  assert.match(text, /Срок перенесён на 16 дней позже/);
  assert.match(text, /Причина: «Демо: перенос из-за поставки материалов/);
  assert.match(text, /Редакция \(демо R03\)/);
  assert.match(text, /Стоимость\s+нет данных/, "R02 keeps tenge off synthetic records");
  assert.match(text, /Синтетическая демо-запись/);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "r02-readonly-desktop-1440-card.png") });
  // unknown id -> honest not found from the real 404
  await page.evaluate(() => window.__stand.instance.selectObject("ast-0000000000"));
  await page.waitForFunction(() => window.__stand.instance.getState().detail === "notfound");
  // null geometry is listed and not drawn
  const nogeo = info.ids["r03-demo-nogeo"];
  const drawn = await page.evaluate(() => window.__stand.map.queryRenderedFeatures().map((f) => f.properties && f.properties.cid).filter(Boolean));
  assert.ok(!drawn.includes(nogeo));
  assert.equal(await page.locator(`[data-id="${nogeo}"]`).count(), 1);
  const log = await (await fetch(base + "/__r03/log")).json();
  assert.ok(log.length >= 3);
  assert.ok(log.every((r) => r.method === "GET" && /^\/api\/civic\/v1\/objects(\/|$)/.test(r.path)), JSON.stringify(log));
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("R02 read-only on 390x844: card readable in the bottom sheet, no horizontal overflow", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await open({ width: 390, height: 844 });
  await page.evaluate((x) => window.__stand.instance.selectObject(x), info.ids["r03-demo-long-kk"]);
  await page.waitForFunction(() => window.__stand.instance.getState().detail === "ready");
  const overflow = await page.evaluate(() => {
    const r = document.getElementById("civic-public");
    return [r, ...r.querySelectorAll(".civic-r03-card, .civic-r03-sec, .civic-r03-dl")].filter((e) => e.offsetParent !== null && e.scrollWidth > e.clientWidth + 1).map((e) => e.className);
  });
  assert.deepEqual(overflow, []);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "r02-readonly-mobile-390-card.png") });
  assert.deepEqual(errors, []);
  await ctx.close();
});
