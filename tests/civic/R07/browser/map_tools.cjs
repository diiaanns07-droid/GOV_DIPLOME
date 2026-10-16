// R07 раунд 15 · R12 INTEGRATION §11: пока карта у инструмента, цели тепловой карты не мешают ему.
// Редактор R04 рисует участок (html[data-civic-editor-tool] + событие civic-editor:tool, крестик на карте) — над целью
// R07 остаётся крестик, щелчок по цели не открывает карточку, значки пропускают нажатие к карте; после инструмента
// всё как раньше («рука», карточка). То же для выбора места жалобы (html.bc-picking, крестик мастера R09) и для панели
// инструмента, которую сняли без «выключения» (событие civic-scenarios:tool).
// Запуск: python -m ui.civic_heat.devserver --port 8619 &   затем
//   NODE_PATH=$(npm root -g) R07_BASE=http://127.0.0.1:8619/civic/heat/demo.html node tests/civic/R07/browser/map_tools.cjs [отчёт.json]
const { chromium } = require("playwright");
const fs = require("fs");

const BASE = process.env.R07_BASE || "http://127.0.0.1:8619/civic/heat/demo.html";
const OUT = process.argv[2] || null;
const results = [];
const check = (name, problems, extra) => {
  results.push({ name, pass: !problems.length, problems, extra });
  console.log((problems.length ? "FAIL " : "PASS ") + name + (problems.length ? " · " + problems.join("; ") : ""));
};

// Точка на карте над целью R07 (участок улицы), не закрытая значком, панелью или кнопками, — и пустое место карты.
const SPOTS = () => {
  const map = window.__map, canvas = map.getCanvas(), r = canvas.getBoundingClientRect();
  const layers = ["r07-seg", "r07-seg-dashed", "r07-area-fill", "r07-obj-dot", "r07-district-fill"].filter((id) => map.getLayer(id));
  let target = null, empty = null;
  for (let y = r.top + 40; y < r.bottom - 40 && !(target && empty); y += 6) {
    for (let x = r.left + 40; x < r.right - 40 && !(target && empty); x += 6) {
      if (document.elementFromPoint(x, y) !== canvas) continue;
      // запас 10 px вокруг: значок не ближе, щелчок не попадает в край линии
      const around = [[0, 0], [-10, 0], [10, 0], [0, -10], [0, 10]].every(([dx, dy]) => document.elementFromPoint(x + dx, y + dy) === canvas);
      if (!around) continue;
      const hits = map.queryRenderedFeatures([x - r.left, y - r.top], { layers });
      const near = map.queryRenderedFeatures([[x - r.left - 14, y - r.top - 14], [x - r.left + 14, y - r.top + 14]], { layers });
      if (!target && hits.length && hits[0].properties.kind === "segment" && hits.every((f) => f.properties.key === hits[0].properties.key)) {
        target = { x, y, key: hits[0].properties.key };
      }
      if (!empty && !near.length) empty = { x, y };
    }
  }
  return { target, empty };
};
const look = (page) => page.evaluate(() => ({
  cursor: window.__map.getCanvas().style.cursor,
  selected: window.__heat.state().selected,
  tool: window.__map.getContainer().classList.contains("r07-map-tool"),
}));
// Как редактор R04: запомнить курсор, поставить крестик, объявить инструмент (атрибут html и всплывающее событие).
const startEditor = (page) => page.evaluate(() => {
  const ed = document.getElementById("fake-editor") || document.body.appendChild(Object.assign(document.createElement("div"), { id: "fake-editor" }));
  const cs = window.__map.getCanvas().style;
  window.__saved = cs.cursor;
  cs.cursor = "crosshair";
  document.documentElement.setAttribute("data-civic-editor-tool", "line");
  ed.dispatchEvent(new CustomEvent("civic-editor:tool", { bubbles: true, detail: { active: true, mode: "line" } }));
});
const stopEditor = (page) => page.evaluate(() => {
  window.__map.getCanvas().style.cursor = window.__saved || "";
  document.documentElement.removeAttribute("data-civic-editor-tool");
  document.getElementById("fake-editor").dispatchEvent(new CustomEvent("civic-editor:tool", { bubbles: true, detail: { active: false } }));
});
const settle = (page, ms) => page.waitForTimeout(ms || 250);

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(`${BASE}?lang=ru&role=akimat&view=nura`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
  await settle(page, 1200);
  const { target, empty } = await page.evaluate(SPOTS);
  check("spots", target && empty ? [] : ["нет точки над участком R07 или пустого места: " + JSON.stringify({ target, empty })], { target, empty });
  if (!target || !empty) { await finish(browser, errors); return; }
  const hover = async (spot) => { await page.mouse.move(spot.x, spot.y, { steps: 3 }); await settle(page, 150); return look(page); };

  // 1. Без инструмента — как раньше: «рука» над целью, пусто — без курсора, щелчок открывает карточку участка.
  {
    const p = [];
    await hover(empty);
    const over = await hover(target);
    const off = await hover(empty);
    if (over.cursor !== "pointer") p.push("над целью курсор «" + over.cursor + "», нужна «рука»");
    if (off.cursor !== "") p.push("после ухода курсор «" + off.cursor + "»");
    await page.mouse.click(target.x, target.y);
    await settle(page, 600);
    const sel = await look(page);
    if (sel.selected !== target.key) p.push("щелчок не открыл карточку участка: " + sel.selected);
    await page.evaluate(() => window.__heat.close());
    await settle(page, 300);
    check("no-tool-pointer-and-card", p, { over, off, sel });
  }

  // 2. Редактор рисует: крестик остаётся над целью и после ухода, щелчок по цели — не карточка, значки пропускают нажатие.
  {
    const p = [];
    await hover(empty);
    await startEditor(page);
    await settle(page);
    const over = await hover(target);
    const off = await hover(empty);
    if (!over.tool) p.push("на карте нет класса r07-map-tool");
    if (over.cursor !== "crosshair") p.push("над целью курсор «" + over.cursor + "», нужен крестик редактора");
    if (off.cursor !== "crosshair") p.push("после ухода с цели курсор «" + off.cursor + "» (крестик стёрт)");
    await page.mouse.click(target.x, target.y);
    await settle(page, 600);
    const sel = await look(page);
    if (sel.selected) p.push("щелчок по цели во время рисования открыл карточку " + sel.selected);
    const badge = await page.evaluate(() => {
      const b = [...document.querySelectorAll(".r07-badge[data-mode]")].find((el) => !el.hidden && el.getBoundingClientRect().width > 0 &&
        (() => { const q = el.getBoundingClientRect(); const x = q.left + q.width / 2, y = q.top + q.height / 2; return x > 300 && x < innerWidth - 80 && y > 80 && y < innerHeight - 80; })());
      if (!b) return null;
      const q = b.getBoundingClientRect(), x = q.left + q.width / 2, y = q.top + q.height / 2;
      return { x, y, pe: getComputedStyle(b).pointerEvents, through: document.elementFromPoint(x, y) === window.__map.getCanvas() };
    });
    if (!badge) p.push("нет видимого значка для проверки");
    else {
      if (badge.pe !== "none" || !badge.through) p.push("значок ловит нажатие во время рисования: " + JSON.stringify(badge));
      await page.mouse.click(badge.x, badge.y);
      await settle(page, 600);
      const after = await look(page);
      if (after.selected) p.push("щелчок по значку во время рисования открыл карточку " + after.selected);
      if (after.cursor !== "crosshair") p.push("после щелчка по значку курсор «" + after.cursor + "»");
    }
    await stopEditor(page);
    await settle(page);
    const done = await look(page);
    if (done.tool) p.push("класс r07-map-tool остался после конца инструмента");
    const again = await hover(target);
    if (again.cursor !== "pointer") p.push("после инструмента над целью курсор «" + again.cursor + "»");
    await page.mouse.click(target.x, target.y);
    await settle(page, 600);
    const sel2 = await look(page);
    if (sel2.selected !== target.key) p.push("после инструмента щелчок не открыл карточку: " + sel2.selected);
    await page.evaluate(() => window.__heat.close());
    await hover(empty);
    check("editor-drawing-keeps-crosshair-and-click", p, { over, off, sel, badge, done, again, sel2 });
  }

  // 3. Инструмент включили, пока мышь над целью («рука» наша, редактор её запомнил): ушли с цели — крестик;
  //    инструмент закончился и вернул «руку» — R07 снимает её, мышь уже не над целью.
  {
    const p = [];
    const over = await hover(target);
    await startEditor(page);
    await settle(page);
    const off = await hover(empty);
    await stopEditor(page);
    await settle(page);
    const end = await look(page);
    if (over.cursor !== "pointer") p.push("до инструмента над целью «" + over.cursor + "»");
    if (off.cursor !== "crosshair") p.push("во время инструмента после ухода с цели «" + off.cursor + "»");
    if (end.cursor !== "") p.push("после инструмента вне цели осталась «" + end.cursor + "»");
    check("tool-started-while-hovering", p, { over, off, end });
  }

  // 4. Житель выбирает место жалобы (мастер R09: html.bc-picking и крестик): уход с цели не стирает крестик (раньше — "").
  {
    const p = [];
    await page.evaluate(() => { document.documentElement.classList.add("bc-picking"); window.__map.getCanvas().style.cursor = "crosshair"; });
    const over = await hover(target);
    const off = await hover(empty);
    if (over.cursor !== "crosshair") p.push("при выборе места над целью курсор «" + over.cursor + "»");
    if (off.cursor !== "crosshair") p.push("при выборе места после ухода с цели курсор «" + off.cursor + "»");
    await page.mouse.click(target.x, target.y);
    await settle(page, 600);
    const sel = await look(page);
    if (sel.selected) p.push("при выборе места щелчок открыл карточку " + sel.selected);
    await page.evaluate(() => { document.documentElement.classList.remove("bc-picking"); window.__map.getCanvas().style.cursor = ""; });
    check("complaint-picking-keeps-crosshair", p, { over, off, sel });
  }

  // 5. Панель инструмента сняли без «выключения» (событие civic-scenarios:tool, элемент удалён): карточки снова открываются.
  {
    const p = [];
    await page.evaluate(() => {
      const wrap = document.body.appendChild(document.createElement("div"));
      wrap.dispatchEvent(new CustomEvent("civic-scenarios:tool", { bubbles: true, detail: { active: true, kind: "closure" } }));
      wrap.remove();
    });
    await settle(page);
    const before = await look(page);
    if (!before.tool) p.push("событие сценария не включило r07-map-tool");
    await hover(empty);
    const over = await hover(target);
    await page.mouse.click(target.x, target.y);
    await settle(page, 600);
    const sel = await look(page);
    if (over.cursor !== "pointer") p.push("после снятой панели над целью курсор «" + over.cursor + "»");
    if (sel.selected !== target.key) p.push("после снятой панели щелчок не открыл карточку: " + sel.selected);
    if (sel.tool) p.push("класс r07-map-tool не снят");
    await page.evaluate(() => window.__heat.close());
    check("stale-tool-heals", p, { before, over, sel });
  }
  await finish(browser, errors);
})().catch((e) => { console.error(e); process.exit(2); });

async function finish(browser, errors) {
  check("no-page-errors", errors.slice(0, 5), null);
  await browser.close();
  const failed = results.filter((r) => !r.pass).length;
  console.log(`${results.length - failed}/${results.length} PASS`);
  if (OUT) fs.writeFileSync(OUT, JSON.stringify({ base: BASE, results }, null, 2));
  process.exit(failed ? 1 : 0);
}
