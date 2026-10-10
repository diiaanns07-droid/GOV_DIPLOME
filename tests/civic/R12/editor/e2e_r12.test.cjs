/* R12 round 14: инструменты точной отметки в редакторе (контрактный mock civic-v1 + ТЕСТОВЫЙ клиент геоданных стенда).
 * «Участок улицы» двумя нажатиями (прилипает к оси, линия по улице), точка -> объект OSM рядом, двор выбором полигона,
 * ошибки (не у улицы, привязка не подключена, без привязки), гонка нажатий, телефон 375 px.
 * Run:  node --test tests/civic/R12/editor/e2e_r12.test.cjs     (R12_SHOTS=1 -> research/round-14-results/R12/screenshots/editor-*.png)
 */
"use strict";
const { describe, it, before, after } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const fs = require("fs");
const { startStand } = require("./stand.cjs");
const { loadPlaywright, makeKit, fk, sleep } = require("./e2e_helpers.cjs");

const PW = loadPlaywright();
const SHOTS = path.resolve(__dirname, "../../../../research/round-14-results/R12/screenshots");

describe("R12 editor: exact place tools", { skip: PW ? false : "playwright not installed" }, () => {
  let stand, browser, K;
  const pages = [];
  before(async () => {
    stand = await startStand();
    browser = await PW.chromium.launch({ args: ["--enable-unsafe-swiftshader"] });
    if (process.env.R12_SHOTS === "1") fs.mkdirSync(SHOTS, { recursive: true });
    K = makeKit({ stand, browser, pages, shotsDir: SHOTS });
  });
  after(async () => {
    for (const p of pages) for (const e of p.errors) console.error("pageerror:", e);
    if (browser) await browser.close();
    if (stand) await stand.close();
  });
  const shot = async (p, name) => { if (process.env.R12_SHOTS === "1") await p.screenshot({ path: path.join(SHOTS, "editor-" + name + ".png") }); };
  async function draft(query, viewport) {
    const p = await K.open(viewport, query);
    await K.loginToList(p);
    await K.fillDraft(p, { title: "Перекрытие участка (тест R12)" });
    await p.check(fk("place-approximate"));
    return p;
  }
  // Пиксель карты для [lon, lat] (стенд: центр [71.43, 51.13], улица идёт по широте 51.13).
  const px = (p, lon, lat) => p.evaluate(([x, y]) => { const q = window.__map.project([x, y]), r = window.__map.getCanvas().getBoundingClientRect(); return { x: r.left + q.x, y: r.top + q.y }; }, [lon, lat]);
  const clickAt = async (p, lon, lat) => { const q = await px(p, lon, lat); await p.mouse.click(q.x, q.y); };

  it("street section: two clicks -> preview along the street -> «Готово» -> saved line on the street axis", async () => {
    const p = await draft();
    await p.click(fk("tool-segment"));
    assert.match(await p.textContent(".civic-r04-tool"), /Нажмите на улицу в начале участка/);
    assert.deepEqual(await p.evaluate(() => window.__toolEvents.at(-1)), { active: true, mode: "segment" });
    assert.equal(await p.isDisabled(fk("tool-done")), true, "«Готово» — только после второго нажатия");
    await clickAt(p, 71.421, 51.1302);          // ~22 м севернее оси: прилипает к улице
    await p.waitForSelector(`${fk("seg-step")}:has-text("Начало: улица Стендовая")`);
    await clickAt(p, 71.438, 51.1299);
    await p.waitForSelector(`${fk("seg-step")}:has-text("Участок: улица Стендовая")`);
    const step = await p.textContent(fk("seg-step"));
    assert.match(step, /\d[\d\s ]* м/, "длина участка в метрах: " + step);
    // предпросмотр на карте — та же линия, что придёт в форму
    const preview = await p.evaluate(() => { const s = window.__map.getStyle().sources; const k = Object.keys(s).find((x) => /^civic-r04-\d+-geom$/.test(x)); return k ? window.__map.getSource(k)._data : null; });
    const line = preview.features.find((f) => f.geometry.type === "LineString");
    assert.ok(line && line.geometry.coordinates.every((c) => c[1] === 51.13), "предпросмотр идёт по оси улицы");
    assert.equal(preview.features.filter((f) => f.properties.vertex).length, 2, "на линии показаны только начало и конец");
    await shot(p, "segment-preview-1280");
    await p.click(fk("tool-done"));
    assert.deepEqual(await p.evaluate(() => window.__toolEvents.at(-1)), { active: false });
    await p.check(fk("geometry_confirmed"));
    await K.saveOk(p, "Черновик создан");
    const [rec] = K.objects();
    assert.equal(rec.geometry.type, "LineString");
    assert.ok(rec.geometry.coordinates.length >= 3);
    assert.ok(rec.geometry.coordinates.every((c) => c[1] === 51.13));
    assert.ok(Math.abs(rec.geometry.coordinates[0][0] - 71.421) < 0.0002 && Math.abs(rec.geometry.coordinates.at(-1)[0] - 71.438) < 0.0002);
    const calls = await p.evaluate(() => window.__geoCalls.map((c) => c.name + ":" + c.args[c.args.length - 1]));
    assert.deepEqual(calls.filter((c) => /^(snap|segment)/.test(c)), ["snap:road", "segment:road"]);
    // у сохранённой линии нет «Изменить вершины» (линия по улице не редактируется от руки)
    assert.equal(await p.$(fk("tool-edit")), null);
    assert.match(await p.textContent(fk("tool-segment")), /Выбрать участок улицы заново/);
    await shot(p, "segment-saved-1280");
  });

  it("street section: a click far from the street says what to do; a new end rebuilds the section; tротуар switches the kind", async () => {
    const p = await draft();
    await p.click(fk("tool-segment"));
    await clickAt(p, 71.43, 51.1325);            // ~280 м от улицы
    await p.waitForSelector('.civic-r04-slot-geom [role=alert]');
    assert.match(await p.textContent(".civic-r04-slot-geom [role=alert]"), /Рядом нет улицы/);
    await clickAt(p, 71.425, 51.13);
    await p.waitForSelector(`${fk("seg-step")}:has-text("Начало")`);
    await clickAt(p, 71.432, 51.13);
    await p.waitForSelector(`${fk("seg-step")}:has-text("Участок:")`);
    const first = await p.textContent(fk("seg-step"));
    await clickAt(p, 71.44, 51.13);               // другой конец — участок перестраивается от того же начала
    await p.waitForFunction((t) => document.querySelector('[data-fk="seg-step"]').textContent !== t && /Участок:/.test(document.querySelector('[data-fk="seg-step"]').textContent), first);
    await p.click(fk("seg-kind-foot"));
    assert.equal(await p.getAttribute(fk("seg-kind-foot"), "aria-pressed"), "true");
    assert.match(await p.textContent(fk("seg-step")), /Нажмите на начало участка/, "смена «Тротуар» начинает участок заново");
    await clickAt(p, 71.425, 51.13);
    await p.waitForSelector(`${fk("seg-step")}:has-text("Начало")`);
    const kinds = await p.evaluate(() => window.__geoCalls.filter((c) => c.name === "snap").map((c) => c.args[1]));
    assert.equal(kinds.at(-1), "foot");
    await p.keyboard.press("Escape");
    assert.equal(K.objects().length, 0);
  });

  it("street section: a quick second click wins over a slow first answer (no stale line)", async () => {
    const p = await draft("?geodelay=400");
    await p.click(fk("tool-segment"));
    await clickAt(p, 71.425, 51.13);
    await p.waitForSelector(`${fk("seg-step")}:has-text("Начало")`, { timeout: 5000 });
    await clickAt(p, 71.432, 51.13);
    await sleep(60);
    await clickAt(p, 71.441, 51.13);             // второй конец раньше ответа на первый
    await p.waitForSelector(`${fk("seg-step")}:has-text("Участок:")`, { timeout: 5000 });
    await sleep(600);
    await p.click(fk("tool-done"));
    await p.check(fk("geometry_confirmed"));
    await K.saveOk(p, "Черновик создан");
    const [rec] = K.objects();
    assert.ok(Math.abs(rec.geometry.coordinates.at(-1)[0] - 71.441) < 0.0002, "сохранён участок до последнего нажатия");
  });

  it("review fixes: switching road/sidewalk or «Начать заново» while an answer is in flight leaves no stale start and no stuck «Строим…»", async () => {
    const p = await draft("?geodelay=500");
    await p.click(fk("tool-segment"));
    await clickAt(p, 71.425, 51.13);              // ответ на «начало» ещё в пути…
    await sleep(80);
    await p.click(fk("seg-kind-foot"));            // …а сотрудник переключил «Тротуар»
    await sleep(800);
    assert.match(await p.textContent(fk("seg-step")), /Нажмите на начало участка/, "старый ответ не стал началом");
    await clickAt(p, 71.425, 51.13);
    await p.waitForSelector(`${fk("seg-step")}:has-text("Начало")`, { timeout: 5000 });
    await clickAt(p, 71.435, 51.13);              // строим участок…
    await sleep(80);
    await p.click(fk("tool-undo"));                // …и сразу «Начать заново»
    await sleep(800);
    assert.match(await p.textContent(fk("seg-step")), /Нажмите на начало участка/, "нет зависшего «Строим участок…»");
    assert.equal(await p.isDisabled(fk("tool-done")), true);
    await p.keyboard.press("Escape");
  });

  it("server without the R12 routes: an honest message, nothing drawn by hand; geo:false disables the tools", async () => {
    const p = await draft("?geo=fail");
    await p.click(fk("tool-segment"));
    await clickAt(p, 71.425, 51.13);
    await p.waitForSelector('.civic-r04-slot-geom [role=alert]');
    assert.match(await p.textContent(".civic-r04-slot-geom [role=alert]"), /Привязка к улицам на этом сервере не подключена/);
    assert.equal(await p.isDisabled(fk("tool-done")), true);
    await p.keyboard.press("Escape");
    const q = await draft("?geo=off");
    assert.equal(await q.isDisabled(fk("tool-segment")), true);
    assert.equal(await q.isDisabled(fk("tool-yard")), true);
    assert.equal(await q.isDisabled(fk("tool-point")), false, "точка и площадь по углам остаются");
  });

  it("point next to an OSM object: one click puts the point exactly on it", async () => {
    const p = await draft();
    await p.click(fk("tool-point"));
    await clickAt(p, 71.4353, 51.1303);           // ~25 м от остановки «Стенд»
    await p.waitForSelector(fk("near-0"));
    assert.match(await p.textContent(fk("near")), /Остановка «Стенд» — \d+ м/);
    await shot(p, "point-near-object-1280");
    await p.click(fk("near-0"));
    await p.waitForSelector(fk("linked"));
    assert.match(await p.textContent(fk("linked")), /Точка стоит на объекте OSM: Остановка «Стенд»/);
    await p.check(fk("geometry_confirmed"));
    await K.saveOk(p, "Черновик создан");
    assert.deepEqual(K.objects()[0].geometry, { type: "Point", coordinates: [71.435, 51.1302] });
    // точка далеко от объектов — подсказки нет
    await p.click(fk("tool-point"));
    await clickAt(p, 71.42, 51.135);
    await sleep(200);
    assert.equal(await p.$(fk("near")), null);
  });

  it("yard: a click inside picks the whole OSM yard; outside — a hint to draw by corners", async () => {
    const p = await draft();
    await p.click(fk("tool-yard"));
    await clickAt(p, 71.44, 51.135);
    await p.waitForSelector('.civic-r04-slot-geom [role=alert]');
    assert.match(await p.textContent(".civic-r04-slot-geom [role=alert]"), /Здесь нет двора на карте OSM/);
    await clickAt(p, 71.4265, 51.132);
    await p.waitForSelector(`${fk("yard-step")}:has-text("Выбран: Двор — улица Стендовая")`);
    await p.click(fk("tool-done"));
    await p.check(fk("geometry_confirmed"));
    await K.saveOk(p, "Черновик создан");
    const g = K.objects()[0].geometry;
    assert.equal(g.type, "Polygon");
    assert.deepEqual(g.coordinates[0][0], [71.425, 51.131]);
  });

  it("phone 375 px: the street tool panel fits, buttons are at least 44 px high, no horizontal scroll", async () => {
    const p = await draft("", { width: 375, height: 812 });
    await p.click(fk("tool-segment"));
    const m = await p.evaluate(() => {
      const ids = ["tool-done", "tool-cancel", "seg-kind-road", "seg-kind-foot"];
      return { overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        heights: ids.map((k) => Math.round(document.querySelector('[data-fk="' + k + '"]').getBoundingClientRect().height)) };
    });
    assert.ok(m.overflow <= 0, "горизонтальная прокрутка " + m.overflow);
    for (const h of m.heights) assert.ok(h >= 44, "высота кнопки " + h);
    await shot(p, "segment-tool-375");
    await p.keyboard.press("Escape");
  });
});
