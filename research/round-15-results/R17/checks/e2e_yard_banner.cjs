// R17 · баннер кризиса жителю двора в зоне: R16 «Я живу здесь» → R17 incidents/updates → баннер (без подписки R08).
//   BIRGE_REPO=<папка сборки> NODE_PATH=$(npm root -g) node research/round-15-results/R17/checks/e2e_yard_banner.cjs <папка кадров>
// Свой сервер на временной базе (CIVIC_DEMO=1, CIVIC_DEMO_WORLD=1); печатает текст баннера у жителя двора в Нуре и без двора.
const { chromium } = require("playwright");
const path = require("path"), fs = require("fs"), os = require("os");
const { spawn, execSync } = require("child_process");
const REPO = process.env.BIRGE_REPO, OUT = process.argv[2];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r17b-")), db = path.join(tmp, "c.sqlite3");
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", CIVIC_DEMO_WORLD: "1" };
  const run = (a) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${a}`, { cwd: REPO, env, stdio: ["ignore", "ignore", "inherit"] });
  run("init"); run("seed-demo --package data/civic/astana/demo_synthetic.json");
  const port = 8990 + Math.floor(Math.random() * 9);
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: "ignore" });
  const kill = () => { try { srv.kill(); } catch {} };
  process.on("exit", kill);
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 150; i++) { try { if ((await fetch(base + "/api/health")).ok) break; } catch {} await sleep(200); }
  await sleep(1500);
  const yard = execSync(`python3 -B -c "from ui.civic_agencies import geo; print(next(y for y, v in geo.yards().items() if v['district'] == 'nura'))"`, { cwd: REPO }).toString().trim();
  const browser = await chromium.launch();
  const result = {};
  for (const [dev, join] of [["device-r17-banner-01", true], ["device-r17-banner-02", false]]) {
    if (join) {
      const r = await fetch(`${base}/api/civic/v2/together/yards/${yard}/join`, { method: "POST", headers: { "Content-Type": "application/json", Origin: base, "X-Birge-Device": dev }, body: JSON.stringify({ device_id: dev }) });
      result.join = r.status;
    }
    for (const [w, h, lang] of [[1366, 768, "ru"], [375, 812, "kk"]]) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h } });
      await ctx.addInitScript(([d, l]) => { localStorage.setItem("birge.device", d); localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l); }, [dev, lang]);
      const page = await ctx.newPage();
      await page.goto(base + "/");
      await sleep(5000);
      const banner = await page.evaluate(() => { const e = document.querySelector(".ag-banner"); return e && e.offsetParent !== null ? e.innerText.replace(/\s+/g, " ").trim().slice(0, 120) : null; });
      result[`${join ? "yard" : "none"}-${w}-${lang}`] = banner;
      if (join) await page.screenshot({ path: `${OUT}/yard-banner-${w}-${lang}.png` });
      await ctx.close();
    }
  }
  console.log(JSON.stringify({ yard, ...result }, null, 1));
  await browser.close(); kill();
})().catch((e) => { console.error(e); process.exit(1); });
