/*
 * R08 · «Сегодня в Астане» попиксельно против эталона: строки текста карточки .sum из REFERENCE.html (вариант A, кадр
 * «Главная акимата», 1366 без масштаба) и сводки R08 на стенде (/civic/akim/today.html, ru) — положение каждой строки
 * от левого верхнего угла карточки, кегль, начертание, цвет. Числа и названия мест на стенде — из данных, а не эталона,
 * поэтому сверяются места строк, а не слова.
 *
 *   git show origin/claude/round-14-package:research/round-14/design/REFERENCE.html > /tmp/REFERENCE.html
 *   NODE_PATH=$(npm root -g) node tests/civic/R08/today_ref_compare.cjs /tmp/REFERENCE.html http://127.0.0.1:8508 [допуск_px]
 *
 * Норма: карточка 388 × 325 ± допуск, каждая строка текста — |dx|, |dy| ≤ допуск (по умолчанию 1), кегль и начертание
 * совпадают. Цвет цифр на плашках мест не сверяется (сознательное отличие R08: контраст, STATUS.md).
 * С ui-kit R11 ≥ a2342cc1 (настоящая граница стекла 1 px) — 0 px; со старым ui-kit — сдвиг на 1 px (нет границы).
 */
"use strict";
const { chromium } = require("playwright");

function collect(sel) {
  const card = document.querySelector(sel);
  const r = card.getBoundingClientRect();
  const out = [];
  const walk = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walk.nextNode())) {
    if (!n.textContent.trim()) continue;
    const el = n.parentElement;
    if (!el.getClientRects().length || el.closest(".bk-sr-only")) continue;
    const cs = getComputedStyle(el);
    const rg = document.createRange();
    rg.selectNodeContents(n);
    const b = rg.getBoundingClientRect();
    if (b.width < 2) continue;
    out.push({ t: n.textContent.trim().slice(0, 18), x: Math.round(b.left - r.left), y: Math.round(b.top - r.top), fs: cs.fontSize, fw: cs.fontWeight, c: cs.color, badge: !!el.closest(".cnt, .akim-today__cnt") });
  }
  return { w: Math.round(r.width), h: Math.round(r.height), out };
}

(async () => {
  const [refPath, base = "http://127.0.0.1:8508", tolArg] = process.argv.slice(2);
  if (!refPath) {
    console.error("укажите путь к REFERENCE.html");
    process.exit(2);
  }
  const tol = Number(tolArg || 1);
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 1366, height: 768 } })).newPage();
  await p.goto("file://" + require("path").resolve(refPath));
  await p.evaluate(() => {
    const st = document.getElementById("stage");
    st.style.width = "1366px";
    st.querySelectorAll(".frame").forEach((f) => (f.style.transform = "none"));
  });
  const A = await p.evaluate(collect, '.frame[data-f="home"] .sum');
  const q = await (await b.newContext({ viewport: { width: 1366, height: 768 } })).newPage();
  await q.addInitScript(() => { try { localStorage.setItem("birge.lang", "ru"); } catch (e) { /* */ } });
  await q.goto(base.replace(/\/$/, "") + "/civic/akim/today.html?lang=ru");
  await q.waitForSelector("#today[data-state=ok]");
  await q.waitForTimeout(400);
  const B = await q.evaluate(collect, "#today");
  await b.close();

  let fails = 0;
  const cardOk = A.w === B.w && Math.abs(A.h - B.h) <= tol;
  if (!cardOk) fails++;
  console.log(`${cardOk ? "PASS" : "FAIL"} карточка: эталон ${A.w} × ${A.h}, R08 ${B.w} × ${B.h}`);
  if (A.out.length !== B.out.length) {
    fails++;
    console.log(`FAIL строк текста: эталон ${A.out.length}, R08 ${B.out.length}`);
  }
  let worst = 0;
  for (let i = 0; i < Math.min(A.out.length, B.out.length); i++) {
    const a = A.out[i], c = B.out[i];
    const dx = c.x - a.x, dy = c.y - a.y;
    worst = Math.max(worst, Math.abs(dx), Math.abs(dy));
    const ok = Math.abs(dx) <= tol && Math.abs(dy) <= tol && a.fs === c.fs && a.fw === c.fw && (a.badge || a.c === c.c);
    if (!ok) fails++;
    console.log(`${ok ? "PASS" : "FAIL"} ${String(i).padStart(2)} «${a.t}» ↔ «${c.t}»: dx ${dx}, dy ${dy}, ${c.fs}/${c.fw}${a.badge || a.c === c.c ? "" : ` цвет ${c.c} ≠ ${a.c}`}`);
  }
  console.log(`\nхудшее смещение ${worst} px, допуск ${tol} px — ${fails ? fails + " FAIL" : "PASS"}`);
  process.exit(fails ? 1 : 0);
})().catch((e) => {
  console.error(e);
  process.exit(2);
});
