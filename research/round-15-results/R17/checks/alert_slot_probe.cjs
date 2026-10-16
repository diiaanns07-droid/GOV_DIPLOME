// R17 · слот плашки кризиса (.birge-alert R01) и левая панель: житель двора в Нуре («Я живу здесь» R16) → баннер «Буран в Нуре»;
// 1024 / 1366, без панели и с паспортом QR (?report=osm-node-4109037549): кто под центром «×» панели (elementFromPoint).
//   BIRGE_REPO=<сборка> NODE_PATH=$(npm root -g) [SLOT_CSS='…'] node research/round-15-results/R17/checks/alert_slot_probe.cjs <кадры>
// SLOT_CSS — проверить правку стиля до сборки (patches/R01_alert_slot_beside_panel.patch). Своя временная база.
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
  const dev = "device-r17-slot-01";
  const r = await fetch(`${base}/api/civic/v2/together/yards/${yard}/join`, { method: "POST", headers: { "Content-Type": "application/json", Origin: base, "X-Birge-Device": dev }, body: JSON.stringify({ device_id: dev }) });
  result.join = r.status;
  const css = process.env.SLOT_CSS || "";
  for (const [w, h, q] of [[1024, 768, ""], [1024, 768, "?report=osm-node-4109037549"], [1366, 768, ""], [1366, 768, "?report=osm-node-4109037549"]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    await ctx.addInitScript(([d]) => { localStorage.setItem("birge.device", d); localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", "ru"); }, [dev]);
    const page = await ctx.newPage();
    await page.goto(base + "/" + q);
    await sleep(6000);
    if (css) await page.addStyleTag({ content: css });
    await sleep(300);
    const g = await page.evaluate(() => {
      const box = (e) => { if (!e) return null; const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return cs.display === "none" || cs.visibility === "hidden" || !r.width ? null : [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)]; };
      const alert = document.querySelector(".birge-alert");
      const panels = [...document.querySelectorAll("#civic-panel, #birge-report-root, .civic-panel, [data-panel]")].map((e) => [e.id || e.className.toString().slice(0, 30), box(e)]).filter((x) => x[1]);
      const close = [...document.querySelectorAll("button")].filter((b) => /^(×|✕)$/.test((b.textContent || "").trim()) || /закрыть|close/i.test(b.getAttribute("aria-label") || "")).map((b) => ({ label: b.getAttribute("aria-label"), box: box(b) })).filter((x) => x.box);
      const hits = close.map((c) => { const x = (c.box[0] + c.box[2]) / 2, y = (c.box[1] + c.box[3]) / 2; const e = document.elementFromPoint(x, y); return [c.label, e ? (e.className && e.className.toString().slice(0, 40)) : null]; });
      const bodyAttrs = [...document.body.attributes].map((a) => a.name + "=" + a.value.slice(0, 30));
      const p = document.querySelector(".civic-panel");
      const pinfo = p ? { id: p.id, cls: p.className.toString().slice(0, 80), hidden: p.hidden, attrs: [...p.attributes].map((a) => a.name + "=" + a.value.slice(0, 20)).slice(0, 8), display: getComputedStyle(p).display, vis: getComputedStyle(p).visibility, box: box(p), opacity: getComputedStyle(p).opacity } : null;
      return { alert: box(alert), banner: !!document.querySelector(".ag-banner"), panels, hits: hits.slice(0, 6), pinfo, bodyAttrs };
    });
    await page.screenshot({ path: `${OUT}/slot-${w}${q ? "-report" : ""}.png` });
    result[`${w}${q ? "-report" : ""}`] = g;
    await ctx.close();
  }
  console.log(JSON.stringify({ yard, ...result }, null, 1));
  await browser.close(); kill();
})().catch((e) => { console.error(e); process.exit(1); });
