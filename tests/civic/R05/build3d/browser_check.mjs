// R05 · 3D-превью · проверка в настоящем браузере (Chromium + Playwright, WebGL2).
//
// Запуск из корня репозитория:
//   node tests/civic/R05/build3d/browser_check.mjs            — все проверки + скриншоты
//   node tests/civic/R05/build3d/browser_check.mjs --no-shots — без скриншотов (быстрее)
// Нужен пакет playwright (глобально или в node_modules) и Chromium. В облаке без GPU WebGL идёт
// через SwiftShader (программная отрисовка): кадры медленнее, чем на ноутбуке.
//
// Сам поднимает статический сервер папки web/ и макет API R06 (/api/civic/v2/proposals по CONTRACT §7).
// Отчёт: research/round-14-results/R05/runs/browser_check.json, скриншоты: research/round-14-results/R05/screens/.
import http from "node:http";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const WEB = path.join(ROOT, "web");
const OUT = path.join(ROOT, "research/round-14-results/R05");
const SHOTS = !process.argv.includes("--no-shots");
// --kit <папка> — взять web/civic/ui-kit и web/civic/i18n из выгрузки другой ветки (R11: как будет в сборке).
const KIT = (() => {
  const i = process.argv.indexOf("--kit");
  return i > 0 && process.argv[i + 1] ? path.resolve(process.argv[i + 1], "web") : null;
})();

function loadPlaywright() {
  for (const id of ["playwright", "/opt/node22/lib/node_modules/playwright"]) {
    try {
      return require(id);
    } catch (e) {
      /* следующий вариант */
    }
  }
  throw new Error("Не найден пакет playwright: npm i -D playwright (или глобально)");
}
const { chromium } = loadPlaywright();

// ───────────── Сервер: статика web/ + макет API R06 ─────────────
const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".txt": "text/plain; charset=utf-8",
};
const api = { enabled: false, items: [], votes: {}, log: [], seq: 0 };
function json(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  res.end(body == null ? "" : JSON.stringify(body));
}
function handleApi(req, res, url, body) {
  api.log.push({ method: req.method, path: url.pathname, body });
  if (!api.enabled) return json(res, 404, { error: { code: "not_found", message: "Адрес API не найден." } });
  const parts = url.pathname.replace(/^\/api\/civic\/v2\//, "").split("/");
  if (parts[0] !== "proposals") return json(res, 404, { error: { code: "not_found" } });
  if (parts.length === 1 && req.method === "GET") return json(res, 200, { items: api.items });
  if (parts.length === 1 && req.method === "POST") {
    const p = Object.assign({}, body, { id: "srv-" + ++api.seq, status: "proposal", votes_up: 0, votes_down: 0 });
    api.items.push(p);
    return json(res, 201, p);
  }
  const p = api.items.find((x) => x.id === decodeURIComponent(parts[1]));
  if (!p) return json(res, 404, { error: { code: "not_found" } });
  if (parts.length === 2 && req.method === "DELETE") {
    api.items = api.items.filter((x) => x !== p);
    return json(res, 204, null);
  }
  if (parts[2] === "vote" && req.method === "POST") {
    const key = p.id + "|" + body.device_id;
    const prev = api.votes[key] || 0;
    if (prev !== body.value) {
      if (prev === 1) p.votes_up--;
      if (prev === -1) p.votes_down--;
      if (body.value === 1) p.votes_up++;
      else p.votes_down++;
      api.votes[key] = body.value;
    }
    return json(res, 200, { proposal: Object.assign({ my_vote: body.value }, p) });
  }
  return json(res, 405, { error: { code: "method_not_allowed" } });
}
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname.startsWith("/api/")) {
    let raw = "";
    req.on("data", (c) => (raw += c));
    await new Promise((r) => req.on("end", r));
    let body = null;
    try {
      body = raw ? JSON.parse(raw) : null;
    } catch (e) {
      return json(res, 400, { error: { code: "invalid_json" } });
    }
    return handleApi(req, res, url, body);
  }
  const rel = decodeURIComponent(url.pathname);
  const base = KIT && (rel.startsWith("/civic/ui-kit/") || rel.startsWith("/civic/i18n/")) ? KIT : WEB;
  const file = path.normalize(path.join(base, rel));
  if (!file.startsWith(base)) return json(res, 403, { error: "forbidden" });
  try {
    const data = await readFile(file);
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
    res.end(data);
  } catch (e) {
    res.writeHead(404, { "Content-Type": "text/plain" });
    res.end("not found");
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const BASE = `http://127.0.0.1:${server.address().port}/civic/build3d/demo.html`;

// ───────────── Помощники ─────────────
const results = [];
function record(id, ok, detail, status) {
  results.push({ id, status: status || (ok ? "PASS" : "FAIL"), detail });
  console.log(`${status || (ok ? "PASS" : "FAIL")}  ${id}${detail ? "  — " + (typeof detail === "string" ? detail : JSON.stringify(detail)) : ""}`);
}
// --only <regexp> — только эти проверки (отладка; отчёт runs/browser_check.json тогда не пишется).
const ONLY = (() => {
  const i = process.argv.indexOf("--only");
  return i > 0 && process.argv[i + 1] ? new RegExp(process.argv[i + 1]) : null;
})();
async function check(id, fn) {
  if (ONLY && !ONLY.test(id)) return;
  try {
    const r = await fn();
    if (r && r.status) record(id, r.status === "PASS", r.detail, r.status);
    else record(id, r !== false, r && r !== true ? r : undefined);
  } catch (e) {
    record(id, false, e.message.split("\n")[0]);
  }
}
function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const pageErrors = [];
async function openPage(ctxOpts, query, opts = {}) {
  const ctx = await browser.newContext(Object.assign({ viewport: { width: 1366, height: 768 } }, ctxOpts));
  const page = await ctx.newPage();
  page._console = [];
  page.on("console", (m) => page._console.push({ type: m.type(), text: m.text() }));
  page.on("pageerror", (e) => pageErrors.push(query + ": " + e.message));
  if (opts.seed) {
    await page.addInitScript((items) => {
      if (!sessionStorage.getItem("seeded")) {
        localStorage.setItem("birge.build3d.proposals.v1", JSON.stringify({ items, votes: {} }));
        sessionStorage.setItem("seeded", "1");
      }
    }, opts.seed);
  }
  await page.goto(BASE + query);
  await waitReady(page, opts.phase || "ready");
  return page;
}
async function waitReady(page, phase = "ready") {
  await page.waitForFunction((ph) => window.__b3d && window.__b3d.getState().phase === ph, phase, { timeout: 60000 });
  if (phase === "ready") await idle(page);
}
async function idle(page) {
  // !isMoving: «тайлы загружены» бывает и посреди полёта камеры (fitBounds/easeTo) — ждать и его конца.
  await page.waitForFunction(() => __map.loaded() && __map.areTilesLoaded() && !__map.isMoving() && !__b3d.getState().animating, null, { timeout: 60000 });
}
const state = (page) => page.evaluate(() => __b3d.getState());
// Вернуть модуль в исходное состояние между проверками и поставить камеру на известный вид.
async function resetView(page, view) {
  await page.evaluate((v) => {
    __b3d.cancel();
    __b3d.select(null);
    __map.jumpTo(Object.assign({ center: [71.4008, 51.1272], zoom: 17.4, pitch: 60, bearing: -30 }, v || {}));
  }, view || null);
  await idle(page);
}
async function shot(page, name) {
  if (!SHOTS) return;
  await idle(page).catch(() => {});
  await page.waitForTimeout(250);
  await page.screenshot({ path: path.join(OUT, "screens", name) });
}
// Экранная точка (в координатах страницы) для lon/lat.
async function screenOf(page, lngLat) {
  return page.evaluate((ll) => {
    const p = __map.project(ll);
    const r = __map.getCanvas().getBoundingClientRect();
    return [p.x + r.left, p.y + r.top];
  }, lngLat);
}
async function placePoint(page, kind, lngLat, rotSteps = 0) {
  await page.click(`.b3d-card[data-kind=${kind}]`);
  const [x, y] = await screenOf(page, lngLat);
  await page.mouse.move(x, y, { steps: 2 });
  await page.mouse.click(x, y);
  for (let i = 0; i < rotSteps; i++) await page.click("[data-action=rotate-right]");
  const g = (await state(page)).ghost;
  await page.click("[data-action=place]", { timeout: 5000 });
  return g;
}
async function placeLighting(page, a, b) {
  await page.click(".b3d-card[data-kind=lighting]");
  const pa = await screenOf(page, a);
  await page.mouse.move(pa[0], pa[1]);
  await page.mouse.click(pa[0], pa[1]);
  const pb = await screenOf(page, b);
  await page.mouse.move(pb[0], pb[1], { steps: 4 });
  await page.mouse.click(pb[0], pb[1]);
  const st = await state(page);
  const hint = await page.textContent(".b3d-hint");
  await page.click("[data-action=place]", { timeout: 5000 });
  return { st, hint };
}

// Набор для обзорных скриншотов: три объекта «как после перезагрузки» + два примера из фикстуры.
const FIXTURE = JSON.parse(await readFile(path.join(WEB, "civic/build3d/data/proposals.fixture.json"), "utf8"));
const SHOWCASE = [
  { id: "s-sports", kind: "sports", geometry: { type: "Point", coordinates: [71.3998, 51.1268] }, rotation_deg: 8 },
]
  .map((p) => Object.assign({ status: "proposal", votes_up: 0, votes_down: 0, year: 2027, district: "nura" }, p))
  .concat(FIXTURE.proposals);
// Точки на ул. Сыганак (настоящие рёбра) для освещения.
const STREETS = JSON.parse(await readFile(path.join(WEB, "civic/build3d/data/nura-streets.json"), "utf8"));
const edge = (id) => STREETS.edges.find((e) => e[0] === id)[5];
const LIGHT_A = edge("osm-w1189551423-3")[0];
const LIGHT_B = edge("osm-w1189551423-3")[1];

const env = {};
await mkdir(path.join(OUT, "screens"), { recursive: true });
await mkdir(path.join(OUT, "runs"), { recursive: true });

// ───────────── 1. Загрузка, заглушка R06, примеры ─────────────
const MAIN_Q = "?center=71.4008,51.1272&zoom=17.4&pitch=60&bearing=-30";
let page = await openPage({}, "?reset=1&" + MAIN_Q.slice(1));
env.gl = await page.evaluate(() => {
  const gl = __map.painter && __map.painter.context.gl;
  return gl ? gl.getParameter(gl.VERSION) + " · " + (gl instanceof WebGL2RenderingContext ? "WebGL2" : "WebGL1") : null;
});
env.user_agent = await page.evaluate(() => navigator.userAgent);
await check("load_auto_falls_back_to_local_store", async () => {
  const s = await state(page);
  assert(s.storeMode === "local", "storeMode " + s.storeMode);
  assert(api.log.some((r) => r.method === "GET" && r.path === "/api/civic/v2/proposals"), "API R06 не спрашивали");
  assert(s.count === FIXTURE.proposals.length, "примеров " + s.count);
  const labels = await page.$$eval(".b3d-label", (els) => els.map((e) => e.textContent));
  assert(labels.length === s.count && labels.every((t) => t === "Проект · 2027"), JSON.stringify(labels));
  return { status: "PASS", detail: `storeMode=local после 404 /proposals; примеров ${s.count}; подписи ${JSON.stringify(labels)}` };
});
await check("maplibre_mercator_matches_core", async () => {
  const d = await page.evaluate(() => {
    const C = CivicBuild3DCore;
    let worst = 0;
    for (const ll of [[71.3995, 51.1268], [71.43, 51.16], [71.25, 51.0]]) {
      const m = maplibregl.MercatorCoordinate.fromLngLat(ll);
      worst = Math.max(worst, Math.abs(m.x - C.mercX(ll[0])), Math.abs(m.y - C.mercY(ll[1])));
      worst = Math.max(worst, Math.abs(m.meterInMercatorCoordinateUnits() - C.meterInMerc(ll[1])) / m.meterInMercatorCoordinateUnits());
    }
    return worst;
  });
  assert(d < 1e-12, "расхождение " + d);
  return { status: "PASS", detail: "макс. расхождение " + d.toExponential(2) };
});

// ───────────── 2. Поставить все 5 видов ─────────────
await check("place_all_five_kinds", async () => {
  const before = (await state(page)).count;
  const pts = { square: [71.3995, 51.1282], playground: [71.4022, 51.1283], sports: [71.3985, 51.1263] };
  await placePoint(page, "square", pts.square);
  await idle(page);
  await placePoint(page, "playground", pts.playground, 2);
  await idle(page);
  await placePoint(page, "sports", pts.sports, 1);
  await idle(page);
  const g = await placePoint(page, "stop", [71.4023, 51.12735]);
  await idle(page);
  const L = await placeLighting(page, LIGHT_A, LIGHT_B);
  await idle(page);
  const s = await state(page);
  assert(s.count === before + 5, "count " + s.count);
  const mine = s.proposals.filter((p) => !p.demo);
  assert(mine.every((p) => p.district === "nura"), "район");
  assert(mine.every((p) => p.year === 2027 && p.status === "proposal"), "год/статус");
  const light = mine.find((p) => p.kind === "lighting");
  assert(light && light.target && light.target.kind === "segment" && light.target.ids.length >= 1, "цель освещения");
  return { status: "PASS", detail: { count: s.count, stop_auto_rotation_deg: Math.round(g.rot), lighting_hint: L.hint, near: mine.map((p) => p.kind + ": " + p.near_street) } };
});
await check("labels_project_on_every_object", async () => {
  const s = await state(page);
  const n = await page.$$eval(".b3d-label", (els) => els.filter((e) => e.textContent.includes("2027") || e.classList.contains("b3d-label--dot")).length);
  assert(n === s.count, `${n} из ${s.count}`);
  return { status: "PASS", detail: `${n} подписей «Проект · 2027» на ${s.count} объектах` };
});

// ───────────── 3. Точность: объект стоит в своих lon/lat при наклоне 0° и 60° и повороте ─────────────
await check("anchor_precision_pitch_0_60_rotation", async () => {
  const views = [
    { pitch: 0, bearing: 0 },
    { pitch: 60, bearing: -35 },
    { pitch: 60, bearing: 120 },
    { pitch: 45, bearing: 250, zoom: 18.2 },
  ];
  let worst = 0;
  const per = [];
  for (const v of views) {
    await page.evaluate((v) => __map.jumpTo(Object.assign({ center: [71.4005, 51.1275], zoom: 17.2 }, v)), v);
    await idle(page);
    const err = await page.evaluate(() => {
      const s = __b3d.getState();
      let w = 0;
      for (const p of s.proposals) {
        const anchor = p.kind === "lighting" ? p.geometry.coordinates[0] : p.geometry.coordinates;
        const a = __b3d._project(p.id, [0, 0, 0]);
        const b = __map.project(anchor);
        if (a) w = Math.max(w, Math.hypot(a.x - b.x, a.y - b.y));
      }
      return w;
    });
    per.push(`${v.pitch}°/${v.bearing}°: ${err.toFixed(3)} px`);
    worst = Math.max(worst, err);
  }
  assert(worst < 1, "ошибка " + worst);
  return { status: "PASS", detail: per.join("; ") };
});
await check("labels_follow_objects_when_tilted", async () => {
  await page.evaluate(() => __map.jumpTo({ center: [71.4005, 51.1275], zoom: 17.6, pitch: 60, bearing: -35 }));
  await idle(page);
  const d = await page.evaluate(() => {
    const s = __b3d.getState();
    const r = __map.getCanvas().getBoundingClientRect();
    let worst = 0, n = 0;
    for (const p of s.proposals) {
      const lab = document.querySelector(`.b3d-label[data-id="${p.id}"]`);
      if (!lab || lab.style.visibility === "hidden" || lab.classList.contains("b3d-label--dot")) continue;
      const lr = lab.getBoundingClientRect();
      const ground = __b3d._project(p.id, [0, 0, 0]);
      // Подпись — над объектом: низ подписи выше точки на земле и по горизонтали рядом.
      if (p.kind !== "lighting") {
        worst = Math.max(worst, Math.abs(lr.left + lr.width / 2 - (ground.x + r.left)));
        if (!(lr.bottom < ground.y + r.top)) return { bad: p.id };
      }
      n++;
    }
    return { worst, n };
  });
  assert(!d.bad, "подпись ниже объекта: " + d.bad);
  assert(d.worst < 40, "смещение " + d.worst);
  return { status: "PASS", detail: `${d.n} подписей над объектами, макс. смещение по x ${d.worst.toFixed(1)} px (60°, поворот −35°)` };
});

// ───────────── 4. Перезагрузка: объекты на месте, без повторной анимации ─────────────
await check("reload_keeps_objects_without_animation", async () => {
  const before = await state(page);
  await page.goto(BASE + MAIN_Q); // тот же адрес, но без ?reset=1 — как обычная перезагрузка
  await page.waitForFunction(() => window.__b3d && window.__b3d.getState().phase === "ready", null, { timeout: 60000 });
  const s = await state(page);
  const hidden = await page.$$eval(".b3d-label--hidden", (els) => els.length);
  assert(s.count === before.count, `было ${before.count}, стало ${s.count}`);
  assert(!s.animating && hidden === 0, "после перезагрузки идёт анимация");
  const same = before.proposals.every((p) => s.proposals.some((q) => q.id === p.id && JSON.stringify(q.geometry) === JSON.stringify(p.geometry) && q.rotation_deg === p.rotation_deg));
  assert(same, "геометрия или поворот изменились");
  return { status: "PASS", detail: `${s.count} объектов, animating=false, скрытых подписей 0` };
});

// ───────────── 5. Голос в карточке; удаление освобождает память; «Отменить» ─────────────
await check("vote_in_card_one_per_device", async () => {
  await resetView(page);
  await page.click('.b3d-label[data-id="p-demo-stop-syganak"]');
  await page.waitForSelector("[data-action=vote-up]");
  const before = (await state(page)).proposals.find((p) => p.id === "p-demo-stop-syganak");
  await page.click("[data-action=vote-up]");
  await page.waitForFunction(() => !document.querySelector('[data-action=vote-up][aria-busy="true"]'));
  await page.click("[data-action=vote-up]");
  await page.waitForTimeout(200);
  const after = (await state(page)).proposals.find((p) => p.id === "p-demo-stop-syganak");
  assert(after.votes_up === before.votes_up + 1 && after.my_vote === 1, JSON.stringify([before.votes_up, after.votes_up, after.my_vote]));
  const pressed = await page.getAttribute("[data-action=vote-up]", "aria-pressed");
  assert(pressed === "true", "aria-pressed");
  if (SHOTS) await page.screenshot({ path: path.join(OUT, "screens", "1366_ru_card_votes.png") });
  await page.click("[data-action=vote-down]");
  await page.waitForTimeout(200);
  const moved = (await state(page)).proposals.find((p) => p.id === "p-demo-stop-syganak");
  assert(moved.votes_up === before.votes_up && moved.votes_down === before.votes_down + 1, "перенос голоса");
  await page.click("[data-action=close-card]");
  return { status: "PASS", detail: `за ${before.votes_up}→${after.votes_up} (повтор не добавил), затем голос перенесён: против ${before.votes_down}→${moved.votes_down}` };
});
await check("delete_frees_gpu_memory_and_undo_restores", async () => {
  await resetView(page);
  const base = (await state(page)).memory.geometries;
  const before = (await state(page)).proposals.map((p) => p.id);
  await placePoint(page, "square", [71.4006, 51.1277]);
  await idle(page);
  const s1 = await state(page);
  const id = s1.proposals.find((p) => !before.includes(p.id)).id;
  const withObj = s1.memory.geometries;
  await page.click(`.b3d-label[data-id="${id}"]`);
  await page.click("[data-action=delete]");
  await page.waitForFunction((id) => !__b3d.getState().proposals.some((p) => p.id === id), id);
  await idle(page);
  const afterDel = (await state(page)).memory.geometries;
  assert(afterDel === base, `геометрий: до ${base}, с объектом ${withObj}, после удаления ${afterDel}`);
  await page.click(".b3d-toasts [data-action=undo]");
  await page.waitForFunction((id) => __b3d.getState().proposals.some((p) => p.id === id), id);
  await idle(page);
  const back = await state(page);
  return { status: "PASS", detail: `геометрий на GPU: ${base} → ${withObj} → ${afterDel} (освобождены); «Отменить» вернул объект, всего ${back.count}` };
});
await check("undo_after_place_removes_object", async () => {
  await resetView(page);
  const c0 = (await state(page)).count;
  await placePoint(page, "playground", [71.4012, 51.1281]);
  await page.waitForSelector(".b3d-toasts [data-action=undo]");
  await page.click(".b3d-toasts [data-action=undo]");
  await page.waitForFunction((c) => __b3d.getState().count === c && !__b3d.getState().animating, c0, { timeout: 30000 });
  return { status: "PASS", detail: `после «Поставить» → «Отменить» объектов снова ${c0}` };
});

// ───────────── 6. Нельзя поставить: наложение, за городом ─────────────
await check("overlap_is_blocked_with_message", async () => {
  await resetView(page);
  await page.click(".b3d-card[data-kind=square]");
  const target = (await state(page)).proposals.find((p) => p.kind === "square");
  const [tx, ty] = await screenOf(page, target.geometry.coordinates);
  await page.mouse.move(tx, ty);
  await page.mouse.click(tx, ty);
  const s = await state(page);
  const disabled = await page.getAttribute("[data-action=place]", "aria-disabled");
  const hint = await page.textContent(".b3d-hint");
  assert(s.ghost.valid.ok === false && s.ghost.valid.reason === "overlap", JSON.stringify(s.ghost.valid));
  assert(disabled === "true", "кнопка «Поставить» доступна");
  if (SHOTS) await page.screenshot({ path: path.join(OUT, "screens", "1366_ru_overlap.png") });
  await page.click("[data-action=cancel]");
  return { status: "PASS", detail: hint };
});
await check("outside_astana_is_blocked", async () => {
  await resetView(page, { center: [71.05, 51.05], zoom: 17 });
  await page.click(".b3d-card[data-kind=stop]");
  const c = await screenOf(page, [71.05, 51.05]);
  await page.mouse.move(c[0], c[1]);
  await page.mouse.click(c[0], c[1]);
  const s = await state(page);
  const hint = await page.textContent(".b3d-hint");
  await page.click("[data-action=cancel]");
  await page.evaluate(() => __map.jumpTo({ center: [71.4005, 51.1275], zoom: 17.2 }));
  assert(s.ghost.valid.reason === "outside_city", JSON.stringify(s.ghost.valid));
  return { status: "PASS", detail: hint };
});
await check("style_swap_keeps_layer_and_objects", async () => {
  await resetView(page);
  const c = (await state(page)).count;
  await page.evaluate(() => {
    const st = __map.getStyle();
    __map.setStyle(st, { diff: false });
  });
  await page.waitForFunction(() => __map.isStyleLoaded() && !!__map.getLayer("civic-build3d"), null, { timeout: 30000 });
  await idle(page);
  const s = await state(page);
  assert(s.count === c && s.phase === "ready", "после смены стиля " + s.count);
  return { status: "PASS", detail: `слой вернулся, объектов ${s.count}` };
});
await check("real_osm_nearby_hint_and_yard_target", async () => {
  await resetView(page, { center: [71.4021, 51.1288], zoom: 17.6 });
  // Остановка рядом с настоящей «БЦ Саад» → подсказка (не блокирует).
  await page.click(".b3d-card[data-kind=stop]");
  await page.waitForFunction(() => document.querySelector(".b3d-hint--info"), null, { timeout: 20000 }).catch(() => {});
  const stopFx = FIXTURE.proposals.find((p) => p.kind === "stop").geometry.coordinates;
  const ps = await screenOf(page, [stopFx[0] - 0.0004, stopFx[1] + 0.0001]);
  await page.mouse.move(ps[0], ps[1]);
  await page.mouse.click(ps[0], ps[1]);
  await page.waitForSelector(".b3d-hint--info", { timeout: 20000 });
  const info = await page.textContent(".b3d-hint--info");
  const placeEnabled = (await page.getAttribute("[data-action=place]", "aria-disabled")) !== "true";
  await page.click("[data-action=cancel]");
  // Детская площадка в центре двора «Eco Park» (OSM landuse=residential) → цель area yard-1424189376.
  await resetView(page, { center: [71.3914, 51.1278], zoom: 17.6 });
  const before = (await state(page)).proposals.map((p) => p.id);
  await placePoint(page, "playground", [71.391411, 51.1276105]);
  await idle(page);
  const created = (await state(page)).proposals.find((p) => !before.includes(p.id));
  await page.click(`.b3d-label[data-id="${created.id}"]`);
  const yardLine = await page.textContent(".b3d-pcard__yard").catch(() => null);
  await page.click("[data-action=close-card]");
  assert(/БЦ Саад/.test(info) && /OpenStreetMap/.test(info) && placeEnabled, info);
  assert(created.target && created.target.kind === "area" && /^yard-\d+$/.test(created.target.id), JSON.stringify(created.target));
  return { status: "PASS", detail: { hint: info.replace(/\s+/g, " ").trim(), target: created.target, card: yardLine } };
});
await page.context().close();

// ───────────── 7. Лимит 20 ─────────────
await check("limit_20_objects", async () => {
  const items = [];
  for (let i = 0; i < 20; i++) {
    const kinds = ["square", "playground", "sports", "stop"];
    items.push({ id: "lim-" + i, kind: kinds[i % 4], geometry: { type: "Point", coordinates: [71.392 + (i % 5) * 0.0009, 51.124 + Math.floor(i / 5) * 0.0007] }, rotation_deg: i * 9, status: "proposal", votes_up: 0, votes_down: 0, year: 2027 });
  }
  const p = await openPage({}, "?store=local&center=71.3938,51.1251&zoom=16.6&pitch=55&bearing=-15", { seed: items });
  const s = await state(p);
  const disabled = await p.$$eval(".b3d-card", (els) => els.every((e) => e.disabled));
  const tag = await p.textContent(".b3d-head .bk-tag--warn").catch(() => null);
  const started = await p.evaluate(() => __b3d.start("square"));
  // Кадры с 20 объектами в SwiftShader (без GPU) — только для сведения, не оценка ноутбука.
  const fps = await p.evaluate(
    () =>
      new Promise((resolve) => {
        let n = 0;
        const t0 = performance.now();
        __map.rotateTo(__map.getBearing() + 90, { duration: 3000 });
        (function tick() {
          n++;
          if (performance.now() - t0 < 3000) requestAnimationFrame(tick);
          else resolve((n * 1000) / (performance.now() - t0));
        })();
      })
  );
  if (SHOTS) await shot(p, "1366_ru_20_objects.png");
  await p.context().close();
  // Та же камера и вращение без объектов — чтобы отделить цену 3D-слоя от цены программной отрисовки карты.
  const p0 = await openPage({}, "?store=local&center=71.3938,51.1251&zoom=16.6&pitch=55&bearing=-15", { seed: [] });
  const fps0 = await p0.evaluate(
    () =>
      new Promise((resolve) => {
        let n = 0;
        const t0 = performance.now();
        __map.rotateTo(__map.getBearing() + 90, { duration: 3000 });
        (function tick() {
          n++;
          if (performance.now() - t0 < 3000) requestAnimationFrame(tick);
          else resolve((n * 1000) / (performance.now() - t0));
        })();
      })
  );
  await p0.context().close();
  env.fps_0_objects_swiftshader = Math.round(fps0 * 10) / 10;
  assert(s.count === 20 && disabled && started === false && tag, JSON.stringify({ count: s.count, disabled, started, tag }));
  env.fps_20_objects_swiftshader = Math.round(fps * 10) / 10;
  env.gpu_geometries_20_objects = s.memory.geometries;
  return { status: "PASS", detail: `20 объектов: каталог выключен, «${tag}»; геометрий на GPU ${s.memory.geometries}; SwiftShader ${env.fps_20_objects_swiftshader} кадр/с (без объектов ${env.fps_0_objects_swiftshader})` };
});

// ───────────── 8. Медленная постройка: кадр «в процессе», подпись появляется после ─────────────
await check("build_animation_grows_then_shows_label", async () => {
  const p = await openPage({}, "?reset=1&store=local&build_ms=5000&center=71.4008,51.1272&zoom=18.1&pitch=60&bearing=-30");
  await placePoint(p, "square", [71.4004, 51.1278]);
  await p.waitForTimeout(1600);
  const mid = await state(p);
  const id = mid.proposals.find((x) => x.kind === "square" && !x.demo).id; // не сквер-пример из фикстуры
  const hiddenMid = await p.$eval(`.b3d-label[data-id="${id}"]`, (e) => e.classList.contains("b3d-label--hidden"));
  if (SHOTS) await p.screenshot({ path: path.join(OUT, "screens", "1366_ru_building.png") });
  await p.waitForFunction(() => !__b3d.getState().animating, null, { timeout: 30000 });
  const hiddenEnd = await p.$eval(`.b3d-label[data-id="${id}"]`, (e) => e.classList.contains("b3d-label--hidden"));
  await p.context().close();
  assert(mid.animating && hiddenMid && !hiddenEnd, JSON.stringify({ animating: mid.animating, hiddenMid, hiddenEnd }));
  return { status: "PASS", detail: "во время постройки animating=true и подпись скрыта; после — подпись видна" };
});

// ───────────── 9. Житель: только просмотр и голос ─────────────
await check("resident_sees_objects_and_votes_no_catalog", async () => {
  const p = await openPage({}, "?reset=1&role=resident&store=local&center=71.4008,51.1272&zoom=17.6&pitch=60&bearing=-30");
  const cards = await p.$$(".b3d-card");
  await p.click('.b3d-label[data-id="p-demo-light-syganak"]');
  const del = await p.$("[data-action=delete]");
  const vote = await p.$("[data-action=vote-up]");
  const started = await p.evaluate(() => __b3d.start("square"));
  if (SHOTS) await p.screenshot({ path: path.join(OUT, "screens", "1366_ru_resident_card.png") });
  await p.context().close();
  assert(cards.length === 0 && !del && vote && started === false, JSON.stringify({ cards: cards.length, del: !!del, vote: !!vote, started }));
  return { status: "PASS", detail: "нет каталога и «Удалить», есть «За/Против»" };
});

// ───────────── 10. Казахский, 375 px, клавиатура ─────────────
const RAW_KEY = /\b(build3d|proposal|common)\.[a-z_]+(\.[a-z_]+)*\b/;
await check("kk_locale_no_raw_keys_no_i18n_warnings", async () => {
  const p = await openPage({}, "?reset=1&lang=kk&store=local&center=71.4008,51.1272&zoom=17.4&pitch=60&bearing=-30");
  const title = await p.textContent(".b3d-title");
  const labels = await p.$$eval(".b3d-label", (els) => els.map((e) => e.textContent));
  await p.click(".b3d-card[data-kind=lighting]");
  const hint = await p.textContent(".b3d-hint");
  const body = await p.evaluate(() => document.body.innerText); // видимый текст (без кода <script> страницы)
  await p.click("[data-action=cancel]");
  await p.click('.b3d-label[data-id="p-demo-stop-syganak"]');
  const card = await p.textContent(".b3d-pcard");
  const warns = p._console.filter((m) => m.text.includes("[i18n]"));
  await p.context().close();
  assert(title === "Не салайық?" && labels.every((t) => t === "Жоба · 2027"), JSON.stringify({ title, labels }));
  assert(!RAW_KEY.test(body) && !RAW_KEY.test(card), "ключ на экране: " + ((body.match(RAW_KEY) || card.match(RAW_KEY) || [])[0]));
  assert(warns.length === 0, JSON.stringify(warns));
  return { status: "PASS", detail: { title, label: labels[0], hint, card: card.replace(/\s+/g, " ").trim() } };
});
await check("phone_375_touch_layout", async () => {
  const p = await openPage({ viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true }, "?reset=1&lang=kk&store=local&center=71.4013,51.1273&zoom=17.2&pitch=55&bearing=-25");
  const metrics = async () =>
    p.evaluate(() => ({
      scroll: document.documentElement.scrollWidth - innerWidth,
      small: [...document.querySelectorAll(".b3d-dock button")].filter((b) => b.getBoundingClientRect().height < 47.5 && b.offsetParent).map((b) => b.textContent),
      cut: [...document.querySelectorAll(".b3d-dock .bk-btn, .b3d-card")]
        .filter((b) => b.scrollWidth > b.clientWidth + 1 || [...b.querySelectorAll("span")].some((s) => s.scrollWidth > b.clientWidth))
        .map((b) => b.textContent),
    }));
  const m1 = await metrics();
  await p.tap(".b3d-card[data-kind=square]");
  const g = (await state(p)).ghost;
  const m2 = await metrics();
  if (SHOTS) await p.screenshot({ path: path.join(OUT, "screens", "375_kk_placing.png") });
  await p.tap("[data-action=place]");
  await p.waitForFunction(() => !__b3d.getState().animating, null, { timeout: 30000 });
  await p.tap('.b3d-label[data-id="p-demo-stop-syganak"]');
  const m3 = await metrics();
  if (SHOTS) await p.screenshot({ path: path.join(OUT, "screens", "375_kk_card.png") });
  await p.context().close();
  for (const m of [m1, m2, m3]) assert(m.scroll <= 0 && m.small.length === 0 && m.cut.length === 0, JSON.stringify(m));
  assert(g.follow === "center", "на телефоне призрак за центром карты: " + g.follow);
  return { status: "PASS", detail: "нет горизонтальной прокрутки, все кнопки ≥ 48 px, текст не обрезан; призрак идёт за центром карты" };
});
await check("catalog_labels_fit_ru_kk_1366_375", async () => {
  const bad = [];
  for (const lang of ["ru", "kk"]) {
    for (const vp of [{ width: 1366, height: 768 }, { width: 375, height: 812 }, { width: 360, height: 740 }]) {
      const p = await openPage({ viewport: vp }, `?reset=1&store=local&lang=${lang}`);
      const cut = await p.evaluate(() =>
        [...document.querySelectorAll(".b3d-card")].filter((c) => c.querySelector(".b3d-card__label").scrollWidth > c.clientWidth - 4).map((c) => c.textContent)
      );
      await p.context().close();
      if (cut.length) bad.push(`${lang} ${vp.width}: ${cut.join(", ")}`);
    }
  }
  assert(!bad.length, bad.join("; "));
  return { status: "PASS", detail: "подписи 5 карточек помещаются: ru и kk, 1366 / 375 / 360 px" };
});
await check("keyboard_tab_enter_escape", async () => {
  const p = await openPage({}, "?reset=1&store=local");
  let found = false;
  for (let i = 0; i < 25 && !found; i++) {
    await p.keyboard.press("Tab");
    found = await p.evaluate(() => document.activeElement && document.activeElement.classList.contains("b3d-card"));
  }
  assert(found, "Tab не дошёл до каталога");
  const ring = await p.evaluate(() => getComputedStyle(document.activeElement).outlineStyle);
  await p.keyboard.press("Enter");
  await p.waitForTimeout(100);
  const s1 = await state(p);
  const focusPlace = await p.evaluate(() => document.activeElement && document.activeElement.getAttribute("data-action"));
  await p.keyboard.press("r");
  const s2 = await state(p);
  await p.keyboard.press("Escape");
  const s3 = await state(p);
  await p.context().close();
  assert(s1.mode === "placing" && s1.ghost.follow === "center", JSON.stringify(s1.ghost));
  assert(s2.ghost.rot === 15 && s3.mode === "idle", "R/Escape");
  return { status: "PASS", detail: `Tab → каталог (рамка ${ring}), Enter → размещение, фокус на «${focusPlace}», R → 15°, Escape → отмена` };
});

// ───────────── 11. Ошибка загрузки 3D: понятное сообщение и «Повторить» ─────────────
await check("three_load_error_state", async () => {
  const p = await openPage({}, "?reset=1&store=local&three=/vendor/three/none.js", { phase: "error" });
  const text = await p.textContent(".b3d-message");
  const retry = await p.$(".b3d-message button");
  if (SHOTS) await p.screenshot({ path: path.join(OUT, "screens", "1366_ru_error.png") });
  await p.context().close();
  assert(retry && /Повторить/.test(text), text);
  return { status: "PASS", detail: text.replace(/\s+/g, " ").trim() };
});

// ───────────── 12. Настоящий путь через API (макет R06 по CONTRACT §7) ─────────────
await check("api_store_contract_roundtrip", async () => {
  api.enabled = true;
  api.items = JSON.parse(JSON.stringify(FIXTURE.proposals)).map((p) => Object.assign(p, { id: "srv-" + p.id }));
  api.log = [];
  const p = await openPage({}, "?reset=1&store=api&center=71.4008,51.1272&zoom=17.4&pitch=60&bearing=-30");
  const s0 = await state(p);
  await placePoint(p, "stop", [71.4023, 51.12735], 1);
  await p.waitForFunction(() => !__b3d.getState().animating && __b3d.getState().proposals.some((x) => /^srv-\d+$/.test(x.id)), null, { timeout: 30000 });
  const created = (await state(p)).proposals.find((x) => /^srv-\d+$/.test(x.id));
  await p.click(`.b3d-label[data-id="${created.id}"]`);
  await p.click("[data-action=vote-up]");
  await p.waitForFunction(() => !document.querySelector('[aria-busy="true"]'));
  await p.click("[data-action=delete]");
  await p.waitForFunction((id) => !__b3d.getState().proposals.some((x) => x.id === id), created.id);
  await p.reload();
  await waitReady(p);
  const s1 = await state(p);
  await p.context().close();
  api.enabled = false;
  const post = api.log.find((r) => r.method === "POST" && r.path === "/api/civic/v2/proposals");
  const vote = api.log.find((r) => r.path.endsWith("/vote"));
  const del = api.log.find((r) => r.method === "DELETE");
  assert(s0.storeMode === "api" && post && vote && del, JSON.stringify(api.log.map((r) => r.method + " " + r.path)));
  assert(post.body.kind === "stop" && post.body.geometry.type === "Point" && typeof post.body.rotation_deg === "number", "тело POST");
  assert(vote.body.value === 1 && /^dev-/.test(vote.body.device_id), "тело голоса");
  assert(s1.count === FIXTURE.proposals.length, "после удаления и перезагрузки " + s1.count);
  return { status: "PASS", detail: { requests: api.log.map((r) => r.method + " " + r.path.replace("/api/civic/v2", "")), post_fields: Object.keys(post.body).sort() } };
});

// ───────────── UX_REVIEW R11, день 3 (#20–#25): по проверке на каждое замечание ─────────────
await check("r11_20_start_close_up_17_4", async () => {
  const p = await openPage({}, "?reset=1&store=local"); // без center — крупный план проектов (flyToProposals)
  const st = await p.evaluate(() => ({
    zoom: __map.getZoom(),
    labels: [...document.querySelectorAll(".b3d-label")].filter((l) => l.style.visibility !== "hidden" && !l.classList.contains("b3d-label--dot")).length,
  }));
  await p.context().close();
  assert(Math.abs(st.zoom - 17.4) < 0.05 && st.labels >= 2, JSON.stringify(st));
  return { status: "PASS", detail: `масштаб ${st.zoom.toFixed(2)}, видно подписей ${st.labels}` };
});
await check("r11_20_catalog_pick_zooms_to_17_5", async () => {
  const p = await openPage({}, "?reset=1&store=local&center=71.4009,51.1276&zoom=16.4");
  await p.click(".b3d-card[data-kind=square]");
  await p.waitForFunction(() => Math.abs(__map.getZoom() - 17.5) < 0.01 && !__map.isMoving(), null, { timeout: 15000 });
  const z = await p.evaluate(() => __map.getZoom());
  await p.context().close();
  return { status: "PASS", detail: `выбор «Сквер» на 16.4 → плавно ${z.toFixed(2)}` };
});
await check("r11_21_model_clickable_pointer_label_40_zone_48", async () => {
  const p = await openPage({}, "?reset=1&store=local&center=71.4022,51.1286&zoom=17.9&pitch=55&bearing=-20");
  const id = "p-demo-square-yard-1148721825";
  const pt = await p.evaluate((id) => {
    const a = __b3d._project(id, [6, -4, 1]); // газон сквера, не подпись
    const r = __map.getCanvas().getBoundingClientRect();
    return [a.x + r.left, a.y + r.top];
  }, id);
  await p.mouse.move(pt[0], pt[1], { steps: 3 });
  await p.waitForTimeout(400);
  const cursor = await p.evaluate(() => __map.getCanvas().style.cursor);
  await p.mouse.click(pt[0], pt[1]);
  await p.waitForSelector(".b3d-dock[data-state=card]");
  const sel = (await state(p)).selected;
  const sizes = await p.$$eval(".b3d-label", (els) =>
    els
      .filter((e) => !e.classList.contains("b3d-label--dot") && e.style.visibility !== "hidden")
      .map((e) => {
        const zone = e.getBoundingClientRect(); // кнопка — зона нажатия
        const pill = e.querySelector(".b3d-label__pill").getBoundingClientRect(); // видимая табличка
        return { h: pill.height, zoneH: zone.height, zoneW: zone.width };
      })
  );
  await p.context().close();
  assert(cursor === "pointer" && sel === id, JSON.stringify({ cursor, sel }));
  assert(sizes.length && sizes.every((z) => z.h >= 40 && z.zoneH >= 48 && z.zoneW >= 48), JSON.stringify(sizes));
  return { status: "PASS", detail: { cursor_over_model: cursor, opened_by_model_click: sel, label_height_px: sizes[0].h, tap_zone_px: sizes[0].zoneH } };
});
await check("r11_21_selected_object_not_under_card_1366_375", async () => {
  const out = [];
  for (const vp of [{ width: 1366, height: 768 }, { width: 375, height: 812 }]) {
    // Остановка-пример у нижнего края экрана: после выбора она должна оказаться над/слева от карточки.
    const p = await openPage({ viewport: vp }, "?reset=1&store=local&center=71.4015,51.1290&zoom=17.4&pitch=55&bearing=-20");
    const id = "p-demo-stop-syganak";
    await p.evaluate((id) => __b3d.select(id), id);
    await p.waitForTimeout(1000);
    const r = await p.evaluate((id) => {
      const a = __b3d._project(id, [0, 0, 0]);
      const c = __map.getCanvas().getBoundingClientRect();
      const d = document.querySelector(".b3d-dock").getBoundingClientRect();
      const x = a.x + c.left,
        y = a.y + c.top;
      return { x: Math.round(x), y: Math.round(y), under: x >= d.left && x <= d.right && y >= d.top && y <= d.bottom, onScreen: x > 0 && x < innerWidth && y > c.top && y < innerHeight };
    }, id);
    out.push(Object.assign({ vp: vp.width }, r));
    if (SHOTS) await p.screenshot({ path: path.join(OUT, "screens", `${vp.width}_ru_card_object_visible.png`) });
    await p.context().close();
  }
  assert(out.every((o) => !o.under && o.onScreen), JSON.stringify(out));
  return { status: "PASS", detail: out.map((o) => `${o.vp} px: объект (${o.x}, ${o.y}) на экране и не под карточкой`).join("; ") };
});
await check("r11_22_23_demo_header_title_and_3d_label", async () => {
  const res = {};
  for (const lang of ["ru", "kk"]) {
    const p = await openPage({}, `?reset=1&store=local&lang=${lang}`);
    res[lang] = await p.evaluate(() => ({
      title: document.getElementById("demo-title").textContent,
      tag_in_header: !!document.querySelector(".bk-header .bk-tag"),
      button_3d_text: document.getElementById("demo-3d").textContent.trim(),
      button_3d_height: document.getElementById("demo-3d").getBoundingClientRect().height,
    }));
    await p.context().close();
  }
  assert(res.ru.title === "3D-превью" && res.kk.title === "3D-көрініс" && !res.ru.tag_in_header, JSON.stringify(res));
  assert(res.ru.button_3d_text === "3D" && res.kk.button_3d_text === "3D" && res.ru.button_3d_height >= 48, JSON.stringify(res));
  return { status: "PASS", detail: res };
});
await check("r11_24_resident_hint_ru_kk", async () => {
  const res = {};
  for (const [lang, vp] of [["ru", { width: 1366, height: 768 }], ["kk", { width: 375, height: 812 }]]) {
    const p = await openPage({ viewport: vp }, `?reset=1&store=local&role=resident&lang=${lang}`);
    res[lang + "_" + vp.width] = (await p.textContent(".b3d-dock")).trim();
    if (SHOTS) await p.screenshot({ path: path.join(OUT, "screens", `${vp.width}_${lang}_resident_hint.png`) });
    await p.context().close();
  }
  assert(res.ru_1366 === "Нажмите на проект, чтобы проголосовать" && res.kk_375 === "Дауыс беру үшін жобаны басыңыз", JSON.stringify(res));
  return { status: "PASS", detail: res };
});
await check("r11_25_offline_basemap_real_osm_yards", async () => {
  const p = await openPage({}, "?reset=1&store=local");
  const r = await p.evaluate(() => ({
    yards_in_source: __map.getSource("yards").serialize().data.features.length,
    yards_on_screen: __map.queryRenderedFeatures({ layers: ["yards"] }).length,
    examples_in_yards: __b3d.getState().proposals.filter((q) => q.target && q.target.kind === "area").map((q) => q.target.label_ru),
  }));
  await p.context().close();
  assert(r.yards_in_source > 100 && r.yards_on_screen >= 2 && r.examples_in_yards.length >= 2, JSON.stringify(r));
  return { status: "PASS", detail: r };
});

// ───────────── Соглашения оболочки R01 и участки улиц R12 ─────────────
await check("r01_birge_mode_event_update_dock", async () => {
  const p = await openPage({}, "?reset=1&store=local");
  await p.evaluate(() => document.dispatchEvent(new CustomEvent("birge:mode", { detail: { mode: "resident" } })));
  await p.waitForTimeout(200);
  const residentCards = await p.$$eval(".b3d-card", (e) => e.length);
  const hint = (await p.textContent(".b3d-dock")).trim();
  await p.evaluate(() => __b3d.update({ mode: "akimat", dock: false }));
  const hidden = await p.$eval(".b3d-dock", (d) => d.getAttribute("data-state"));
  const labels = await p.$$eval(".b3d-label", (e) => e.length);
  await p.evaluate(() => __b3d.update({ dock: true }));
  const back = await p.$$eval(".b3d-card", (e) => e.length);
  await p.context().close();
  assert(residentCards === 0 && /проголосовать/.test(hint) && hidden === "empty" && labels >= 4 && back === 5, JSON.stringify({ residentCards, hint, hidden, labels, back }));
  return { status: "PASS", detail: "birge:mode → житель без каталога; update({dock:false}) прячет каталог, объекты остаются; update({dock:true}) возвращает" };
});
await check("mode_switch_clears_akimat_undo_toast", async () => {
  // Сборка B2 R01: акимат поставил объект → «Житель». Тост «Проект поставлен · Отменить» не должен остаться у жителя.
  const p = await openPage({}, "?reset=1&store=local&" + MAIN_Q.slice(1));
  await placePoint(p, "sports", [71.3998, 51.1268]);
  await p.waitForSelector(".bk-toast [data-action=undo]", { timeout: 10000 });
  await p.evaluate(() => document.dispatchEvent(new CustomEvent("birge:mode", { detail: { mode: "resident" } })));
  await p.waitForTimeout(150);
  const toastsResident = await p.$$eval(".b3d .bk-toast", (e) => e.length);
  const cards = await p.$$eval(".b3d-card", (e) => e.length);
  await p.context().close();
  assert(toastsResident === 0 && cards === 0, JSON.stringify({ toastsResident, cards }));
  return { status: "PASS", detail: "после «Житель» тоста акимата с «Отменить» нет, каталога нет" };
});
await check("catalog_labels_fit_cards_in_narrow_host", async () => {
  // Оболочка R01 даёт модулю 720 px (B2): «Спортплощадка» не должна выходить за рамку карточки; все 5 — в строку.
  const p = await openPage({}, "?reset=1&store=local&" + MAIN_Q.slice(1));
  const out = {};
  for (const lang of ["ru", "kk"]) {
    if (lang === "kk") await p.click(".bk-seg [data-lang=kk]").catch(() => p.evaluate(() => window.BirgeI18n && BirgeI18n.setLang("kk")));
    await p.waitForTimeout(200);
    for (const w of [800, 720, 600]) {
      out[lang + w] = await p.evaluate((w) => {
        const dock = document.querySelector(".b3d-dock");
        dock.style.width = w + "px";
        const row = document.querySelector(".b3d-cards");
        const cards = [...document.querySelectorAll(".b3d-card")];
        const res = cards.map((c) => {
          const l = c.querySelector(".b3d-card__label") || c;
          const rc = c.getBoundingClientRect();
          const range = document.createRange();
          range.selectNodeContents(l);
          const rt = range.getBoundingClientRect();
          return { text: l.textContent, inside: rt.left >= rc.left + 1 && rt.right <= rc.right - 1, fs: parseFloat(getComputedStyle(c).fontSize) };
        });
        dock.style.width = "";
        return { allInRow: row.scrollWidth <= row.clientWidth + 1, bad: res.filter((r) => !r.inside).map((r) => r.text), minFs: Math.min(...res.map((r) => r.fs)) };
      }, w);
    }
  }
  await p.context().close();
  const bad = Object.entries(out).filter(([k, v]) => v.bad.length || v.minFs < 14 || (!k.endsWith("600") && !v.allInRow));
  assert(bad.length === 0, JSON.stringify(out));
  return { status: "PASS", detail: out };
});
await check("r10_b026_far_zoom_dots_24px_and_cluster_1366_375_ru_kk", async () => {
  // R10 B-026: на виде «вся Астана» таблички сжимались в точки 18 px и пять проектов ложились в одну точку.
  // Теперь: точка 32 px со значком вида; совпавшие точки — одна метка с числом; нажатие приближает к ним.
  const out = [];
  for (const vp of [{ width: 1366, height: 768 }, { width: 375, height: 812 }]) {
    for (const lang of ["ru", "kk"]) {
      const touch = vp.width < 640 ? { hasTouch: true, isMobile: true } : {};
      const p = await openPage(Object.assign({ viewport: vp }, touch), `?reset=1&store=local&lang=${lang}&center=71.4012,51.1278&zoom=12&pitch=0`);
      await p.waitForTimeout(300);
      const far = await p.evaluate(() => {
        const vis = [...document.querySelectorAll(".b3d-label")].filter((b) => b.style.visibility !== "hidden");
        const pills = vis.map((b) => b.querySelector(".b3d-label__pill").getBoundingClientRect());
        const cl = document.querySelector(".b3d-label--cluster");
        return { visible: vis.length, minPill: Math.round(Math.min(...pills.map((r) => Math.min(r.width, r.height)))),
          zone: Math.round(Math.min(...vis.map((b) => b.getBoundingClientRect().height))),
          count: cl ? cl.querySelector(".b3d-label__count").textContent : null, aria: cl ? cl.getAttribute("aria-label") : null };
      });
      if (SHOTS) await p.screenshot({ path: path.join(OUT, "screens", `b026_cluster_${vp.width}_${lang}.png`) });
      const z0 = await p.evaluate(() => __map.getZoom());
      await (touch.hasTouch ? p.tap(".b3d-label--cluster") : p.click(".b3d-label--cluster"));
      // Полёт камеры (fitBounds, 700 мс) — ждать его конца: «тайлы загружены» бывает и посреди полёта.
      await p.waitForFunction(() => __map.isMoving(), null, { timeout: 2000 }).catch(() => {});
      await p.waitForFunction(() => !__map.isMoving(), null, { timeout: 10000 });
      await idle(p);
      const near = await p.evaluate(() => ({ zoom: +__map.getZoom().toFixed(2), full: document.querySelectorAll(".b3d-label:not(.b3d-label--dot)").length,
        clusters: document.querySelectorAll(".b3d-label--cluster").length }));
      out.push({ vp: vp.width, lang, far, z0: +z0.toFixed(1), near });
      await p.context().close();
    }
  }
  const kkAria = out.find((o) => o.lang === "kk").far.aria || "";
  assert(out.every((o) => o.far.count === "4" && o.far.minPill >= 24 && o.far.zone >= 48 && o.near.zoom >= o.z0 + 3 && o.near.clusters === 0 && o.near.full >= 3) && /жоба/.test(kkAria),
    JSON.stringify(out));
  return { status: "PASS", detail: out.map((o) => `${o.vp} ${o.lang}: метка «${o.far.count}» (${o.far.aria}), точка ≥ ${o.far.minPill} px, зона ${o.far.zone} → масштаб ${o.near.zoom}, полных подписей ${o.near.full}`).join("; ") };
});
await check("kk_street_names_from_osm_card_and_lighting_hint_1366_375", async () => {
  // Самопроверка по UX_BRIEF п. 6: в kk название улицы — казахское из OSM (name:kk), если оно там есть.
  const out = [];
  for (const vp of [{ width: 1366, height: 768 }, { width: 375, height: 812 }]) {
    const touch = vp.width < 640 ? { hasTouch: true, isMobile: true } : {};
    const p = await openPage(Object.assign({ viewport: vp }, touch), "?reset=1&store=local&lang=kk&" + MAIN_Q.slice(1));
    await p.evaluate(() => __b3d.select("p-demo-stop-syganak"));
    await p.waitForSelector(".b3d-dock[data-state=card]");
    await idle(p);
    const card = await p.$eval(".b3d-dock", (d) => d.innerText);
    if (SHOTS) await p.screenshot({ path: path.join(OUT, "screens", `kk_street_${vp.width}_card.png`) });
    await p.evaluate(() => __b3d.select(null));
    await (touch.hasTouch ? p.tap(".b3d-card[data-kind=lighting]") : p.click(".b3d-card[data-kind=lighting]"));
    await p.evaluate((ll) => __map.jumpTo({ center: ll }), LIGHT_A); // точка улицы — в центре карты, не под панелью
    await idle(p);
    const [x, y] = await screenOf(p, LIGHT_A);
    if (touch.hasTouch) await p.touchscreen.tap(x, y);
    else {
      await p.mouse.move(x, y);
      await p.mouse.click(x, y);
    }
    await p.waitForTimeout(300);
    const hint = await p.textContent(".b3d-hint");
    out.push({ vp: vp.width, card: (card.match(/Жанында:[^\n]*/) || [""])[0], hint: hint.trim() });
    await p.context().close();
  }
  assert(out.every((o) => /Сығанақ көшесі/.test(o.card) && /Сығанақ көшесі/.test(o.hint) && !/улица/.test(o.card + o.hint)), JSON.stringify(out));
  return { status: "PASS", detail: out };
});
await check("kk_no_russian_street_names_in_card_and_hint", async () => {
  // R11 ночь, B3 п. 5: «Жанында: улица Керей и Жанибек хандар» — по-русски внутри казахской фразы. Улица без name:kk
  // в OSM — по правилу R07 («… көшесі»); проверяем на проекте у такой улицы и на подсказке освещения.
  const noKk = STREETS.names.find((n, i) => !STREETS.names_kk[i] && /^улица /.test(n));
  const e = STREETS.edges.find((row) => STREETS.names[row[1]] === noKk);
  const mid = e[5][Math.floor(e[5].length / 2)];
  const item = { id: "s-kk-street", kind: "square", geometry: { type: "Point", coordinates: mid }, rotation_deg: 0, status: "proposal",
    votes_up: 0, votes_down: 0, year: 2027, near_street: noKk, demo: false };
  const p = await openPage({}, `?store=local&lang=kk&center=${mid[0]},${mid[1]}&zoom=17.4&pitch=50`, { seed: [item] });
  await p.evaluate(() => __b3d.select("s-kk-street"));
  await p.waitForSelector(".b3d-dock[data-state=card]");
  const card = await p.$eval(".b3d-dock", (d) => d.innerText);
  if (SHOTS) await p.screenshot({ path: path.join(OUT, "screens", "kk_street_rule_1366_card.png") });
  await p.evaluate(() => __b3d.select(null));
  await p.click(".b3d-card[data-kind=lighting]");
  const [x, y] = await screenOf(p, e[5][0]);
  await p.mouse.move(x, y);
  await p.mouse.click(x, y);
  await p.waitForTimeout(300);
  const hint = await p.textContent(".b3d-hint");
  // Смена языка посреди размещения: подсказка с улицей — на новом языке.
  await p.click(".bk-seg [data-lang=ru]");
  await p.waitForTimeout(300);
  const hintRu = await p.textContent(".b3d-hint");
  await p.context().close();
  const expected = noKk.replace(/^улица /, "") + " көшесі";
  assert(hintRu.includes(noKk), "после РУС подсказка по-русски: " + hintRu);
  assert(card.includes("Жанында: " + expected) && hint.includes(expected) && !/улица|проспект/.test(card + hint), JSON.stringify({ noKk, card, hint }));
  return { status: "PASS", detail: { street_ru: noKk, card: (card.match(/Жанында:[^\n]*/) || [""])[0], hint: hint.trim() } };
});
await check("rate_limit_429_says_too_many_without_retry_ru_kk", async () => {
  // R15 U1: ответ 429 (лимит шлюза R01 по адресу) — не «Проверьте связь…» и без «Повторить» (повтор снова упрётся в лимит).
  const out = {};
  for (const lang of ["ru", "kk"]) {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
    const p = await ctx.newPage();
    p.on("pageerror", (e) => pageErrors.push("429: " + e.message));
    await p.route("**/api/civic/v2/proposals**", (route) => {
      const req = route.request();
      if (req.method() === "GET") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: FIXTURE.proposals }) });
      return route.fulfill({ status: 429, contentType: "application/json", headers: { "Retry-After": "60" },
        body: JSON.stringify({ error: "too_many_requests", message: "Слишком много запросов" }) });
    });
    await p.goto(BASE + `?store=api&lang=${lang}&` + MAIN_Q.slice(1));
    await waitReady(p);
    await p.evaluate((id) => __b3d.select(id), FIXTURE.proposals[0].id);
    await p.click("[data-action=vote-up]");
    await p.waitForSelector(".bk-toast--error", { timeout: 10000 });
    out[lang] = await p.evaluate(() => ({ text: document.querySelector(".bk-toast--error").innerText.trim(), retry: !!document.querySelector(".bk-toast [data-action^=retry]") }));
    if (SHOTS && lang === "kk") await p.screenshot({ path: path.join(OUT, "screens", "toast_429_1366_kk.png") });
    await ctx.close();
  }
  assert(/Слишком много/.test(out.ru.text) && /тым көп/.test(out.kk.text) && !out.ru.retry && !out.kk.retry && !/связ|Байланыс/.test(out.ru.text + out.kk.text), JSON.stringify(out));
  return { status: "PASS", detail: out };
});
await check("reload_during_list_request_logs_no_console_error", async () => {
  // R01 I-05: перезагрузка страницы обрывает запрос списка («TypeError: Failed to fetch») — это не ошибка модуля:
  // ни console.error, ни тоста. Настоящий обрыв связи без ухода со страницы — тост «Повторить» и console.warn.
  const out = {};
  for (const [w, h, lang] of [[1366, 768, "ru"], [1366, 768, "kk"], [375, 812, "ru"], [375, 812, "kk"]]) {
    const phone = w < 700;
    const ctx = await browser.newContext(phone ? { viewport: { width: w, height: h }, hasTouch: true, isMobile: true } : { viewport: { width: w, height: h } });
    const p = await ctx.newPage();
    const errors = [];
    const warns = [];
    p.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
      if (m.type() === "warning" && /\[build3d\]/.test(m.text())) warns.push(m.text());
    });
    let hold = true;
    let held = 0;
    await p.route("**/api/civic/v2/proposals**", (route) => {
      if (hold && route.request().method() === "GET") {
        held++;
        return; // не отвечаем: запрос висит, пока страницу не перезагрузят
      }
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: FIXTURE.proposals }) });
    });
    await p.goto(BASE + `?store=api&lang=${lang}&` + MAIN_Q.slice(1));
    for (let i = 0; i < 600 && !held; i++) await p.waitForTimeout(100); // ждём, пока запрос списка уйдёт и повиснет
    const heldBefore = held;
    hold = false;
    await p.reload();
    await waitReady(p);
    await p.waitForTimeout(500);
    const afterReload = { errors: errors.filter((e) => /build3d|Failed to fetch/.test(e)), count: (await state(p)).count };
    // Обрыв без ухода со страницы: соединение сброшено — тост с «Повторить», в консоли предупреждение, не ошибка.
    await p.unroute("**/api/civic/v2/proposals**");
    await p.route("**/api/civic/v2/proposals**", (route) => route.abort("connectionreset"));
    const n0 = errors.length;
    await p.evaluate(() => __b3d.refresh());
    await p.waitForSelector(".bk-toast--error", { timeout: 10000 });
    const net = await p.evaluate(() => ({
      toast: document.querySelector(".bk-toast--error").innerText.trim(),
      retry: !!document.querySelector(".bk-toast [data-action=retry-load]"),
    }));
    if (SHOTS) await p.screenshot({ path: path.join(OUT, "screens", `net_toast_${w}_${lang}.png`) });
    const netErrors = errors.slice(n0).filter((e) => /build3d/.test(e));
    await ctx.close();
    const d = { heldBefore, afterReload, net, netErrors, warns: warns.slice(-1) };
    out[`${w}_${lang}`] = d;
    assert(heldBefore >= 1, "запрос списка не был в полёте: " + JSON.stringify(d));
    assert(afterReload.errors.length === 0 && afterReload.count >= 1, JSON.stringify(d));
    assert(net.retry && netErrors.length === 0 && warns.length >= 1, JSON.stringify(d));
    assert(lang === "ru" ? /Повторить/.test(net.toast) : /Қайталау/.test(net.toast) && !/Повторить/.test(net.toast), JSON.stringify(d));
  }
  return { status: "PASS", detail: out };
});
await check("r01_map_getter_waits_for_map", async () => {
  const p = await openPage({}, "?reset=1&store=local");
  const r = await p.evaluate(async () => {
    __b3d.destroy();
    let ready = null;
    const h = CivicBuild3D.mount({ map: () => ready, mode: "resident", store: "local" });
    const before = h.getState().phase;
    setTimeout(() => {
      ready = __map;
    }, 700);
    await h.ready;
    const after = h.getState();
    h.destroy();
    return { before, phase: after.phase, count: after.count };
  });
  await p.context().close();
  assert(r.before === "waiting_map" && r.phase === "ready" && r.count >= 4, JSON.stringify(r));
  return { status: "PASS", detail: r };
});
await check("lighting_outside_nura_without_r12_says_so", async () => {
  const p = await openPage({}, "?reset=1&store=local&center=71.4314,51.1604&zoom=17.4&pitch=50&bearing=0");
  await p.click(".b3d-card[data-kind=lighting]");
  const c = await screenOf(p, [71.4300153, 51.1601624]);
  await p.mouse.move(c[0], c[1]);
  await p.mouse.click(c[0], c[1]);
  await p.waitForTimeout(800);
  const hint = (await p.textContent(".b3d-hint")).trim();
  await p.context().close();
  assert(/только в районе Нура/.test(hint), hint);
  return { status: "PASS", detail: hint + " (маршрутов R12 нет на этом сервере; с R12 — geo_check.mjs)" };
});

// ───────────── 13. Скриншоты для DELIVERY: 1366 и 375, наклон 0° и 60°, ru и kk ─────────────
if (SHOTS) {
  await check("screenshots_1366_375_pitch_0_60_ru_kk", async () => {
    const made = [];
    for (const lang of ["ru", "kk"]) {
      for (const pitch of [60, 0]) {
        const desk = await openPage({}, `?lang=${lang}&store=local&pitch=${pitch}&bearing=${pitch ? -20 : 0}`, { seed: SHOWCASE });
        await shot(desk, `1366_${lang}_p${pitch}.png`);
        made.push(`1366_${lang}_p${pitch}.png`);
        await desk.context().close();
        const phone = await openPage({ viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 }, `?lang=${lang}&store=local&pitch=${pitch}&bearing=${pitch ? -20 : 0}`, { seed: SHOWCASE });
        await shot(phone, `375_${lang}_p${pitch}.png`);
        made.push(`375_${lang}_p${pitch}.png`);
        await phone.context().close();
      }
    }
    // Призрак остановки (сама встаёт вдоль улицы) и участок освещения перед «Поставить».
    const g = await openPage({}, "?reset=1&store=local&center=71.4016,51.1273&zoom=18.4&pitch=60&bearing=-25");
    await g.click(".b3d-card[data-kind=stop]");
    const [x, y] = await screenOf(g, [71.4019, 51.12738]);
    await g.mouse.move(x, y, { steps: 3 });
    await shot(g, "1366_ru_ghost_stop.png");
    await g.click("[data-action=cancel]");
    await g.evaluate(() => __map.jumpTo({ center: [71.4031, 51.1271], zoom: 17.6, pitch: 60, bearing: -25 }));
    await idle(g);
    await g.click(".b3d-card[data-kind=lighting]");
    const pa = await screenOf(g, LIGHT_A);
    await g.mouse.move(pa[0], pa[1]);
    await g.mouse.click(pa[0], pa[1]);
    const pb = await screenOf(g, LIGHT_B);
    await g.mouse.move(pb[0], pb[1], { steps: 3 });
    await g.mouse.click(pb[0], pb[1]);
    await shot(g, "1366_ru_lighting_ghost.png");
    await g.context().close();
    made.push("1366_ru_ghost_stop.png", "1366_ru_lighting_ghost.png");
    return { status: "PASS", detail: made.join(", ") };
  });
}

await check("no_page_errors", async () => {
  assert(pageErrors.length === 0, pageErrors.join(" | "));
  return { status: "PASS", detail: "0 ошибок страницы во всех проверках" };
});
results.push({
  id: "smooth_on_laptop_gpu",
  status: "NOT_RUN",
  detail: "В облаке нет GPU (WebGL через SwiftShader). Плавность 20 объектов на ноутбуке проверить локально: RUN.txt, шаг LOCAL.",
});

await browser.close();
server.close();

let sha = null;
try {
  sha = execSync("git rev-parse HEAD", { cwd: ROOT }).toString().trim();
} catch (e) {
  /* не git */
}
const report = {
  role: "R05",
  generated_at: new Date().toISOString(),
  tested_sha: sha,
  dirty: (() => {
    try {
      return execSync("git status --porcelain -- web/civic/build3d web/vendor/three tests/civic/R05/build3d", { cwd: ROOT }).toString().trim().length > 0;
    } catch (e) {
      return null;
    }
  })(),
  environment: Object.assign({ node: process.version, chromium: browser.version ? browser.version() : null, renderer: "SwiftShader (без GPU)",
    ui_kit_i18n: KIT ? "из выгрузки --kit " + path.relative(ROOT, path.dirname(KIT)) : "web/civic/ui-kit, web/civic/i18n этой ветки" }, env),
  summary: {
    pass: results.filter((r) => r.status === "PASS").length,
    fail: results.filter((r) => r.status === "FAIL").length,
    not_run: results.filter((r) => r.status === "NOT_RUN").length,
  },
  checks: results,
};
if (!ONLY) await writeFile(path.join(OUT, "runs", "browser_check.json"), JSON.stringify(report, null, 1) + "\n");
console.log(`\nИтого: ${report.summary.pass} PASS, ${report.summary.fail} FAIL, ${report.summary.not_run} NOT_RUN → research/round-14-results/R05/runs/browser_check.json`);
process.exit(report.summary.fail ? 1 : 0);
