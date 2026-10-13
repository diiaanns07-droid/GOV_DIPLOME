// R06 · эталон 13 окт: кадры «Проекты и идеи» в сборке R01 для сравнения с REFERENCE.html (вариант A) — житель (лист,
// карточка под строкой на телефоне, «Вы поддержали», «Проекты акимата») и акимат (лист, выбранная идея на голосовании,
// чек-лист, проекты), 1366×768 и 375×812, языки через запятую. Заменяет кадры дизайн-марафона (прежний вид карточек).
//   NODE_PATH="$(npm root -g)" node tests/civic/R06/round14/design_shots.cjs <дерево сборки> <папка> <префикс> [ru,kk]
// Сервер — app.py дерева с CIVIC_DEMO=1 на временной базе; сотрудник со случайным паролем. Демо-данные synthetic.
// Пары «эталон / было / стало» — research/round-14-results/R06/reference/.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const path = require("path"), fs = require("fs"), os = require("os"), net = require("net"), crypto = require("crypto");
const ROOT = path.resolve(process.argv[2]), OUT = path.resolve(process.argv[3]), PFX = process.argv[4] || "x";
const LANGS = (process.argv[5] || "ru").split(",");
fs.mkdirSync(OUT, { recursive: true });
const PW = "Altyn-" + crypto.randomBytes(8).toString("hex") + "-Orda";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok) => { const s = net.createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => ok(p)); }); });
async function server() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cmp-")), db = path.join(tmp, "c.sqlite3"), port = await freePort();
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (a, i) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${a}`, { cwd: ROOT, env, input: i, stdio: [i ? "pipe" : "ignore", "ignore", "inherit"] });
  run("init"); run("seed-demo --package data/civic/astana/demo_synthetic.json"); run("seed-r14-demo");
  run("create-editor cmpcheck --password-stdin --public-label Акимат", PW + "\n");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: "ignore" });
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) break; } catch {} await sleep(200); }
  srv.base = `http://127.0.0.1:${port}/`;
  return srv;
}
async function page(b, base, w, lang, mode, login) {
  const ctx = await b.newContext({ viewport: { width: w, height: w < 600 ? 812 : 768 } });
  await ctx.addInitScript(([m, l]) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); } catch (e) {} }, [mode, lang]);
  const p = await ctx.newPage();
  await p.goto(base);
  if (login) { await p.evaluate(async (pw) => { await fetch("/api/civic/v1/session/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "cmpcheck", password: pw }) }); }, PW); await p.reload(); }
  await p.waitForTimeout(1500);
  return p;
}
const shot = (p, name) => p.screenshot({ path: path.join(OUT, `${PFX}-${name}.png`) });
async function clickFirst(p, sels) { for (const s of sels) { const l = p.locator(s).first(); if (await l.count()) { await l.click().catch(() => {}); return true; } } return false; }
const nth = async (p, sel, i) => { const l = p.locator(sel).nth(i); if (await l.count()) { await l.click().catch(() => {}); return true; } return false; };
(async () => {
  const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const srv = await server();
  try {
    for (const lang of LANGS) for (const w of [1366, 375]) {
      const tag = `${w}-${lang}`;
      let p = await page(b, srv.base, w, lang, "resident");
      await p.goto(srv.base + "#ideas"); await p.waitForTimeout(3000);
      await shot(p, `resident-${tag}`);
      if (w < 600) { await nth(p, ".ri-pc[data-idea] .ri-pc__open", 0); await p.waitForTimeout(900); await shot(p, `resident-open-${tag}`); }
      await nth(p, "[data-key^=support-]", 0); await p.waitForTimeout(900);
      await shot(p, `resident-supported-${tag}`);
      await clickFirst(p, ["[data-key=tab-projects]"]); await p.waitForTimeout(1500);
      await shot(p, `resident-projects-${tag}`);
      await p.context().close();
      p = await page(b, srv.base, w, lang, "akimat", true);
      await p.goto(srv.base + "#projects"); await p.waitForTimeout(3000);
      await shot(p, `akimat-${tag}`);
      await nth(p, ".ri-pc[data-idea] .ri-pc__open", 1); await p.waitForTimeout(1200);
      await shot(p, `akimat-open-${tag}`);
      await clickFirst(p, ["[data-key=pd-check]"]); await p.waitForTimeout(900);
      await shot(p, `akimat-check-${tag}`);
      await clickFirst(p, ["[data-key=tab-projects]"]); await p.waitForTimeout(1500);
      await shot(p, `akimat-projects-${tag}`);
      await p.context().close();
    }
  } finally { srv.kill(); await b.close(); }
})();
