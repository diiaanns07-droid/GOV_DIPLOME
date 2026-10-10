// R05 · 3D-превью ↔ настоящий сервер предложений R06 (его стенд tests/civic/R06/round14/serve_r14.py).
//
// Как запустить (из корня ЭТОЙ ветки; стенд R06 — из его ветки, к нему подкладываются файлы R05):
//   git worktree add --detach ../r06 origin/claude/round-14-r06
//   cp -r web/civic/build3d ../r06/web/civic/ && mkdir -p ../r06/web/vendor/three && cp web/vendor/three/* ../r06/web/vendor/three/
//   (cd ../r06 && python3 tests/civic/R06/round14/serve_r14.py --port 8616 > /tmp/stand.json &)
//   node tests/civic/R05/build3d/r06_stand_check.mjs /tmp/stand.json
// Проверяет: список с сервера (демо R06), вход сотрудника, «Поставить» (CSRF; контекст 3D near_street/target —
// R06 поставки 2 его хранит, поставки 1 отвечает 422 и клиент повторяет базовым телом), голос с device_id,
// карточку R06 внутри панели 3D, «Удалить» = withdraw, «Отменить» (поставка 2 — то же предложение с голосом),
// «Войдите…» без сессии. Поколение R06 определяется по ответу на первый POST и пишется в отчёт.
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
    if (r.url().includes("/api/")) page._req.push({ m: r.method(), u: r.url().replace(ORIGIN, ""), body: r.postData(), r });
  });
  await page.goto(ORIGIN + "/civic/build3d/demo.html" + query);
  await page.waitForFunction(() => window.__b3d && window.__b3d.getState().phase === "ready", null, { timeout: 60000 });
  await page.waitForFunction(() => __map.loaded() && !__b3d.getState().animating, null, { timeout: 60000 });
  return page;
}
// Перед снимком — дождаться конца анимаций интерфейса (карточка выезжает 240 мс; на программном WebGL кадры редкие).
const settle = (p) =>
  p.waitForFunction(() => !document.getAnimations().some((a) => a.playState === "running" || a.pending), null, { timeout: 5000 }).catch(() => {});
const screenOf = (p, ll) =>
  p.evaluate((ll) => {
    const q = __map.project(ll);
    const r = __map.getCanvas().getBoundingClientRect();
    return [q.x + r.left, q.y + r.top];
  }, ll);
await mkdir(path.join(OUT, "screens"), { recursive: true });
const PLACE_AT = [71.4009, 51.1283]; // в верхней половине вида (не под панелью каталога), свободное место
let generation = "unknown"; // поколение API R06: delivery1 (3d10f7d/7031afa) | delivery2 (d043e7b+)
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
  const isCreate = (r) => r.m === "POST" && /\/api\/civic\/v2\/proposals$/.test(r.u.replace(/\?.*$/, ""));
  const posts = p._req.filter(isCreate);
  const statusOf = async (r) => {
    const res = await r.r.response();
    return res ? res.status() : 0;
  };
  const firstStatus = await statusOf(posts[0]);
  const first = JSON.parse(posts[0].body);
  const body = JSON.parse(posts[posts.length - 1].body);
  generation = firstStatus === 201 ? "delivery2" : "delivery1";
  check("placed_where_clicked", Math.abs(body.geometry.coordinates[0] - PLACE_AT[0]) < 2e-5 && Math.abs(body.geometry.coordinates[1] - PLACE_AT[1]) < 2e-5, body.geometry.coordinates);
  check("create_sends_3d_context", typeof first.near_street === "string" && first.near_street.length > 0 && !("status" in first) && !("district" in first), first);
  if (generation === "delivery2") {
    check("r06_d2_accepts_context_first_try", posts.length === 1 && firstStatus === 201, { posts: posts.length, firstStatus });
  } else {
    check("r06_d1_rejects_context_then_basic_fields", posts.length === 2 && (firstStatus === 422 || firstStatus === 400) &&
      Object.keys(body).sort().join(",") === "demo,geometry,kind,planned_year,rotation_deg", { firstStatus, retry: body });
  }
  const created = (await p.evaluate(() => __b3d.getState())).proposals.find((q) => !before.includes(q.id));
  check("created_on_server_with_year_and_rotation", created.year === 2027 && created.rotation_deg === body.rotation_deg && created.status === "proposal", created);
  if (generation === "delivery2") check("r06_d2_stores_near_street", created.near_street === first.near_street, { sent: first.near_street, got: created.near_street });
  // Карточка: открыть щелчком по самой модели (не по подписи).
  const g = await p.evaluate((id) => __b3d._project(id, [0, 0, 1]), created.id);
  const cr = await p.evaluate(() => { const r = __map.getCanvas().getBoundingClientRect(); return [r.left, r.top]; });
  await p.mouse.click(cr[0] + g.x, cr[1] + g.y);
  await p.waitForSelector(".b3d-r06 .r06-card", { timeout: 10000 });
  check("r06_card_inside_3d_panel", true, await p.textContent(".b3d-r06 .bk-card__title"));
  if (await p.$('.b3d-r06 .r06-vote__btn[data-value="1"]')) {
    // R06 поставки 1: акимат голосует в карточке.
    await p.click('.b3d-r06 .r06-vote__btn[data-value="1"]');
    await p.waitForFunction(() => document.querySelector('.b3d-r06 .r06-vote__btn[data-value="1"][aria-pressed="true"]'), null, { timeout: 15000 });
    const voteReq = p._req.find((r) => /\/vote$/.test(r.u));
    check("vote_through_r06_card_with_device_id", !!voteReq && /"device_id":"dev-[0-9a-f]{32}"/.test(voteReq.body), voteReq && voteReq.body);
  } else {
    // R06 поставки 2 (UX_REVIEW день 3, п. 16): у акимата голоса числами и «Одобрить / Отклонить»; голос — как житель.
    const akimatCard = await p.evaluate(() => ({ tally: !!document.querySelector(".b3d-r06 .r06-tally"), approve: !!document.querySelector(".b3d-r06 [data-action=approve]"),
      del: !!document.querySelector(".b3d [data-action=delete]") }));
    check("akimat_r06_card_tally_approve_and_3d_delete", akimatCard.tally && akimatCard.approve && akimatCard.del, akimatCard);
    const voted = await p.evaluate(async (id) => {
      const r = await fetch("/api/civic/v2/proposals/" + id + "/vote", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value: 1, device_id: localStorage.getItem("birge.device_id") }), credentials: "same-origin" });
      await __b3d.refresh();
      return r.status;
    }, created.id);
    check("vote_with_device_id_then_refresh", voted === 200, voted);
  }
  const st = await p.evaluate((id) => __b3d.getState().proposals.find((q) => q.id === id), created.id);
  check("vote_synced_to_3d_object", st.votes_up === 1 && st.my_vote === 1, { up: st.votes_up, my: st.my_vote });
  await settle(p);
  await p.screenshot({ path: path.join(OUT, "screens", "r06_1366_ru_card.png") });
  await p.click("[data-action=delete]");
  await p.waitForFunction((id) => !__b3d.getState().proposals.some((q) => q.id === id), created.id, { timeout: 15000 });
  check("delete_is_withdraw", p._req.some((r) => r.m === "POST" && r.u.endsWith("/proposals/" + created.id + "/withdraw")), p._req.filter((r) => r.m !== "GET").map((r) => r.m + " " + r.u));
  // «Отменить» в тосте: R06 поставки 2 возвращает ТО ЖЕ предложение (id и голос), поставки 1 — новое без голосов.
  await p.click(".bk-toast [data-action=undo]");
  await p.waitForFunction((n) => __b3d.getState().proposals.length === n && !__b3d.getState().animating, before.length + 1, { timeout: 15000 });
  const back = (await p.evaluate(() => __b3d.getState())).proposals.find((q) => !before.includes(q.id));
  const restorePost = p._req.filter(isCreate).slice(posts.length)[0];
  if (generation === "delivery2") {
    check("undo_restores_same_proposal_with_vote", back.id === created.id && back.votes_up === 1 && JSON.parse(restorePost.body).id === created.id,
      { id: back.id, votes_up: back.votes_up });
  } else {
    check("undo_recreates_on_old_r06", !!back && back.kind === "stop" && back.status === "proposal", { id: back && back.id, votes_up: back && back.votes_up });
  }
  // Снова «Удалить» → после перезагрузки снятого проекта нет (R06 не показывает withdrawn), остальные на месте.
  await p.evaluate((id) => __b3d.select(id), back.id);
  await p.waitForSelector("[data-action=delete]", { timeout: 10000 });
  await p.click("[data-action=delete]");
  await p.waitForFunction((id) => !__b3d.getState().proposals.some((q) => q.id === id), back.id, { timeout: 15000 });
  await p.reload();
  await p.waitForFunction(() => window.__b3d && window.__b3d.getState().phase === "ready", null, { timeout: 60000 });
  const after = (await p.evaluate(() => __b3d.getState())).proposals.map((q) => q.id);
  check("withdrawn_gone_after_reload", !after.includes(created.id) && !after.includes(back.id) && after.length === before.length, { before: before.length, after: after.length });
  await p.context().close();

  // 3. Телефон, казахский: карточка R06 в панели 3D.
  p = await open("?store=api&r06=1&lang=kk&role=resident&center=71.4012,51.1278&zoom=17.2&pitch=55&bearing=-20", { width: 375, height: 812 });
  const firstId = (await p.evaluate(() => __b3d.getState())).proposals[0].id;
  await p.evaluate((id) => __b3d.select(id), firstId);
  await p.waitForSelector(".b3d-r06 .r06-card", { timeout: 10000 });
  const hasApprove = !!(await p.$(".b3d-r06 [data-action=approve]"));
  const hasDelete = !!(await p.$("[data-action=delete]"));
  await settle(p);
  await p.screenshot({ path: path.join(OUT, "screens", "r06_375_kk_resident_card.png") });
  check("resident_r06_card_no_staff_actions", !hasApprove && !hasDelete, { hasApprove, hasDelete });
  await p.context().close();
} catch (e) {
  check("run", false, e.message.split("\n")[0]);
}
check("no_page_errors", errors.length === 0, errors.slice(0, 3));
await browser.close();
await mkdir(path.join(OUT, "runs"), { recursive: true });
// Отчёт: поставка 2 R06 — r06_stand_check.json, поставка 1 — r06_stand_check_r06d1.json (R06_SHA — какой код стенда).
const report = generation === "delivery1" ? "r06_stand_check_r06d1.json" : "r06_stand_check.json";
await writeFile(path.join(OUT, "runs", report), JSON.stringify({ generated_at: new Date().toISOString(),
  stand: { url: stand.url, r06_sha: process.env.R06_SHA || null, r06_generation: generation }, checks: results }, null, 1) + "\n");
process.exit(results.every((r) => r.status === "PASS") ? 0 : 1);
