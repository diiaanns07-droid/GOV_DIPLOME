// R05 · раунд 15 · производительность 3D проектов: кадры в секунду при наклоне и вращении на 1366 × 768 и ленивая
// загрузка three.js. В облаке WebGL — SwiftShader (программная отрисовка на CPU): числа здесь — нижняя граница, на
// ноутбуке с видеокартой — LOCAL-12. Так и пишется в отчёт.
//
// Нужен стенд (COMMON «КАК ПОДНЯТЬ СТЕНД»). Запуск:  NODE_PATH=$(npm root -g) node tests/civic/R05/round15/perf_fps.mjs [--url …]
// Отчёт — research/round-15-results/R05/runs/perf_fps.json.
import { mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const arg = (n, d) => { const i = process.argv.indexOf(n); return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : d; };
const URL0 = arg("--url", "http://127.0.0.1:8655");
const { chromium } = require("playwright");
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
const page = await ctx.newPage();
const requests = [];
page.on("request", (r) => requests.push({ url: r.url().replace(URL0, ""), at: Date.now() }));
await page.goto(URL0 + "/?lang=ru");
await page.waitForFunction(() => window.CivicShell?.build3d && window.BirgeShell, null, { timeout: 60000 });
await page.waitForFunction(() => { try { return map.loaded() && !map.isMoving(); } catch (e) { return false; } }, null, { timeout: 60000 });
await page.waitForTimeout(1500);
const lazyFlat = requests.filter((r) => /three\.module|build3d\/data\/(nura|astana|proposals)/.test(r.url)).map((r) => r.url);

// Слой «Проекты», объёмный вид на проектах Нуры, затем замер: 4 с вращения и 3 с наклона туда-обратно.
await page.evaluate(() => window.BirgeShell.setLayer("projects"));
await page.waitForFunction(() => window.CivicShell.build3d.getState().phase === "ready", null, { timeout: 60000 });
const lazyAfterLayer = requests.filter((r) => /three\.module/.test(r.url)).length;
await page.evaluate(() => window.CivicShell.build3d.flyToProposals());
await page.waitForFunction(() => !map.isMoving(), null, { timeout: 30000 });
await page.evaluate(() => window.CivicShell.build3d.view3d(true));
await page.waitForFunction(() => { const s = window.CivicShell.build3d.getState(); return s.view === "3d" && s.three === "ready" && !s.animating; }, null, { timeout: 60000 });
await page.waitForFunction(() => !map.isMoving(), null, { timeout: 30000 });
await page.waitForTimeout(1500);
const state = await page.evaluate(() => { const s = window.CivicShell.build3d.getState(); return { count: s.count, memory: s.memory, zoom: +map.getZoom().toFixed(2), pitch: +map.getPitch().toFixed(1) }; });
async function measure(label, start) {
  return page.evaluate(async ([label, start]) => {
    let frames = 0, renders = 0;
    const onRender = () => renders++;
    map.on("render", onRender);
    let raf = true;
    const tick = () => { frames++; if (raf) requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
    const t0 = performance.now();
    await new Promise((res) => { new Function("res", start)(res); });
    const ms = performance.now() - t0;
    raf = false;
    map.off("render", onRender);
    return { label, ms: Math.round(ms), raf_fps: +(frames / (ms / 1000)).toFixed(1), map_fps: +(renders / (ms / 1000)).toFixed(1) };
  }, [label, start]);
}
const rotate = await measure("вращение 4 с (bearing +120°)", "map.once('moveend', res); map.easeTo({ bearing: map.getBearing() + 120, duration: 4000, easing: (t) => t });");
const tilt = await measure("наклон 3 с (60° → 30° → 60°)", "map.once('moveend', () => { map.once('moveend', res); map.easeTo({ pitch: 60, duration: 1500, easing: (t) => t }); }); map.easeTo({ pitch: 30, duration: 1500, easing: (t) => t });");
await ctx.close();
// Плоская карта без проектов — та же сцена для сравнения (три.js не участвует).
const ctx2 = await browser.newContext({ viewport: { width: 1366, height: 768 } });
const p2 = await ctx2.newPage();
await p2.goto(URL0 + "/?lang=ru");
await p2.waitForFunction(() => window.CivicShell?.build3d, null, { timeout: 60000 });
await p2.waitForFunction(() => { try { return map.loaded() && !map.isMoving(); } catch (e) { return false; } }, null, { timeout: 60000 });
await p2.evaluate(() => map.jumpTo({ center: [71.37, 51.13], zoom: 16.5, pitch: 52, bearing: -16 }));
await p2.waitForTimeout(1500);
const base = await p2.evaluate(async () => {
  let frames = 0, raf = true;
  const tick = () => { frames++; if (raf) requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
  const t0 = performance.now();
  await new Promise((res) => { map.once("moveend", res); map.easeTo({ bearing: map.getBearing() + 120, duration: 4000, easing: (t) => t }); });
  raf = false;
  return { label: "та же карта без 3D проектов, вращение 4 с", raf_fps: +(frames / ((performance.now() - t0) / 1000)).toFixed(1) };
});
await ctx2.close();
await browser.close();
let sha = "?";
try { sha = execSync("git rev-parse --short HEAD", { cwd: ROOT }).toString().trim(); } catch (e) {}
const report = {
  at: new Date().toISOString(), url: URL0, code_head: sha,
  env: "облако: Chromium headless, WebGL через SwiftShader (программная графика на CPU, без GPU) — числа ниже ноутбука; на ноутбуке — LOCAL-12",
  lazy: { flat_map_three_or_data_requests: lazyFlat, three_requests_after_projects_layer_flat: lazyAfterLayer },
  scene: state, results: [rotate, tilt, base],
};
console.log(JSON.stringify(report, null, 1));
await mkdir(path.join(ROOT, "research/round-15-results/R05/runs"), { recursive: true });
await writeFile(path.join(ROOT, "research/round-15-results/R05/runs/perf_fps.json"), JSON.stringify(report, null, 1));
