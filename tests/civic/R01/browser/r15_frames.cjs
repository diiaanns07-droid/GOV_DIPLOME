// R01 round 15: frames of the new sections for the build acceptance (amendment P1 — a person looks at every frame:
// no drawn copies of buildings or logos, no large illustrations, no emoji, no glow/gradients «for beauty»).
// Starts a stand with the R02 demo world and a staff account, then shoots 1366 / 1024 / 375 × ru / kk:
//   akimat — map with the legend line (+ «▶ Хроника»), «Картина дня», «Ведомства» (табло, календарь работ, кризис),
//   «Сделаем вместе», «Вопросы и встречи», «Спросить Birge», the chronicle bar, «Ситуационный центр» (/civic/board/);
//   resident — map, «Мой двор» (scene 7), «Сделаем вместе», «Мои обращения».
// Usage: node tests/civic/R01/browser/r15_frames.cjs <out_dir> [sizes=1366,1024,375] [langs=ru,kk]
// Writes <out_dir>/<size>_<lang>_<view>_<screen>.jpg and frames.json (what was shot, page errors). Writes nothing into the repo.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(__dirname, "../../../..");
const OUT = path.resolve(process.argv[2] || "r15-frames-out");
const SIZES = (process.argv[3] || "1366,1024,375").split(",").map(Number);
const LANGS = (process.argv[4] || "ru,kk").split(",");
const USER = "operator", PASSWORD = "Birge-Stend-Kokshetau-77";
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet|\[i18n\] неизвестный ключ/i;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function startServer(port, dir) {
  const db = path.join(dir, "civic.sqlite3");
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", CIVIC_DEMO_WORLD: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (args, input) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: REPO, env, input, stdio: ["pipe", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  run(`create-editor ${USER} --password-stdin`, PASSWORD + "\n" + PASSWORD + "\n");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}
const ready = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && window.BirgeShell && typeof mapReady !== "undefined" && mapReady
  && document.querySelector("#birge-header"), null, { timeout: 45000 }).then(() => page.waitForTimeout(1200));

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r01-r15-frames-"));
  const port = await freePort();
  const srv = await startServer(port, tmp);
  const base = `http://127.0.0.1:${port}/`;
  const browser = await chromium.launch();
  const shots = [];
  try {
    for (const w of SIZES) for (const lang of LANGS) for (const mode of ["akimat", "resident"]) {
      const mobile = w < 761, h = mobile ? 812 : 768;
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile });
      await ctx.addInitScript(([m, l]) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); } catch (e) { /* без хранилища */ } }, [mode, lang]);
      const page = await ctx.newPage();
      const errs = [];
      page.on("pageerror", (e) => errs.push("pageerror: " + e.message));
      page.on("console", (m) => { if (m.type() === "error" && !NOISE.test(m.text())) errs.push(m.text().slice(0, 200)); });
      await page.goto(base);
      await ready(page);
      if (mode === "akimat") await page.evaluate(([u, p]) => window.CivicShell.api.login(u, p), [USER, PASSWORD]).catch(() => null);
      const shoot = async (name) => {
        const file = `${w}_${lang}_${mode}_${name}.jpg`;
        await page.screenshot({ path: path.join(OUT, file), type: "jpeg", quality: 72 });
        shots.push({ file, size: w, lang, mode, name, hash: await page.evaluate(() => location.hash) });
      };
      const section = async (id, pathPart) => {
        await page.evaluate(([s, p]) => window.BirgeShell.setSection(s, p ? { path: p } : undefined), [id, pathPart || null]);
        await page.waitForTimeout(1500);
      };
      await shoot("map");
      if (mode === "akimat") {
        await section("day"); await shoot("day");
        if (await page.evaluate(() => window.BirgeShell.sections().includes("agencies"))) {
          await section("agencies", "board"); await shoot("agencies-board");
          await section("agencies", "calendar"); await shoot("agencies-calendar");
          await section("agencies", "crisis/inc-w15-buran"); await shoot("agencies-crisis");
        }
        for (const id of ["together", "meetings", "analyst"]) {
          if (await page.evaluate((s) => window.BirgeShell.sections().includes(s), id)) { await section(id); await shoot(id); }
        }
        await section("map");
        const chip = await page.$("#birge-legend .birge-replay-chip");
        if (chip && await chip.isVisible()) {
          await chip.click();
          await page.waitForFunction(() => document.querySelector(".rp-host .rp-bar"), null, { timeout: 8000 }).catch(() => null);
          await page.waitForTimeout(4000);
          await shoot("chronicle");
          await page.keyboard.press("Escape");
          await page.waitForTimeout(600);
        }
        if (!mobile) {
          await page.goto(base + "civic/board/");
          await page.waitForTimeout(3500);
          await shoot("board-page");
        }
      } else {
        if (await page.evaluate(() => window.BirgeShell.sections().includes("yard"))) {
          await page.evaluate(() => window.BirgeTogether ? window.BirgeTogether.open("yard", "yard-1454082640") : window.BirgeShell.setSection("yard"));
          await page.waitForTimeout(2000);
          await shoot("yard");
        }
        if (await page.evaluate(() => window.BirgeShell.sections().includes("together"))) { await section("together"); await shoot("together"); }
        await section("map");
        await page.evaluate(() => window.CivicShell.openMine && window.CivicShell.openMine());
        await page.waitForTimeout(1500);
        await shoot("mine");
      }
      shots.push({ page: `${w}_${lang}_${mode}`, errors: errs });
      await ctx.close();
    }
  } finally {
    await browser.close();
    srv.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  fs.writeFileSync(path.join(OUT, "frames.json"), JSON.stringify(shots, null, 1));
  const errors = shots.filter((s) => s.errors && s.errors.length);
  console.log(JSON.stringify({ frames: shots.filter((s) => s.file).length, pages_with_errors: errors.length }));
  for (const e of errors) console.log("ERRORS " + e.page + ": " + e.errors.slice(0, 3).join(" | "));
}
main().catch((e) => { console.error(e); process.exit(2); });
