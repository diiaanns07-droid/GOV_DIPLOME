// R06 раунд 14 · R10 B-018 в НАСТОЯЩЕЙ сборке R01: «Картина дня» в ҚАЗ — названия демо-объектов по-казахски.
//
//   git archive origin/claude/sharp-dijkstra-0t87gl | tar -x -C /tmp/r01      # дерево сборки (только чтение)
//   (поверх — пути R06 из этой ветки, если проверяете ещё не взятую поставку: ui/civic_store, web/civic/proposals)
//   NODE_PATH="$(npm root -g)" node tests/civic/R06/round14/app_r01_day_kk.cjs /tmp/r01 [папка-скриншотов]
//
// Запускает python3 -B app.py дерева R01 с CIVIC_DEMO=1 на временной базе (seed-demo demo_synthetic.json +
// seed-r14-demo — как r14_b2.cjs R01), 1366 и 375: ҚАЗ → «Күн қорытындысы» → блок «Кестеден қалып жатқан нысандар».
// Проверяет: у каждого объекта блока казахское название (нет русских «Ремонт/Демо/улица…» и нет «Демо»),
// и в РУС — без служебного «Демо:». Синтетика: объекты и этапы — демо-набор, помечены «Пример».
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const ROOT = path.resolve(process.argv[2] || ".");
const OUT = process.argv[3] ? path.resolve(process.argv[3]) : null;
const results = [];
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail ? " — " + String(detail).slice(0, 400) : ""));
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function start(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (args) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: ROOT, env, stdio: ["ignore", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  run("seed-r14-demo");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

async function lateTitles(page) {
  await page.waitForSelector(".akim-objects", { timeout: 30000 });
  await page.waitForTimeout(600);
  return page.evaluate(() => Array.from(document.querySelectorAll(".akim-objects li, .akim-objects .akim-row, .akim-objects [data-id]"))
    .map((li) => (li.querySelector("strong, b, .akim-row__title, h3, h4, a, span") || li).textContent.trim()).filter(Boolean));
}

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r06-day-kk-"));
  const port = await freePort();
  const srv = await start(port, path.join(tmp, "civic.sqlite3"));
  const base = `http://127.0.0.1:${port}/`;
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  try {
    const api = await (await fetch(base + "api/civic/v2/objects/lagging")).json();
    const late = (api.data || api).late || [];
    check("API: отстающие демо-объекты с title_kk", late.length > 0 && late.every((o) => o.title_kk), late.map((o) => o.id + "=" + o.title_kk).join(" | "));
    for (const width of [1366, 375]) {
      const ctx = await browser.newContext({ viewport: { width, height: width < 600 ? 812 : 768 } });
      await ctx.addInitScript(() => { try { localStorage.setItem("birge.mode", "akimat"); } catch (e) {} });
      const page = await ctx.newPage();
      const errs = [];
      page.on("pageerror", (e) => errs.push(e.message));
      await page.goto(base);
      await page.waitForFunction(() => window.BirgeI18n && window.CivicShell, null, { timeout: 45000 });
      await page.evaluate(() => window.BirgeI18n.setLang("kk"));
      await page.waitForTimeout(400);
      const dayBtn = await page.$("#birge-header [data-section=day]");
      if (dayBtn && await dayBtn.isVisible()) await dayBtn.click();
      else await page.evaluate(() => document.querySelector("#birge-header [data-section=day]")?.click());
      const kk = await lateTitles(page);
      const russian = kk.filter((t) => /Демо|Ремонт|ремонт|Благоустройство|улица|строительство/.test(t));
      check(width + " ҚАЗ: «Картина дня» — названия объектов по-казахски", kk.length > 0 && russian.length === 0, kk.join(" | "));
      if (OUT) {
        fs.mkdirSync(OUT, { recursive: true });
        const block = await page.$(".akim-objects");
        await block.scrollIntoViewIfNeeded();
        await page.screenshot({ path: path.join(OUT, `r06-app-${width}-kk-day.png`) });
        await block.screenshot({ path: path.join(OUT, `r06-app-${width}-kk-day-objects.png`) });
      }
      await page.evaluate(() => window.BirgeI18n.setLang("ru"));
      await page.waitForTimeout(600);
      const ru = await lateTitles(page);
      check(width + " РУС: названия без служебного «Демо:»", ru.length > 0 && !ru.some((t) => /Демо|синтетик/i.test(t)), ru.join(" | "));
      check(width + ": нет ошибок JavaScript", errs.length === 0, errs.join(" | "));
      await ctx.close();
    }
  } finally {
    await browser.close();
    srv.kill();
  }
  const failed = results.filter((r) => !r.ok).length;
  console.log(JSON.stringify({ total: results.length, failed }));
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
