// R07: читаемость карты (просьба владельца): 1) при открытии карта вписывает 10 мест из списка; 2) смысловой зум
// и кластеры вместо пропавших значков; 5) белая обводка подписей; 6) режим фокуса; 9) подсказка при наведении.
// Запуск: python -m ui.civic_heat.devserver &   затем
//   NODE_PATH=$(npm root -g) node tests/civic/R07/browser/readability.js [папка] [метка] [--shots-only]
// --shots-only — только кадры (для кадров «до» на старом коде, где кластеров и фокуса ещё нет).
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.env.R07_BASE || "http://127.0.0.1:8617/civic/heat/demo.html";
const OUT = process.argv[2] || path.join(__dirname, "..", "..", "..", "..", "research", "round-14-results", "R07", "screens", "readability");
const LABEL = process.argv[3] || "after";
const SHOTS_ONLY = process.argv.includes("--shots-only");
fs.mkdirSync(OUT, { recursive: true });
const SIZES = { 1366: { width: 1366, height: 768 }, 375: { width: 375, height: 812 } };
const NURA = [71.4045, 51.1285];

async function open(browser, size, lang, query = "") {
  const page = await browser.newPage({ viewport: SIZES[size], deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(`${BASE}?lang=${lang}&role=akimat${query}`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
  await page.waitForTimeout(1800);
  return { page, errors };
}
const jump = async (page, center, zoom) => {
  await page.evaluate(([c, z]) => window.__map.jumpTo({ center: c, zoom: z }), [center, zoom]);
  await page.waitForTimeout(1400);
};
const shot = (page, name) => page.screenshot({ path: path.join(OUT, `${LABEL}-${name}.png`) });

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });
  const results = [];
  const check = (name, problems, extra) => { results.push({ name, pass: !problems.length, problems, extra }); console.log((problems.length ? "FAIL " : "PASS ") + name + (problems.length ? " · " + problems.join("; ") : "")); };
  for (const size of [1366, 375]) for (const lang of ["ru", "kk"]) {
    const tag = `${size}-${lang}`;
    // --- открытие: карта вписывает 10 мест из списка ---
    let { page, errors } = await open(browser, size, lang, size === 375 ? "&sheet=peek" : "");
    await shot(page, `${tag}-1-open`);
    if (!SHOTS_ONLY) {
      const r = await page.evaluate(() => ({ fitted: window.__heat.state().fittedKeys, list: [...document.querySelectorAll(".r07-item")].map((b) => b.dataset.key),
        mode: window.__heat.state().mode, kinds: [...new Set(window.__heat.badges().map((b) => b.key.split(":")[0]))] }));
      const p = [];
      if (r.fitted.join() !== r.list.join() || r.list.length < 3) p.push("вписаны не те места, что в списке");
      if (r.mode === "districts" && r.kinds.some((k) => k !== "district")) p.push("на обзоре города не только районы: " + r.kinds.join(","));
      check(`open-fit-${tag}`, p.concat(errors), { mode: r.mode, n: r.list.length });
    }
    // --- 12–15: дворы и участки, объекты — только в кластерах; кластеры не налезают ---
    await jump(page, NURA, 13.4);
    await shot(page, `${tag}-2-z13`);
    if (!SHOTS_ONLY) {
      const r = await page.evaluate(() => {
        const bs = window.__heat.badges();
        const els = [...document.querySelectorAll(".r07-badge:not([hidden])")];
        const rs = els.map((e) => e.getBoundingClientRect());
        let overlaps = 0;
        for (let i = 0; i < rs.length; i++) for (let j = i + 1; j < rs.length; j++) {
          const a = rs[i], b = rs[j];
          if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) overlaps++;
        }
        const clusters = bs.filter((b) => b.mode === "cluster");
        return { objects: bs.filter((b) => b.mode !== "cluster" && b.key.startsWith("object:")).length, clusters: clusters.length,
          members: clusters.reduce((a, c) => a + c.members.length, 0), overlaps,
          clusterHalo: (() => { const c = document.querySelector(".r07-cluster"); return c ? getComputedStyle(c).textShadow : ""; })(),
          countHalo: (() => { const c = document.querySelector(".r07-badge__count"); return c ? getComputedStyle(c).textShadow + " | " + getComputedStyle(c).boxShadow : ""; })() };
      });
      const p = [];
      if (r.objects) p.push(`на 13,4 по отдельности видно ${r.objects} объектов (должны быть в кластерах)`);
      if (!r.clusters) p.push("нет ни одного кластера");
      if (r.overlaps) p.push(`значки налезают: ${r.overlaps}`);
      if (!/255, 255, 255|#fff/i.test(r.countHalo)) p.push("у подписи значка нет белой обводки");
      check(`semantic-zoom-${tag}`, p, r);
      // кластер: число = сумма людей, цвет = самого высокого уровня; нажатие — приблизить
      const c = await page.evaluate(async () => {
        const cl = window.__heat.badges().filter((b) => b.mode === "cluster").sort((a, b) => b.members.length - a.members.length)[0];
        if (!cl) return null;
        const el = [...document.querySelectorAll(".r07-badge--cluster")].find((e) => e.dataset.key === cl.key);
        const d = await (await fetch("/api/civic/v2/heat?days=30&zoom=15")).json();
        const items = d.items.filter((x) => cl.members.includes(x.target.kind + ":" + x.target.id));
        const sum = items.reduce((a, x) => a + x.count, 0);
        const active = items.filter((x) => x.state !== "fixed");
        const top = (active.length ? active : items).sort((a, b) => b.weight - a.weight || b.count - a.count)[0];
        return { n: Number(el.innerText.replace(/\D/g, "")), sum, color: getComputedStyle(el).getPropertyValue("--r07-c").trim(), want: top.color,
          aria: el.getAttribute("aria-label"), zoom: window.__map.getZoom(), objects: items.some((x) => x.target.kind === "object"), key: cl.key };
      });
      if (c) {
        await page.click(`.r07-badge--cluster[data-key="${c.key}"]`);
        await page.waitForTimeout(1500);
        const z2 = await page.evaluate(() => window.__map.getZoom());
        const p2 = [];
        if (c.n !== c.sum) p2.push(`число кластера ${c.n}, а людей в его местах ${c.sum}`);
        if (c.color.toLowerCase() !== String(c.want).toLowerCase()) p2.push(`цвет кластера ${c.color}, а самого горячего места ${c.want}`);
        if (!(z2 > c.zoom + 0.5)) p2.push("нажатие на кластер не приблизило карту");
        if (c.objects && z2 < 15) p2.push("кластер с объектами приблизил меньше 15-го масштаба");
        if (!c.aria) p2.push("у кластера нет aria-label");
        check(`cluster-click-${tag}`, p2, { n: c.n, sum: c.sum, z: [c.zoom, z2] });
      } else check(`cluster-click-${tag}`, ["нет кластера для проверки"], null);
    }
    await page.close();
    // --- режим фокуса: выбранная крупнее, остальные 40 %, Esc — сброс ---
    ({ page, errors } = await open(browser, size, lang, "&view=nura" + (size === 375 ? "&sheet=half" : "")));
    // место в Нуре (вокруг есть другие значки): первым в списке может оказаться место в другом районе — демо-жалобы
    // привязаны к дате, и порядок мест меняется день ото дня (с 12 окт первым стал участок в Байконуре)
    await page.evaluate(async () => {
      const d = await (await fetch("/api/civic/v2/heat?days=30&zoom=14")).json();
      const nura = new Set((d.data || d).items.filter((x) => x.district === "nura").map((x) => x.target.kind + ":" + x.target.id));
      const b = [...document.querySelectorAll(".r07-item")].find((x) => nura.has(x.dataset.key)) || document.querySelector(".r07-item");
      b.click();
    });
    await page.waitForTimeout(1300);
    await shot(page, `${tag}-3-focus`);
    if (!SHOTS_ONLY) {
      const f = await page.evaluate(() => {
        const sel = document.querySelector(".r07-badge--selected .r07-badge__inner");
        const other = [...document.querySelectorAll(".r07-badge:not(.r07-badge--selected):not([hidden]) .r07-badge__inner")];
        return { focusing: window.__map.getContainer().classList.contains("r07-focusing"), scale: sel ? getComputedStyle(sel).transform : "none",
          dim: other.map((e) => Number(getComputedStyle(e).opacity)), layer: window.__map.getPaintProperty("r07-seg", "line-opacity") };
      });
      await page.keyboard.press("Escape");
      await page.waitForTimeout(500);
      const after = await page.evaluate(() => ({ focusing: window.__map.getContainer().classList.contains("r07-focusing"),
        dim: [...document.querySelectorAll(".r07-badge:not([hidden]) .r07-badge__inner")].map((e) => Number(getComputedStyle(e).opacity)),
        layer: window.__map.getPaintProperty("r07-seg", "line-opacity"), card: !!document.querySelector(".r07-card") }));
      const p = [];
      if (!f.focusing) p.push("нет режима фокуса при выбранной цели");
      // значок 44 px, выбранный ×1.15 (≈ 51 px) и с тёмным кольцом (FINAL-3)
      const sc = Number((/matrix\(([\d.]+)/.exec(f.scale) || [])[1] || 1);
      if (!(sc >= 1.1)) p.push("выбранный значок не крупнее: " + f.scale);
      if (!f.dim.length || f.dim.some((o) => Math.abs(o - 0.4) > 0.02)) p.push("остальные значки не бледнеют до 40 %: " + f.dim.slice(0, 5).join(","));
      if (!Array.isArray(f.layer)) p.push("слои карты не бледнеют (нет выражения фокуса)");
      if (after.focusing || after.card || after.dim.some((o) => o < 0.99) || Array.isArray(after.layer)) p.push("Esc не сбросил фокус");
      check(`focus-${tag}`, p.concat(errors), { dimmed: f.dim.length });
    }
    await page.close();
    // --- подсказка при наведении: название · сколько человек · категория (только мышь) ---
    if (size === 1366) {
      ({ page, errors } = await open(browser, size, lang, "&view=nura&z=15.4"));
      const b = await page.evaluate(() => {
        const host = window.__map.getContainer().getBoundingClientRect();
        const bs = window.__heat.badges().filter((x) => x.mode === "full" && x.key.startsWith("object:") && x.cx > host.left + 60 && x.cx < host.left + 800 && x.cy > host.top + 80 && x.cy < host.bottom - 200);
        return bs[0] || null;
      });
      if (b) {
        await page.mouse.move(b.cx, b.cy);
        await page.waitForTimeout(400);
        await shot(page, `${tag}-4-tooltip`);
        if (!SHOTS_ONLY) {
          const tip = await page.evaluate(async (key) => {
            const el = document.querySelector(".r07-tip");
            const d = await (await fetch("/api/civic/v2/heat?days=30&zoom=15")).json();
            const it = d.items.find((x) => x.target.kind + ":" + x.target.id === key);
            return { text: el && !el.hidden ? el.textContent : "", label: document.documentElement.lang === "kk" ? it.target.label_kk : it.target.label_ru, count: it.count,
              title: document.querySelector(".r07-badge:hover")?.getAttribute("title") || null };
          }, b.key);
          const p = [];
          const parts = tip.text.split(" · ");
          if (parts[0] !== tip.label) p.push("в подсказке нет названия: " + tip.text);
          if (!parts[1] || !parts[1].includes(String(tip.count))) p.push("в подсказке нет числа людей: " + tip.text);
          if (!parts[2]) p.push("в подсказке нет категории: " + tip.text);
          if (tip.title) p.push("осталась системная подсказка title (двойная)");
          await page.mouse.move(5, 300);
          await page.waitForTimeout(200);
          if (await page.evaluate(() => { const el = document.querySelector(".r07-tip"); return el && !el.hidden; })) p.push("подсказка не прячется");
          check(`tooltip-${tag}`, p.concat(errors), { text: tip.text });
        }
      } else if (!SHOTS_ONLY) check(`tooltip-${tag}`, ["нет значка объекта для наведения"], null);
      await page.close();
    }
  }
  await browser.close();
  if (!SHOTS_ONLY) fs.writeFileSync(path.join(OUT, `readability-${LABEL}.json`), JSON.stringify(results, null, 1));
  const failed = results.filter((r) => !r.pass).length;
  console.log(SHOTS_ONLY ? "кадры сняты" : failed ? `FAIL ${failed}/${results.length}` : `PASS ${results.length}/${results.length}`);
  process.exit(failed ? 1 : 0);
})();
