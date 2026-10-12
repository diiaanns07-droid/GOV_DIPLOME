// R06 волна 2: слой карты «Идеи жителей» в сборке R01 вместе с 3D-модулем R05 (≥ 395d9ea: setIdeas, событие идеи).
//
//   Дерево: FINAL R01 + web/civic/build3d R05 (+ его proposed_r01_wave2.patch) + пути R06 + r01_wave2_r06.patch.
//   NODE_PATH="$(npm root -g)" node tests/civic/R06/round14/app_r01_ideas_layer.cjs <дерево> [папка-скриншотов]
//
// Проверяет правило перегруза (R11 IA_WAVE2 §0.2): по умолчанию слоя нет; «Идеи жителей» — пункт в «Слой на карте»;
// при включении метки идей (голосование + ставшие проектом) рисует R05; нажатие на метку — карточка идеи в разделе.
// Со старым R05 (без setIdeas) пункта слоя быть не должно — пустых слоёв нет (отдельный прогон: та же команда на FINAL).
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const ROOT = path.resolve(process.argv[2] || ".");
const OUT = process.argv[3] ? path.resolve(process.argv[3]) : null;
if (OUT) fs.mkdirSync(OUT, { recursive: true });
const results = [];
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail && !ok ? " — " + String(detail).slice(0, 400) : ""));
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r06-layer-"));
  const db = path.join(tmp, "c.sqlite3");
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  for (const a of ["init", "seed-demo --package data/civic/astana/demo_synthetic.json", "seed-r14-demo"]) {
    execSync(`python3 -B -m ui.civic_store --db "${db}" ${a}`, { cwd: ROOT, env, stdio: ["ignore", "ignore", "inherit"] });
  }
  const port = await freePort();
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: "ignore" });
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) break; } catch {} await sleep(200); }
  const base = `http://127.0.0.1:${port}/`;
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  try {
    const hasR05 = fs.readFileSync(path.join(ROOT, "web/civic/build3d/build3d.js"), "utf8").includes("setIdeas");
    for (const [width, lang] of [[1366, "ru"], [375, "kk"]]) {
      const tag = `${width}-${lang}`;
      const ctx = await browser.newContext({ viewport: { width, height: width < 600 ? 812 : 768 } });
      await ctx.addInitScript((l) => { try { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l); } catch (e) {} }, lang);
      const page = await ctx.newPage();
      const errs = [];
      page.on("pageerror", (e) => errs.push(e.message));
      await page.goto(base);
      await page.waitForFunction(() => window.CivicShell && window.CivicShell.build3d && window.BirgeShell, null, { timeout: 30000 });
      await page.waitForTimeout(hasR05 ? 2500 : 4000); // слой регистрируется, когда R05 смонтирован (≤ 30 с)
      check(`${tag} по умолчанию дополнительного слоя нет`, await page.evaluate(() => !window.BirgeShell.layer && !document.body.dataset.birgeLayer));
      const options = await page.evaluate(() => Array.from(document.querySelectorAll("#birge-layer-list input")).map((i) => i.value));
      if (!hasR05) {
        check(`${tag} R05 без setIdeas — пункта «Идеи жителей» нет (пустого слоя нет)`, !options.includes("ideas"), options.join(","));
        await ctx.close();
        continue;
      }
      check(`${tag} «Идеи жителей» — пункт в «Слой на карте»`, options.includes("ideas"), options.join(","));
      await page.evaluate(() => window.BirgeShell.setLayer("ideas"));
      await page.waitForFunction(() => (window.CivicShell.build3d.getState().ideas || 0) > 0, null, { timeout: 15000 }).catch(() => null);
      const state = await page.evaluate(() => window.CivicShell.build3d.getState());
      check(`${tag} слой включён: R05 рисует 4 идеи (3 на голосовании + 1 стала проектом)`, state.ideas === 4, JSON.stringify(state).slice(0, 300));
      // Камера — на демо-идеи Нуры (на телефоне выше середины: низ экрана занимает шторка).
      const camera = await page.evaluate((phone) => { const m = map; m.jumpTo({ center: [71.3665, phone ? 51.1335 : 51.136], zoom: phone ? 15 : 15.6 }); return m.getZoom(); }, width < 600); // eslint-disable-line no-undef
      await page.waitForTimeout(1500);
      if (OUT) await page.screenshot({ path: path.join(OUT, `w2-layer-${tag}.png`) });
      const labels = await page.locator(".b3d-label--idea").count();
      check(`${tag} на карте метки идей видны (z ${camera.toFixed(1)})`, labels > 0, labels);
      // Нажимаем ту метку, которую в точке нажатия ничего не закрывает (кнопки карты, шторка, легенда).
      const free = await page.evaluate(() => Array.from(document.querySelectorAll(".b3d-label--idea")).findIndex((b) => {
        const r = b.getBoundingClientRect();
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return r.width > 0 && hit && (hit === b || b.contains(hit));
      }));
      check(`${tag} хотя бы одна метка идеи не закрыта кнопками и шторкой`, free >= 0, free);
      if (free >= 0) {
        await page.locator(".b3d-label--idea").nth(free).click();
        await page.waitForSelector(".ri .ri-card--flash, .ri .ri-card", { timeout: 15000 }).catch(() => null);
        const opened = await page.evaluate(() => [window.BirgeShell.section, !!document.querySelector(".ri .ri-card")]);
        check(`${tag} нажатие на метку идеи — раздел «Идеи», карточка открыта`, opened[0] === "ideas" && opened[1], JSON.stringify(opened));
      }
      await page.evaluate(() => { window.BirgeShell.setSection("map"); window.BirgeShell.setLayer(null); });
      await page.waitForTimeout(500);
      check(`${tag} слой выключен — идей на карте нет`, await page.evaluate(() => !(window.CivicShell.build3d.getState().ideas)));
      check(`${tag} нет ошибок JS`, errs.length === 0, errs.join(" | "));
      await ctx.close();
    }
  } finally {
    await browser.close();
    srv.kill();
  }
  const fail = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - fail}/${results.length} PASS`);
  process.exit(fail ? 1 : 0);
})();
