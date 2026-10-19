// R07 · видео перехода «В работе → Служба сообщила, что исправлено → Проверено жителями» на стенде R07 (synthetic, отдельный экземпляр
// devserver — его данные в памяти, после остановки сбрасываются). Статус меняется настоящим запросом стенда
// POST /complaints/{id}/status (как R09), затем событие birge:complaint — R07 перечитывает данные: цвет значка перетекает,
// одно кольцо, карточка меняет статус; затем ответ жителя «да» (POST /complaints/{id}/verify) — «проверено жителями».
//   node fixed_video.cjs <out-dir> [port] [lang] [noverify]
const { chromium } = require("/opt/node-tools/node_modules/playwright");
const OUT = process.argv[2], PORT = process.argv[3] || "8627", LANG = process.argv[4] || "ru", VERIFY = process.argv[5] !== "noverify";
const BASE = `http://127.0.0.1:${PORT}`;
(async () => {
  const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const ctx = await b.newContext({ viewport: { width: 1366, height: 768 }, recordVideo: { dir: OUT, size: { width: 1366, height: 768 } } });
  const p = await ctx.newPage();
  const errs = []; p.on("pageerror", (e) => errs.push(String(e).slice(0, 160)));
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await p.goto(`${BASE}/civic/heat/demo.html?lang=${LANG}&role=akimat&view=nura`, { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 45000 });
  await p.waitForTimeout(1500);
  // цель: открытая «в работе», видна сейчас на карте, с номерами жалоб, которые можно менять
  const pick = await p.evaluate(async (base) => {
    const map = window.__map; const c = map.getCenter(), z = map.getZoom();
    const res = await fetch(`${base}/api/civic/v2/heat?days=30&zoom=${Math.floor(z * 10) / 10}`).then((r) => r.json());
    const items = (res.data || res).items || [];
    const vis = (it) => { const pt = map.project(it.anchor); return pt.x > 60 && pt.x < 900 && pt.y > 120 && pt.y < 700; };
    const it = items.find((x) => x.state === "active" && x.status === "in_progress" && (x.open_ids || []).length && vis(x))
      || items.find((x) => x.state === "active" && (x.open_ids || []).length && vis(x));
    return it ? { target: it.target, ids: it.open_ids, label: it.target.label_ru, status: it.status, center: [c.lng, c.lat], z } : null;
  }, BASE);
  console.log("цель", JSON.stringify(pick && { label: pick.label, status: pick.status, ids: pick.ids.length }));
  if (!pick) { await ctx.close(); await b.close(); return; }
  await p.evaluate((t) => window.__heat.focusTarget(t.kind, t.id), pick.target);
  await p.waitForTimeout(3500);
  // служба отмечает «исправлено» все открытые жалобы цели — как кнопка R09 у сотрудника
  await p.evaluate(async ([base, ids, target]) => {
    for (const id of ids) await fetch(`${base}/api/civic/v2/complaints/${encodeURIComponent(id)}/status`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: "fixed" }) });
    window.dispatchEvent(new CustomEvent("birge:complaint", { detail: { type: "status", target } }));
  }, [BASE, pick.ids, pick.target]);
  await p.waitForTimeout(4500);
  const status = () => p.evaluate(() => { const c = document.querySelector(".r07-card .bk-status"); return c ? c.textContent.trim() : null; });
  console.log("служба сообщила:", await status());
  // житель отвечает «Да, исправлено» (двойник R09 POST /complaints/{id}/verify на стенде) — «Проверено жителями»
  if (VERIFY) {
    await p.evaluate(async ([base, id, target]) => {
      await fetch(`${base}/api/civic/v2/complaints/${encodeURIComponent(id)}/verify`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answer: "yes" }) });
      window.dispatchEvent(new CustomEvent("birge:complaint", { detail: { type: "status", target } }));
    }, [BASE, pick.ids[0], pick.target]);
    await p.waitForTimeout(4500);
    console.log("проверено:", await status());
  }
  console.log("ошибки", errs.length ? errs : 0);
  await ctx.close();
  await b.close();
})();
