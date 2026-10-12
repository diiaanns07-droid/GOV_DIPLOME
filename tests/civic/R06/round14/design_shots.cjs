// R06 · дизайн-марафон: кадры всех экранов и состояний R06 в сборке R01 (1366×768, 375×812; ru, kk).
//   NODE_PATH="$(npm root -g)" node tests/civic/R06/round14/design_shots.cjs <дерево сборки> <папка> [фильтр-подстрока имени кадра] [ширины,через,запятую] [языки]
// Сервер — app.py дерева с CIVIC_DEMO=1 на временной базе; сотрудник с случайным паролем. Демо-данные synthetic.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const path = require("path"), fs = require("fs"), os = require("os"), net = require("net"), crypto = require("crypto");
const ROOT = path.resolve(process.argv[2]), OUT = path.resolve(process.argv[3]);
const ONLY = process.argv[4] || "";
const WIDTHS = (process.argv[5] || "1366,375").split(",").map(Number);
const LANGS = (process.argv[6] || "ru,kk").split(",");
fs.mkdirSync(OUT, { recursive: true });
const PW = "Kokzhiek-" + crypto.randomBytes(8).toString("hex") + "-Esil";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok) => { const s = net.createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => ok(p)); }); });
const log = [];

async function server() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "dm-")), db = path.join(tmp, "c.sqlite3"), port = await freePort();
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (a, i) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${a}`, { cwd: ROOT, env, input: i, stdio: [i ? "pipe" : "ignore", "ignore", "inherit"] });
  run("init"); run("seed-demo --package data/civic/astana/demo_synthetic.json"); run("seed-r14-demo");
  run("create-editor dmcheck --password-stdin --public-label Акимат", PW + "\n");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: "ignore" });
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) break; } catch {} await sleep(200); }
  srv.base = `http://127.0.0.1:${port}/`;
  return srv;
}

async function page(browser, base, w, lang, mode, login) {
  const ctx = await browser.newContext({ viewport: { width: w, height: w < 600 ? 812 : 768 }, deviceScaleFactor: 1 });
  await ctx.addInitScript(([m, l]) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); } catch (e) {} }, [mode, lang]);
  const p = await ctx.newPage();
  p.errs = [];
  p.on("pageerror", (e) => p.errs.push(e.message));
  await p.goto(base);
  if (login) {
    await p.evaluate(async (pw) => {
      await fetch("/api/civic/v1/session/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "dmcheck", password: pw }) });
    }, PW);
    await p.reload();
  }
  await p.waitForTimeout(800);
  return p;
}
async function shot(p, name, opts) {
  await p.waitForTimeout((opts && opts.wait) || 450);
  if (ONLY && !name.includes(ONLY)) return;
  const file = path.join(OUT, name + ".png");
  if (opts && opts.tall) {
    // Весь лист раздела: высота окна — по содержимому прокручиваемого листа (до 2600).
    const h = await p.evaluate(() => {
      const s = document.querySelector("#birge-screen") || document.scrollingElement;
      const sc = s.querySelector(".birge-screen__body") || s;
      return Math.min(2600, Math.max(innerHeight, sc.scrollHeight + 160));
    });
    const vp = p.viewportSize();
    await p.setViewportSize({ width: vp.width, height: h });
    await p.waitForTimeout(300);
    await p.screenshot({ path: file });
    await p.setViewportSize(vp);
  } else await p.screenshot({ path: file });
  log.push(name);
}

async function resident(browser, base, w, lang) {
  const tag = `${w}-${lang}`;
  // загрузка, ошибка, пусто
  {
    const p = await page(browser, base, w, lang, "resident");
    await p.route("**/api/civic/v2/ideas?*", async (r) => { await sleep(6000); r.continue().catch(() => {}); });
    await p.goto(base + "#ideas");
    await shot(p, `r-loading-${tag}`, { wait: 700 });
    await p.unroute("**/api/civic/v2/ideas?*");
    await p.route("**/api/civic/v2/ideas?*", (r) => r.abort("failed"));
    await p.goto(base + "#map"); await p.waitForTimeout(300);
    await p.goto(base + "#ideas");
    await shot(p, `r-error-${tag}`, { wait: 1500 });
    await p.unroute("**/api/civic/v2/ideas?*");
    await p.route("**/api/civic/v2/ideas?*", async (r) => {
      const res = await r.fetch(); const j = await res.json(); const d = j.data || j; d.items = []; d.counts = {};
      r.fulfill({ response: res, json: j });
    });
    await p.goto(base + "#map"); await p.waitForTimeout(300);
    await p.goto(base + "#ideas");
    await shot(p, `r-empty-${tag}`, { wait: 1500 });
    await p.context().close();
  }
  // список, вкладки, «Подробнее», поддержка
  {
    const p = await page(browser, base, w, lang, "resident");
    await p.goto(base + "#ideas");
    await p.waitForSelector(".ri .ri-card", { timeout: 30000 });
    await shot(p, `r-list-${tag}`);
    await shot(p, `r-list-tall-${tag}`, { tall: true });
    await p.locator(".ri-card .bk-details summary, .ri-card .ri-more summary").first().click();
    await shot(p, `r-more-${tag}`);
    const sup = p.locator(".ri-support").first();
    await sup.scrollIntoViewIfNeeded();
    await sup.click();
    await shot(p, `r-supported-${tag}`, { wait: 200 });
    await p.locator("[role=tab]").nth(1).click();
    await shot(p, `r-tab-project-${tag}`);
    await p.locator("[role=tab]").nth(2).click();
    await shot(p, `r-tab-rejected-${tag}`);
    if (p.errs.length) log.push("ERR " + tag + " " + p.errs.join(" | "));
    await p.context().close();
  }
  // мастер
  {
    const p = await page(browser, base, w, lang, "resident");
    await p.goto(base + "#ideas");
    await p.waitForSelector(".ri .ri-card", { timeout: 30000 });
    await p.locator("[data-key=new]").click();
    await shot(p, `w-step1-${tag}`);
    await p.locator("[data-key=pick]").click();
    await p.waitForSelector(".ri-pick");
    await shot(p, `w-pick-${tag}`, { wait: 900 });
    const box = await p.locator("#map canvas, .maplibregl-canvas").first().boundingBox();
    if (box) {
      await p.mouse.click(box.x + box.width * 0.55, box.y + box.height * 0.45);
      await p.waitForTimeout(900);
      await p.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.5);
      await shot(p, `w-pick-chosen-${tag}`, { wait: 600 });
      await p.locator(".ri-pick .bk-btn--primary").click();
    }
    await p.waitForSelector(".ri-wizard", { timeout: 10000 });
    await shot(p, `w-step1-done-${tag}`, { wait: 1200 });
    await p.locator("[data-key=next]").click();
    await shot(p, `w-step2-${tag}`);
    await p.locator("#ri-title").fill(lang === "kk" ? "Хабарласыңыз: 8 701 123 45 67" : "Звоните 8 701 123 45 67");
    await p.locator("[data-key=next]").click();
    await shot(p, `w-step2-error-${tag}`);
    await p.locator("#ri-title").fill(lang === "kk" ? "Керей және Жәнібек хандар көшесіндегі балалар алаңы" : "Детская площадка во дворе у школы № 45");
    await p.locator("#ri-text").fill(lang === "kk" ? "Аулада балаларға ойнайтын орын жоқ. Әткеншек пен құм салғышы бар шағын алаң қажет, кешке жарық болса екен." : "Во дворе детям негде играть. Нужна небольшая площадка с качелями и песочницей, вечером — со светом.");
    await shot(p, `w-step2-filled-${tag}`);
    await p.locator("[data-key=next]").click();
    await shot(p, `w-step3-${tag}`);
    await p.locator("[data-key=kind-playground]").click();
    await p.locator("[data-key=send]").click();
    await p.waitForSelector(".ri-sent", { timeout: 10000 });
    await shot(p, `w-sent-${tag}`);
    await p.locator("[data-key=back-list]").click();
    await p.waitForSelector(".ri-card", { timeout: 10000 });
    await shot(p, `r-mine-review-${tag}`, { wait: 900 });
    if (p.errs.length) log.push("ERR " + tag + " " + p.errs.join(" | "));
    await p.context().close();
  }
  // карточка проекта R06 на карте (проект по идее жителей)
  {
    const p = await page(browser, base, w, lang, "resident");
    const id = await p.evaluate(async () => {
      const r = await fetch("/api/civic/v2/proposals"); const j = await r.json(); const items = (j.data || j).items || [];
      const x = items.find((i) => i.idea) || items[0]; return x && x.id;
    });
    await p.waitForFunction(() => window.CivicShell && window.CivicShell.build3d && window.CivicShell.build3d.select, null, { timeout: 30000 }).catch(() => {});
    await p.evaluate(() => { try { window.BirgeShell && window.BirgeShell.setLayer && window.BirgeShell.setLayer("projects"); } catch (e) {} });
    await p.evaluate(() => { try { window.CivicShell.build3d.flyToProposals(); } catch (e) {} });
    await p.waitForTimeout(5000);
    await p.evaluate((id) => { try { window.CivicShell.build3d.select(id); } catch (e) {} }, id);
    await shot(p, `p-card-idea-${tag}`, { wait: 2000 });
    await p.context().close();
  }
}

async function akimat(browser, base, w, lang) {
  const tag = `${w}-${lang}`;
  {
    const p = await page(browser, base, w, lang, "akimat");
    await p.goto(base + "#projects");
    await shot(p, `a-nologin-${tag}`, { wait: 2500 });
    await p.goto(base + "#works");
    await shot(p, `k-nologin-${tag}`, { wait: 2500 });
    await p.context().close();
  }
  const p = await page(browser, base, w, lang, "akimat", true);
  await p.goto(base + "#projects");
  await p.waitForSelector(".ri .ri-card", { timeout: 30000 });
  await shot(p, `a-queue-${tag}`);
  await shot(p, `a-queue-tall-${tag}`, { tall: true });
  // идея на проверке: публиковать / отклонить / скрыть
  const review = p.locator(".ri-card", { has: p.locator('.bk-status[data-status="new"]') }).first();
  await review.locator("button[data-key^=open-]").click();
  await shot(p, `a-review-open-${tag}`);
  await p.locator(".ri-card--open .ri-panel button").nth(1).click();
  await shot(p, `a-reject-form-${tag}`);
  await p.locator(".ri-card--open button[data-key^=open-]").click();
  // идея на голосовании: чек-лист
  const voting = p.locator(".ri-card", { has: p.locator('.bk-status[data-status="accepted"]') }).first();
  await voting.locator("button[data-key^=open-]").click();
  await p.locator(".ri-card--open").scrollIntoViewIfNeeded();
  await shot(p, `a-check-${tag}`);
  for (const k of ["land", "networks", "access", "maintenance"]) await p.locator(`[data-key=check-${k}-yes]`).click();
  await p.locator(".ri-card--open [data-key=project]").scrollIntoViewIfNeeded();
  await shot(p, `a-check-allyes-${tag}`);
  await p.locator(".ri-card--open button[data-key^=open-]").click();
  await p.locator(".ri-decided summary").click();
  await p.locator(".ri-decided").scrollIntoViewIfNeeded();
  await shot(p, `a-decided-${tag}`);
  await p.locator("[data-key=tab-projects]").click();
  await shot(p, `a-projects-${tag}`, { wait: 900 });
  await shot(p, `a-projects-tall-${tag}`, { tall: true });
  // работы и отключения
  await p.goto(base + "#works");
  await p.waitForSelector(".rw [data-work]", { timeout: 30000 });
  await shot(p, `k-works-${tag}`);
  await shot(p, `k-works-tall-${tag}`, { tall: true });
  await p.locator("[data-key=add]").click();
  await shot(p, `k-form-${tag}`, { wait: 600 });
  await shot(p, `k-form-tall-${tag}`, { tall: true });
  const save = p.locator(".rw-form .bk-btn--primary").first();
  await save.scrollIntoViewIfNeeded();
  await save.click();
  await shot(p, `k-form-errors-${tag}`, { wait: 700 });
  await shot(p, `k-form-errors-tall-${tag}`, { tall: true });
  if (p.errs.length) log.push("ERR akimat " + tag + " " + p.errs.join(" | "));
  await p.context().close();
}

(async () => {
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  for (const w of WIDTHS) for (const lang of LANGS) {
    const srv = await server();
    try {
      if (!ONLY || /^(r|w|p)-/.test(ONLY)) await resident(browser, srv.base, w, lang).catch((e) => log.push(`FAIL resident ${w} ${lang}: ${e.message.split("\n")[0]}`));
      if (!ONLY || /^(a|k)-/.test(ONLY) || /nologin/.test(ONLY)) await akimat(browser, srv.base, w, lang).catch((e) => log.push(`FAIL akimat ${w} ${lang}: ${e.message.split("\n")[0]}`));
    } finally { srv.kill(); }
  }
  await browser.close();
  console.log(log.join("\n"));
})();
