const { chromium } = require("playwright");
const OUT = process.argv[2];
const BASE = process.argv[3] || "http://127.0.0.1:8655";   // адрес стенда сборки (RUN.txt §3)
(async () => {
  const b = await chromium.launch();
  const out = [];
  for (const [w, h] of [[1366, 768], [375, 812]]) {
    const p = await b.newPage({ viewport: { width: w, height: h } });
    const errors = [];
    p.on("pageerror", (e) => errors.push(String(e)));
    await p.goto(BASE + "/");
    await p.evaluate(async () => {
      await fetch("/api/civic/v1/session/login", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "operator", password: "demo-password-2026" }) });
      localStorage.setItem("birge.mode", "akimat");
    });
    await p.goto(BASE + "/?r=" + w + "#analyst");   // новый адрес — настоящая перезагрузка, сессия видна оболочке
    await p.waitForTimeout(2500);
    const reg = await p.evaluate(() => ({ more: window.BirgeShell && window.BirgeShell.moreItems(), section: window.BirgeShell && window.BirgeShell.section,
      mounted: !!document.querySelector(".ba"), title: document.querySelector("#birge-screen-title") && document.querySelector("#birge-screen-title").textContent }));
    out.push({ w, reg });
    if (!reg.mounted) { out.push({ w, err: "not mounted", errors }); await p.screenshot({ path: OUT + "/shell_fail_" + w + ".png" }); continue; }
    await p.fill("#ba-input", "Где в Нуре больше всего жалоб на снег за неделю и какие службы отстают?");
    await p.press("#ba-input", "Enter");
    await p.waitForSelector(".ba-answer", { timeout: 15000 });
    await p.waitForTimeout(400);
    await p.screenshot({ path: OUT + "/shell_answer_" + w + "_ru.png" });
    await p.click('.ba-actions [data-action="map"]');
    await p.waitForTimeout(3500);
    const after = await p.evaluate(() => ({ section: window.BirgeShell.section, hash: location.hash,
      card: !!document.querySelector(".r07-card, .r07-panel [data-key], .r07-sel, [class*='r07-card']"),
      cardText: (document.querySelector("[class*='r07-card'], .r07-panel") || {}).textContent || "" }));
    out.push({ w, after: { section: after.section, hash: after.hash, card: after.card, cardText: after.cardText.slice(0, 160) }, errors });
    await p.screenshot({ path: OUT + "/shell_map_" + w + "_ru.png" });
    // «Где копаем дважды?» (на 375 — по-казахски): строки — улицы; вторая строка открывает свой конфликт в «Календаре
    // работ» R12 (BirgeWorksCalendar.openConflict) — на карточке конфликта та же улица.
    const lang = w === 375 ? "kk" : "ru";
    await p.goto(BASE + "/?r=" + w + "c&lang=" + lang + "#analyst");
    await p.waitForTimeout(2500);
    await p.fill("#ba-input", lang === "kk" ? "Жұмыстар қайшылығы қайда?" : "Где копаем дважды?");
    await p.press("#ba-input", "Enter");
    await p.waitForSelector(".ba-items", { timeout: 15000 });
    await p.waitForTimeout(400);
    const rows = p.locator(".ba-items .ba-item");
    const row = ((await rows.nth(1).locator(".bk-list__title").textContent()) || "").trim();
    await p.mouse.move(1, h - 1);   // курсор не над строкой — на кадре нет подсветки наведения
    await p.screenshot({ path: OUT + "/shell_conflicts_" + w + "_" + lang + ".png" });
    await rows.nth(1).click();
    await p.waitForTimeout(2500);
    const opened = await p.evaluate(() => ({ section: window.BirgeShell.section, hash: location.hash,
      text: document.body.innerText.slice(0, 4000) }));
    out.push({ w, conflict: { row, section: opened.section, hash: opened.hash, street_on_screen: !!row && opened.text.includes(row) },
      errors });
    await p.screenshot({ path: OUT + "/shell_conflict_opened_" + w + "_" + lang + ".png" });
    await p.close();
  }
  console.log(JSON.stringify(out, null, 1));
  await b.close();
})().catch((e) => { console.error(e); process.exit(2); });
