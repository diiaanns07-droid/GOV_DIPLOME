// R07: значки целей не «плывут» за картой и не перепрыгивают после её остановки (замечание владельца на демо).
// Запуск: python -m ui.civic_heat.devserver &   затем
//   NODE_PATH=$(npm root -g) node tests/civic/R07/browser/pan_stability.js [папка] [метка]
// Проверки (1366×768 и 375×812):
//   1) во время перетаскивания карты в КАЖДОМ кадре центр значка = map.project(его точки) ± 2 px;
//   2) перетащили и остановились → после отпускания мыши ни один видимый значок не сдвинулся (точка та же, ±1 px на экране);
//   3) резкий бросок с инерцией — та же проверка кадров до полной остановки, точки значков не перевыбираются;
//   4) после смены масштаба значки разложены заново и не налезают друг на друга.
// R07_BASE — адрес демо (по умолчанию стенд R07 на 8617). R07_VIDEO=1 — записать видео перетаскивания (webm).
// R07_SHELL=1 — страница оболочки R01 (/?mode=civic…): модуль берётся из window.CivicShell.heat, карта — .maplibregl-map.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.env.R07_BASE || "http://127.0.0.1:8617/civic/heat/demo.html";
const OUT = process.argv[2] || path.join(__dirname, "..", "..", "..", "..", "research", "round-14-results", "R07", "screens", "pan");
const LABEL = process.argv[3] || "after";
const TOL = 2;
fs.mkdirSync(OUT, { recursive: true });
const SIZES = { desktop: { width: 1366, height: 768 }, phone: { width: 375, height: 812 } };

async function open(browser, size, video) {
  const ctx = await browser.newContext({ viewport: SIZES[size], deviceScaleFactor: 1,
    ...(video ? { recordVideo: { dir: OUT, size: SIZES[size] } } : {}) });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  // Нет сети в облаке (подложка из интернета) — это окружение, не ошибка модуля.
  page.on("console", (m) => { if (m.type() === "error" && !/ERR_TUNNEL_CONNECTION_FAILED|ERR_NAME_NOT_RESOLVED|ERR_INTERNET_DISCONNECTED/.test(m.text())) errors.push(m.text()); });
  await page.goto(BASE + (BASE.includes("?") ? "&" : "?") + "lang=ru", { waitUntil: "networkidle" });
  await page.waitForFunction(() => {
    const h = window.__heat || (window.CivicShell && window.CivicShell.heat);
    if (h && !window.__heat) window.__heat = h;
    // Старый модуль (до правки, для кадров «до») не отдаёт px/py и isMoving — тогда считаем по window.__map стенда.
    if (h && !h.isMoving && window.__map) {
      const badges = h.badges.bind(h);
      h.isMoving = () => window.__map.isMoving();
      h.badges = () => { const host = window.__map.getContainer().getBoundingClientRect();
        return badges().map((b) => { const p = window.__map.project(b.spot); return { ...b, px: host.left + p.x, py: host.top + p.y }; }); };
    }
    // Старый модуль в оболочке (карты наружу нет): кадры не проверить (px = NaN), но прыжки после отпускания — видно.
    if (h && !h.isMoving) h.isMoving = () => false;
    return h && h.state().status === "ready" && h.badges().length > 0;
  }, null, { timeout: 30000 });
  await page.waitForTimeout(1500);
  // Сэмплер кадров + наглядная разметка: красный крестик — где значок ДОЛЖЕН быть (map.project точки значка).
  await page.evaluate(() => {
    const cv = document.createElement("canvas");
    cv.id = "pan-overlay";
    Object.assign(cv.style, { position: "fixed", inset: "0", pointerEvents: "none", zIndex: 9999 });
    cv.width = innerWidth; cv.height = innerHeight;
    document.body.append(cv);
    const g = cv.getContext("2d");
    window.__pan = { samples: [], on: true, draw: false };
    const tick = () => {
      if (!window.__pan.on) return;
      const bs = window.__heat.badges();
      let worst = 0, worstKey = null;
      g.clearRect(0, 0, cv.width, cv.height);
      for (const b of bs) {
        const x = b.px, y = b.py;   // map.project(точка значка) + левый верхний угол карты
        if (x === undefined || Number.isNaN(x)) continue;
        const d = Math.hypot(b.cx - x, b.cy - y);
        if (d > worst) { worst = d; worstKey = b.key; }
        if (window.__pan.draw) {
          g.strokeStyle = "#d00"; g.lineWidth = 2;
          g.beginPath(); g.moveTo(x - 9, y); g.lineTo(x + 9, y); g.moveTo(x, y - 9); g.lineTo(x, y + 9); g.stroke();
        }
      }
      window.__pan.samples.push({ worst: Math.round(worst * 10) / 10, worstKey, n: bs.length, moving: window.__heat.isMoving() });
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
  return { ctx, page, errors };
}

// Точка для начала перетаскивания: внутри карты, не на значке, не на панели и кнопках.
async function dragStart(page) {
  return page.evaluate(() => {
    const host = document.querySelector(".maplibregl-map").getBoundingClientRect();
    const bad = [...document.querySelectorAll(".r07-badge:not([hidden]), #panel, .r07-maplegend, .mapbtns, header, .maplibregl-ctrl, .civic-slot, .birge-sheet, [class*='panel']")]
      .map((el) => el.getBoundingClientRect()).filter((r) => r.width);
    const pts = [];
    for (let fy = 0.3; fy <= 0.7; fy += 0.05) for (let fx = 0.2; fx <= 0.6; fx += 0.05) pts.push([host.left + host.width * fx, host.top + host.height * fy]);
    const ok = pts.find(([x, y]) => !bad.some((r) => x > r.left - 20 && x < r.right + 20 && y > r.top - 20 && y < r.bottom + 20)
      && document.elementFromPoint(x, y)?.classList.contains("maplibregl-canvas"));
    return ok || [host.left + host.width * 0.35, host.top + host.height * 0.5];
  });
}

// edge: значок упёрся в край карты или в плашку поверх неё (легенда, панель, кнопки) — ему можно переставиться
// (правило: перераскладывать при сдвиге, только если значок ушёл за край или начал налезать).
const snapshot = (page) => page.evaluate(() => {
  const host = document.querySelector(".maplibregl-map").getBoundingClientRect();
  const over = [...document.querySelectorAll(".r07-maplegend, #panel, .maplibregl-ctrl-group, .maplibregl-ctrl-attrib, .attr, .mapbtns button, #demo-new, .b3d-label, .maplibregl-marker:not(.r07-badge)")]
    .filter((el) => getComputedStyle(el).visibility !== "hidden").map((el) => el.getBoundingClientRect()).filter((r) => r.width);
  const els = new Map([...document.querySelectorAll(".r07-badge")].map((el) => [el, el.getBoundingClientRect()]));
  return window.__heat.badges().map((b) => {
    const r = [...els.values()].find((q) => Math.abs(q.left + q.width / 2 - b.cx) < 0.5 && Math.abs(q.top + q.height / 2 - b.cy) < 0.5);
    const edge = !r || r.left < host.left + 2 || r.top < host.top + 2 || r.right > host.right - 2 || r.bottom > host.bottom - 2 ||
      over.some((o) => r.left < o.right && o.left < r.right && r.top < o.bottom && o.top < r.bottom);
    return { key: b.key, spot: b.spot, mode: b.mode, cx: b.cx, cy: b.cy, edge };
  });
});

function compare(before, after) {
  const moved = [];
  const a = new Map(after.map((b) => [b.key, b]));
  for (const b of before) {
    const x = a.get(b.key);
    if (!x || b.edge) continue;   // спрятался или упёрся в край / плашку — ему переставиться можно, это не «сдвиг»
    const spotSame = b.spot[0] === x.spot[0] && b.spot[1] === x.spot[1];
    const d = Math.hypot(b.cx - x.cx, b.cy - x.cy);
    if (!spotSame || d > 1 || b.mode !== x.mode) moved.push({ key: b.key, spotSame, px: Math.round(d * 10) / 10, mode: b.mode + "→" + x.mode });
  }
  return moved;
}

// Карта остановилась: isMoving() = false и значки не двигаются 3 замера подряд. В оболочке R01 moveend после
// отпускания мыши приходит только со следующим движением мыши — поэтому сдвигаем указатель на 1 px.
async function settle(page, x, y) {
  let prev = null, same = 0;
  for (let i = 0; i < 80 && same < 3; i++) {
    await page.waitForTimeout(100);
    if (i === 3) await page.mouse.move(x + 1, y);
    const cur = await page.evaluate(() => JSON.stringify([window.__heat.isMoving(), window.__heat.badges().map((b) => [Math.round(b.cx), Math.round(b.cy)])]));
    same = cur === prev && !JSON.parse(cur)[0] ? same + 1 : 0;
    prev = cur;
  }
}

async function drag(page, [x, y], dx, dy, { steps = 40, pause = 150, shotName = null } = {}) {
  // На видео крестики видны всё перетаскивание: значок должен стоять ровно на своём крестике
  await page.evaluate((v) => { window.__pan.samples = []; window.__pan.keep = v; window.__pan.draw = v; }, process.env.R07_VIDEO === "1");
  await page.mouse.move(x, y);
  await page.mouse.down();
  for (let i = 1; i <= steps; i++) {
    await page.mouse.move(x + (dx * i) / steps, y + (dy * i) / steps);
    await page.waitForTimeout(16);
    if (shotName && i === Math.round(steps * 0.6)) {
      // Кадр «в движении»: крестики (где значок должен быть) рисуются каждый кадр; рывок мыши и сразу снимок —
      // со старым transition значки в этот момент ещё едут к своим местам.
      await page.evaluate(() => { window.__pan.draw = true; });
      await page.waitForTimeout(32);
      await page.mouse.move(x + (dx * i) / steps - 40, y + (dy * i) / steps - 25);
      await page.screenshot({ path: path.join(OUT, shotName) });
      await page.evaluate(() => { window.__pan.draw = !!window.__pan.keep; });
      await page.mouse.move(x + (dx * i) / steps, y + (dy * i) / steps);
    }
  }
  if (pause) await page.waitForTimeout(pause);
  await page.evaluate(() => { window.__pan.draw = false; });
  const beforeRelease = await snapshot(page);
  const endX = x + dx, endY = y + dy;
  await page.mouse.up();
  await settle(page, endX, endY);
  const settled = await snapshot(page);
  await page.waitForTimeout(1200);   // moveend → раскладка значков
  await page.mouse.move(endX + 1, endY + 1);
  await page.waitForTimeout(300);
  const after = await snapshot(page);
  const samples = await page.evaluate(() => window.__pan.samples);
  return { beforeRelease, settled, after, samples };
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });
  const report = { label: LABEL, base: BASE, tolerance_px: TOL, runs: [] };
  let failed = 0;
  for (const size of ["desktop", "phone"]) {
    const { ctx, page, errors } = await open(browser, size, process.env.R07_VIDEO === "1");
    // R07_FOCUS=1 — сначала открыть самое горячее место (оболочка R01 открывается городом, в режиме районов),
    // потом закрыть карточку: проверяем режим мест (дворы, участки, объекты), а не районов.
    if (process.env.R07_FOCUS) {
      await page.evaluate(async () => {
        const api = (document.querySelector('script[src*="heat.js"]') && "/api/civic/v2") || "/api/civic/v2";
        const data = await (await fetch(api + "/heat?days=30&zoom=15")).json();
        const top = (data.items || []).find((it) => it.state === "active" && it.target.kind !== "district");
        if (top) await window.__heat.focusTarget(top.target.kind, top.target.id);
      });
      await page.waitForTimeout(2500);
      await page.keyboard.press("Escape");
      const [a, b2] = await dragStart(page); await settle(page, a, b2); await page.waitForTimeout(1200);
    }
    const start = await dragStart(page);
    const w = SIZES[size].width;
    // 1–2) перетаскивание с остановкой перед отпусканием (без инерции)
    // на телефоне сдвиг меньше: карта маленькая, при большом сдвиге почти все значки упираются в края
    const k = size === "phone" ? 0.45 : 1;
    const slow = await drag(page, start, -Math.round(w * 0.18 * k), -Math.round(90 * k), { shotName: `pan-${LABEL}-${size}-drag.png` });
    const slowWorst = Math.max(0, ...slow.samples.map((s) => s.worst));
    const slowMoved = compare(slow.beforeRelease, slow.after);
    // 3) бросок с инерцией: отпускаем на ходу
    const start2 = await dragStart(page);
    const fling = await drag(page, start2, Math.round(w * 0.2 * k), Math.round(70 * k), { steps: 8, pause: 0 });
    const flingWorst = Math.max(0, ...fling.samples.map((s) => s.worst));
    const flingMoved = compare(fling.settled, fling.after);
    await page.screenshot({ path: path.join(OUT, `pan-${LABEL}-${size}-after.png`) });
    // 4) смена масштаба → раскладка заново, значки не налезают
    const [zx, zy] = await dragStart(page);
    await page.mouse.move(zx, zy);
    for (let i = 0; i < 3; i++) { await page.mouse.wheel(0, -240); await page.waitForTimeout(60); }
    await page.waitForTimeout(400);
    await settle(page, zx, zy);
    await page.waitForTimeout(800);
    const overlaps = await page.evaluate(() => {
      const els = [...document.querySelectorAll(".r07-badge:not([hidden])")];
      const rs = els.map((el) => el.getBoundingClientRect());
      let n = 0;
      const pairs = [];
      for (let i = 0; i < rs.length; i++) for (let j = i + 1; j < rs.length; j++) {
        const a = rs[i], b = rs[j];
        if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) {
          n++;
          pairs.push([els[i].dataset.mode, els[j].dataset.mode, [a.left, a.top, a.width, a.height].map(Math.round), [b.left, b.top, b.width, b.height].map(Math.round)]);
        }
      }
      return { n, badges: rs.length, pairs, zoom: window.__heat.state().mode };
    });
    const run = {
      size, mode: await page.evaluate(() => window.__heat.state().mode),
      frames: slow.samples.length + fling.samples.length, badges: slow.beforeRelease.length,
      at_edge_on_release: slow.beforeRelease.filter((b) => b.edge).length,
      drag_worst_px: slowWorst, fling_worst_px: flingWorst,
      moved_after_release: slowMoved, moved_after_fling: flingMoved,
      overlaps_after_zoom: overlaps, errors,
    };
    run.pass = slowWorst <= TOL && flingWorst <= TOL && !slowMoved.length && !flingMoved.length && overlaps.n === 0 && !errors.length
      && slow.samples.length > 20 && slow.beforeRelease.length > 0;
    if (!run.pass) failed++;
    report.runs.push(run);
    console.log(JSON.stringify({ size, mode: run.mode, pass: run.pass, frames: run.frames, badges: run.badges, at_edge: run.at_edge_on_release, drag_worst_px: slowWorst, fling_worst_px: flingWorst,
      moved_after_release: slowMoved.length, moved_after_fling: flingMoved.length, overlaps_after_zoom: overlaps.n, errors: errors.length }));
    const video = page.video();
    await ctx.close();
    if (video) fs.renameSync(await video.path(), path.join(OUT, `pan-${LABEL}-${size}.webm`));
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, `pan-${LABEL}.json`), JSON.stringify(report, null, 1));
  console.log(failed ? `FAIL ${failed}/${report.runs.length}` : `PASS ${report.runs.length}/${report.runs.length}`);
  process.exit(failed ? 1 : 0);
})();
