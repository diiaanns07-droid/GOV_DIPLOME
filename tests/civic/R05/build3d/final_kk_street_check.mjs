// R05 · R10 B-033 / R11 ночь 7 п. 2 в сборке R01: строка улицы в карточке проекта на казахском — казахское название
// с правильным регистром («Жанында: Керей және Жәнібек хандар көшесі»), без русских слов; на русском — «Рядом: …».
// Шаг 5 сценария R01/R10: акимат ставит сквер у точки 71.402341, 51.117181, житель открывает его карточку.
// Заголовки (R06 ≥ d707efc строит «вид + улица»): казахский — из near_street_kk (OSM name:kk), без русского имени;
// сквер на левом берегу (точка теста R01 r14_b2, вне улиц Нуры) получает улицу от R12 /street-snap.
//   (в папке сборки R01) export CIVIC_DB_PATH=/tmp/f.sqlite3 CIVIC_DEMO=1; python3 -B -m ui.civic_store --db /tmp/f.sqlite3 init /
//     seed-demo --package data/civic/astana/demo_synthetic.json / seed-r14-demo / create-editor operator --password-stdin
//   python3 -B app.py --host 127.0.0.1 --port 8805 &
//   node tests/civic/R05/build3d/final_kk_street_check.mjs http://127.0.0.1:8805/ <файл с паролем> [метка сборки]
// Пароль не печатается и не попадает в отчёт. Отчёт: runs/final_kk_street.json, кадры screens/final_kk_street_<w>_<lang>.png.
import { createRequire } from "node:module";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const OUT = path.join(ROOT, "research/round-14-results/R05");
const URL0 = process.argv[2] || "http://127.0.0.1:8805/";
const PW = process.argv[3] ? (await readFile(process.argv[3], "utf8")).trim() : null;
const LABEL = process.argv[4] || URL0;
let chromium;
for (const id of ["playwright", "/opt/node22/lib/node_modules/playwright"]) {
  try {
    ({ chromium } = require(id));
    break;
  } catch (e) {
    /* следующий */
  }
}
const PLACE = [71.402341, 51.117181]; // точка шага 5 сценария R01/R10
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
await mkdir(path.join(OUT, "screens"), { recursive: true });
const out = [];
let placedId = null;
for (const vp of [{ width: 1366, height: 768 }, { width: 375, height: 812 }]) {
  for (const lang of ["kk", "ru"]) {
    const ctx = await browser.newContext(Object.assign({ viewport: vp }, vp.width < 640 ? { hasTouch: true, isMobile: true } : {}));
    await ctx.addInitScript(() => {
      try {
        localStorage.setItem("birge.mode", "akimat");
      } catch (e) {
        /* нет хранилища */
      }
    });
    const p = await ctx.newPage();
    const errors = [];
    p.on("pageerror", (e) => errors.push(e.message));
    await p.goto(URL0);
    await p.waitForFunction(() => window.CivicShell?.build3d?.getState?.().phase === "ready", null, { timeout: 60000 });
    await p.evaluate((l) => BirgeI18n.setLang(l), lang);
    if (!placedId) {
      // Один раз: сотрудник ставит сквер у точки шага 5 (как в сценарии).
      const ok = PW ? await p.evaluate((pw) => CivicShell.api.login("operator", pw).then(() => true, () => false), PW) : false;
      if (!ok) throw new Error("вход сотрудника не удался (нужен файл с паролем)");
      await p.evaluate((pl) => map.jumpTo({ center: pl, zoom: 17.4, pitch: 50, bearing: -20 }), PLACE);
      await p.waitForTimeout(600);
      if (await p.evaluate(() => document.getElementById("birge-build3d-root").dataset.catalog === "closed")) await p.click(".birge-b3d-toggle");
      const before = await p.evaluate(() => CivicShell.build3d.getState().proposals.map((q) => q.id));
      await p.click("#birge-build3d-root .b3d-card[data-kind=square]");
      await p.waitForTimeout(800);
      const xy = await p.evaluate((pl) => {
        const c = map.getCanvas().getBoundingClientRect(),
          q = map.project(pl);
        return [c.left + q.x, c.top + q.y];
      }, PLACE);
      await p.mouse.move(xy[0], xy[1]);
      await p.mouse.click(xy[0], xy[1]);
      await p.waitForTimeout(400);
      await p.click("#birge-build3d-root [data-action=place]");
      await p.waitForFunction(
        (ids) => { const s = CivicShell.build3d.getState(); return s.proposals.some((q) => !ids.includes(q.id) && !/^tmp-/.test(q.id)) && !s.animating; },
        before,
        { timeout: 30000 }
      );
      placedId = await p.evaluate((ids) => CivicShell.build3d.getState().proposals.find((q) => !ids.includes(q.id)).id, before);
    }
    // Житель открывает карточку этого проекта.
    await p.evaluate(() => document.dispatchEvent(new CustomEvent("birge:mode", { detail: { mode: "resident" } })));
    await p.evaluate((id) => CivicShell.build3d.select(id), placedId);
    await p.waitForTimeout(900);
    await p.waitForFunction(() => !document.getAnimations().some((a) => a.playState === "running" || a.pending), null, { timeout: 5000 }).catch(() => {});
    const text = await p.evaluate(() => document.querySelector("#birge-build3d-root .b3d-dock").innerText);
    const line = (text.match(lang === "kk" ? /Жанында:[^\n]*/ : /Рядом:[^\n]*/) || [""])[0];
    const shot = `screens/final_kk_street_${vp.width}_${lang}.png`;
    await p.screenshot({ path: path.join(OUT, shot) });
    const ok =
      lang === "kk"
        ? /^Жанында: \S.*(көшесі|даңғылы|алаңы|жолы)$/.test(line) && !/улица|проспект|Және|Хандар|Батыр /.test(line)
        : /^Рядом: \S/.test(line);
    out.push({ vp: vp.width, lang, line, ok, shot, page_errors: errors.slice(0, 2) });
    console.log(`${ok && !errors.length ? "PASS" : "FAIL"} ${vp.width} ${lang}: ${line}`);
    await ctx.close();
  }
}
// Заголовки: сквер у Керей и Жәнібек (Нура) и сквер на левом берегу (улица — от R12).
const LEFT_BANK = [71.4148, 51.1131];
const titles = {};
{
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  await ctx.addInitScript(() => {
    try {
      localStorage.setItem("birge.mode", "akimat");
    } catch (e) {
      /* нет хранилища */
    }
  });
  const p = await ctx.newPage();
  await p.goto(URL0);
  await p.waitForFunction(() => window.CivicShell?.build3d?.getState?.().phase === "ready", null, { timeout: 60000 });
  await p.evaluate((pw) => CivicShell.api.login("operator", pw), PW);
  const pick = (id) => p.evaluate((id) => { const q = CivicShell.build3d.getState().proposals.find((x) => x.id === id); return q && { title_ru: q.title_ru, title_kk: q.title_kk, near_street: q.near_street, near_street_kk: q.near_street_kk || null }; }, id);
  titles.nura = await pick(placedId);
  await p.evaluate((pl) => map.jumpTo({ center: pl, zoom: 17.4, pitch: 50, bearing: -20 }), LEFT_BANK);
  await p.waitForTimeout(800);
  if (await p.evaluate(() => document.getElementById("birge-build3d-root").dataset.catalog === "closed")) await p.click(".birge-b3d-toggle");
  const before = await p.evaluate(() => CivicShell.build3d.getState().proposals.map((q) => q.id));
  await p.click("#birge-build3d-root .b3d-card[data-kind=square]");
  await p.waitForTimeout(800);
  const xy = await p.evaluate((pl) => { const c = map.getCanvas().getBoundingClientRect(), q = map.project(pl); return [c.left + q.x, c.top + q.y]; }, LEFT_BANK);
  await p.mouse.move(xy[0], xy[1]);
  await p.mouse.click(xy[0], xy[1]);
  await p.waitForTimeout(400);
  const snaps = [];
  p.on("request", (r) => { if (/\/street-snap\?/.test(r.url())) snaps.push(r.url().replace(/^.*\/street-snap/, "street-snap")); });
  await p.click("#birge-build3d-root [data-action=place]");
  await p.waitForFunction((ids) => { const s = CivicShell.build3d.getState(); return s.proposals.some((q) => !ids.includes(q.id) && !/^tmp-/.test(q.id)) && !s.animating; }, before, { timeout: 30000 });
  const leftId = await p.evaluate((ids) => CivicShell.build3d.getState().proposals.find((q) => !ids.includes(q.id)).id, before);
  titles.left_bank = Object.assign({ street_snap_requests: snaps.length }, await pick(leftId));
  titles.left_bank_cards = {};
  await ctx.close();
  // Карточка этого проекта у жителя: заголовок на экране, 1366/375 × ru/kk.
  for (const vp of [{ width: 1366, height: 768 }, { width: 375, height: 812 }]) {
    for (const lang of ["ru", "kk"]) {
      const c2 = await browser.newContext(Object.assign({ viewport: vp }, vp.width < 640 ? { hasTouch: true, isMobile: true } : {}));
      await c2.addInitScript((l) => { try { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l); } catch (e) { /* нет хранилища */ } }, lang);
      const q = await c2.newPage();
      await q.goto(URL0);
      await q.waitForFunction(() => window.CivicShell?.build3d?.getState?.().phase === "ready", null, { timeout: 60000 });
      await q.evaluate((pl) => map.jumpTo({ center: pl, zoom: 17.4, pitch: 50, bearing: -20 }), LEFT_BANK);
      await q.evaluate((id) => CivicShell.build3d.select(id), leftId);
      await q.waitForTimeout(1200);
      await q.waitForFunction(() => !document.getAnimations().some((a) => a.playState === "running" || a.pending), null, { timeout: 5000 }).catch(() => {});
      const head = await q.evaluate(() => { const d = document.querySelector("#birge-build3d-root .b3d-dock"); const h = d && d.querySelector(".bk-card__title, h2, h3"); return h ? h.textContent.trim() : null; });
      const shot = `screens/final_left_bank_card_${vp.width}_${lang}.png`;
      await q.screenshot({ path: path.join(OUT, shot) });
      titles.left_bank_cards[`${vp.width}_${lang}`] = { title_on_screen: head, shot };
      await c2.close();
    }
  }
}
const tn = titles.nura || {}, tl = titles.left_bank || {};
const cards = titles.left_bank_cards || {};
const titlesOk = /Керей және Жәнібек хандар көшесі маңында/.test(tn.title_kk || "") && !/ и Жанибек|улица/.test(tn.title_kk || "") &&
  !!tl.near_street && /^Сквер у /.test(tl.title_ru || "") && /^Гүлзар · .+ маңында$/.test(tl.title_kk || "") &&
  Object.entries(cards).length === 4 && Object.entries(cards).every(([k, v]) => v.title_on_screen === (k.endsWith("_kk") ? tl.title_kk : tl.title_ru));
out.push({ titles, ok: titlesOk });
console.log(`${titlesOk ? "PASS" : "FAIL"} titles: ${JSON.stringify(titles)}`);
await browser.close();
const status = out.every((o) => o.ok && !(o.page_errors || []).length) ? "PASS" : "FAIL";
await writeFile(
  path.join(OUT, "runs", "final_kk_street.json"),
  JSON.stringify({ generated_at: new Date().toISOString(), build: LABEL, place: PLACE, proposal: placedId, status, checks: out }, null, 1) + "\n"
);
console.log(status);
process.exit(status === "PASS" ? 0 : 1);
