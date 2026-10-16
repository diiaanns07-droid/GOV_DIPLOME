// R07 раунд 15+ · П3, сцена 0: «Показать на карте» у задачи «ИИ-разбора» R04 ведёт на место, жалоб по которому за
// период нет (их создаст «Создать задачи»). Раньше на обзоре города карта молчала: /heat/target — 404, перелёта нет,
// тоста нет. Теперь 404 приносит place (подпись, точка, форма): карта летит к месту, обводит его тёмным контуром без
// цвета жалоб, тост называет место. Чужой id — честное «жалоб нет» без перелёта; контур снимается выбором цели и Esc.
// Запуск: python -m ui.civic_heat.devserver --port 8619 &   затем
//   NODE_PATH=$(npm root -g) R07_BASE=http://127.0.0.1:8619/civic/heat/demo.html node tests/civic/R07/browser/place_no_complaints.cjs [отчёт.json] [папка кадров]
const { chromium } = require("playwright");
const fs = require("fs");

const BASE = process.env.R07_BASE || "http://127.0.0.1:8619/civic/heat/demo.html";
const OUT = process.argv[2] || null;
const SHOTS = process.argv[3] || null;
const PLACE = { kind: "area", id: "yard-1026285033", ru: "Двор ЖК «Grand Champion»", kk: "«Grand Champion» ТК ауласы" };   // двор R12, в демо жалоб нет
const results = [];
const check = (name, problems, extra) => {
  results.push({ name, pass: !problems.length, problems, extra });
  console.log((problems.length ? "FAIL " : "PASS ") + name + (problems.length ? " · " + problems.join("; ") : ""));
};
const look = (page, anchor) => page.evaluate((a) => {
  const map = window.__map, c = map.getCanvas(), r = c.getBoundingClientRect();
  const ids = ["r07-place-line", "r07-place-approx", "r07-place-ring"].filter((id) => map.getLayer(id));
  let at = null;
  if (a) {
    const p = map.project(a), x = r.left + p.x, y = r.top + p.y;
    at = { x: Math.round(x), y: Math.round(y), open: document.elementFromPoint(x, y) === c };   // не под панелью и не под тостом
  }
  return { zoom: +map.getZoom().toFixed(2), outline: ids.reduce((n, id) => n + map.queryRenderedFeatures({ layers: [id] }).length, 0),
    selected: window.__heat.state().selected, mode: window.__heat.state().mode, at,
    toasts: [...document.querySelectorAll(".r07-toast:not(.r07-toast--out)")].map((el) => el.textContent.trim()) };
}, anchor || null);
const go = async (page, kind, id) => {
  await page.evaluate(() => document.querySelectorAll(".r07-toast").forEach((el) => el.remove()));
  await page.evaluate((h) => { location.hash = h; }, `#target=${kind}:${id}`);
  await page.waitForTimeout(2600);
};

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });
  for (const [w, h, lang] of [[1366, 768, "ru"], [375, 812, "kk"]]) {
    const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    const errors = [], places = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    // 404 «жалоб нет» — ответ API, а не ошибка страницы; остальное в консоли — ошибка
    page.on("console", (m) => { if (m.type() === "error" && !/\/heat\/target\?/.test((m.location() || {}).url || "")) errors.push(m.text()); });
    page.on("response", async (r) => {
      if (!/\/heat\/target\?/.test(r.url())) return;
      let b = null; try { b = await r.json(); } catch (e) { /* */ }
      places.push({ status: r.status(), place: b && b.place ? { id: b.place.id, anchor: b.place.anchor, geometry: b.place.geometry && b.place.geometry.type } : null });
    });
    await page.goto(`${BASE}?lang=${lang}&role=akimat&view=city`, { waitUntil: "networkidle" });
    await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
    await page.waitForTimeout(1200);
    const tag = `${w}-${lang}`;
    const start = await look(page);

    // 1. С обзора города — на двор без жалоб: перелёт к месту, контур, тост с названием, карточки нет.
    {
      const p = [];
      places.length = 0;
      await go(page, PLACE.kind, PLACE.id);
      const resp = places[0] || {};
      const anchor = resp.place && resp.place.anchor;
      const s = await look(page, anchor);
      const name = lang === "kk" ? PLACE.kk : PLACE.ru;
      if (resp.status !== 404 || !resp.place) p.push("ответ /heat/target без place: " + JSON.stringify(resp));
      if (start.mode !== "districts") p.push("старт не с обзора районов: " + start.mode);
      if (s.zoom < 15) p.push("карта не подлетела: масштаб " + s.zoom);
      if (!s.at || !s.at.open) p.push("место не на открытой части карты: " + JSON.stringify(s.at));
      if (!s.outline) p.push("нет контура места");
      if (s.selected) p.push("открылась карточка " + s.selected);
      if (!s.toasts.some((x) => x.includes(name) && /жалоб нет|шағым жоқ/.test(x))) p.push("тост без названия места: " + JSON.stringify(s.toasts));
      if (SHOTS) await page.screenshot({ path: `${SHOTS}/place_no_complaints_${tag}.png` });
      check(`${tag} place-flies-outlines-and-names`, p, { resp, s });
    }

    // 2. Esc снимает контур (как карточку).
    {
      const p = [];
      await page.keyboard.press("Escape");
      await page.waitForTimeout(300);
      const s = await look(page);
      if (s.outline) p.push("контур остался после Esc");
      check(`${tag} esc-clears-outline`, p, { s });
    }

    // 3. Чужой id — честное «жалоб нет» без названия, без перелёта и без контура.
    {
      const p = [];
      places.length = 0;
      const before = await look(page);
      await go(page, "area", "yard-999999999999");
      const s = await look(page);
      const resp = places[0] || {};
      if (resp.status !== 404 || resp.place) p.push("ответ для чужого id: " + JSON.stringify(resp));
      if (Math.abs(s.zoom - before.zoom) > 0.01) p.push(`карта сдвинулась: ${before.zoom} → ${s.zoom}`);
      if (s.outline) p.push("контур у чужого id");
      if (!s.toasts.some((x) => /жалоб нет|шағым жоқ/.test(x))) p.push("нет тоста «жалоб нет»: " + JSON.stringify(s.toasts));
      check(`${tag} unknown-id-honest-empty`, p, { resp, s });
    }

    // 4. Снова место без жалоб, затем цель с жалобами: карточка открывается, контур первого места снят.
    {
      const p = [];
      await go(page, PLACE.kind, PLACE.id);
      const mid = await look(page);
      const real = await page.evaluate(async () => {   // любое место с жалобами за 30 дней (тот же API, что у карты)
        const b = await (await fetch("/api/civic/v2/heat?days=30&zoom=16")).json();
        const it = (b.items || []).find((x) => x.target.kind !== "district" && x.count > 0);
        return it ? { kind: it.target.kind, id: it.target.id, key: it.target.kind + ":" + it.target.id } : null;
      });
      if (!mid.outline) p.push("контур не появился перед выбором цели");
      if (!real) p.push("нет горячего места для выбора");
      else {
        await go(page, real.kind, real.id);
        const s = await look(page);
        if (s.selected !== real.key) p.push("карточка цели с жалобами не открылась: " + s.selected);
        if (s.outline) p.push("контур места без жалоб остался при открытой карточке");
      }
      await page.evaluate(() => window.__heat.close());
      check(`${tag} real-target-replaces-outline`, p, { mid: mid.outline, real });
    }
    check(`${tag} no-page-errors`, errors.slice(0, 5), null);
    await page.close();
  }
  await browser.close();
  const failed = results.filter((r) => !r.pass).length;
  console.log(`${results.length - failed}/${results.length} PASS`);
  if (OUT) fs.writeFileSync(OUT, JSON.stringify({ base: BASE, results }, null, 2));
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
