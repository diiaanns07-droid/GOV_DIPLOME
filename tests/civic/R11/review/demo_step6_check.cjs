/*
 * R11 · шаг 6 DEMO_SCRIPT: карточка остановки «Хан Шатыр» у сотрудника (ҚАЗ, 1366) — есть ли «Взять в работу» и
 * «Отметить исправленным» (R07 B-037: у мест только с примерами кнопок нет — у «Хан Шатыр» должны быть).
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/demo_step6_check.cjs http://127.0.0.1:<порт>/ <файл-пароля> <кадр.png>
 */
const fs = require("fs");
const { chromium } = require("playwright");
(async () => {
  const pw = fs.readFileSync(process.argv[3], "utf8").trim();
  const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const p = await b.newPage({ viewport: { width: 1366, height: 768 } });
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await p.addInitScript(() => { localStorage.setItem("birge.lang", "kk"); localStorage.setItem("birge.mode", "akimat"); });
  await p.goto(process.argv[2]);
  await p.waitForFunction(() => window.CivicShell && window.CivicShell.heat && window.CivicShell.heat.state && window.CivicShell.heat.state().status === "ready", null, { timeout: 45000 }); await p.waitForTimeout(1200);
  await p.evaluate((pw) => window.CivicShell.api.login("operator", pw), pw); await p.waitForTimeout(800);
  const t = await p.evaluate(async () => { const d = await (await fetch("/api/civic/v2/heat?days=30&zoom=16")).json(); const it = (d.data || d).items.find((x) => /Хан Шатыр/.test(x.target.label_ru || "")); return it ? { kind: it.target.kind, id: it.target.id, label: it.target.label_kk, count: it.count, open: (it.open_ids || []).length } : null; });
  console.log("Хан Шатыр:", JSON.stringify(t));
  if (t) {
    await p.evaluate((t) => window.CivicShell.heat.focusTarget(t.kind, t.id), t); await p.waitForTimeout(2000);
    const r = await p.evaluate(() => ({ take: !!document.querySelector("[data-act='take']"), fixed: !!document.querySelector("[data-act='fixed']"), example: (document.querySelector(".r07-note--demo") || {}).textContent || null }));
    console.log("кнопки:", JSON.stringify(r));
    await p.screenshot({ path: process.argv[4] });
  }
  await b.close();
})();
