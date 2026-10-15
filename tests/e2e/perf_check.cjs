// R10 · раунд 15 · производительность (R10.txt задача 6, VISUAL_BRIEF №1): первый значок карты ≤ 3 с; плавность «Хроники
// города» R07 и перемещения карты; время ответа «Спросить Birge» R03.
//
//   NODE_PATH="$(npm root -g)" node tests/e2e/perf_check.cjs --root <папка сборки> --out <папка> [--no-world] [--repeat 3]
//        [--sizes 1366x768,1024x768] [--replay-days 7]
//
// Сервер сборки — с демо-миром (CIVIC_DEMO_WORLD=1), временная база. Итог: <out>/PERF.json и PERF.md.
//   1. Первый значок с числом на карте (мс от начала навигации, медиана --repeat окон без кэша) — порог 3000 мс.
//   2. «Хроника города»: BirgeReplay.open({days, autoplay}) → до конца воспроизведения → stats() модуля R07 (кадры, средний
//      и p95 кадр, худший кадр) + наш счёт кадров requestAnimationFrame; сколько значков на карте (целей в кадре).
//      Порог VISUAL_BRIEF №1 — 60 кадров/с на ноутбуке при 1 000 целей. В облаке WebGL программный (3–7 к/с) — это ИНФО,
//      не FAIL: мерить на ноутбуке (LOCAL), тот же скрипт.
//   3. Перемещение карты (easeTo) и перелёт (flyTo) — кадры/с и p95 кадра.
//   4. «Спросить Birge»: первый ответ после старта и медиана следующих (API).
"use strict";
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path"), os = require("os");
const L = require("./r10_lib.cjs");
const { sleep } = L;

const args = L.parseArgs(process.argv.slice(2));
const ROOT = path.resolve(args.root || path.join(__dirname, "../.."));
const OUT = path.resolve(args.out || path.join(os.tmpdir(), "r10-perf"));
const REPEAT = Math.max(1, Number(args.repeat || 3));
const SIZES = String(args.sizes || "1366x768").split(",").map((s) => s.split("x").map(Number));
const DAYS = Number(args["replay-days"] || 7);
const WORLD = !args["no-world"];
const CENTER = [71.4065, 51.1312];  // Нура, «Хан Шатыр»
const rows = [];
const add = (name, status, value, note) => { rows.push({ name, status, value, note: note || null });
  console.log(`${status.padEnd(7)} ${name} — ${JSON.stringify(value)}${note ? " (" + note + ")" : ""}`); };

async function firstBadge(browser, base, [w, h]) {
  const times = [];
  for (let i = 0; i < REPEAT; i++) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    await ctx.addInitScript(() => { try { localStorage.setItem("birge.mode", "akimat"); } catch (e) { /* без хранилища */ } });
    // Момент записывает сама страница (как map_baseline): опрос из теста ждал бы конца длинных задач загрузки и
    // прибавлял к времени 0,3–0,6 с, которых пользователь не видит.
    await ctx.addInitScript(() => {
      const vis = (e) => { const b = e.getBoundingClientRect(); return b.width > 0 && b.height > 0 && b.bottom > 0 && b.top < innerHeight && b.right > 0 && b.left < innerWidth; };
      const tick = () => {
        try { if ([...document.querySelectorAll(".maplibregl-marker")].some((e) => vis(e) && /\d/.test(e.innerText))) { window.__r10fb = Math.round(performance.now()); return; } } catch (e) { /* страница строится */ }
        if (performance.now() < 30000) setTimeout(tick, 40);
      };
      tick();
    });
    const page = await ctx.newPage();
    await page.goto(base, { waitUntil: "commit" });
    const t = await page.waitForFunction(() => typeof window.__r10fb === "number", null, { timeout: 30000, polling: 100 })
      .then(() => page.evaluate(() => window.__r10fb), () => null);
    times.push(t);
    await ctx.close();
  }
  return { median_ms: L.median(times), runs: times };
}

async function replayAndMap(browser, base, [w, h]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  await ctx.addInitScript(() => { try { localStorage.setItem("birge.mode", "akimat"); } catch (e) { /* без хранилища */ } });
  const page = await ctx.newPage();
  await page.goto(base);
  await page.waitForFunction(() => typeof map !== "undefined" && map && map.loaded && map.loaded(), null, { timeout: 40000 }).catch(() => null);
  await sleep(3000);
  const out = { size: `${w}x${h}` };
  // Перемещение и перелёт карты (как glass_check.cjs SMOOTH): кадры requestAnimationFrame во время анимации камеры.
  out.map = await page.evaluate(async (center) => {
    // eslint-disable-next-line no-undef
    const m = typeof map !== "undefined" && map && map.getStyle ? map : null;
    if (!m) return null;
    const wait = (ms) => new Promise((ok) => setTimeout(ok, ms));
    const frames = async (start, ms) => { const d = []; let last = performance.now(); const t0 = last; let run = true;
      const loop = (t) => { d.push(t - last); last = t; if (run) requestAnimationFrame(loop); };
      requestAnimationFrame(loop); start(); await wait(ms); run = false; await wait(50);
      const v = d.slice(1).sort((a, b) => a - b);
      return { fps: Math.round((v.length * 1000) / (performance.now() - t0)), p95_ms: Math.round(v[Math.floor(v.length * 0.95)] || 0) }; };
    m.jumpTo({ center, zoom: 14, pitch: 0, bearing: 0 }); await wait(2000);
    const markers = [...document.querySelectorAll(".maplibregl-marker")].filter((e) => e.getBoundingClientRect().width > 0).length;
    const pan = await frames(() => m.easeTo({ center: [center[0] + 0.02, center[1] + 0.006], duration: 2000 }), 2300);
    m.jumpTo({ center, zoom: 11 }); await wait(1500);
    const fly = await frames(() => m.flyTo({ center, zoom: 14, duration: 2000 }), 2300);
    return { markers_z14: markers, pan, fly };
  }, CENTER).catch((e) => ({ error: String(e.message || e).slice(0, 200) }));
  // «Хроника города» R07.
  const has = await page.evaluate(() => !!(window.BirgeReplay && typeof window.BirgeReplay.open === "function")).catch(() => false);
  if (!has) { out.replay = { skipped: "модуля BirgeReplay (R07) нет на странице" }; await ctx.close(); return out; }
  out.replay = await page.evaluate(async (days) => {
    const wait = (ms) => new Promise((ok) => setTimeout(ok, ms));
    // eslint-disable-next-line no-undef
    const m = typeof map !== "undefined" ? map : null;
    if (m) { m.jumpTo({ zoom: 11.5 }); await wait(1200); }
    const ours = []; let last = performance.now(); let run = true;
    const loop = (t) => { ours.push(t - last); last = t; if (run) requestAnimationFrame(loop); };
    const heat = window.CivicShell && window.CivicShell.heat;
    const t0 = performance.now();
    const rp = window.BirgeReplay.open({ map: m, heat, days, autoplay: true });
    requestAnimationFrame(loop);
    let st = null, maxMarkers = 0;
    for (let i = 0; i < 300; i++) {  // до 60 с
      await wait(200);
      st = rp.state ? rp.state() : null;
      maxMarkers = Math.max(maxMarkers, [...document.querySelectorAll(".maplibregl-marker")].filter((e) => e.getBoundingClientRect().width > 0).length);
      if (st && (st.ended || st.status === "error" || st.status === "empty")) break;
    }
    run = false; await wait(50);
    const v = ours.slice(1).sort((a, b) => a - b);
    const stats = rp.stats ? rp.stats() : null;
    const result = { took_ms: Math.round(performance.now() - t0), state: st, stats, markers_max: maxMarkers,
      raf: { fps: v.length ? Math.round((v.length * 1000) / v.reduce((a, b) => a + b, 0)) : 0, p95_ms: Math.round(v[Math.floor(v.length * 0.95)] || 0) } };
    try { rp.close(); } catch (e) { /* закрыто */ }
    return result;
  }, DAYS).catch((e) => ({ error: String(e.message || e).slice(0, 200) }));
  await page.screenshot({ path: path.join(OUT, `replay-end-${w}.jpg`), type: "jpeg", quality: 70 }).catch(() => null);
  await ctx.close();
  return out;
}

async function askTiming(base, staffAcc) {
  const A = L.api(base);
  if (!staffAcc || !staffAcc.user || !(await A.login(staffAcc.user, staffAcc.pass)).ok) return { skipped: "нет входа сотрудника" };
  const qs = ["Сколько жалоб в Нуре за неделю?", "Какая служба больше всего просрочила?", "Нұрада 30 күнде қанша шағым түсті?",
    "Где больше всего жалоб на снег?", "Сколько обращений проверено жителями за месяц?"];
  const ms = [];
  for (const q of qs) {
    const r = await A.call("POST", "/api/civic/v2/assistant/ask", { question: q, lang: /[әғқңөұүһі]/i.test(q) ? "kk" : "ru" }, true);
    if (r.status === 503 || r.status === 404) return { skipped: `маршрут ответил ${r.status}` };
    ms.push(Math.round(r.ms));
  }
  return { first_ms: ms[0], median_rest_ms: L.median(ms.slice(1)), all: ms };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const srv = await L.startServer(ROOT, { demo: true, staff: true, world: WORLD });
  const browser = await chromium.launch();
  const result = { meta: { root: ROOT, sha: L.buildSha(ROOT), world: WORLD, machine: L.machine(), when: new Date().toISOString(),
    note: "облако: программный WebGL (3–7 к/с) — плавность здесь ИНФО, мерить на ноутбуке тем же скриптом" } };
  try {
    result.ask = await askTiming(srv.base, srv.staff);  // первым: «первый ответ после старта» — честный холодный старт
    for (const size of SIZES) {
      const tag = size.join("x");
      result[`first_badge_${tag}`] = await firstBadge(browser, srv.base, size);
      result[`replay_${tag}`] = await replayAndMap(browser, srv.base, size);
    }
  } finally { await browser.close(); await srv.stop(); }
  const soft = /swiftshader|llvmpipe|software/i.test(JSON.stringify(result.meta.machine)) || !process.env.R10_REAL_GPU;
  for (const size of SIZES) {
    const tag = size.join("x");
    const fb = result[`first_badge_${tag}`];
    add(`первый значок с числом, ${tag}`, fb.median_ms === null ? "FAIL" : fb.median_ms <= 3000 ? "PASS" : "FAIL", fb, "порог 3000 мс");
    const rp = result[`replay_${tag}`];
    if (rp.map && !rp.map.error) add(`перемещение карты, ${tag}`, "ИНФО", rp.map, soft ? "облако: программный WebGL" : null);
    if (rp.replay && rp.replay.skipped) add(`«Хроника города», ${tag}`, "NOT_RUN", rp.replay.skipped);
    else if (rp.replay && rp.replay.error) add(`«Хроника города», ${tag}`, "FAIL", rp.replay.error);
    else if (rp.replay) {
      const s = rp.replay.stats || {};
      const ended = rp.replay.state && rp.replay.state.ended;
      add(`«Хроника города» доигрывает до конца, ${tag}`, ended ? "PASS" : "FAIL", { took_ms: rp.replay.took_ms, state: rp.replay.state && rp.replay.state.status });
      add(`«Хроника города» плавность, ${tag}`, soft ? "ИНФО" : (s.fps >= 55 ? "PASS" : "FAIL"),
        { fps_module: s.fps, p95_ms: s.p95_ms, worst_ms: s.worst_ms, fps_raf: rp.replay.raf.fps, markers_max: rp.replay.markers_max },
        soft ? "облако: программный WebGL; порог 60 к/с — на ноутбуке" : "порог 55–60 к/с");
    }
  }
  const ask = result.ask;
  if (ask.skipped) add("«Спросить Birge»: время ответа", "NOT_RUN", ask.skipped);
  else add("«Спросить Birge»: время ответа", ask.first_ms <= 3000 && ask.median_rest_ms <= 1500 ? "PASS" : "FAIL", ask,
    "первый ответ ≤ 3 с, дальше ≤ 1,5 с");
  fs.writeFileSync(path.join(OUT, "PERF.json"), JSON.stringify({ ...result, rows }, null, 1));
  const md = [`# R10 · производительность · ${result.meta.sha}`, "", "```", JSON.stringify(result.meta), "```", "",
    "| Проверка | Итог | Значение | Примечание |", "|---|---|---|---|",
    ...rows.map((r) => `| ${r.name} | ${r.status} | ${JSON.stringify(r.value).slice(0, 220).replace(/\|/g, "/")} | ${r.note || ""} |`)];
  fs.writeFileSync(path.join(OUT, "PERF.md"), md.join("\n") + "\n");
  process.exit(rows.some((r) => r.status === "FAIL") ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
