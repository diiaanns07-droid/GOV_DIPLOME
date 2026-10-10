// R05 · 3D-превью ВНУТРИ оболочки R01 (сборка B1, ветка claude/sharp-dijkstra-0t87gl) с патчем proposed_r01_b2.patch.
//   git worktree add --detach ../r01 origin/claude/sharp-dijkstra-0t87gl && cd ../r01
//   git apply <эта ветка>/research/round-14-results/R05/proposed_r01_b2.patch
//   git checkout <эта ветка> -- web/civic/build3d web/vendor/three      (или скопировать эти папки)
//   python3 -m ui.web_server --port 8799 --civic-db /tmp/b1.sqlite3
//   node tests/civic/R05/build3d/app_b1_smoke.mjs http://127.0.0.1:8799/
// Модуль монтирует сама оболочка (shell.js), тест его не трогает — только нажимает, как человек.
// Отчёт: research/round-14-results/R05/runs/app_b1_smoke.json, скриншоты screens/b1_*.png.
import { writeFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
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
const results = [];
const check = (id, ok, detail) => {
  results.push({ id, status: ok ? "PASS" : "FAIL", detail });
  console.log((ok ? "PASS " : "FAIL ") + id + (detail !== undefined ? " — " + JSON.stringify(detail) : ""));
};
const overlap = (a, b) => a && b && a.left < b.right - 1 && a.right > b.left + 1 && a.top < b.bottom - 1 && a.bottom > b.top + 1;
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const errors = [];
async function open(vp, extra) {
  const ctx = await browser.newContext(Object.assign({ viewport: vp }, extra || {}));
  const p = await ctx.newPage();
  p.on("pageerror", (e) => errors.push(e.message));
  await p.goto(URL0);
  await p.waitForFunction(() => typeof map !== "undefined" && map && map.loaded && map.isStyleLoaded(), null, { timeout: 60000 });
  await p.evaluate(() => map.jumpTo({ center: [71.4009, 51.1279], zoom: 17.4, pitch: 58, bearing: -20 }));
  await p.waitForFunction(() => document.querySelectorAll(".b3d-label").length >= 2, null, { timeout: 60000 });
  await p.waitForTimeout(800);
  return p;
}
const rect = (p, sel) => p.evaluate((s) => { const n = document.querySelector(s); if (!n || !n.offsetParent && getComputedStyle(n).position !== "fixed") return null; const r = n.getBoundingClientRect(); return { left: r.left, top: r.top, right: r.right, bottom: r.bottom, w: r.width, h: r.height }; }, sel);
await mkdir(path.join(OUT, "screens"), { recursive: true });
try {
  // Ноутбук: по умолчанию «Акимат» (defaultMode R01) — каталог справа от панели оболочки, не под ней.
  let p = await open({ width: 1366, height: 768 });
  const labels = await p.$$eval(".b3d-label", (els) => els.map((e) => e.textContent));
  check("shell_mounted_module_with_projects", labels.length >= 2 && labels.every((t) => /2027|Проект|Жоба/.test(t)), labels);
  const cards = await p.$$(".b3d-card");
  const dockR = await rect(p, ".b3d-dock"), panelR = await rect(p, "#civic-panel");
  check("akimat_catalog_not_under_shell_panel", cards.length === 5 && !overlap(dockR, panelR), { dock: dockR, panel: panelR });
  // Поставить сквер в свободной части карты.
  const before = labels.length;
  await p.click(".b3d-card[data-kind=square]");
  const pt = await p.evaluate(() => { const r = map.getCanvas().getBoundingClientRect(); return [r.left + r.width * 0.62, r.top + r.height * 0.35]; });
  await p.mouse.move(pt[0], pt[1]);
  await p.mouse.click(pt[0], pt[1]);
  await p.click("[data-action=place]");
  await p.waitForFunction((n) => document.querySelectorAll(".b3d-label").length === n + 1, before, { timeout: 30000 });
  await p.waitForTimeout(1600);
  check("place_square_in_shell", true, (await p.$$(".b3d-label")).length);
  await p.screenshot({ path: path.join(OUT, "screens", "b1_1366_ru_akimat.png") });
  // Карточка справа не перекрывает панель оболочки.
  await p.click(".b3d-label");
  await p.waitForSelector(".b3d-dock[data-state=card]");
  await p.waitForTimeout(600);
  const cardR = await rect(p, ".b3d-dock"), panel2 = await rect(p, "#civic-panel");
  check("card_not_over_shell_panel", !overlap(cardR, panel2), { card: cardR, panel: panel2 });
  await p.screenshot({ path: path.join(OUT, "screens", "b1_1366_ru_card.png") });
  // «Житель» в шапке R01 → каталог исчезает, подсказка про голос (событие birge:mode, без пересоздания модуля).
  await p.click('[data-mode="resident"]');
  await p.waitForTimeout(400);
  const hint = await p.textContent(".b3d-dock").catch(() => "");
  const cardsAfter = await p.$$(".b3d-card");
  check("shell_mode_switch_to_resident", cardsAfter.length === 0, { hint: hint.trim().slice(0, 80) });
  await p.context().close();

  // Телефон 375 (житель по умолчанию): подсказка над шторкой оболочки, не под ней; казахский.
  p = await open({ width: 375, height: 812 }, { hasTouch: true, isMobile: true });
  await p.evaluate(() => window.BirgeI18n && BirgeI18n.setLang("kk"));
  await p.waitForTimeout(600);
  const hintR = await rect(p, ".b3d-dock"), sheetR = await rect(p, "#civic-panel");
  const hintText = await p.textContent(".b3d-dock").catch(() => "");
  check("phone_resident_hint_above_shell_sheet", hintR && !overlap(hintR, sheetR) && /жобаны басыңыз/.test(hintText), { hint: hintR, sheet: sheetR, text: hintText.trim() });
  await p.screenshot({ path: path.join(OUT, "screens", "b1_375_kk_resident.png") });
  await p.context().close();
} catch (e) {
  check("run", false, e.message.split("\n")[0]);
}
check("no_page_errors", errors.length === 0, errors.slice(0, 3));
await browser.close();
await mkdir(path.join(OUT, "runs"), { recursive: true });
await writeFile(path.join(OUT, "runs", "app_b1_smoke.json"), JSON.stringify({ generated_at: new Date().toISOString(), url: URL0, r01_branch: "claude/sharp-dijkstra-0t87gl@e9b34a6", checks: results }, null, 1) + "\n");
process.exit(results.every((r) => r.status === "PASS") ? 0 : 1);
