// R10 · раунд 14 · «карта и сценарий не стали хуже» — сравнение нового прогона с эталоном (POLISH_WAVE_2.md, правило 7).
//
//   node tests/e2e/compare_baseline.cjs --base research/round-14-results/R10/baseline_8e67c65 --new <папка прогона>
//        [--control <папка>]  — свежий прогон 8e67c65 на ЭТОЙ ЖЕ машине: время сравнивается с ним, а вид — с эталоном
//        [--out <папка>]      — куда положить COMPARE.md / COMPARE.json / кадры сравнения (по умолчанию <new>/compare)
//
// Папка прогона: e2e/RESULT.json (demo_flow.cjs) и map/BASELINE.json + map/default-*.png (map_baseline.cjs);
// можно и без подпапок. Итог: FAIL — стало хуже (правило нарушено), СМОТРЕТЬ — изменилось, решает человек по кадру,
// OK — не хуже, ИНФО — для сведения (например, исправленные проверки). Вердикт «не хуже» — когда нет ни одного FAIL.
// Пороги (выбраны по разбросу двух прогонов 8e67c65 на одной машине — см. baseline_8e67c65/README.md):
//   шаг сценария медленнее, если > ×1.25 и > +2 с; вариант целиком — > ×1.15 и > +5 с;
//   загрузка карты — > max(×1.25, +0.5 с); отклик интерфейса — > max(×1.5, +0.7 с); API — > max(×2, +0.3 с) → СМОТРЕТЬ;
//   кадры вида по умолчанию: изменилось > 2 % точек → СМОТРЕТЬ (строгая часть — слои, значки, камера).
// Время сравнивается строго (FAIL) только при одинаковой машине и Chromium; иначе — СМОТРЕТЬ и совет взять --control.
"use strict";
const fs = require("fs"), path = require("path");
const L = require("./r10_lib.cjs");

const args = L.parseArgs(process.argv.slice(2));
if (!args.base || !args.new) { console.error("нужно: --base <эталон> --new <прогон> [--control <прогон 8e67c65 на этой машине>]"); process.exit(2); }
const BASE = path.resolve(String(args.base)), NEW = path.resolve(String(args.new));
const CONTROL = args.control ? path.resolve(String(args.control)) : null;
const OUT = path.resolve(String(args.out || path.join(NEW, "compare")));

const find = (dir, sub, file) => [path.join(dir, sub, file), path.join(dir, file)].find((f) => fs.existsSync(f)) || null;
const readJ = (f) => (f ? JSON.parse(fs.readFileSync(f, "utf8")) : null);
const items = [];
// Одобренные изменения (решения владельца, записанные ролями): <эталон>/ACCEPTED.json — {layers: {id: причина},
// controls: {"зона: имя": причина}}. Такое изменение — «ИНФО: принято», а не FAIL/СМОТРЕТЬ; владелец может вычеркнуть строку.
const ACCEPTED = (() => { try { return JSON.parse(fs.readFileSync(path.join(BASE, "ACCEPTED.json"), "utf8")); } catch { return {}; } })();
const acceptedLayer = (id) => (ACCEPTED.layers || {})[id] || null;
const acceptedControl = (c) => (ACCEPTED.controls || {})[c] || null;
const add = (status, area, what, detail) => items.push({ status, area, what, detail: detail ?? null });

const sameMachine = (a, b) => !!(a && b && a.machine && b.machine && a.machine.cpu === b.machine.cpu && a.machine.cores === b.machine.cores && a.chromium === b.chromium);

// ------------------------------------------------------------------------------------------------ сценарий
function compareScenario(base, now, timeRef) {
  if (!base || !now) { add("СМОТРЕТЬ", "сценарий", "нет RESULT.json сценария", { base: !!base, new: !!now }); return; }
  const key = (r) => `${r.layer} | ${r.step} | ${r.name}`;
  const nb = new Map(now.results.map((r) => [key(r), r]));
  const bb = new Map(base.results.map((r) => [key(r), r]));
  let kept = 0;
  for (const [k, r] of bb) {
    const n = nb.get(k);
    if (!n) add("СМОТРЕТЬ", "сценарий", "проверки нет в новом прогоне (переименована или пропала)", { check: k, was: r.status });
    else if (r.status === "PASS" && n.status !== "PASS") add("FAIL", "сценарий", "было PASS — стало " + n.status, { check: k, detail: n.detail, shot: n.shot });
    else if (r.status !== "PASS" && n.status === "PASS") add("ИНФО", "сценарий", "было " + r.status + " — стало PASS", { check: k });
    else if (r.status === "PASS") kept++;
  }
  const added = [...nb.keys()].filter((k) => !bb.has(k));
  add("OK", "сценарий", `PASS сохранились: ${kept}; итог эталона ${JSON.stringify(base.counts)}, нового ${JSON.stringify(now.counts)}`, added.length ? { new_checks: added.slice(0, 30) } : null);
  for (const k of added) { const n = nb.get(k); if (n.status === "FAIL") add("FAIL", "сценарий", "новая проверка — FAIL", { check: k, detail: n.detail }); }
  // Время шагов: тот же сценарий, то же время (с запасом на разброс).
  const ref = timeRef || base;
  if (!ref.timing || !now.timing) { add("СМОТРЕТЬ", "сценарий · время", "нет времени шагов (прогон старой версией demo_flow.cjs)"); return; }
  for (const [layer, t] of Object.entries(ref.timing)) {
    const n = now.timing[layer];
    if (!n) continue;
    for (const [st, ms] of Object.entries(t.steps)) {
      const m = n.steps[st];
      if (m === undefined) continue;
      const slow = m > ms * 1.25 && m - ms > 2000;
      add(slow ? "FAIL" : "OK", "сценарий · время", `${layer} шаг ${st}: ${(ms / 1000).toFixed(1)} → ${(m / 1000).toFixed(1)} с`, slow ? { ratio: +(m / ms).toFixed(2) } : null);
    }
    const slow = n.total_ms > t.total_ms * 1.15 && n.total_ms - t.total_ms > 5000;
    add(slow ? "FAIL" : "OK", "сценарий · время", `${layer} целиком: ${(t.total_ms / 1000).toFixed(0)} → ${(n.total_ms / 1000).toFixed(0)} с`);
  }
}

// ------------------------------------------------------------------------------------------------ карта
function compareMap(base, now, timeRef) {
  if (!base || !now) { add("СМОТРЕТЬ", "карта", "нет BASELINE.json карты", { base: !!base, new: !!now }); return; }
  const ref = timeRef || base;
  const strict = sameMachine(ref.meta, now.meta);
  const slowStatus = strict ? "FAIL" : "СМОТРЕТЬ";
  if (!strict) add("СМОТРЕТЬ", "карта · время", "другая машина или Chromium — время только для сведения; для строгого сравнения прогоните map_baseline.cjs на 8e67c65 здесь же и передайте --control",
    { ref: ref.meta && ref.meta.machine, now: now.meta && now.meta.machine });
  for (const [tag, b] of Object.entries(base.cases)) {
    const n = now.cases[tag], r = (ref.cases || {})[tag] || b;
    if (!n) { add("СМОТРЕТЬ", "карта", `${tag}: варианта нет в новом прогоне`); continue; }
    if (n.error) { add("FAIL", "карта", `${tag}: прогон варианта прервался`, n.error); continue; }
    // 1. Загрузка.
    for (const k of ["dcl", "map_loaded", "first_badge", "primary_visible", "wall_ms"]) {
      const was = r.median && r.median[k], is = n.median && n.median[k];
      if (typeof was !== "number") continue;
      // У акимата «главное» — заголовок «Горячие места» (не кнопка): не наступило — смотреть кадр, не FAIL.
      if (typeof is !== "number") { add(k === "primary_visible" && /akimat$/.test(tag) ? "СМОТРЕТЬ" : "FAIL", "карта · загрузка", `${tag}: «${k}» не наступило`, { was }); continue; }
      const slow = is > Math.max(was * 1.25, was + 500);
      add(slow ? slowStatus : "OK", "карта · загрузка", `${tag}: ${k} ${(was / 1000).toFixed(2)} → ${(is / 1000).toFixed(2)} с`);
    }
    // Бюджет правила 5: первая отрисовка ≤ 3 с на ноутбуке (в облаке WebGL программный — если и эталон > 3 с, мерить на ноутбуке).
    const w = Number(tag.split("x")[0]);
    if (w >= 1024 && n.median && typeof n.median.first_badge === "number" && n.median.first_badge > 3000)
    {
      const baseOver = !!(r.median && r.median.first_badge > 3000);
      add(baseOver ? "СМОТРЕТЬ" : "FAIL", "карта · бюджет", `${tag}: первый значок через ${(n.median.first_badge / 1000).toFixed(2)} с > 3 с (правило 5)`,
        { baseline_s: r.median && r.median.first_badge / 1000, ...(baseOver ? { note: "эталон тоже > 3 с — среда облака; замер на ноутбуке владельца (Codex М9)" } : {}) });
    }
    const reqMore = n.median.requests > r.median.requests * 1.2 + 5, kbMore = n.median.bytes_kb > r.median.bytes_kb * 1.25 + 200;
    add(reqMore || kbMore ? "СМОТРЕТЬ" : "OK", "карта · загрузка", `${tag}: запросов ${r.median.requests} → ${n.median.requests}, КБ ${r.median.bytes_kb} → ${n.median.bytes_kb}`);
    const newApi = ((n.requests && n.requests.api_paths) || []).filter((p) => !((b.requests && b.requests.api_paths) || []).includes(p));
    if (newApi.length) add("СМОТРЕТЬ", "карта · загрузка", `${tag}: новые запросы API при открытии карты (правило 5: новые слои грузятся, только когда включены)`, newApi);
    // 2. Вид по умолчанию: строгая часть — слои, виды значков, камера.
    const fb = b.fingerprint || {}, fn = n.fingerprint || {};
    const lb = (fb.style && fb.style.layers_visible) || [], ln = (fn.style && fn.style.layers_visible) || [];
    const plus = ln.filter((x) => !lb.includes(x)), minus = lb.filter((x) => !ln.includes(x));
    // Новые слои подложки (источник vector / raster — стиль карты, решение владельца) — «СМОТРЕТЬ»; новые функциональные
    // слои (geojson, image, custom 3D) по умолчанию — FAIL (правило 1). Без сведений об источнике — FAIL (строже).
    const kind = (fn.style && fn.style.layer_kind) || {};
    const basemap = plus.filter((x) => /^(vector|raster|raster-dem|background)$/.test(kind[x] || ""));
    const accepted = plus.filter((x) => !basemap.includes(x) && acceptedLayer(x));
    for (const x of accepted) add("ИНФО", "карта · вид", `${tag}: новый слой ${x} — принято`, acceptedLayer(x));
    const thematic = plus.filter((x) => !basemap.includes(x) && !acceptedLayer(x));
    add(thematic.length ? "FAIL" : "OK", "карта · вид", `${tag}: видимые слои по умолчанию ${lb.length} → ${ln.length}` + (thematic.length ? " — новые функциональные слои видны сразу (правило 1)" : ""),
      thematic.length ? { new: thematic, kinds: thematic.map((x) => kind[x] || "?") } : null);
    if (basemap.length) add("СМОТРЕТЬ", "карта · вид", `${tag}: новые слои подложки (стиль карты) — сверить кадр`, { new: basemap.slice(0, 30), n: basemap.length });
    if (minus.length) add("СМОТРЕТЬ", "карта · вид", `${tag}: слои пропали или переименованы`, minus);
    for (const id of ln.filter((x) => lb.includes(x))) {
      const was = fb.style.rendered[id], is = fn.style.rendered[id];
      if (typeof was === "number" && typeof is === "number" && Math.abs(is - was) > Math.max(5, was * 0.3))
        add("СМОТРЕТЬ", "карта · вид", `${tag}: слой ${id} — нарисовано ${was} → ${is}`);
    }
    const kb = Object.keys(fb.marker_kinds || {}), kn = Object.keys(fn.marker_kinds || {});
    const newKinds = kn.filter((k) => !kb.includes(k));
    add(newKinds.length ? "FAIL" : "OK", "карта · вид", `${tag}: значков на карте ${fb.markers} → ${fn.markers}` + (newKinds.length ? " — новые виды значков по умолчанию (правило 1)" : ""), newKinds.length ? { new_kinds: newKinds, kinds: fn.marker_kinds } : null);
    if (!newKinds.length && Math.abs((fn.markers || 0) - (fb.markers || 0)) > Math.max(3, (fb.markers || 0) * 0.2))
      add("СМОТРЕТЬ", "карта · вид", `${tag}: число значков заметно изменилось`, { was: fb.marker_kinds, now: fn.marker_kinds });
    if (fb.labels3d !== fn.labels3d) add("СМОТРЕТЬ", "карта · вид", `${tag}: 3D-табличек ${fb.labels3d} → ${fn.labels3d}`);
    if (fb.style && fn.style) {
      const moved = Math.abs(fb.style.zoom - fn.style.zoom) > 0.3 || Math.hypot(fb.style.center[0] - fn.style.center[0], fb.style.center[1] - fn.style.center[1]) > 0.01 || fb.style.pitch !== fn.style.pitch;
      add(moved ? "СМОТРЕТЬ" : "OK", "карта · вид", `${tag}: камера по умолчанию z${fb.style.zoom} ${fb.style.center} наклон ${fb.style.pitch} → z${fn.style.zoom} ${fn.style.center} наклон ${fn.style.pitch}`);
    }
    // Кнопки вне карты: новое поверх карты — перегруз (правило 1); меню — правило 2.
    const cname = (c) => `${c.zone}: ${c.name}`;
    const cb = new Set((fb.controls || []).map(cname)), cn = (fn.controls || []).map(cname);
    const newCtl = cn.filter((c) => !cb.has(c)), goneCtl = [...cb].filter((c) => !cn.includes(c));
    const overMap = newCtl.filter((c) => c.startsWith("поверх карты") && !acceptedControl(c));
    for (const c of newCtl.filter((x) => acceptedControl(x))) add("ИНФО", "интерфейс", `${tag}: новая кнопка «${c}» — принято`, acceptedControl(c));
    add(overMap.length ? "СМОТРЕТЬ" : "OK", "интерфейс", `${tag}: кнопок вне карты ${cb.size} → ${cn.length}` + (overMap.length ? " — новые кнопки поверх карты (правило 1)" : ""),
      newCtl.length || goneCtl.length ? { new: newCtl.slice(0, 20), gone: goneCtl.slice(0, 20) } : null);
    if (JSON.stringify(b.menu) !== JSON.stringify(n.menu)) add("СМОТРЕТЬ", "интерфейс", `${tag}: пункты меню изменились (правило 2: житель ≤ 5, акимат ≤ 5)`, { was: b.menu, now: n.menu });
    // Карточка места: правило 3 (не растёт бесконечно — главное сверху, остальное в «Подробнее») и правило 4 (одна главная кнопка).
    const kb_ = b.card, kn_ = n.card;
    if (kb_ && !kn_) add("FAIL", "карточка", `${tag}: карточка «${kb_.title}» не открылась нажатием по значку`);
    else if (kb_ && kn_) {
      add(kn_.primary > 1 ? "FAIL" : "OK", "карточка", `${tag}: главных кнопок ${kb_.primary} → ${kn_.primary} (правило 4: одна)`, kn_.primary > 1 ? kn_.primary_names : null);
      if (kb_.primary_in_view && kn_.primary_in_view === false) add("FAIL", "карточка", `${tag}: главная кнопка карточки больше не видна без прокрутки`, kn_.primary_names);
      const grew = kn_.content_h > kb_.content_h * 1.25 && kn_.content_h - kb_.content_h > 120;
      add(grew ? "СМОТРЕТЬ" : "OK", "карточка", `${tag}: высота содержимого ${kb_.content_h} → ${kn_.content_h} px, кнопок ${kb_.buttons} → ${kn_.buttons}, «Подробнее» ${kb_.details} → ${kn_.details}` + (grew ? " — карточка выросла (правило 3)" : ""));
    }
    // 3. Плавность и отклик.
    for (const k of ["pan", "fly"]) {
      const was = r.smooth && r.smooth[k], is = n.smooth && n.smooth[k];
      if (!was || !is) continue;
      const worse = (is.p95_ms > was.p95_ms * 1.5 && is.p95_ms - was.p95_ms > 20) || is.fps < was.fps * 0.7;
      add(worse ? "СМОТРЕТЬ" : "OK", "карта · плавность", `${tag}: ${k} ${was.fps} → ${is.fps} кадр/с, p95 ${was.p95_ms} → ${is.p95_ms} мс`);
    }
    for (const [k, was] of Object.entries(r.transitions || {})) {
      const is = (n.transitions || {})[k];
      if (typeof was !== "number") continue;
      if (typeof is !== "number") { add("FAIL", "интерфейс · отклик", `${tag}: ${k} — не дождались результата`, { was }); continue; }
      const slow = is > Math.max(was * 1.5, was + 700);
      add(slow ? slowStatus : "OK", "интерфейс · отклик", `${tag}: ${k} ${was} → ${is} мс`);
    }
  }
  for (const [k, was] of Object.entries(ref.api || {})) {
    const is = (now.api || {})[k];
    if (!is) { add("СМОТРЕТЬ", "API", `${k}: нет в новом прогоне`); continue; }
    if (was.status.join() !== is.status.join()) add("FAIL", "API", `${k}: статус ${was.status} → ${is.status}`);
    const slow = is.median_ms > Math.max(was.median_ms * 2, was.median_ms + 300);
    add(slow ? "СМОТРЕТЬ" : "OK", "API", `${k}: медиана ${was.median_ms} → ${is.median_ms} мс, ${was.kb} → ${is.kb} КБ`);
  }
}

// ------------------------------------------------------------------------------------------------ кадры
// Попиксельно в браузере (без лишних пакетов): доля точек, где цвет отличается больше чем на 32 по любому каналу;
// отдельно — верхняя полоса 72 px (шапка) и остальное (карта и панели). Кадр «эталон | новый | разница».
async function compareShots(baseDir, newDir) {
  const { chromium } = require("playwright");
  const shotsB = baseDir ? fs.readdirSync(baseDir).filter((f) => /^default-.*\.png$/.test(f)) : [];
  if (!shotsB.length) { add("СМОТРЕТЬ", "кадры", "в эталоне нет кадров вида по умолчанию"); return; }
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent("<html><body></body></html>");
  try {
    for (const f of shotsB) {
      const nf = newDir && path.join(newDir, f);
      if (!nf || !fs.existsSync(nf)) { add("СМОТРЕТЬ", "кадры", `${f}: нет в новом прогоне`); continue; }
      const a = "data:image/png;base64," + fs.readFileSync(path.join(baseDir, f)).toString("base64");
      const b = "data:image/png;base64," + fs.readFileSync(nf).toString("base64");
      const r = await page.evaluate(async ([a, b]) => {
        const load = (src) => new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = src; });
        const [ia, ib] = await Promise.all([load(a), load(b)]);
        const w = ia.width, h = ia.height;
        if (ib.width !== w || ib.height !== h) return { size: [w, h, ib.width, ib.height] };
        const px = (img) => { const c = document.createElement("canvas"); c.width = w; c.height = h; const x = c.getContext("2d"); x.drawImage(img, 0, 0); return x.getImageData(0, 0, w, h); };
        const da = px(ia), db = px(ib);
        const out = document.createElement("canvas"); out.width = w * 3; out.height = h; const o = out.getContext("2d");
        o.drawImage(ia, 0, 0); o.drawImage(ib, w, 0);
        const diff = o.createImageData(w, h);
        let n = 0, top = 0;
        for (let i = 0; i < da.data.length; i += 4) {
          const d = Math.max(Math.abs(da.data[i] - db.data[i]), Math.abs(da.data[i + 1] - db.data[i + 1]), Math.abs(da.data[i + 2] - db.data[i + 2]));
          const y = (i / 4 / w) | 0;
          if (d > 32) { n++; if (y < 72) top++; diff.data[i] = 220; diff.data[i + 1] = 30; diff.data[i + 2] = 30; diff.data[i + 3] = 255; }
          else { const g = (da.data[i] + da.data[i + 1] + da.data[i + 2]) / 3; diff.data[i] = diff.data[i + 1] = diff.data[i + 2] = 255 - (255 - g) * 0.25; diff.data[i + 3] = 255; }
        }
        o.putImageData(diff, w * 2, 0);
        const half = document.createElement("canvas"); half.width = w * 1.5; half.height = h / 2; half.getContext("2d").drawImage(out, 0, 0, half.width, half.height);
        return { changed: n / (w * h), top: top / (w * Math.min(72, h)), rest: (n - top) / (w * Math.max(1, h - 72)), jpg: half.toDataURL("image/jpeg", 0.7) };
      }, [a, b]);
      if (r.size) { add("СМОТРЕТЬ", "кадры", `${f}: другой размер кадра`, r.size); continue; }
      const name = f.replace(/^default-/, "diff-").replace(/\.png$/, ".jpg");
      fs.writeFileSync(path.join(OUT, name), Buffer.from(r.jpg.split(",")[1], "base64"));
      const pct = (x) => (x * 100).toFixed(1) + " %";
      add(r.changed > 0.02 ? "СМОТРЕТЬ" : "OK", "кадры", `${f}: изменилось ${pct(r.changed)} точек (шапка ${pct(r.top)}, карта и панели ${pct(r.rest)})`, { image: name });
    }
  } finally { await browser.close(); }
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const e2eB = readJ(find(BASE, "e2e", "RESULT.json")), e2eN = readJ(find(NEW, "e2e", "RESULT.json"));
  const e2eC = CONTROL ? readJ(find(CONTROL, "e2e", "RESULT.json")) : null;
  const mapBf = find(BASE, "map", "BASELINE.json"), mapNf = find(NEW, "map", "BASELINE.json");
  const mapB = readJ(mapBf), mapN = readJ(mapNf), mapC = CONTROL ? readJ(find(CONTROL, "map", "BASELINE.json")) : null;
  compareScenario(e2eB, e2eN, e2eC);
  compareMap(mapB, mapN, mapC);
  await compareShots(mapBf && path.dirname(mapBf), mapNf && path.dirname(mapNf));
  const counts = {};
  items.forEach((i) => (counts[i.status] = (counts[i.status] || 0) + 1));
  const verdict = counts.FAIL ? "ХУЖЕ" : "НЕ ХУЖЕ";
  const meta = { base: BASE, new: NEW, control: CONTROL, when: new Date().toISOString(),
    base_sha: (e2eB && e2eB.meta.sha) || (mapB && mapB.meta.sha), new_sha: (e2eN && e2eN.meta.sha) || (mapN && mapN.meta.sha),
    same_machine: sameMachine((mapC || mapB || {}).meta, (mapN || {}).meta) };
  fs.writeFileSync(path.join(OUT, "COMPARE.json"), JSON.stringify({ meta, verdict, counts, items }, null, 1));
  const order = ["FAIL", "СМОТРЕТЬ", "ИНФО", "OK"];
  const md = [`# R10 · сравнение с эталоном · ${meta.base_sha} → ${meta.new_sha}: **${verdict}**`, "", "```", JSON.stringify(meta), "```", "",
    `Итого: ${order.filter((s) => counts[s]).map((s) => `${s} ${counts[s]}`).join(" · ")}`, "",
    "FAIL — правило 7 нарушено (стало хуже); СМОТРЕТЬ — изменилось, решает человек по кадру `diff-*.jpg` (эталон | новый | разница красным).", "",
    "| Итог | Область | Что | Подробно |", "|---|---|---|---|",
    ...order.flatMap((s) => items.filter((i) => i.status === s).map((i) => `| **${i.status}** | ${i.area} | ${i.what} | ${i.detail ? JSON.stringify(i.detail).replace(/\|/g, "/").slice(0, 260) : ""} |`))];
  fs.writeFileSync(path.join(OUT, "COMPARE.md"), md.join("\n") + "\n");
  console.log(verdict, counts, "→", OUT);
  process.exit(counts.FAIL ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
