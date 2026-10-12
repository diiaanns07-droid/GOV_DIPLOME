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
// Оболочка R01 волны 2 (8bbace7+): проекты R05 — слой «Проекты», по умолчанию выключен. Включаем его, как человек в
// «Слоях» (BirgeShell.setLayer). У старых сборок без слоёв — ничего не делаем.
const PROJECTS_ON = () => {
  const tick = setInterval(() => {
    try {
      if (window.BirgeShell && typeof BirgeShell.setLayer === "function") {
        if (BirgeShell.layer !== "projects") BirgeShell.setLayer("projects");
        if (BirgeShell.layer === "projects") clearInterval(tick);
      }
    } catch (e) {
      /* оболочка ещё грузится */
    }
  }, 200);
  setTimeout(() => clearInterval(tick), 30000);
};
async function open(vp, mode, lang, extra) {
  const ctx = await browser.newContext(Object.assign({ viewport: vp }, extra || {}));
  await ctx.addInitScript(PROJECTS_ON);
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
// «Акимат / Житель»: в чистом дизайне FINAL-3 (R11 CLEAN_PASS №4) — в меню аватара, раньше — кнопками в шапке.
async function switchMode(p, mode) {
  if (await p.$("#birge-header .birge-avatar")) {
    await p.click("#birge-header .birge-avatar");
    await p.click(`#birge-account [data-mode=${mode}]`);
  } else await p.click(`#birge-header [data-mode="${mode}"]`);
}
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
  // Дизайн-марафон (R11 INTEGRATION 11.3): с proposed_r01_marathon.patch «Закрыть» — «×» в листе каталога, кнопка
  // оболочки под листом спрятана; «×» сворачивает каталог и возвращает фокус на «Что построить?». Без патча — как было.
  const xr = await p.evaluate(() => {
    const vis = (e) => !!e && getComputedStyle(e).display !== "none" && e.getClientRects().length > 0;
    const x = document.querySelector("#birge-build3d-root .b3d-head__close"), t = document.querySelector(".birge-b3d-toggle");
    return { x: vis(x), toggle: vis(t), toggleText: t ? t.textContent.trim() : null, xSize: x ? Math.round(x.getBoundingClientRect().height) : null };
  });
  if (xr.x) {
    await p.click("#birge-build3d-root .b3d-head__close");
    await p.waitForTimeout(300);
    Object.assign(xr, await p.evaluate(() => ({
      after: document.getElementById("birge-build3d-root")?.dataset.catalog,
      focus: document.activeElement?.classList.contains("birge-b3d-toggle") || false,
      toggleAfter: document.querySelector(".birge-b3d-toggle")?.textContent.trim(),
    })));
    await openCatalog(p);
  }
  check("catalog_close_x_inside_sheet (proposed_r01_marathon.patch)", xr.x ? !xr.toggle && xr.xSize >= 44 && xr.after === "closed" && xr.focus : xr.toggle, xr);
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
  await switchMode(p, "resident");
  await p.waitForTimeout(400);
  const res = await p.evaluate(() => ({ cards: document.querySelectorAll("#birge-build3d-root .b3d-card").length, toasts: document.querySelectorAll("#birge-build3d-root .bk-toast").length,
    hint: (document.querySelector("#birge-build3d-root .b3d-dock") || {}).innerText || "", same: !!window.CivicShell.build3d }));
  check("shell_mode_switch_to_resident_without_remount", res.cards === 0 && res.toasts === 0 && /проголосовать/.test(res.hint), res);
  await shot(p, "b2_1366_ru_resident.png");
  // 5. Акимат снова и «Удалить» (POST …/withdraw).
  await switchMode(p, "akimat");
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
    await ctx.addInitScript(PROJECTS_ON);
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
    await ctx.addInitScript(PROJECTS_ON);
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); } catch (e) { /* нет хранилища */ } }, lang);
    const q = await ctx.newPage();
    q.on("pageerror", (e) => errors.push(e.message));
    await q.goto(URL0);
    await q.waitForFunction(() => window.CivicShell?.build3d?.getState?.().phase === "ready", null, { timeout: 60000 });
    const target = await q.evaluate(() => { const x = CivicShell.build3d.getState().proposals.find((y) => y.kind !== "lighting"); return { id: x.id, ll: x.geometry.coordinates }; });
    const ll = target.ll;
    await q.evaluate((c) => map.jumpTo({ center: c, zoom: 17.4, pitch: 50, bearing: -20 }), ll);
    await q.waitForTimeout(500);
    let sheet0 = null, lab = null;
    // Объект на 230 px от верха; если его подпись закрыта (в облаке без тайлов — плашка #map-status оболочки «Карта улиц
    // не загрузилась»), пробуем чуть ниже: проверка — про карточку и шапку, а не про плашку.
    for (const yy of [230, 290, 340]) {
      await q.evaluate(([c, y]) => { const s = map.project(c); map.panBy([s.x - map.getCanvas().clientWidth / 2, s.y - y], { duration: 0 }); }, [ll, yy]);
      // Карта наклонена — объёмный вид включается, когда догрузится three.js (данные слоя «Проекты» грузятся при его
      // включении): тогда метка встаёт над моделью. Место метки берём после этого, а не до.
      await q.waitForFunction(() => { const s = CivicShell.build3d.getState(); return s.view !== "3d" || s.three === "ready" || s.three === "error"; }, null, { timeout: 30000 }).catch(() => {});
      await q.waitForTimeout(1200);
      sheet0 = await q.evaluate(() => document.querySelector(".civic-panel").dataset.sheet);
      // Нажимаем подпись именно этого проекта (раньше — первую видимую: попадалось освещение, у которого «точка
      // объекта» _project — начало участка, а не подпись).
      lab = await q.evaluate((id) => { const b = document.querySelector(`.b3d-label[data-id="${id}"]`); if (!b || b.style.visibility === "hidden") return null; const r = b.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, t = document.elementFromPoint(x, y); return t && b.contains(t) && y < 420 ? [Math.round(x), Math.round(y)] : null; }, target.id);
      if (lab) break;
    }
    if (lab) {
      await q.touchscreen.tap(lab[0], lab[1]);
      await q.waitForTimeout(1500);
    }
    const m = await q.evaluate(() => {
      const st = CivicShell.build3d.getState(), d = document.querySelector("#birge-build3d-root .b3d-dock"), dr = d.getBoundingClientRect(), h = document.querySelector("header.topbar").getBoundingClientRect();
      const o = st.selected ? CivicShell.build3d._project(st.selected) : null, top = document.elementFromPoint(h.left + 40, h.bottom - 6);
      const sl = st.selected && document.querySelector(`.b3d-label[data-id="${st.selected}"]`), lr = sl && sl.getBoundingClientRect();
      const lc = lr && document.elementFromPoint((lr.left + lr.right) / 2, (lr.top + lr.bottom) / 2);
      return { state: d.dataset.state, sheet: document.querySelector(".civic-panel").dataset.sheet, dock: [Math.round(dr.top), Math.round(dr.bottom)], header_bottom: Math.round(h.bottom),
        header_free: !!(top && top.closest("header.topbar")), object: o ? [Math.round(o.x), Math.round(o.y)] : null, object_above_card: !!o && o.y > h.bottom && o.y < dr.top,
        label: lr ? [Math.round(lr.top), Math.round(lr.bottom)] : null, label_above_card: !!(lr && lc && lc.closest(".b3d-label") && lr.top >= h.bottom && lr.bottom <= dr.top) };
    });
    await shot(q, `phone_akimat_half_card_375_${lang}.png`);
    halfCards[lang] = Object.assign({ sheet_before: sheet0, tapped: lab }, m);
    await ctx.close();
  }
  // 11. R10 B-039: ноутбук, житель — подсказка «Нажмите на проект…» не лежит на легенде R07 (с патчем 2 легенда в avoid).
  const hints = {};
  for (const [vp, lang] of [[{ width: 1366, height: 768 }, "ru"], [{ width: 1366, height: 768 }, "kk"], [{ width: 1100, height: 700 }, "kk"]]) {
    const ctx = await browser.newContext({ viewport: vp });
    await ctx.addInitScript(PROJECTS_ON);
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l); } catch (e) { /* нет хранилища */ } }, lang);
    const q = await ctx.newPage();
    q.on("pageerror", (e) => errors.push(e.message));
    await q.goto(URL0);
    await q.waitForFunction(() => window.CivicShell?.build3d?.getState?.().phase === "ready", null, { timeout: 60000 });
    await q.waitForFunction(() => document.querySelector(".r07-maplegend"), null, { timeout: 30000 }).catch(() => {});
    await q.waitForTimeout(2500);
    const m = await q.evaluate(() => {
      const R = (n) => { if (!n || getComputedStyle(n).visibility === "hidden") return null; const r = n.getBoundingClientRect(); return r.width ? { l: Math.round(r.left), t: Math.round(r.top), r: Math.round(r.right), b: Math.round(r.bottom) } : null; };
      // Легенда: R07 .r07-maplegend; в чистом дизайне FINAL-3 видна строка #birge-legend (а .r07-maplegend — 0 × 0).
      const d = document.querySelector("#birge-build3d-root .b3d-dock"), hint = R(d), lg = R(document.querySelector(".r07-maplegend")) || R(document.getElementById("birge-legend")), fab = R(document.querySelector(".bc-fab"));
      const ov = (a, b) => !!(a && b && a.l < b.r && a.r > b.l && a.t < b.b && a.b > b.t);
      return { state: d && d.dataset.state, hint, legend: lg, over_legend: ov(hint, lg), over_fab: ov(hint, fab) };
    });
    await shot(q, `hint_legend_shell_${vp.width}_${lang}.png`);
    hints[vp.width + "_" + lang] = m;
    await ctx.close();
  }
  check("resident_hint_not_over_r07_legend_1366_1100", Object.values(hints).every((r) => r.state === "hint" && r.hint && r.legend && !r.over_legend && !r.over_fab), hints);

  // 12. POLISH_WAVE_2 «Лёгкая карточка раньше 3D; 3D — по кнопке»: житель, плоская карта оболочки — three.js не грузится,
  // карточка проекта лёгкая; «Посмотреть в 3D» — объёмный вид и наклон; кнопка «3D» оболочки ещё раз — снова лёгкий вид.
  const light = {};
  for (const [vp, lang, extra] of [[{ width: 1366, height: 768 }, "ru", {}], [{ width: 1366, height: 768 }, "kk", {}],
    [{ width: 375, height: 812 }, "ru", { hasTouch: true, isMobile: true }], [{ width: 375, height: 812 }, "kk", { hasTouch: true, isMobile: true }]]) {
    const ctx = await browser.newContext(Object.assign({ viewport: vp }, extra));
    await ctx.addInitScript(PROJECTS_ON);
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l); } catch (e) { /* нет хранилища */ } }, lang);
    const q = await ctx.newPage();
    q.on("pageerror", (e) => errors.push(e.message));
    const threeReq = [];
    q.on("request", (r) => { if (/three\.module/.test(r.url())) threeReq.push(r.url()); });
    await q.goto(URL0);
    await q.waitForFunction(() => window.CivicShell?.build3d?.getState?.().phase === "ready", null, { timeout: 60000 });
    await q.waitForTimeout(1500);
    const s0 = await q.evaluate(() => { const s = CivicShell.build3d.getState(); return { view: s.view, three: s.three, pitch: Math.round(map.getPitch()) }; });
    const req0 = threeReq.length;
    // 14,5 — ниже автонаклона оболочки R01 (52° с 15-го масштаба): плоская карта, лёгкий вид. Берём проект, чья табличка
    // на этом масштабе не закрыта соседней (у демо R06 рядом несколько проектов — ближе они расходятся, как на любой карте).
    let target = null;
    for (const cand of await q.evaluate(() => CivicShell.build3d.getState().proposals.filter((x) => x.kind !== "lighting"))) {
      await q.evaluate((c) => map.jumpTo({ center: c, zoom: 14.5, pitch: 0, bearing: 0 }), cand.geometry.coordinates);
      await q.waitForTimeout(900);
      const free = await q.evaluate((id) => { const b = document.querySelector(`.b3d-label[data-id="${id}"]`); if (!b || b.style.visibility === "hidden") return false;
        const r = b.getBoundingClientRect(), t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!t && b.contains(t); }, cand.id);
      if (free) { target = cand; break; }
    }
    const lab = await q.$(`.b3d-label[data-id="${target.id}"]`);
    if (extra.hasTouch) await lab.tap();
    else await lab.click();
    await q.waitForSelector("#birge-build3d-root .b3d-dock[data-state=card] [data-action=view3d]", { timeout: 10000 });
    const btn = await q.getAttribute("#birge-build3d-root [data-action=view3d]", "aria-label"); // видно «3D», имя — полное
    await shot(q, `light_shell_card_${vp.width}_${lang}.png`);
    await q.click("#birge-build3d-root [data-action=view3d]");
    await q.waitForFunction(() => { const s = CivicShell.build3d.getState(); return s.view === "3d" && s.three === "ready" && !map.isMoving(); }, null, { timeout: 30000 });
    await q.waitForTimeout(800);
    const s1 = await q.evaluate(() => { const s = CivicShell.build3d.getState(); return { view: s.view, pitch: Math.round(map.getPitch()), geometries: s.memory && s.memory.geometries, selected: s.selected }; });
    await shot(q, `light_shell_3d_${vp.width}_${lang}.png`);
    // Кнопка «3D» оболочки (карта ровно в её наклоне) — ещё раз: плоская карта, лёгкий вид.
    const tool = await q.$("#toggle-3d");
    let s2 = null;
    if (tool && (await tool.isVisible())) {
      await tool.click();
      await q.waitForFunction(() => CivicShell.build3d.getState().view === "light" && !map.isMoving(), null, { timeout: 10000 }).catch(() => {});
      s2 = await q.evaluate(() => ({ view: CivicShell.build3d.getState().view, pitch: Math.round(map.getPitch()) }));
    }
    light[vp.width + "_" + lang] = { start: s0, three_requests_before: req0, button: btn, after: s1, after_shell_3d_button: s2 };
    await ctx.close();
  }
  check("light_card_first_3d_by_button_in_shell", Object.entries(light).every(([k, r]) => r.start.view === "light" && r.start.three === "idle" && r.three_requests_before === 0 &&
    r.button === (k.endsWith("_kk") ? "3D көріністе қарау" : "Посмотреть в 3D") && r.after.view === "3d" && r.after.pitch >= 30 && r.after.geometries > 0 && !!r.after.selected &&
    (!r.after_shell_3d_button || r.after_shell_3d_button.view === "light")), light);

  // 13. Волна 2, защита от перегруза п. 5 и п. 7 (идеи): слой «Проекты» выключен (по умолчанию) — R05 не грузит ни
  // three.js, ни свои данные (улицы, районы, список проектов). Мастер идеи R06 зовёт pickObject() — каталог эскиза
  // виден и при выключенном слое (нужен proposed_r01_final3.patch (в нём и wave2): оболочка прячет корень R05 вместе со слоем), «Готово»
  // отдаёт эскиз, после — корень снова скрыт. Включили слой — только тогда проекты грузятся и видны.
  const lazy = {};
  for (const [vp, lang, extra] of [[{ width: 1366, height: 768 }, "ru", {}], [{ width: 375, height: 812 }, "kk", { hasTouch: true, isMobile: true }]]) {
    const ctx = await browser.newContext(Object.assign({ viewport: vp }, extra));
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l); } catch (e) { /* нет хранилища */ } }, lang);
    const q = await ctx.newPage();
    q.on("pageerror", (e) => errors.push(e.message));
    const threeReq = [], dataReq = [];
    q.on("request", (r) => {
      if (/three\.module/.test(r.url())) threeReq.push(r.url());
      if (/civic\/build3d\/data\/(nura-streets|astana-districts|proposals\.fixture)\.json/.test(r.url())) dataReq.push(r.url().replace(/^.*\//, ""));
    });
    await q.goto(URL0);
    await q.waitForFunction(() => typeof map !== "undefined" && map && map.loaded() && window.CivicShell?.build3d?.getState, null, { timeout: 60000 });
    await q.waitForTimeout(2500);
    const off = await q.evaluate(() => { const s = CivicShell.build3d.getState(), r = document.getElementById("birge-build3d-root");
      return { layer: window.BirgeShell && BirgeShell.layer, phase: s.phase, three: s.three, root: r ? getComputedStyle(r).display : "absent",
        labels: [...document.querySelectorAll(".b3d-label")].filter((b) => getComputedStyle(b).display !== "none").length }; });
    off.data_requests = dataReq.slice();
    off.three_requests = threeReq.length;
    await q.evaluate(() => { map.jumpTo({ center: [71.4006, 51.1283], zoom: 17.4, pitch: 0, bearing: 0 }); window.__pick = null;
      CivicShell.build3d.pickObject().then((r) => { window.__pick = { done: true, value: r }; }); });
    const shown = await q.waitForSelector("#birge-build3d-root .b3d-dock[data-state=pick] .b3d-card", { state: "visible", timeout: 20000 }).then(() => true, () => false);
    const pick = { catalog_visible: shown };
    if (shown) {
      await shot(q, `shell_idea_pick_catalog_${vp.width}_${lang}.png`);
      const card = await q.$('#birge-build3d-root .b3d-card[data-kind="sports"]');
      if (extra.hasTouch) await card.tap(); else await card.click();
      await q.waitForFunction(() => { const s = CivicShell.build3d.getState(); return s.mode === "placing" && !!s.ghost && s.three === "ready"; }, null, { timeout: 30000 });
      await q.waitForFunction(() => !map.isMoving(), null, { timeout: 10000 }).catch(() => {});
      const at = await q.evaluate(() => { const pt = map.project([71.4003, 51.1286]); return [pt.x, pt.y]; });
      if (extra.hasTouch) await q.touchscreen.tap(at[0], at[1]);
      else { await q.mouse.move(at[0], at[1]); await q.mouse.click(at[0], at[1]); }
      await q.waitForTimeout(600);
      pick.done_button = (await q.textContent("#birge-build3d-root [data-action=place]")).trim();
      pick.toggle_hidden = await q.evaluate(() => { const t = document.querySelector(".birge-b3d-toggle"); return !t || getComputedStyle(t).display === "none"; });
      await shot(q, `shell_idea_pick_placing_${vp.width}_${lang}.png`);
      await q.click("#birge-build3d-root [data-action=place]");
      await q.waitForFunction(() => window.__pick && window.__pick.done, null, { timeout: 10000 });
      pick.result = await q.evaluate(() => window.__pick.value && window.__pick.value.kind);
      await q.waitForTimeout(400);
      pick.root_after = await q.evaluate(() => getComputedStyle(document.getElementById("birge-build3d-root")).display);
    } else {
      await q.evaluate(() => CivicShell.build3d.cancel());
      await shot(q, `shell_idea_pick_hidden_${vp.width}_${lang}.png`);
    }
    // Слой «Проекты» включили — данные и проекты появляются.
    await q.evaluate(() => BirgeShell.setLayer("projects"));
    await q.waitForFunction(() => { const s = CivicShell.build3d.getState(); return s.phase === "ready" && s.count > 0; }, null, { timeout: 60000 }).catch(() => {});
    await q.evaluate(() => CivicShell.build3d.flyToProposals({ duration: 0 }));
    await q.waitForTimeout(1200);
    const on = await q.evaluate(() => { const s = CivicShell.build3d.getState();
      return { phase: s.phase, count: s.count, labels: [...document.querySelectorAll(".b3d-label")].filter((b) => getComputedStyle(b).display !== "none").length }; });
    on.data_requests = dataReq.slice();
    lazy[vp.width + "_" + lang] = { off, pick, on };
    await ctx.close();
  }
  check("projects_layer_off_r05_loads_nothing_then_loads_when_on", Object.values(lazy).every((r) => r.off.layer !== "projects" && r.off.phase === "idle" && r.off.three === "idle" &&
    r.off.data_requests.length === 0 && r.off.three_requests === 0 && r.off.root === "none" && r.off.labels === 0 && r.on.phase === "ready" && r.on.count > 0 && r.on.labels > 0 &&
    r.on.data_requests.length >= 3), lazy);
  check("idea_pick_visible_with_projects_layer_off (proposed_r01_final3.patch)", Object.entries(lazy).every(([k, r]) => r.pick.catalog_visible &&
    r.pick.done_button === (k.endsWith("_kk") ? "Дайын" : "Готово") && r.pick.toggle_hidden && r.pick.result === "sports" && r.pick.root_after === "none"), Object.fromEntries(Object.entries(lazy).map(([k, r]) => [k, r.pick])));

  // 14. R10 B-041: телефон, акимат, шаг 5 сценария — «Не салайық?» → «Гүлзар» → нажать на карту → ↺ ↻ → «Орнату».
  // Пока ставим, призрак виден (не под панелью и шторкой; ↺ ↻ — значками в строке названия). После «Поставить»
  // место проекта — карта, сообщение «Проект поставлен · Отменить» внизу поверх шторки, не на проекте и не на «3D»;
  // когда объект построился — его табличка «Проект · 2027» видна.
  const b041 = {};
  let vi = 0;
  for (const [vp, lang] of [[{ width: 375, height: 667 }, "kk"], [{ width: 375, height: 812 }, "ru"], [{ width: 360, height: 800 }, "ru"]]) {
    const PLACE = [71.4148, 51.1131 + 0.0012 * vi++]; // как R10 demo_flow
    const ctx = await browser.newContext({ viewport: vp, hasTouch: true, isMobile: true });
    await ctx.addInitScript(PROJECTS_ON);
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); } catch (e) { /* нет хранилища */ } }, lang);
    const q = await ctx.newPage();
    q.on("pageerror", (e) => errors.push(e.message));
    await q.goto(URL0);
    await q.waitForFunction(() => window.CivicShell?.build3d?.getState?.().phase === "ready", null, { timeout: 60000 });
    const ok = PASSWORD ? await q.evaluate((pw) => CivicShell.api.login("operator", pw).then(() => true, () => false), PASSWORD) : false;
    const ids0 = await q.evaluate(() => CivicShell.build3d.getState().proposals.map((x) => x.id));
    await q.evaluate((c) => map.jumpTo({ center: c, zoom: 17, pitch: 0, bearing: 0 }), PLACE);
    await q.waitForTimeout(2500); // автонаклон оболочки (52° с 15-го масштаба)
    await q.tap(".birge-b3d-toggle");
    await q.waitForSelector('#birge-build3d-root .b3d-dock[data-state="catalog"] .b3d-card', { state: "visible", timeout: 10000 });
    await q.tap('#birge-build3d-root .b3d-card[data-kind="square"]');
    await q.waitForFunction(() => { const s = CivicShell.build3d.getState(); return s.mode === "placing" && s.three === "ready" && !!s.ghost; }, null, { timeout: 30000 });
    await q.waitForFunction(() => !map.isMoving(), null, { timeout: 10000 }).catch(() => {});
    await q.waitForTimeout(500);
    const placing = await q.evaluate(() => { const s = CivicShell.build3d.getState(), g = map.project(s.ghost.pos), e = document.elementFromPoint(g.x, g.y);
      const rot = document.querySelector('#birge-build3d-root .b3d-head [data-action="rotate-right"]');
      return { ghost: [Math.round(g.x), Math.round(g.y)], ghost_on_map: !!e && (e.tagName === "CANVAS" || !!e.closest(".b3d-labels")),
        rotate_in_head: !!rot, rotate_name: rot && rot.textContent.trim(), dock_h: Math.round(document.querySelector("#birge-build3d-root .b3d-dock").getBoundingClientRect().height) }; });
    await shot(q, `b041_placing_${vp.width}x${vp.height}_${lang}.png`);
    await q.touchscreen.tap(placing.ghost[0], placing.ghost[1]);
    await q.waitForTimeout(700);
    await q.tap('#birge-build3d-root [data-action="rotate-right"]');
    await q.waitForTimeout(300);
    const at = await q.evaluate(() => CivicShell.build3d.getState().ghost.pos);
    await q.tap("#birge-build3d-root [data-action=place]");
    await q.waitForTimeout(900);
    const look = () => q.evaluate(([ll, ids]) => {
      const pt = map.project(ll), e = document.elementFromPoint(pt.x, pt.y);
      const t = document.querySelector("#birge-build3d-root .b3d-toasts .bk-toast"), tr = t && t.getBoundingClientRect();
      const tc = tr && document.elementFromPoint((tr.left + tr.right) / 2, (tr.top + tr.bottom) / 2);
      const b = document.getElementById("toggle-3d"), br = b && b.getBoundingClientRect();
      const ov = (a, c) => !!(a && c && a.left < c.right && a.right > c.left && a.top < c.bottom && a.bottom > c.top);
      const mine = CivicShell.build3d.getState().proposals.find((x) => !ids.includes(x.id));
      const lab = mine && document.querySelector(`.b3d-label[data-id="${mine.id}"]`), lr = lab && lab.getBoundingClientRect();
      const lc = lr && document.elementFromPoint((lr.left + lr.right) / 2, (lr.top + lr.bottom) / 2);
      const lg = document.getElementById("birge-legend"), lgr = lg && getComputedStyle(lg).display !== "none" && lg.getBoundingClientRect();
      return { place_on_map: !!e && (e.tagName === "CANVAS" || !!e.closest(".b3d-labels")), toast: tr ? [Math.round(tr.top), Math.round(tr.bottom)] : null,
        toast_visible: !!(tc && tc.closest(".bk-toast")), toast_over_place: !!(tr && pt.x >= tr.left && pt.x <= tr.right && pt.y >= tr.top && pt.y <= tr.bottom),
        toast_over_3d: ov(tr, br), saved: !!mine && !/^tmp-/.test(mine.id), id: mine ? mine.id : null, label_visible: !!(lc && lc.closest(".b3d-label")),
        label_over_legend: ov(lr, lgr), label: lr ? [Math.round(lr.top), Math.round(lr.bottom)] : null, legend: lgr ? [Math.round(lgr.top), Math.round(lgr.bottom)] : null };
    }, [at, ids0]);
    const now = await look();
    await shot(q, `b041_placed_${vp.width}x${vp.height}_${lang}.png`);
    await q.waitForTimeout(6500);
    const later = await look();
    b041[`${vp.width}x${vp.height}_${lang}`] = { login: ok, placing, now, later: { place_on_map: later.place_on_map, label_visible: later.label_visible, label_over_legend: later.label_over_legend,
      label: later.label, legend: later.legend, saved: later.saved } };
    // Снять поставленный проект («Удалить» в его карточке): повторный прогон на той же базе иначе упирается в занятое
    // место (рядом с проектом ставить нельзя — «Поставить» неактивна).
    if (later.saved) {
      await q.evaluate((id) => CivicShell.build3d.select(id), later.id);
      await q.click("#birge-build3d-root [data-action=delete]", { timeout: 10000 }).catch(() => null);
      await q.waitForFunction((id) => !CivicShell.build3d.getState().proposals.some((x) => x.id === id), later.id, { timeout: 10000 }).catch(() => {});
      await q.waitForTimeout(800);
    }
    await ctx.close();
  }
  check("r10_b041_phone_placed_project_not_under_message_or_panel", Object.values(b041).every((r) => r.login && r.placing.ghost_on_map && r.placing.rotate_in_head &&
    r.now.place_on_map && r.now.toast && r.now.toast_visible && !r.now.toast_over_place && !r.now.toast_over_3d && r.later.place_on_map && r.later.saved), b041);
  // Табличка поставленного проекта не под легендой оболочки: R05 видит легенду, только если она в opts.avoid (патч).
  check("r10_b041_label_clear_of_shell_legend (proposed_r01_final3.patch)", Object.values(b041).every((r) => r.later.label_visible && !r.later.label_over_legend),
    Object.fromEntries(Object.entries(b041).map(([k, r]) => [k, { label: r.later.label, legend: r.later.legend, visible: r.later.label_visible }])));

  check("phone_akimat_card_with_half_sheet_does_not_cover_shell_header",
    Object.values(halfCards).every((r) => r.tapped && r.state === "card" && r.header_free && r.dock[0] >= r.header_bottom && (r.sheet !== "peek" || (r.object_above_card && r.label_above_card))), halfCards);

  // 15. Раунд 14, 12 окт (своя проверка R05 на FINAL-2 шаг 4): телефон, акимат — карточка каждого вида проекта.
  // На 375×667 и 360×800 высокая карточка («Одобрить / Отклонить», «Удалить») поднималась до шапки, и выбранный
  // проект уходил под шапку и «Территорию». Теперь «Удалить» — в строке «Рядом», карточка опускается до низа экрана
  // поверх свёрнутой шторки; подпись выбранного проекта видна целиком между панелями сверху и карточкой.
  const phoneCards = {};
  for (const [vp, lang] of [[{ width: 375, height: 667 }, "kk"], [{ width: 360, height: 800 }, "ru"], [{ width: 375, height: 812 }, "ru"]]) {
    const ctx = await browser.newContext({ viewport: vp, hasTouch: true, isMobile: true });
    await ctx.addInitScript(PROJECTS_ON);
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); } catch (e) { /* нет хранилища */ } }, lang);
    const q = await ctx.newPage();
    q.on("pageerror", (e) => errors.push(e.message));
    await q.goto(URL0);
    await q.waitForFunction(() => window.CivicShell?.build3d?.getState?.().phase === "ready", null, { timeout: 60000 });
    // по одному проекту каждого вида (демо R06: сквер, площадка, спорт, остановка, освещение)
    const kinds = await q.evaluate(() => { const seen = {}; for (const x of CivicShell.build3d.getState().proposals) if (!seen[x.kind]) seen[x.kind] = x.id; return seen; });
    const rows = {};
    for (const [kind, id] of Object.entries(kinds)) {
      await q.evaluate(() => CivicShell.build3d.select(null));
      await q.evaluate((id) => { const x = CivicShell.build3d.getState().proposals.find((y) => y.id === id); const c = x.kind === "lighting" ? x.geometry.coordinates[0] : x.geometry.coordinates; map.jumpTo({ center: c, zoom: 17.4, pitch: 50, bearing: -20 }); }, id);
      await q.waitForFunction(() => { const s = CivicShell.build3d.getState(); return s.view !== "3d" || s.three === "ready" || s.three === "error"; }, null, { timeout: 30000 }).catch(() => {});
      await q.waitForTimeout(600);
      await q.evaluate((id) => CivicShell.build3d.select(id), id);
      await q.waitForTimeout(1600);
      rows[kind] = await q.evaluate((id) => {
        const st = CivicShell.build3d.getState(), d = document.querySelector("#birge-build3d-root .b3d-dock"), dr = d.getBoundingClientRect();
        const lab = document.querySelector(`.b3d-label[data-id="${id}"]`), lr = lab && lab.getBoundingClientRect();
        // Плашка R01 «Карта улиц не загрузилась — показан упрощённый фон» (#map-status, body.offline-basemap) — только в
        // облаке без тайлов; на ноутбуке с локальной подложкой её нет (LOCAL_FINAL п. 10). Её не считаем, но пишем в отчёт.
        const stack = lr ? document.elementsFromPoint((lr.left + lr.right) / 2, (lr.top + lr.bottom) / 2) : [];
        const env_notice = stack.length > 0 && !!stack[0].closest("#map-status");
        const c = stack.find((e) => !e.closest("#map-status"));
        const ov = (a, b) => !!(a && b && a.left < b.right - 1 && a.right > b.left + 1 && a.top < b.bottom - 1 && a.bottom > b.top + 1);
        const under = [];
        for (const sel of ["header.topbar", ".civic-explore", ".map-tools", "#birge-legend"]) {
          const e = document.querySelector(sel);
          if (e && getComputedStyle(e).display !== "none" && ov(lr, e.getBoundingClientRect())) under.push(sel);
        }
        return { state: d.dataset.state, selected: st.selected === id, dock: [Math.round(dr.top), Math.round(dr.bottom)], label: lr ? [Math.round(lr.left), Math.round(lr.top), Math.round(lr.right), Math.round(lr.bottom)] : null,
          visible: !!(c && c.closest(".b3d-label")), env_notice, whole_on_screen: !!(lr && lr.left >= 0 && lr.right <= innerWidth), above_card: !!(lr && lr.bottom <= dr.top), under, dock_in_screen: dr.bottom <= innerHeight + 1 };
      }, id);
      if (kind === "sports") await shot(q, `phone_card_room_${vp.width}x${vp.height}_${lang}.png`);
    }
    phoneCards[`${vp.width}x${vp.height}_${lang}`] = rows;
    await ctx.close();
  }
  check("phone_akimat_card_every_project_visible_above_card", Object.values(phoneCards).every((rows) => Object.keys(rows).length >= 4 &&
    Object.values(rows).every((r) => r.state === "card" && r.selected && r.visible && r.whole_on_screen && r.above_card && r.dock_in_screen && !r.under.some((u) => u !== "#birge-legend"))), phoneCards);

  // 16. LOCAL_FINAL № 9 / P3 (Codex): все кнопки R05 — зона нажатия ≥ 48 px (UX_BRIEF). Состояния: начало, лёгкая
  // карточка, 3D, каталог, размещение, сообщение «Проект поставлен · Отменить»; ноутбук ru и телефон kk.
  const sizes = {};
  for (const [vp, lang, touch] of [[{ width: 1366, height: 768 }, "ru", false], [{ width: 375, height: 812 }, "kk", true]]) {
    const ctx = await browser.newContext(Object.assign({ viewport: vp }, touch ? { hasTouch: true, isMobile: true } : {}));
    await ctx.addInitScript(PROJECTS_ON);
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); } catch (e) { /* нет хранилища */ } }, lang);
    const q = await ctx.newPage();
    q.on("pageerror", (e) => errors.push(e.message));
    await q.goto(URL0);
    await q.waitForFunction(() => window.CivicShell?.build3d?.getState?.().phase === "ready", null, { timeout: 60000 });
    if (PASSWORD) await q.evaluate((pw) => CivicShell.api.login("operator", pw).catch(() => null), PASSWORD);
    const small = [];
    const measure = async (tag) => small.push(...(await q.evaluate((tag) => {
      const out = [];
      for (const e of document.querySelectorAll("#birge-build3d-root button, #birge-build3d-root [role=button], .b3d-label")) {
        const cs = getComputedStyle(e);
        if (cs.display === "none" || cs.visibility === "hidden" || e.closest("[hidden]")) continue;
        const r = e.getBoundingClientRect();
        if (!r.width || !r.height) continue;
        let w = r.width, h = r.height; // зона нажатия: сам элемент или ::before/::after с отрицательным отступом
        for (const ps of ["::before", "::after"]) {
          const p = getComputedStyle(e, ps);
          if (p.content === "none" || p.position !== "absolute") continue;
          w = Math.max(w, r.width - (parseFloat(p.left) || 0) - (parseFloat(p.right) || 0));
          h = Math.max(h, r.height - (parseFloat(p.top) || 0) - (parseFloat(p.bottom) || 0));
        }
        if (Math.min(w, h) < 47.5) out.push({ tag, el: (e.dataset.action || e.className.toString()).slice(0, 40), w: Math.round(w), h: Math.round(h) });
      }
      return out;
    }, tag)));
    const sq = await q.evaluate(() => CivicShell.build3d.getState().proposals.find((x) => x.kind === "square"));
    await q.evaluate((c) => map.jumpTo({ center: c, zoom: 14.6, pitch: 0, bearing: 0 }), sq.geometry.coordinates);
    await q.waitForTimeout(1200);
    await measure("start");
    await q.evaluate((id) => CivicShell.build3d.select(id), sq.id);
    await q.waitForTimeout(1200);
    await measure("card_light");
    const v3 = await q.$("#birge-build3d-root [data-action=view3d]");
    if (v3) {
      await v3.click();
      await q.waitForFunction(() => CivicShell.build3d.getState().three === "ready" && !map.isMoving(), null, { timeout: 30000 }).catch(() => {});
      await q.waitForTimeout(600);
    }
    await measure("card_3d");
    await q.evaluate(() => CivicShell.build3d.select(null));
    await q.waitForTimeout(400);
    // телефон: кнопка «Что построить?» сама опускает шторку (R01 B-022)
    await openCatalog(q).catch(() => null);
    await q.waitForTimeout(400);
    await measure("catalog");
    await q.click('#birge-build3d-root .b3d-card[data-kind="square"]').catch(() => null);
    await q.waitForFunction(() => CivicShell.build3d.getState().mode === "placing" && CivicShell.build3d.getState().three === "ready", null, { timeout: 30000 }).catch(() => {});
    await q.waitForTimeout(600);
    await measure("placing");
    const g = await q.evaluate(() => { const s = CivicShell.build3d.getState(); return s.ghost ? map.project(s.ghost.pos) : null; });
    if (g) {
      if (touch) await q.touchscreen.tap(g.x, g.y);
      else await q.mouse.click(g.x, g.y);
      await q.waitForTimeout(400);
    }
    let placed = false;
    const pl = await q.$("#birge-build3d-root [data-action=place]");
    if (pl && !(await pl.isDisabled())) {
      await pl.click();
      await q.waitForSelector("#birge-build3d-root .b3d-toasts .bk-toast .bk-btn", { timeout: 10000 }).then(() => (placed = true), () => null);
    }
    await measure("placed_toast");
    if (placed) await q.click("#birge-build3d-root .b3d-toasts .bk-toast .bk-btn").catch(() => null); // «Отменить»: не копим проекты
    await q.waitForTimeout(600);
    sizes[`${vp.width}_${lang}`] = { placed_and_undone: placed, below_48: small };
    await ctx.close();
  }
  check("r05_controls_tap_zone_48px (LOCAL_FINAL №9)", Object.values(sizes).every((r) => r.placed_and_undone && r.below_48.length === 0), sizes);

  // 17. R10 B-045 и проектор 1024 (R10 B-043/B-044): 1024–1366 px, слой «Проекты». «Что построить?», открытый каталог
  // акимата и подсказка жителя не лежат на легенде, панели и кнопках карты. На 1024 открытый каталог закрывал кнопку
  // «Слой на карте» (R05: панель сужается до столбика кнопок), подсказка жителя в полосе 162 px — тоже (оболочка:
  // proposed_r01_final3.patch даёт ей всю ширину над легендой).
  const wide = {};
  for (const [w, h] of [[1024, 768], [1100, 800], [1280, 800], [1366, 768]]) {
    for (const mode of ["akimat", "resident"]) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h } });
      await ctx.addInitScript(PROJECTS_ON);
      await ctx.addInitScript((m) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", "kk"); } catch (e) { /* нет хранилища */ } }, mode);
      const q = await ctx.newPage();
      q.on("pageerror", (e) => errors.push(e.message));
      await q.goto(URL0);
      await q.waitForFunction(() => window.CivicShell?.build3d?.getState?.().phase === "ready", null, { timeout: 60000 });
      await q.waitForTimeout(2500);
      const look = () => q.evaluate(() => {
        const R = (e) => { if (!e) return null; const cs = getComputedStyle(e); if (cs.display === "none" || cs.visibility === "hidden") return null; const r = e.getBoundingClientRect(); return r.width && r.height ? r : null; };
        const ov = (a, b) => !!(a && b && a.left < b.right - 1 && a.right > b.left + 1 && a.top < b.bottom - 1 && a.bottom > b.top + 1);
        const mine = { toggle: R(document.querySelector(".birge-b3d-toggle")), dock: R(document.querySelector("#birge-build3d-root .b3d-dock")) };
        const host = { legend: R(document.getElementById("birge-legend")), panel: R(document.getElementById("civic-panel")), tools: R(document.querySelector(".map-tools")), header: R(document.querySelector("header.topbar")) };
        const hits = [];
        for (const [a, ra] of Object.entries(mine)) for (const [b, rb] of Object.entries(host)) if (ov(ra, rb)) hits.push(a + "×" + b);
        return { state: document.querySelector("#birge-build3d-root .b3d-dock")?.dataset.state, hits, dock_w: mine.dock ? Math.round(mine.dock.width) : null };
      });
      const r = { start: await look() };
      if (mode === "akimat" && (await q.$(".birge-b3d-toggle")) && (await q.isVisible(".birge-b3d-toggle"))) {
        await q.click(".birge-b3d-toggle");
        await q.waitForTimeout(800);
        r.catalog = await look();
        if (w === 1024) await shot(q, "wide_1024_akimat_catalog.png");
      }
      if (mode === "resident" && w === 1024) await shot(q, "wide_1024_resident_hint.png");
      wide[`${w}_${mode}`] = r;
      await ctx.close();
    }
  }
  check("r10_b045_1024_1366_catalog_and_toggle_clear_of_legend_and_map_buttons", Object.entries(wide).filter(([k]) => k.endsWith("_akimat")).every(([, r]) => r.start.hits.length === 0 && r.catalog && r.catalog.state === "catalog" && r.catalog.hits.length === 0), wide);
  check("resident_hint_1024_1366_clear_of_map_buttons (proposed_r01_final3.patch)", Object.entries(wide).filter(([k]) => k.endsWith("_resident")).every(([, r]) => r.start.state === "hint" && r.start.hits.length === 0), Object.fromEntries(Object.entries(wide).filter(([k]) => k.endsWith("_resident"))));
} catch (e) {
  check("run", false, e.message.split("\n")[0]);
}
check("no_page_errors", errors.length === 0, errors.slice(0, 3));
await browser.close();
await mkdir(path.join(OUT, "runs"), { recursive: true });
await writeFile(path.join(OUT, "runs", "app_b2_smoke.json"), JSON.stringify({ generated_at: new Date().toISOString(), url: URL0,
  r01: process.env.R01_LABEL || "claude/sharp-dijkstra-0t87gl@f54361d + proposed_r01_b2.patch", checks: results }, null, 1) + "\n");
process.exit(results.every((r) => r.status === "PASS") ? 0 : 1);
