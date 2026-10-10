// R05 · 3D-превью · дымовая проверка в НАСТОЯЩЕМ приложении (web/index.html + web/map.js + сервер R01).
//
// Нужен запущенный сервер R01 с патчем research/round-14-results/R05/proposed_r01.patch:
//   git worktree add --detach ../r05-app HEAD && cd ../r05-app && git apply <путь>/proposed_r01.patch
//   python -m ui.web_server --port 8799
// Затем из корня этой ветки:  node tests/civic/R05/build3d/app_smoke.mjs http://127.0.0.1:8799/
// Оболочку R01 (shell.js) скрипт не меняет: монтирует модуль сам, на ту карту, которую создал map.js.
// Отчёт: research/round-14-results/R05/runs/app_smoke.json, скриншот screens/app_1366_ru_smoke.png.
import { createRequire } from "node:module";
import { writeFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const OUT = path.join(ROOT, "research/round-14-results/R05");
const URL0 = process.argv[2] || "http://127.0.0.1:8799/";
let chromium;
for (const id of ["playwright", "/opt/node22/lib/node_modules/playwright"]) {
  try {
    ({ chromium } = require(id));
    break;
  } catch (e) {
    /* следующий */
  }
}
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const result = { url: URL0, checks: [] };
const ok = (id, pass, detail) => {
  result.checks.push({ id, status: pass ? "PASS" : "FAIL", detail });
  console.log((pass ? "PASS " : "FAIL ") + id + (detail ? " — " + JSON.stringify(detail) : ""));
};
try {
  await page.goto(URL0);
  // map.js создаёт карту в глобальной переменной map; ждём её загрузки (без интернета — запасной стиль).
  await page.waitForFunction(() => typeof map !== "undefined" && map && map.loaded && map.isStyleLoaded(), null, { timeout: 60000 });
  ok("app_map_ready", true, await page.evaluate(() => ({ center: map.getCenter().toArray(), zoom: map.getZoom(), layers: map.getStyle().layers.length })));
  ok("module_scripts_served", await page.evaluate(() => !!(window.CivicBuild3D && window.CivicBuild3DCore && window.CivicBuild3DModels)));
  await page.evaluate(() => {
    map.jumpTo({ center: [71.4018, 51.1276], zoom: 17.8, pitch: 60, bearing: -25 });
    window.__b3d = CivicBuild3D.mount({ map, role: "akimat", buildMs: 300 });
  });
  await page.waitForFunction(() => __b3d.getState().phase !== "loading", null, { timeout: 60000 });
  const s = await page.evaluate(() => __b3d.getState());
  ok("mount_on_real_map", s.phase === "ready" && s.storeMode === "local", { phase: s.phase, storeMode: s.storeMode, count: s.count });
  // Поставить остановку в центре экрана мышью.
  await page.click(".b3d-card[data-kind=stop]");
  const c = await page.evaluate(() => {
    const r = map.getCanvas().getBoundingClientRect();
    return [r.left + r.width / 2, r.top + r.height * 0.4];
  });
  await page.mouse.move(c[0], c[1]);
  await page.mouse.click(c[0], c[1]);
  await page.click("[data-action=place]");
  await page.waitForFunction(() => !__b3d.getState().animating && __b3d.getState().count >= 3, null, { timeout: 30000 });
  const err = await page.evaluate(() => {
    const st = __b3d.getState();
    let w = 0;
    for (const p of st.proposals) {
      const a = __b3d._project(p.id, [0, 0, 0]);
      const b = map.project(p.kind === "lighting" ? p.geometry.coordinates[0] : p.geometry.coordinates);
      if (a) w = Math.max(w, Math.hypot(a.x - b.x, a.y - b.y));
    }
    return { count: st.count, worst_px: w };
  });
  ok("place_on_real_map_precise", err.count >= 3 && err.worst_px < 1, err);
  await mkdir(path.join(OUT, "screens"), { recursive: true });
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(OUT, "screens", "app_1366_ru_smoke.png") });
  ok("no_page_errors", errors.length === 0, errors.slice(0, 3));
} catch (e) {
  ok("smoke_run", false, e.message.split("\n")[0]);
}
await browser.close();
await mkdir(path.join(OUT, "runs"), { recursive: true });
result.generated_at = new Date().toISOString();
await writeFile(path.join(OUT, "runs", "app_smoke.json"), JSON.stringify(result, null, 1) + "\n");
process.exit(result.checks.every((c) => c.status === "PASS") ? 0 : 1);
