// R06 раунд 14 · клиент 3D R05 (web/civic/build3d/build3d-core.js, createApiStore) против настоящего API R06.
//
//   git show origin/claude/r14-R05:web/civic/build3d/build3d-core.js > /tmp/build3d-core.js   # проверено на 7f42cb3
//   python3 tests/civic/R06/round14/serve_r14.py --port 8616 > /tmp/stand.json &
//   node tests/civic/R06/round14/r05_client_r14.cjs /tmp/stand.json /tmp/build3d-core.js
//
// Клиент R05 @ 7f42cb3: тело POST — {kind, geometry, rotation_deg, planned_year, demo}; CSRF сотрудника берёт сам
// из GET /api/civic/v1/session; «Удалить» — POST /proposals/{id}/withdraw, при 404/405 — запасной DELETE;
// «Отменить» — повторный POST той же копии (новый id). Ответ понимает и с конвертом R06 {ok, data}, и без него
// (шлюз R01 CivicV2Gateway отдаёт data как есть) — проверяем оба вида: «r06» (стенд напрямую) и «r01» (конверт снят).
"use strict";
const fs = require("fs");

const stand = JSON.parse(fs.readFileSync(process.argv[2], "utf8").split("\n")[0]);
const core = require(process.argv[3]);
const base = new URL(stand.url).origin;
const results = [];
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail ? " — " + detail : ""));
};

// Браузер на том же адресе: cookie сессии (если есть), Origin; mode "r01" снимает конверт, как шлюз R01;
// noWithdraw — сервер без маршрута withdraw (проверка запасного DELETE).
function browserFetch(cookie, mode, noWithdraw) {
  return (url, init) => {
    const target = new URL(url, base);
    if (noWithdraw && /\/withdraw$/.test(target.pathname)) {
      return Promise.resolve(new Response('{"error":"not_found"}', { status: 404, headers: { "Content-Type": "application/json" } }));
    }
    const headers = Object.assign({}, (init && init.headers) || {}, { Origin: base });
    if (cookie) headers.Cookie = cookie;
    return fetch(target, Object.assign({}, init, { headers })).then(async (res) => {
      const text = await res.text();
      let body = null;
      try { body = text ? JSON.parse(text) : null; } catch (e) { body = null; }
      const out = mode === "r01" && body && body.ok === true && "data" in body ? JSON.stringify(body.data) : text;
      return new Response(out, { status: res.status, headers: { "Content-Type": "application/json" } });
    });
  };
}

(async () => {
  const login = await fetch(base + "/api/civic/v1/session/login", {
    method: "POST", headers: { "Content-Type": "application/json", Origin: base },
    body: JSON.stringify({ username: stand.username, password: stand.password }),
  });
  const cookie = (login.headers.get("set-cookie") || "").split(";")[0];
  check("вход сотрудника на стенде", login.status === 200 && cookie, String(login.status));
  const deviceId = "dev-" + "0123456789abcdef".repeat(2);  // формат R05/R06: "dev-" + 32 hex

  for (const mode of ["r06", "r01"]) {
    const opts = (c, noWithdraw) => ({ prefix: base + "/api/civic/v2", fetch: browserFetch(c, mode, noWithdraw), deviceId });
    const anon = core.createApiStore(opts(null));
    const staff = core.createApiStore(opts(cookie));
    const staffNoWithdraw = core.createApiStore(opts(cookie, true));

    const list = await anon.list([71.30, 51.10, 71.40, 51.16]);
    check(mode + ": list(bbox) → предложения в Нуре", list.length >= 5 && list.every((p) => p.id && p.kind), String(list.length));

    const draft = { kind: "playground", geometry: { type: "Point", coordinates: [71.3668, 51.1361] }, rotation_deg: 90,
                    year: 2027, status: "proposal", near_street: "улица Ильяса Омарова", demo: false };
    let denied = null;
    try { await anon.create(draft); } catch (e) { denied = e; }
    check(mode + ": create без входа → 401", denied && denied.status === 401, denied ? denied.status + " " + denied.code : "создано");

    const created = await staff.create(draft);  // CSRF клиент берёт сам из /api/civic/v1/session
    check(mode + ": create сотрудником (CSRF из сессии) → поля 3D", created.id && created.year === 2027 && created.rotation_deg === 90 &&
          created.status === "proposal", JSON.stringify({ id: created.id, year: created.year, rot: created.rotation_deg }));

    const voted = await anon.vote(created.id, 1);
    check(mode + ": vote → my_vote и счётчик", voted.votes_up === 1 && voted.my_vote === 1, JSON.stringify({ up: voted.votes_up, my: voted.my_vote }));
    const mine = (await anon.list()).find((p) => p.id === created.id);
    check(mode + ": list с device_id → «мой голос» после перезагрузки", mine && mine.my_vote === 1, mine ? String(mine.my_vote) : "нет");

    await staff.remove(created.id);
    check(mode + ": remove (withdraw) → в списке нет", !(await anon.list()).some((p) => p.id === created.id));

    const restored = await staff.restore(voted);
    check(mode + ": restore («Отменить») → предложение снова в списке", restored.id && restored.status === "proposal" &&
          (await anon.list()).some((p) => p.id === restored.id), restored.id + (restored.id === created.id ? " (тот же id)" : " (новый id)"));

    await staffNoWithdraw.remove(restored.id);
    check(mode + ": remove без маршрута withdraw → запасной DELETE", !(await anon.list()).some((p) => p.id === restored.id));
  }

  const failed = results.filter((r) => !r.ok).length;
  console.log(JSON.stringify({ total: results.length, failed }));
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
