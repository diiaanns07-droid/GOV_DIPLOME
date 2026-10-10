// R05 · освещение вдоль участка улицы через настоящий движок R12 (engine.civic_geo), в том числе вне Нуры.
//   python3 tests/civic/R05/build3d/geo_stand.py --r12 <копия ветки R12> --port 8617 &
//   node tests/civic/R05/build3d/geo_check.mjs http://127.0.0.1:8617
// Отчёт: research/round-14-results/R05/runs/geo_check.json, скриншот screens/geo_1366_kk_lighting.png.
import { writeFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const OUT = path.join(ROOT, "research/round-14-results/R05");
const ORIGIN = process.argv[2] || "http://127.0.0.1:8617";
let chromium;
for (const id of ["playwright", "/opt/node22/lib/node_modules/playwright"]) {
  try {
    ({ chromium } = require(id));
    break;
  } catch (e) {
    /* следующий */
  }
}
const results = [];
const check = (id, ok, detail) => {
  results.push({ id, status: ok ? "PASS" : "FAIL", detail });
  console.log((ok ? "PASS " : "FAIL ") + id + (detail !== undefined ? " — " + JSON.stringify(detail) : ""));
};
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const errors = [];
async function open(q) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const p = await ctx.newPage();
  p.on("pageerror", (e) => errors.push(e.message));
  await p.goto(ORIGIN + "/civic/build3d/demo.html" + q);
  await p.waitForFunction(() => window.__b3d && window.__b3d.getState().phase === "ready", null, { timeout: 60000 });
  await p.waitForFunction(() => __map.loaded() && !__b3d.getState().animating, null, { timeout: 60000 });
  return p;
}
const screenOf = (p, ll) =>
  p.evaluate((ll) => {
    const q = __map.project(ll);
    const r = __map.getCanvas().getBoundingClientRect();
    return [q.x + r.left, q.y + r.top];
  }, ll);
async function twoClicks(p, a, b) {
  await p.click(".b3d-card[data-kind=lighting]");
  let [x, y] = await screenOf(p, a);
  await p.mouse.move(x, y);
  await p.mouse.click(x, y);
  await p.waitForFunction(() => __b3d.getState().hint === "build3d.hint.segment_end", null, { timeout: 60000 });
  [x, y] = await screenOf(p, b);
  await p.mouse.move(x, y, { steps: 3 });
  await p.mouse.click(x, y);
  await p.waitForFunction(() => { const g = __b3d.getState().ghost; return g && g.section && g.section.ok && g.section.source === "r12"; }, null, { timeout: 60000 });
  return (await p.evaluate(() => __b3d.getState())).ghost.section;
}
try {
  // Есиль, вне области своего индекса улиц (71.375–71.420): без R12 было бы «только в районе Нура».
  const A = [71.4300153, 51.1601624], B = [71.4327112, 51.1603615];
  let p = await open("?reset=1&store=local&lang=kk&center=71.4314,51.1604&zoom=17.6&pitch=50&bearing=0");
  const sec = await twoClicks(p, A, B);
  const hint = await p.textContent(".b3d-hint");
  check("lighting_outside_nura_via_r12", sec.ok && sec.edge_ids.length >= 1 && sec.length_m > 150, { length_m: sec.length_m, edges: sec.edge_ids, name: sec.name, name_kk: sec.name_kk });
  check("kk_street_name_from_r12", !!sec.name_kk && hint.includes(sec.name_kk) && !hint.includes(sec.name), { hint, name_kk: sec.name_kk });
  await p.screenshot({ path: path.join(OUT, "screens", "geo_1366_kk_lighting.png") });
  await p.click("[data-action=place]");
  await p.waitForFunction(() => !__b3d.getState().animating && __b3d.getState().proposals.some((q) => q.kind === "lighting" && !q.demo), null, { timeout: 30000 });
  const placed = (await p.evaluate(() => __b3d.getState())).proposals.find((q) => q.kind === "lighting" && !q.demo);
  check("placed_lighting_follows_r12_shape", JSON.stringify(placed.geometry.coordinates) === JSON.stringify(sec.coords) && placed.target.ids.join() === sec.edge_ids.join(), placed.target);
  await p.context().close();
  // Внутри Нуры R12 заменяет свой расчёт (тот же участок ул. Сыганак, но с казахским названием).
  p = await open("?reset=1&store=local&center=71.3986,51.1277&zoom=17.6&pitch=50&bearing=0");
  const s2 = await twoClicks(p, [71.399922, 51.12758], [71.39733, 51.1279]);
  check("nura_section_r12_matches_local_length", Math.abs(s2.length_m - 184.3) < 1.5, { length_m: s2.length_m, name_kk: s2.name_kk });
  await p.context().close();
} catch (e) {
  check("run", false, e.message.split("\n")[0]);
}
check("no_page_errors", errors.length === 0, errors.slice(0, 3));
await browser.close();
await mkdir(path.join(OUT, "runs"), { recursive: true });
await writeFile(path.join(OUT, "runs", "geo_check.json"), JSON.stringify({ generated_at: new Date().toISOString(), origin: ORIGIN, checks: results }, null, 1) + "\n");
process.exit(results.every((r) => r.status === "PASS") ? 0 : 1);
