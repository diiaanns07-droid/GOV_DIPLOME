// R05 · 3D-превью ВНУТРИ оболочки R01 — сборка B2 (claude/sharp-dijkstra-0t87gl @ f54361d) с файлами R05 этой ветки
// и патчем research/round-14-results/R05/proposed_r01_b2.patch (без адаптера build3dFetch, без пересоздания модуля).
//   git worktree add --detach ../r01 f54361d && cd ../r01
//   git apply <эта ветка>/research/round-14-results/R05/proposed_r01_b2.patch
//   cp -r <эта ветка>/web/civic/build3d/. web/civic/build3d/ && cp <эта ветка>/web/vendor/three/* web/vendor/three/
//   export CIVIC_DB_PATH=/tmp/b2.sqlite3 CIVIC_DEMO=1
//   python3 -B -m ui.civic_store --db /tmp/b2.sqlite3 init / seed-demo --package data/civic/astana/demo_synthetic.json /
//     seed-r14-demo / create-editor operator --password-stdin   (пароль — свой, в файл с правами 600)
//   python3 -B app.py --host 127.0.0.1 --port 8801
//   node tests/civic/R05/build3d/app_b2_smoke.mjs http://127.0.0.1:8801/ <файл с паролем сотрудника>
// Модуль монтирует оболочка (shell.js); тест нажимает, как человек. Пароль не печатается и не попадает в отчёт.
// Отчёт: research/round-14-results/R05/runs/app_b2_smoke.json, скриншоты screens/b2_*.png (1366/375 × ru/kk).
// На голове R01 (B3+, каталог свёрнут в кнопку) — патч proposed_r01_b3.patch; R01_LABEL=<сборка> — подпись в отчёте.
import { writeFile, mkdir, readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const OUT = path.join(ROOT, "research/round-14-results/R05");
const URL0 = process.argv[2] || "http://127.0.0.1:8801/";
const PASSWORD = process.argv[3] ? (await readFile(process.argv[3], "utf8")).trim() : null;
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
const NOISE = /openfreemap|Failed to load resource|GL Driver|swiftshader|GPU stall|WebGL|civic-r03-demo-ring/i;
async function open(vp, mode, lang, extra) {
  const ctx = await browser.newContext(Object.assign({ viewport: vp }, extra || {}));
  await ctx.addInitScript(([m, l]) => {
    try {
      localStorage.setItem("birge.mode", m);
      if (l) localStorage.setItem("birge.lang", l);
    } catch (e) {
      /* нет хранилища */
    }
  }, [mode, lang]);
  const p = await ctx.newPage();
  p.on("pageerror", (e) => errors.push(e.message));
  p.on("console", (m) => {
    if (m.type() === "error" && !NOISE.test(m.text())) errors.push("console: " + m.text().slice(0, 200));
  });
  await p.goto(URL0);
  await p.waitForFunction(() => typeof map !== "undefined" && map && map.loaded && map.isStyleLoaded(), null, { timeout: 60000 });
  if (lang) await p.evaluate((l) => window.BirgeI18n && BirgeI18n.setLang(l), lang);
  await p.waitForFunction(() => { const s = window.CivicShell?.build3d?.getState?.(); return s && s.phase === "ready"; }, null, { timeout: 60000 });
  // Камера к проектам — как при открытии 3D-превью (UX_REVIEW день 3, п. 20): крупный план 17.4 у ближайшего к центру.
  await p.evaluate(() => { map.jumpTo({ pitch: 58, bearing: -20 }); CivicShell.build3d.flyToProposals({ duration: 0 }); });
  await p.waitForFunction(() => document.querySelectorAll(".b3d-label").length >= 2, null, { timeout: 60000 });
  await p.waitForTimeout(800);
  return p;
}
// Сборка B3+ R01 сворачивает каталог в кнопку «Что построить?» (.birge-b3d-toggle): раскрыть, если свёрнут.
const openCatalog = async (p) => {
  const closed = await p.evaluate(() => document.getElementById("birge-build3d-root")?.dataset.catalog === "closed");
  if (closed) {
    await p.click(".birge-b3d-toggle");
    await p.waitForSelector('#birge-build3d-root .b3d-dock[data-state="catalog"] .b3d-card', { state: "visible", timeout: 5000 });
  }
  return closed;
};
const settle = (p) =>
  p.waitForFunction(() => !document.getAnimations().some((a) => a.playState === "running" || a.pending), null, { timeout: 5000 }).catch(() => {});
const shot = async (p, name) => {
  await settle(p);
  await p.screenshot({ path: path.join(OUT, "screens", name) });
};
const rect = (p, sel) => p.evaluate((s) => { const n = document.querySelector(s); if (!n || (!n.offsetParent && getComputedStyle(n).position !== "fixed")) return null; const r = n.getBoundingClientRect(); return { left: r.left, top: r.top, right: r.right, bottom: r.bottom, w: r.width, h: r.height }; }, sel);
// Подписи карточек каталога внутри рамки (UX: в 720 px оболочки «Спортплощадка» выходила за рамку).
const labelsFit = (p) => p.evaluate(() => [...document.querySelectorAll(".b3d-card")].filter((c) => {
  const l = c.querySelector(".b3d-card__label") || c, rc = c.getBoundingClientRect(), range = document.createRange();
  range.selectNodeContents(l);
  const rt = range.getBoundingClientRect();
  return rt.left < rc.left || rt.right > rc.right || parseFloat(getComputedStyle(c).fontSize) < 14;
}).map((c) => c.textContent.trim()));
await mkdir(path.join(OUT, "screens"), { recursive: true });
try {
  // 1. Ноутбук, «Акимат», ru: каталог слева от панели «Карта жалоб», подписи в рамке.
  let p = await open({ width: 1366, height: 768 }, "akimat", "ru");
  const folded = await openCatalog(p);
  const labels = await p.$$eval(".b3d-label", (els) => els.map((e) => e.textContent));
  check("shell_mounted_module_with_projects", labels.length >= 2 && labels.every((t) => /2027|Проект/.test(t)), { labels, catalog_folded_by_shell: folded });
  const dockR = await rect(p, "#birge-build3d-root .b3d-dock"), panelR = await rect(p, ".civic-panel");
  check("akimat_catalog_not_under_shell_panel", (await p.$$(".b3d-card")).length === 5 && !overlap(dockR, panelR), { dock: dockR, panel: panelR });
  check("catalog_labels_inside_cards_ru", (await labelsFit(p)).length === 0, await labelsFit(p));
  // 2. Вход сотрудника (клиент оболочки) → «Поставить» сквер → R06 хранит (через BirgeShell.api.v2, без адаптера).
  const login = PASSWORD ? await p.evaluate((pw) => window.CivicShell.api.login("operator", pw).then(() => true, () => false), PASSWORD) : false;
  check("staff_login_through_shell", login === true, login);
  const before = await p.evaluate(() => CivicShell.build3d.getState().count);
  const beforeIds = await p.evaluate(() => CivicShell.build3d.getState().proposals.map((q) => q.id));
  const posts = [];
  p.on("response", (r) => { if (/\/api\/civic\/v2\/proposals$/.test(new URL(r.url()).pathname) && r.request().method() === "POST") posts.push(r.status()); });
  // Свободное место в Нуре (вдали от демо-проектов R06) — там ставим сквер.
  await p.evaluate(() => map.jumpTo({ center: [71.4009, 51.1279], zoom: 17.4, pitch: 58, bearing: -20 }));
  await p.waitForTimeout(600);
  await openCatalog(p);
  await p.click("#birge-build3d-root .b3d-card[data-kind=square]");
  const pt = await p.evaluate(() => { const r = map.getCanvas().getBoundingClientRect(); return [r.left + r.width * 0.42, r.top + r.height * 0.42]; });
  await p.mouse.move(pt[0], pt[1]);
  await p.mouse.click(pt[0], pt[1]);
  await p.click("#birge-build3d-root [data-action=place]");
  await p.waitForFunction((n) => { const s = CivicShell.build3d.getState(); return s.count === n + 1 && s.proposals.every((q) => !/^tmp-/.test(q.id)) && !s.animating; }, before, { timeout: 30000 });
  // Новый проект — тот, которого не было до «Поставить» (в базе стенда могут быть скверы прежних прогонов).
  const placed = await p.evaluate((ids) => CivicShell.build3d.getState().proposals.find((q) => !ids.includes(q.id) && q.kind === "square"), beforeIds);
  check("place_square_stored_by_r06_via_shell_client", !!placed && posts[posts.length - 1] === 201, { posts, id: placed && placed.id, year: placed && placed.year });
  await shot(p, "b2_1366_ru_akimat.png");
  // 3. Карточка: не над панелью оболочки; «Удалить» — у акимата.
  await p.evaluate((id) => CivicShell.build3d.select(id), placed.id);
  await p.waitForSelector("#birge-build3d-root .b3d-dock[data-state=card]");
  await p.waitForTimeout(600);
  const cardR = await rect(p, "#birge-build3d-root .b3d-dock"), panel2 = await rect(p, ".civic-panel");
  check("card_not_over_shell_panel", !overlap(cardR, panel2) && !!(await p.$("#birge-build3d-root [data-action=delete]")), { card: cardR, panel: panel2 });
  // Легенда тепловой карты R07 (внизу слева) не лежит под карточкой проекта (R11 ночь, B3 п. 9; правило в патче R01).
  const legend = await p.evaluate(() => { const l = document.querySelector(".r07-maplegend"); return l ? getComputedStyle(l).visibility : "нет легенды"; });
  check("r07_legend_hidden_while_3d_card_open", legend !== "visible", legend);
  // Камера ставит объект в свободную часть карты: не под карточкой, шапкой, «Территорией», панелью и кнопками карты.
  await p.waitForFunction(() => !map.isMoving(), null, { timeout: 5000 }).catch(() => {});
  await p.waitForTimeout(300);
  const objAt = await p.evaluate((id) => { const g = CivicShell.build3d._project(id, [0, 0, 1]); const c = map.getCanvas().getBoundingClientRect(); return g && { x: c.left + g.x, y: c.top + g.y }; }, placed.id);
  const covers = await p.evaluate((pt) => ["header.topbar", ".civic-explore", "#civic-panel", ".map-tools", "#birge-build3d-root .b3d-dock", "#birge-build3d-root .b3d-toasts"].filter((s) => {
    const n = document.querySelector(s); if (!n) return false; const r = n.getBoundingClientRect(); return pt.x > r.left - 8 && pt.x < r.right + 8 && pt.y > r.top - 8 && pt.y < r.bottom + 8; }), objAt);
  check("selected_object_visible_in_free_part_of_shell_map", !!objAt && covers.length === 0 && objAt.y > 0 && objAt.x > 0, { object: objAt, under: covers });
  await shot(p, "b2_1366_ru_card.png");
  // 4. «Житель» в шапке R01 → модуль сам (birge:mode): каталога нет, подсказка, тоста «Отменить» акимата нет.
  await p.evaluate((id) => CivicShell.build3d.select(null), placed.id);
  await p.click('#birge-header [data-mode="resident"]');
  await p.waitForTimeout(400);
  const res = await p.evaluate(() => ({ cards: document.querySelectorAll("#birge-build3d-root .b3d-card").length, toasts: document.querySelectorAll("#birge-build3d-root .bk-toast").length,
    hint: (document.querySelector("#birge-build3d-root .b3d-dock") || {}).innerText || "", same: !!window.CivicShell.build3d }));
  check("shell_mode_switch_to_resident_without_remount", res.cards === 0 && res.toasts === 0 && /проголосовать/.test(res.hint), res);
  await shot(p, "b2_1366_ru_resident.png");
  // 5. Акимат снова и «Удалить» (POST …/withdraw).
  await p.click('#birge-header [data-mode="akimat"]');
  await p.waitForTimeout(300);
  await p.evaluate((id) => CivicShell.build3d.select(id), placed.id);
  await p.waitForSelector("#birge-build3d-root [data-action=delete]");
  const del = p.waitForResponse((r) => /\/withdraw$/.test(new URL(r.url()).pathname), { timeout: 15000 }).catch(() => null);
  await p.click("#birge-build3d-root [data-action=delete]");
  const delR = await del;
  check("delete_is_withdraw_in_shell", delR && delR.status() === 200, delR && delR.status());
  await p.context().close();

  // 6. Ноутбук, kk, «Акимат»: каталог по-казахски, подписи в рамке.
  p = await open({ width: 1366, height: 768 }, "akimat", "kk");
  await openCatalog(p);
  const kkCards = await p.$$eval("#birge-build3d-root .b3d-card", (els) => els.map((e) => e.innerText.trim()));
  check("kk_catalog_in_shell", kkCards.length === 5 && kkCards.includes("Гүлзар") && (await labelsFit(p)).length === 0, kkCards);
  await shot(p, "b2_1366_kk_akimat.png");
  await p.context().close();

  // 7. Телефон 375, житель, kk: шторка «Карта жалоб» открыта — подсказка её не закрывает (скрыта, правило birge.css
  //    из патча); шторка опущена (выбор района) — подсказка над ней.
  p = await open({ width: 375, height: 812 }, "resident", "kk", { hasTouch: true, isMobile: true });
  const halfHint = await rect(p, "#birge-build3d-root .b3d-dock"), halfSheet = await rect(p, ".civic-panel");
  check("phone_kk_resident_hint_does_not_cover_open_sheet", !overlap(halfHint, halfSheet), { hint: halfHint, sheet: halfSheet });
  await p.evaluate(() => { const sel = document.querySelector(".civic-explore select"); const opt = [...sel.options].find((o) => o.value); sel.value = opt.value; sel.dispatchEvent(new Event("change", { bubbles: true })); });
  await p.waitForTimeout(1200);
  await p.evaluate(() => { map.jumpTo({ pitch: 55, bearing: -20 }); CivicShell.build3d.flyToProposals({ duration: 0 }); });
  await p.waitForTimeout(800);
  const hintR = await rect(p, "#birge-build3d-root .b3d-dock"), sheetR = await rect(p, ".civic-panel");
  const hintText = await p.$eval("#birge-build3d-root .b3d-dock", (d) => d.innerText).catch(() => "");
  check("phone_kk_resident_hint_above_lowered_sheet", hintR && !overlap(hintR, sheetR) && hintR.right <= 375 && /жобаны басыңыз/.test(hintText), { hint: hintR, sheet: sheetR, text: hintText.trim() });
  await shot(p, "b2_375_kk_resident.png");
  await p.context().close();

  // 8. Телефон 375, акимат, ru: шторка опущена (выбор района) → каталог над ней, в пределах экрана.
  p = await open({ width: 375, height: 812 }, "akimat", "ru", { hasTouch: true, isMobile: true });
  if (await p.$(".birge-b3d-toggle")) await p.tap(".birge-b3d-toggle"); // B3+: кнопка сама опускает шторку (R10 B-022)
  else await p.evaluate(() => { const sel = document.querySelector(".civic-explore select"); const opt = [...sel.options].find((o) => o.value); sel.value = opt.value; sel.dispatchEvent(new Event("change", { bubbles: true })); });
  await p.waitForTimeout(1200);
  await p.evaluate(() => { map.jumpTo({ pitch: 55, bearing: -20 }); CivicShell.build3d.flyToProposals({ duration: 0 }); });
  await p.waitForTimeout(800);
  const ph = await p.evaluate(() => { const d = document.querySelector("#birge-build3d-root .b3d-dock"), s = document.querySelector(".civic-panel"); const r = d.getBoundingClientRect(), q = s.getBoundingClientRect();
    return { sheet: s.dataset.sheet, state: d.dataset.state, shown: getComputedStyle(d).display !== "none", left: Math.round(r.left), right: Math.round(r.right), bottom: Math.round(r.bottom), sheetTop: Math.round(q.top), scrollX: document.documentElement.scrollWidth > innerWidth }; });
  check("phone_ru_akimat_catalog_above_peek_sheet", ph.sheet === "peek" && ph.shown && ph.left >= 0 && ph.right <= 375 && ph.bottom <= ph.sheetTop + 1 && !ph.scrollX, ph);
  await shot(p, "b2_375_ru_akimat.png");
  await p.context().close();

  // 9. R01 I-05: перезагрузка, пока запрос списка проектов в полёте, — в консоли нет «[build3d] … Failed to fetch».
  const reloads = {};
  for (const [vp, lang, extra] of [[{ width: 1366, height: 768 }, "ru", {}], [{ width: 375, height: 812 }, "kk", { hasTouch: true, isMobile: true }]]) {
    const ctx = await browser.newContext(Object.assign({ viewport: vp }, extra));
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); } catch (e) { /* нет хранилища */ } }, lang);
    const q = await ctx.newPage();
    const own = [];
    q.on("console", (m) => { if (m.type() === "error" && /build3d|Failed to fetch/.test(m.text())) own.push(m.text().slice(0, 200)); });
    let hold = true, held = 0;
    await q.route(/\/api\/civic\/v2\/proposals(\?|$)/, (route) => {
      if (hold && route.request().method() === "GET") { held++; return; } // не отвечаем: запрос висит до перезагрузки
      return route.continue();
    });
    await q.goto(URL0);
    for (let i = 0; i < 600 && !held; i++) await q.waitForTimeout(100);
    const heldBefore = held;
    hold = false;
    await q.reload();
    await q.waitForFunction(() => { const s = window.CivicShell?.build3d?.getState?.(); return s && s.phase === "ready"; }, null, { timeout: 60000 });
    await q.waitForTimeout(800);
    const count = await q.evaluate(() => CivicShell.build3d.getState().count);
    reloads[vp.width + "_" + lang] = { heldBefore, count, console_errors: own };
    await ctx.close();
  }
  check("shell_reload_during_list_request_no_console_error", Object.values(reloads).every((r) => r.heldBefore >= 1 && r.count >= 1 && r.console_errors.length === 0), reloads);

  // 10. Ночь 9: телефон, акимат, шторка «half» — нажать проект над шторкой. Карточка не закрывает шапку оболочки (R05
  // fitDock); с proposed_r01_final2.patch оболочка опускает шторку — карточка целиком и объект над ней виден.
  const halfCards = {};
  for (const lang of ["kk", "ru"]) {
    const ctx = await browser.newContext({ viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true });
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); } catch (e) { /* нет хранилища */ } }, lang);
    const q = await ctx.newPage();
    q.on("pageerror", (e) => errors.push(e.message));
    await q.goto(URL0);
    await q.waitForFunction(() => window.CivicShell?.build3d?.getState?.().phase === "ready", null, { timeout: 60000 });
    const ll = await q.evaluate(() => CivicShell.build3d.getState().proposals.find((x) => x.kind !== "lighting").geometry.coordinates);
    await q.evaluate((c) => map.jumpTo({ center: c, zoom: 17.4, pitch: 50, bearing: -20 }), ll);
    await q.waitForTimeout(500);
    await q.evaluate((c) => { const s = map.project(c); map.panBy([s.x - map.getCanvas().clientWidth / 2, s.y - 230], { duration: 0 }); }, ll);
    await q.waitForTimeout(1200);
    const sheet0 = await q.evaluate(() => document.querySelector(".civic-panel").dataset.sheet);
    const lab = await q.evaluate(() => { for (const b of document.querySelectorAll(".b3d-label")) { if (b.style.visibility === "hidden") continue; const r = b.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, t = document.elementFromPoint(x, y); if (t && b.contains(t) && y < 420) return [Math.round(x), Math.round(y)]; } return null; });
    if (lab) {
      await q.touchscreen.tap(lab[0], lab[1]);
      await q.waitForTimeout(1500);
    }
    const m = await q.evaluate(() => {
      const st = CivicShell.build3d.getState(), d = document.querySelector("#birge-build3d-root .b3d-dock"), dr = d.getBoundingClientRect(), h = document.querySelector("header.topbar").getBoundingClientRect();
      const o = st.selected ? CivicShell.build3d._project(st.selected) : null, top = document.elementFromPoint(h.left + 40, h.bottom - 6);
      return { state: d.dataset.state, sheet: document.querySelector(".civic-panel").dataset.sheet, dock: [Math.round(dr.top), Math.round(dr.bottom)], header_bottom: Math.round(h.bottom),
        header_free: !!(top && top.closest("header.topbar")), object: o ? [Math.round(o.x), Math.round(o.y)] : null, object_above_card: !!o && o.y > h.bottom && o.y < dr.top };
    });
    await shot(q, `phone_akimat_half_card_375_${lang}.png`);
    halfCards[lang] = Object.assign({ sheet_before: sheet0, tapped: lab }, m);
    await ctx.close();
  }
  // 11. R10 B-039: ноутбук, житель — подсказка «Нажмите на проект…» не лежит на легенде R07 (с патчем 2 легенда в avoid).
  const hints = {};
  for (const [vp, lang] of [[{ width: 1366, height: 768 }, "ru"], [{ width: 1366, height: 768 }, "kk"], [{ width: 1100, height: 700 }, "kk"]]) {
    const ctx = await browser.newContext({ viewport: vp });
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l); } catch (e) { /* нет хранилища */ } }, lang);
    const q = await ctx.newPage();
    q.on("pageerror", (e) => errors.push(e.message));
    await q.goto(URL0);
    await q.waitForFunction(() => window.CivicShell?.build3d?.getState?.().phase === "ready", null, { timeout: 60000 });
    await q.waitForFunction(() => document.querySelector(".r07-maplegend"), null, { timeout: 30000 }).catch(() => {});
    await q.waitForTimeout(2500);
    const m = await q.evaluate(() => {
      const R = (n) => { if (!n || getComputedStyle(n).visibility === "hidden") return null; const r = n.getBoundingClientRect(); return r.width ? { l: Math.round(r.left), t: Math.round(r.top), r: Math.round(r.right), b: Math.round(r.bottom) } : null; };
      const d = document.querySelector("#birge-build3d-root .b3d-dock"), hint = R(d), lg = R(document.querySelector(".r07-maplegend")), fab = R(document.querySelector(".bc-fab"));
      const ov = (a, b) => !!(a && b && a.l < b.r && a.r > b.l && a.t < b.b && a.b > b.t);
      return { state: d && d.dataset.state, hint, legend: lg, over_legend: ov(hint, lg), over_fab: ov(hint, fab) };
    });
    await shot(q, `hint_legend_shell_${vp.width}_${lang}.png`);
    hints[vp.width + "_" + lang] = m;
    await ctx.close();
  }
  check("resident_hint_not_over_r07_legend_1366_1100", Object.values(hints).every((r) => r.state === "hint" && r.hint && r.legend && !r.over_legend && !r.over_fab), hints);

  check("phone_akimat_card_with_half_sheet_does_not_cover_shell_header",
    Object.values(halfCards).every((r) => r.tapped && r.state === "card" && r.header_free && r.dock[0] >= r.header_bottom && (r.sheet !== "peek" || r.object_above_card)), halfCards);
} catch (e) {
  check("run", false, e.message.split("\n")[0]);
}
check("no_page_errors", errors.length === 0, errors.slice(0, 3));
await browser.close();
await mkdir(path.join(OUT, "runs"), { recursive: true });
await writeFile(path.join(OUT, "runs", "app_b2_smoke.json"), JSON.stringify({ generated_at: new Date().toISOString(), url: URL0,
  r01: process.env.R01_LABEL || "claude/sharp-dijkstra-0t87gl@f54361d + proposed_r01_b2.patch", checks: results }, null, 1) + "\n");
process.exit(results.every((r) => r.status === "PASS") ? 0 : 1);
