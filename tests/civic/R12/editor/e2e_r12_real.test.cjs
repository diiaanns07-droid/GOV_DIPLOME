/* R12 round 14: «Участок улицы» в редакторе на НАСТОЯЩЕМ графе OSM Астаны (engine/civic_geo через
 * tests/civic/R12/geo_api_server.py). Сотрудник делает два нажатия на улице Сакена Сейфуллина — сохранённая
 * линия везде не дальше 5 м от формы рёбер графа (CONTRACT §8.3).
 * Run:  node --test tests/civic/R12/editor/e2e_r12_real.test.cjs   (R12_SHOTS=1 -> research/round-14-results/R12/screenshots/)
 */
"use strict";
const { describe, it, before, after } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const fs = require("fs");
const { spawn, execFileSync } = require("child_process");
const { startStand } = require("./stand.cjs");
const { loadPlaywright, makeKit, fk } = require("./e2e_helpers.cjs");

const PW = loadPlaywright();
const REPO = path.resolve(__dirname, "../../../..");
const SHOTS = path.resolve(REPO, "research/round-14-results/R12/screenshots");

describe("R12 editor on the real OSM graph", { skip: PW ? false : "playwright not installed" }, () => {
  let stand, browser, K, geo, geoUrl;
  const pages = [];
  before(async () => {
    geo = spawn("python3", ["-B", path.join(REPO, "tests/civic/R12/geo_api_server.py")], { cwd: REPO, stdio: ["ignore", "pipe", "inherit"] });
    geoUrl = await new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error("geo server did not start")), 60000);
      geo.stdout.on("data", (d) => { const m = /READY (\d+)/.exec(String(d)); if (m) { clearTimeout(t); resolve("http://127.0.0.1:" + m[1] + "/api/civic/v2"); } });
    });
    stand = await startStand();
    browser = await PW.chromium.launch({ args: ["--enable-unsafe-swiftshader"] });
    K = makeKit({ stand, browser, pages, shotsDir: SHOTS });
  });
  after(async () => {
    for (const p of pages) for (const e of p.errors) console.error("pageerror:", e);
    if (browser) await browser.close();
    if (stand) await stand.close();
    if (geo) geo.kill();
  });

  it("two clicks on улица Сакена Сейфуллина -> a saved line within 5 m of the OSM street everywhere", async () => {
    const p = await K.open(undefined, "?geo=real&geoPrefix=" + encodeURIComponent(geoUrl));
    await K.loginToList(p);
    await K.fillDraft(p, { title: "Перекрытие Сейфуллина (демо R12)" });
    await p.check(fk("place-approximate"));
    await p.evaluate(() => window.__map.jumpTo({ center: [71.4289, 51.1716], zoom: 16 }));
    await p.waitForFunction(() => !window.__map.isMoving());
    const clickAt = async (lon, lat) => {
      const q = await p.evaluate(([x, y]) => { const a = window.__map.project([x, y]), r = window.__map.getCanvas().getBoundingClientRect(); return { x: r.left + a.x, y: r.top + a.y }; }, [lon, lat]);
      await p.mouse.click(q.x, q.y);
    };
    await p.click(fk("tool-segment"));
    await clickAt(71.4251, 51.1712);
    await p.waitForSelector(`${fk("seg-step")}:has-text("Начало: улица Сакена Сейфуллина")`, { timeout: 15000 });
    await clickAt(71.4326, 51.1719);
    await p.waitForSelector(`${fk("seg-step")}:has-text("Участок: улица Сакена Сейфуллина")`, { timeout: 15000 });
    if (process.env.R12_SHOTS === "1") { fs.mkdirSync(SHOTS, { recursive: true }); await p.screenshot({ path: path.join(SHOTS, "editor-real-seifullin-1280.png") }); }
    await p.click(fk("tool-done"));
    await p.check(fk("geometry_confirmed"));
    await K.saveOk(p, "Черновик создан");
    const g = K.objects()[0].geometry;
    assert.equal(g.type, "LineString");
    assert.ok(g.coordinates.length >= 4, "линия повторяет вершины OSM, а не 2 точки: " + g.coordinates.length);
    // Проверка точности на стороне Python: каждые 2 м линии — не дальше 5 м от ребра графа.
    const out = execFileSync("python3", ["-B", "-c", [
      "import json,sys; from engine.civic_geo.graph import get_graph; from engine.civic_geo import geo",
      "c=json.loads(sys.argv[1]); g=get_graph()",
      "near=[e.geometry for _,e,_ in g.nearest(c[len(c)//2], 600)]",
      "print(round(geo.max_offset_m(c, near), 2))"].join("\n"), JSON.stringify(g.coordinates)], { cwd: REPO, encoding: "utf8" });
    const off = Number(out.trim());
    assert.ok(off <= 5, "отклонение от улицы " + off + " м");
  });
});
