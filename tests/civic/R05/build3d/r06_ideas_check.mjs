// R05 · идеи жителей ↔ настоящий API идей R06 (волна 2 п. 7; R06 claude/r14-R06 @ 57b7b53+, стенд serve_r14.py).
//
//   git worktree add --detach ../r06w origin/claude/r14-R06
//   cp -r web/civic/build3d ../r06w/web/civic/ && mkdir -p ../r06w/web/vendor/three && cp web/vendor/three/* ../r06w/web/vendor/three/
//   (cd ../r06w && python3 tests/civic/R06/round14/serve_r14.py --port 8620 > /tmp/ideas_stand.json &)
//   node tests/civic/R05/build3d/r06_ideas_check.mjs /tmp/ideas_stand.json
// Проверяет то, что делает R05, на данных R06 (без экрана «Идеи» R06 — его ещё нет):
//   1. GET /ideas → R05 читает все идеи (Core.normalizeIdea); слой «Идеи жителей» показывает голосование, «акимат
//      проверяет» и ставшие проектом (так просит слой R06: status=voting,project), отклонённые — нет;
//      модели — у идей с объектом каталога, у идеи без объекта — только метка «Идея · N»; нажатие → onIdeaSelect(id).
//   2. Эскиз R05 pickObject() → POST /ideas R06 принимает его как поле object (201, «на проверке»).
//   3. Проект из идеи (R06 кладёт idea {id, votes}) → в карточке проекта «По идее жителей · N голосов».
// Пароль сотрудника стенда не нужен (всё — путь жителя) и в отчёт не пишется.
// Отчёт: research/round-14-results/R05/runs/r06_ideas_check.json, скриншоты screens/r06_ideas_*.png.
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const OUT = path.join(ROOT, "research/round-14-results/R05");
const stand = JSON.parse((await readFile(process.argv[2] || "/tmp/ideas_stand.json", "utf8")).split("\n")[0]);
const ORIGIN = new URL(stand.url).origin;
const API = ORIGIN + "/api/civic/v2";
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
const getJson = async (url) => {
  const r = await fetch(url);
  const b = await r.json().catch(() => null);
  return { status: r.status, body: b && b.data !== undefined ? b.data : b }; // шлюз v2: {ok, data}
};
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const errors = [];
async function open(query, vp) {
  vp = vp || { width: 1366, height: 768 };
  const ctx = await browser.newContext(Object.assign({ viewport: vp }, vp.width < 640 ? { hasTouch: true, isMobile: true } : {}));
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(ORIGIN + "/civic/build3d/demo.html" + query);
  await page.waitForFunction(() => window.__b3d && window.__map && __map.loaded(), null, { timeout: 60000 });
  return page;
}
await mkdir(path.join(OUT, "screens"), { recursive: true });
let r06 = "unknown";
try {
  // 1. Список идей R06 → слой «Идеи жителей» R05.
  const list = await getJson(API + "/ideas");
  const items = (list.body && list.body.items) || [];
  const byStatus = items.reduce((m, x) => ((m[x.status] = (m[x.status] || 0) + 1), m), {});
  r06 = list.status === 200 ? "ideas API" : "нет /ideas (" + list.status + ")";
  check("r06_ideas_list_public_statuses", list.status === 200 && items.length >= 3 && !items.some((x) => x.status === "review" || x.status === "hidden"),
    { http: list.status, count: items.length, by_status: byStatus });
  const voting = items.filter((x) => x.status === "voting");
  const shown = items.filter((x) => ["voting", "checking", "project"].includes(x.status));
  const withKind = voting.filter((x) => x.object && x.object.kind && x.object.kind !== "lighting");
  for (const [w, h, lang] of [[1366, 768, "ru"], [375, 812, "kk"]]) {
    const phone = w < 640;
    const c = voting[0] ? voting[0].geometry.coordinates : [71.367, 51.136];
    const p = await open(`?store=api&r06=1&view=3d&projects=0&lang=${lang}&center=${c[0]},${c[1]}&zoom=16.4&pitch=50&bearing=-20`,
      Object.assign({ width: w, height: h }, {}));
    const n = await p.evaluate((list) => __b3d.setIdeas(list), items);
    await p.waitForFunction(() => __b3d.getState().three === "ready", null, { timeout: 30000 });
    await p.evaluate((list) => {
      const pts = list.map((x) => x.geometry.coordinates);
      const b = pts.reduce((a, q) => [Math.min(a[0], q[0]), Math.min(a[1], q[1]), Math.max(a[2], q[0]), Math.max(a[3], q[1])], [999, 999, -999, -999]);
      __map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: { top: 90, bottom: innerWidth < 640 ? 260 : 200, left: 60, right: 60 }, duration: 0, maxZoom: 17 });
    }, voting);
    await p.waitForFunction(() => !__map.isMoving(), null, { timeout: 10000 }).catch(() => {});
    await p.waitForTimeout(1500);
    const st = await p.evaluate(() => ({
      ideas: __b3d.getState().ideas,
      labels: [...document.querySelectorAll(".b3d-label--idea")].filter((b) => getComputedStyle(b).display !== "none").map((b) => ({ id: b.dataset.idea, text: b.textContent.trim() })),
      geometries: __b3d.getState().memory && __b3d.getState().memory.geometries,
    }));
    await p.screenshot({ path: path.join(OUT, "screens", `r06_ideas_layer_${w}_${lang}.png`) });
    // Нажатие на метку идеи → onIdeaSelect (карточку рисует R06).
    let picked = null;
    const lab = await p.$(`.b3d-label--idea[data-idea="${voting[0] && voting[0].id}"]`);
    if (lab) {
      await (phone ? lab.tap() : lab.click()).catch((e) => errors.push("tap: " + e.message.split("\n")[0]));
      await p.waitForTimeout(400);
      picked = await p.evaluate(() => window.__lastIdea && window.__lastIdea.id);
    }
    await p.context().close();
    const expectLabels = shown.map((x) => `Идея · ${x.votes}`).sort();
    check(`r06_ideas_layer_shows_public_ideas_${w}_${lang}`, n === shown.length && st.ideas === shown.length &&
      JSON.stringify(st.labels.map((l) => l.text).sort()) === JSON.stringify(expectLabels) && picked === (voting[0] && voting[0].id),
      { set: n, shown: shown.length, voting: voting.length, with_model: withKind.length, labels: st.labels, geometries: st.geometries, picked });
  }

  // 2. Эскиз R05 → новая идея R06 (житель): POST /ideas с object = результат pickObject.
  const p2 = await open("?store=api&r06=1&view=3d&projects=0&lang=ru&center=71.3655,51.1335&zoom=17.4&pitch=50&bearing=-20");
  await p2.evaluate(() => { window.__pk = null; __b3d.pickObject({ kind: "playground" }).then((r) => { window.__pk = { done: true, value: r }; }); });
  await p2.waitForFunction(() => __b3d.getState().mode === "placing" && !!__b3d.getState().ghost && __b3d.getState().three === "ready", null, { timeout: 30000 });
  // Свободное место: несколько точек над панелью, пока «Готово» не станет доступно.
  let ok = false;
  for (const [fx, fy] of [[0.5, 0.35], [0.4, 0.3], [0.6, 0.3], [0.45, 0.42], [0.55, 0.25]]) {
    const at = await p2.evaluate(([fx, fy]) => { const r = __map.getCanvas().getBoundingClientRect(); return [r.left + r.width * fx, r.top + r.height * fy]; }, [fx, fy]);
    await p2.mouse.move(at[0], at[1]);
    await p2.mouse.click(at[0], at[1]);
    await p2.waitForTimeout(500);
    if (await p2.evaluate(() => { const g = __b3d.getState().ghost; return !!(g && g.valid && g.valid.ok); })) { ok = true; break; }
  }
  await p2.screenshot({ path: path.join(OUT, "screens", "r06_ideas_sketch_1366_ru.png") });
  if (ok) await p2.click("[data-action=place]");
  else await p2.click("[data-action=cancel]");
  await p2.waitForFunction(() => window.__pk && window.__pk.done, null, { timeout: 10000 });
  const sketch = await p2.evaluate(() => window.__pk.value);
  const created = sketch ? await p2.evaluate(async ([api, s]) => {
    const r = await fetch(api + "/ideas", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "Детская площадка во дворе", description: "Проверка R05: эскиз из каталога 3D", geometry: s.geometry,
        object: s, device_id: "r05-check-" + Date.now().toString(36), lang: "ru" }) });
    const j = await r.json().catch(() => null);
    const b = j && j.data !== undefined ? j.data : j;
    return { status: r.status, item: b && (b.item || b) };
  }, [API, sketch]) : null;
  await p2.context().close();
  const it = created && created.item;
  check("r05_sketch_accepted_by_r06_as_idea_object", !!sketch && created && created.status === 201 && it && it.status === "review" && it.object && it.object.kind === "playground" &&
    Math.abs(it.object.geometry.coordinates[0] - sketch.geometry.coordinates[0]) < 1e-6,
    { sketch: sketch && { kind: sketch.kind, near_street: sketch.near_street, target: sketch.target && sketch.target.kind }, http: created && created.status,
      idea: it && { status: it.status, object: it.object && { kind: it.object.kind, rotation_deg: it.object.rotation_deg } } });

  // 3. Проект из идеи: R06 кладёт idea {id, votes} в предложение → строка «По идее жителей · N голосов».
  const props = await getJson(API + "/proposals");
  const fromIdea = ((props.body && props.body.items) || []).find((x) => x.idea && x.idea.id);
  const lines = {};
  for (const lang of ["ru", "kk"]) {
    if (!fromIdea) break;
    const g = fromIdea.geometry.type === "Point" ? fromIdea.geometry.coordinates : fromIdea.geometry.coordinates[Math.floor(fromIdea.geometry.coordinates.length / 2)];
    const p3 = await open(`?store=api&r06=1&view=auto&lang=${lang}&center=${g[0]},${g[1]}&zoom=16.8&pitch=0&bearing=0`);
    await p3.waitForFunction(() => __b3d.getState().phase === "ready", null, { timeout: 60000 });
    await p3.evaluate((id) => __b3d.select(id), fromIdea.id);
    // Строку рисует карточка R06 (BirgeProposals.showsIdea = true) или, без неё, сама карточка R05 (.b3d-pcard__idea).
    await p3.waitForSelector(".b3d-dock[data-state=card]", { timeout: 10000 }).catch(() => {});
    await p3.waitForTimeout(800);
    lines[lang] = await p3.evaluate(() => { const d = document.querySelector(".b3d-dock[data-state=card]"); if (!d) return null;
      const m = d.innerText.replace(/\s+/g, " ").match(/(По идее жителей|Тұрғындар идеясы бойынша) · \d+ [^\s·]+/); return m ? m[0] : null; });
    const own = await p3.evaluate(() => !!document.querySelector(".b3d-pcard__idea"));
    lines[lang + "_drawn_by"] = own ? "R05" : "R06";
    await p3.screenshot({ path: path.join(OUT, "screens", `r06_ideas_project_card_1366_${lang}.png`) });
    await p3.context().close();
  }
  const v = fromIdea && fromIdea.idea.votes;
  check("project_from_r06_idea_card_says_by_residents", !!fromIdea && lines.ru === `По идее жителей · ${v} ${v % 10 === 1 && v % 100 !== 11 ? "голос" : [2, 3, 4].includes(v % 10) && ![12, 13, 14].includes(v % 100) ? "голоса" : "голосов"}` &&
    lines.kk === `Тұрғындар идеясы бойынша · ${v} дауыс`, { proposal: fromIdea && { id: fromIdea.id, kind: fromIdea.kind, idea: fromIdea.idea }, lines });
} catch (e) {
  check("run", false, e.message.split("\n")[0]);
}
check("no_page_errors", errors.length === 0, errors.slice(0, 3));
await browser.close();
await mkdir(path.join(OUT, "runs"), { recursive: true });
await writeFile(path.join(OUT, "runs", "r06_ideas_check.json"), JSON.stringify({ generated_at: new Date().toISOString(), r06: (process.env.R06_SHA || "claude/r14-R06") + " · " + r06,
  checks: results }, null, 1) + "\n");
process.exit(results.every((r) => r.status === "PASS") ? 0 : 1);
