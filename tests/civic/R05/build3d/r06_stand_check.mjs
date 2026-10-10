// R05 · 3D-превью ↔ настоящий сервер предложений R06 (его стенд tests/civic/R06/round14/serve_r14.py).
//
// Как запустить (из корня ЭТОЙ ветки; стенд R06 — из его ветки, к нему подкладываются файлы R05):
//   git worktree add --detach ../r06 origin/claude/round-14-r06
//   cp -r web/civic/build3d ../r06/web/civic/ && mkdir -p ../r06/web/vendor/three && cp web/vendor/three/* ../r06/web/vendor/three/
//   (cd ../r06 && python3 tests/civic/R06/round14/serve_r14.py --port 8616 > /tmp/stand.json &)
//   node tests/civic/R05/build3d/r06_stand_check.mjs /tmp/stand.json
// Проверяет: список с сервера (демо R06), вход сотрудника, «Поставить» (POST только с полями R06, CSRF),
// голос с device_id, карточку R06 внутри панели 3D, «Удалить» = withdraw, «Войдите…» без сессии.
// Отчёт: research/round-14-results/R05/runs/r06_stand_check.json, скриншоты screens/r06_*.png.
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const OUT = path.join(ROOT, "research/round-14-results/R05");
const stand = JSON.parse((await readFile(process.argv[2] || "/tmp/stand.json", "utf8")).split("\n")[0]);
const ORIGIN = new URL(stand.url).origin;
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
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const errors = [];
async function open(query, vp) {
  const ctx = await browser.newContext({ viewport: vp || { width: 1366, height: 768 } });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  page._req = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/")) page._req.push({ m: r.method(), u: r.url().replace(ORIGIN, ""), body: r.postData() });
  });
  await page.goto(ORIGIN + "/civic/build3d/demo.html" + query);
  await page.waitForFunction(() => window.__b3d && window.__b3d.getState().phase === "ready", null, { timeout: 60000 });
  await page.waitForFunction(() => __map.loaded() && !__b3d.getState().animating, null, { timeout: 60000 });
  return page;
}
const screenOf = (p, ll) =>
  p.evaluate((ll) => {
    const q = __map.project(ll);
    const r = __map.getCanvas().getBoundingClientRect();
    return [q.x + r.left, q.y + r.top];
  }, ll);
await mkdir(path.join(OUT, "screens"), { recursive: true });
const PLACE_AT = [71.4009, 51.1283]; // в верхней половине вида (не под панелью каталога), свободное место
try {
  // 1. Без входа: список с сервера R06, «Поставить» → «Войдите как сотрудник акимата».
  let p = await open("?store=api&r06=1&center=71.4012,51.1278&zoom=17.4&pitch=58&bearing=-20");
  let s = await p.evaluate(() => __b3d.getState());
  check("list_from_r06_server", s.storeMode === "api" && s.count >= 5, { storeMode: s.storeMode, count: s.count, kinds: s.proposals.map((x) => x.kind + ":" + x.year + ":" + (x.demo ? "demo" : "")) });
  check("list_sends_device_id_no_bbox", p._req.some((r) => r.m === "GET" && /\/api\/civic\/v2\/proposals\?device_id=dev-[0-9a-f]{32}$/.test(r.u)), p._req.filter((r) => r.m === "GET").map((r) => r.u));
  await p.click(".b3d-card[data-kind=stop]");
  let [x, y] = await screenOf(p, PLACE_AT);
  await p.mouse.move(x, y);
  await p.mouse.click(x, y);
  await p.click("[data-action=place]");
  await p.waitForSelector(".bk-toast--error", { timeout: 15000 });
  const noStaff = await p.textContent(".bk-toast--error");
  check("create_without_staff_says_login", /Войдите как сотрудник/.test(noStaff), noStaff.trim());
  await p.context().close();

  // 2. Сотрудник: вход, «Поставить» (POST с полями R06 и CSRF), карточка R06, голос, «Удалить» = withdraw.
  p = await open("?store=api&r06=1&center=71.4012,51.1278&zoom=17.4&pitch=58&bearing=-20");
  const login = await p.evaluate(async (cred) => {
    const r = await fetch("/api/civic/v1/session/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cred), credentials: "same-origin" });
    return r.status;
  }, { username: stand.username, password: stand.password });
  check("staff_login", login === 200, login);
  const before = (await p.evaluate(() => __b3d.getState())).proposals.map((q) => q.id);
  await p.click(".b3d-card[data-kind=stop]");
  [x, y] = await screenOf(p, PLACE_AT);
  await p.mouse.move(x, y);
  await p.mouse.click(x, y);
  await p.click("[data-action=place]");
  await p.waitForFunction((b) => __b3d.getState().proposals.some((q) => !b.includes(q.id) && /^p-[0-9a-f]{12}$/.test(q.id)) && !__b3d.getState().animating, before, { timeout: 30000 });
  const post = p._req.find((r) => r.m === "POST" && /\/api\/civic\/v2\/proposals$/.test(r.u.replace(/\?.*$/, "")));
  const body = JSON.parse(post.body);
  check("placed_where_clicked", Math.abs(body.geometry.coordinates[0] - PLACE_AT[0]) < 2e-5 && Math.abs(body.geometry.coordinates[1] - PLACE_AT[1]) < 2e-5, body.geometry.coordinates);
  check("create_posts_only_r06_fields", Object.keys(body).sort().join(",") === "demo,geometry,kind,planned_year,rotation_deg", body);
  const created = (await p.evaluate(() => __b3d.getState())).proposals.find((q) => !before.includes(q.id));
  check("created_on_server_with_year_and_rotation", created.year === 2027 && created.rotation_deg === body.rotation_deg && created.status === "proposal", created);
  // Карточка: открыть щелчком по самой модели (не по подписи).
  const g = await p.evaluate((id) => __b3d._project(id, [0, 0, 1]), created.id);
  const cr = await p.evaluate(() => { const r = __map.getCanvas().getBoundingClientRect(); return [r.left, r.top]; });
  await p.mouse.click(cr[0] + g.x, cr[1] + g.y);
  await p.waitForSelector(".b3d-r06 .r06-card", { timeout: 10000 });
  check("r06_card_inside_3d_panel", true, await p.textContent(".b3d-r06 .bk-card__title"));
  await p.click('.b3d-r06 .r06-vote__btn[data-value="1"]');
  await p.waitForFunction(() => document.querySelector('.b3d-r06 .r06-vote__btn[data-value="1"][aria-pressed="true"]'), null, { timeout: 15000 });
  const voteReq = p._req.find((r) => /\/vote$/.test(r.u));
  check("vote_through_r06_card_with_device_id", !!voteReq && /"device_id":"dev-[0-9a-f]{32}"/.test(voteReq.body), voteReq && voteReq.body);
  const st = await p.evaluate((id) => __b3d.getState().proposals.find((q) => q.id === id), created.id);
  check("vote_synced_to_3d_object", st.votes_up === 1 && st.my_vote === 1, { up: st.votes_up, my: st.my_vote });
  await p.screenshot({ path: path.join(OUT, "screens", "r06_1366_ru_card.png") });
  await p.click("[data-action=delete]");
  await p.waitForFunction((id) => !__b3d.getState().proposals.some((q) => q.id === id), created.id, { timeout: 15000 });
  check("delete_is_withdraw", p._req.some((r) => r.m === "POST" && r.u.endsWith("/proposals/" + created.id + "/withdraw")), p._req.filter((r) => r.m !== "GET").map((r) => r.m + " " + r.u));
  // После перезагрузки снятого проекта нет (R06 не показывает withdrawn), остальные на месте.
  await p.reload();
  await p.waitForFunction(() => window.__b3d && window.__b3d.getState().phase === "ready", null, { timeout: 60000 });
  const after = (await p.evaluate(() => __b3d.getState())).proposals.map((q) => q.id);
  check("withdrawn_gone_after_reload", !after.includes(created.id) && after.length === before.length, { before: before.length, after: after.length });
  await p.context().close();

  // 3. Телефон, казахский: карточка R06 в панели 3D.
  p = await open("?store=api&r06=1&lang=kk&role=resident&center=71.4012,51.1278&zoom=17.2&pitch=55&bearing=-20", { width: 375, height: 812 });
  const firstId = (await p.evaluate(() => __b3d.getState())).proposals[0].id;
  await p.evaluate((id) => __b3d.select(id), firstId);
  await p.waitForSelector(".b3d-r06 .r06-card", { timeout: 10000 });
  const hasApprove = !!(await p.$(".b3d-r06 [data-action=approve]"));
  const hasDelete = !!(await p.$("[data-action=delete]"));
  await p.screenshot({ path: path.join(OUT, "screens", "r06_375_kk_resident_card.png") });
  check("resident_r06_card_no_staff_actions", !hasApprove && !hasDelete, { hasApprove, hasDelete });
  await p.context().close();
} catch (e) {
  check("run", false, e.message.split("\n")[0]);
}
check("no_page_errors", errors.length === 0, errors.slice(0, 3));
await browser.close();
await mkdir(path.join(OUT, "runs"), { recursive: true });
await writeFile(path.join(OUT, "runs", "r06_stand_check.json"), JSON.stringify({ generated_at: new Date().toISOString(), stand: { url: stand.url }, checks: results }, null, 1) + "\n");
process.exit(results.every((r) => r.status === "PASS") ? 0 : 1);
