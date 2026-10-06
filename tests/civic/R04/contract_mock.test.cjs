"use strict";
// Self-tests for the civic-v1 contract mock. Run: node --test tests/civic/R04/contract_mock.test.cjs
const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const { createMockServer } = require("./contract_mock.cjs");

// Test-only fixture credentials (never used outside this in-memory mock).
const USERS = [
  { username: "editor-a", password: "fixture-only-pass-a", name: "Редактор А", role: "editor" },
  { username: "viewer-b", password: "fixture-only-pass-b", name: "Наблюдатель Б", role: "viewer" },
];
const PUBLIC_KEYS = [
  "schema_version", "id", "city", "kind", "title", "description", "status", "publication",
  "geometry", "geometry_precision", "schedule", "budget", "responsible", "evidence_type",
  "source_refs", "evidence_notes", "updated_at", "revision",
];
const DRAFT = { title: "Ремонт тротуара", kind: "roadworks", evidence_type: "synthetic" };

async function start(t, opts = {}) {
  const mock = createMockServer({ users: USERS, ...opts });
  const base = await mock.listen();
  t.after(() => mock.close());
  return { mock, base };
}

// Every API response must be a JSON envelope with no-store, never HTML.
async function call(base, method, p, { body, raw, cookie, csrf, origin } = {}) {
  const headers = {};
  if (body !== undefined || raw !== undefined) headers["content-type"] = "application/json";
  if (cookie) headers.cookie = cookie;
  if (csrf) headers["x-csrf-token"] = csrf;
  if (origin) headers.origin = origin;
  const res = await fetch(`${base}/api/civic/v1${p}`, {
    method, headers, body: raw !== undefined ? raw : body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  assert.match(res.headers.get("content-type"), /^application\/json/, `${method} ${p} content-type`);
  assert.equal(res.headers.get("cache-control"), "no-store");
  const json = JSON.parse(text);
  assert.equal(json.ok, res.status === 200);
  if (!json.ok) assert.equal(typeof json.error.code, "string");
  return { status: res.status, headers: res.headers, json, data: json.data, error: json.error };
}

async function login(base, user = USERS[0]) {
  const r = await call(base, "POST", "/session/login", { body: { username: user.username, password: user.password } });
  assert.equal(r.status, 200);
  const setCookie = r.headers.getSetCookie()[0];
  return { cookie: setCookie.split(";")[0], csrf: r.data.csrf_token, origin: base, setCookie, data: r.data };
}

const as = (base, s) => (method, p, body) => call(base, method, p, { body, cookie: s.cookie, csrf: s.csrf, origin: s.origin });

test("session: login, cookie flags, generic failures, rate limit and logout", async (t) => {
  let nowMs = Date.parse("2026-10-06T08:00:00Z");
  const { base } = await start(t, { clock: () => new Date(nowMs) });

  const anon = await call(base, "GET", "/session");
  assert.deepEqual(anon.data, { authenticated: false, user: null, csrf_token: null });

  const wrongPass = await call(base, "POST", "/session/login", { body: { username: "editor-a", password: "nope" } });
  const noUser = await call(base, "POST", "/session/login", { body: { username: "ghost", password: "nope" } });
  assert.equal(wrongPass.status, 401);
  assert.equal(wrongPass.error.code, "invalid_credentials");
  assert.deepEqual(noUser.error, wrongPass.error, "does not reveal which part was wrong");

  const foreign = await call(base, "POST", "/session/login", {
    origin: "http://evil.example", body: { username: "editor-a", password: USERS[0].password },
  });
  assert.equal(foreign.status, 403);
  assert.equal(foreign.error.code, "origin");

  const s = await login(base);
  assert.match(s.setCookie, /^civic_session=[\w-]{20,};/);
  for (const flag of ["HttpOnly", "SameSite=Strict", "Path=/"]) assert.ok(s.setCookie.includes(flag), flag);
  assert.deepEqual(s.data.user, { name: "Редактор А", role: "editor" }, "no username in session DTO");
  const me = await call(base, "GET", "/session", { cookie: s.cookie });
  assert.equal(me.data.authenticated, true);
  assert.equal(me.data.csrf_token, s.csrf);

  // 5 consecutive failures, then even the correct password is rate limited.
  for (let i = 0; i < 5; i++) {
    const r = await call(base, "POST", "/session/login", { body: { username: "editor-a", password: `bad-${i}` } });
    assert.equal(r.status, 401);
  }
  const limited = await call(base, "POST", "/session/login", { body: { username: "editor-a", password: USERS[0].password } });
  assert.equal(limited.status, 429);
  assert.equal(limited.error.code, "rate_limited");
  nowMs += 16 * 60 * 1000;
  await login(base); // lockout window passed

  const noCsrf = await call(base, "POST", "/session/logout", { cookie: s.cookie });
  assert.equal(noCsrf.status, 403);
  assert.equal(noCsrf.error.code, "csrf");
  const out = await call(base, "POST", "/session/logout", { cookie: s.cookie, csrf: s.csrf, origin: base });
  assert.deepEqual(out.data, { authenticated: false, user: null, csrf_token: null });
  assert.match(out.headers.getSetCookie()[0], /Max-Age=0/);
  assert.equal((await call(base, "GET", "/session", { cookie: s.cookie })).data.authenticated, false);
});

test("staff access: 401 without session, 403 for CSRF/origin/role, session expiry", async (t) => {
  const { mock, base } = await start(t);
  const port = new URL(base).port;
  assert.equal((await call(base, "GET", "/staff/objects")).status, 401);
  const unauth = await call(base, "POST", "/staff/objects", { body: DRAFT });
  assert.equal(unauth.status, 401);
  assert.equal(unauth.error.code, "unauthenticated");

  const s = await login(base);
  const noCsrf = await call(base, "POST", "/staff/objects", { body: DRAFT, cookie: s.cookie, origin: base });
  assert.equal(noCsrf.status, 403);
  assert.equal(noCsrf.error.code, "csrf");
  const badCsrf = await call(base, "POST", "/staff/objects", { body: DRAFT, cookie: s.cookie, csrf: "x", origin: base });
  assert.equal(badCsrf.error.code, "csrf");
  const evil = await call(base, "POST", "/staff/objects", { body: DRAFT, cookie: s.cookie, csrf: s.csrf, origin: "http://evil.example" });
  assert.equal(evil.status, 403);
  assert.equal(evil.error.code, "origin");

  const viewer = await login(base, USERS[1]);
  assert.equal((await as(base, viewer)("GET", "/staff/objects")).error.code, "forbidden");
  assert.equal((await as(base, viewer)("POST", "/staff/objects", DRAFT)).status, 403);
  assert.equal(mock.state.objects.size, 0, "rejected requests created nothing");

  const viaLocalhost = await call(base, "POST", "/staff/objects", {
    body: DRAFT, cookie: s.cookie, csrf: s.csrf, origin: `http://localhost:${port}`,
  });
  assert.equal(viaLocalhost.status, 200);

  mock.hooks.expireSessions();
  assert.equal((await as(base, s)("GET", "/staff/objects")).status, 401);
  assert.equal((await call(base, "GET", "/session", { cookie: s.cookie })).data.authenticated, false);
});

test("create: server-assigned fields, honest defaults, validation map", async (t) => {
  const clockIso = "2026-10-06T06:00:00.000Z";
  const { mock, base } = await start(t, { clock: () => new Date(clockIso) });
  const s = await login(base);
  const staff = as(base, s);

  const created = await staff("POST", "/staff/objects", {
    ...DRAFT, id: "hijack", revision: 99, publication: "published", updated_at: "2000-01-01T00:00:00Z",
    city: "almaty", schema_version: "x", created_by: { name: "Самозванец" }, actor: "root",
    schedule: { planned_start: "2026-10-14" }, internal_notes: "служебно",
  });
  assert.equal(created.status, 200);
  const item = created.data.item;
  assert.equal(item.id, "obj-1");
  assert.equal(item.revision, 1);
  assert.equal(item.publication, "draft");
  assert.equal(item.updated_at, clockIso);
  assert.equal(item.city, "astana");
  assert.equal(item.schema_version, "civic-v1");
  assert.deepEqual(item.created_by, { name: "Редактор А" });
  assert.deepEqual(item.budget, { amount_kzt: null, basis: "unknown", source_id: null }, "unknown budget is not 0");
  assert.deepEqual(item.schedule, { planned_start: "2026-10-14", original_planned_end: null, current_planned_end: null, actual_end: null });
  assert.equal(item.status, "unknown");
  assert.equal(item.geometry, null);

  const posts = mock.hooks.requests.filter((r) => r.method === "POST" && r.path === "/api/civic/v1/staff/objects");
  assert.equal(posts.length, 1);
  assert.equal(posts[0].status, 200);

  const detail = await staff("GET", "/staff/objects/obj-1");
  assert.equal(detail.data.history.length, 1);
  assert.equal(detail.data.history[0].action, "create");
  assert.equal(detail.data.history[0].actor, "editor-a");
  assert.equal(detail.data.history[0].public_actor_label, "Редактор");

  const bad = await staff("POST", "/staff/objects", {
    title: "<b>Ремонт</b>", kind: "roadworks", evidence_type: "observed", foo: 1,
    budget: { amount_kzt: "100", source_id: "s9" },
    schedule: { planned_start: "2026-02-30" },
    geometry: { type: "LineString", coordinates: [[71.4, 51.1]] },
    source_refs: [{ id: "s1", url: "ftp://example.org", access_status: "fetched" }],
  });
  assert.equal(bad.status, 422);
  assert.equal(bad.error.code, "validation");
  for (const key of ["title", "foo", "budget.amount_kzt", "budget.source_id", "schedule.planned_start", "geometry", "source_refs[0].url"]) {
    assert.equal(typeof bad.error.fields[key], "string", key);
  }

  const infinite = await call(base, "POST", "/staff/objects", {
    raw: `{"title":"x","kind":"event","evidence_type":"derived","budget":{"amount_kzt":1e999}}`,
    cookie: s.cookie, csrf: s.csrf, origin: base,
  });
  assert.equal(infinite.status, 422);
  assert.ok(infinite.error.fields["budget.amount_kzt"]);

  const badJson = await call(base, "POST", "/staff/objects", { raw: "{nope", cookie: s.cookie, csrf: s.csrf, origin: base });
  assert.equal(badJson.status, 400);
  assert.equal(badJson.error.code, "bad_json");
  assert.equal(mock.state.objects.size, 1);
});

test("publication: drafts hidden, reason required, public DTO and history are allowlisted", async (t) => {
  const { base } = await start(t);
  const s = await login(base);
  const staff = as(base, s);
  const { item } = (await staff("POST", "/staff/objects", {
    ...DRAFT, internal_notes: "СЕКРЕТНАЯ-ЗАМЕТКА",
    schedule: { planned_start: "2026-10-14", original_planned_end: "2026-10-20", current_planned_end: "2026-10-20" },
  })).data;
  await staff("POST", `/staff/objects/${item.id}/update`, { expected_revision: 1, changes: { description: "черновая правка" } });

  assert.deepEqual((await call(base, "GET", "/objects")).data, { items: [], next_cursor: null });
  const hiddenDraft = await call(base, "GET", `/objects/${item.id}`);
  const missing = await call(base, "GET", "/objects/obj-404");
  assert.equal(hiddenDraft.status, 404);
  assert.deepEqual(hiddenDraft.json, missing.json, "draft and unknown id are indistinguishable");

  for (const reason of [undefined, "   "]) {
    const r = await staff("POST", `/staff/objects/${item.id}/publish`, { expected_revision: 2, reason });
    assert.equal(r.status, 422);
    assert.ok(r.error.fields.reason);
  }
  const pub = await staff("POST", `/staff/objects/${item.id}/publish`, { expected_revision: 2, reason: "Проверено по плану" });
  assert.equal(pub.data.item.publication, "published");
  assert.equal(pub.data.item.revision, 3);
  assert.equal(pub.data.item.schedule.original_planned_end, "2026-10-20");
  const again = await staff("POST", `/staff/objects/${item.id}/publish`, { expected_revision: 3, reason: "ещё раз" });
  assert.equal(again.status, 409);
  assert.equal(again.error.code, "invalid_transition");
  // Internal-only change while published must not appear publicly.
  await staff("POST", `/staff/objects/${item.id}/update`, { expected_revision: 3, changes: { internal_notes: "СЕКРЕТНАЯ-2" }, reason: "служебно" });

  const list = await call(base, "GET", "/objects");
  const detail = await call(base, "GET", `/objects/${item.id}`);
  assert.equal(list.data.items.length, 1);
  assert.deepEqual(Object.keys(list.data.items[0]), PUBLIC_KEYS);
  assert.deepEqual(Object.keys(detail.data.item), PUBLIC_KEYS);
  const publicText = JSON.stringify([list.json, detail.json]);
  for (const leak of ["СЕКРЕТНАЯ", "internal_notes", "created_by", "first_published_at", "editor-a", "Редактор А", "\"actor\""]) {
    assert.ok(!publicText.includes(leak), `public response leaks ${leak}`);
  }
  assert.deepEqual(detail.data.history.map((h) => h.action), ["publish"], "draft-era and internal-only entries hidden");
  assert.equal(detail.data.history[0].public_actor_label, "Редактор");

  const staffDetail = await staff("GET", `/staff/objects/${item.id}`);
  assert.equal(staffDetail.data.item.internal_notes, "СЕКРЕТНАЯ-2");
  assert.equal(staffDetail.data.history.length, 4);
  assert.ok(staffDetail.data.history.every((h) => h.actor === "editor-a"));

  const noReason = await staff("POST", `/staff/objects/${item.id}/archive`, { expected_revision: 4 });
  assert.equal(noReason.status, 422);
  const archived = await staff("POST", `/staff/objects/${item.id}/archive`, { expected_revision: 4, reason: "Работы отменены" });
  assert.equal(archived.data.item.publication, "archived");
  assert.equal((await call(base, "GET", `/objects/${item.id}`)).status, 404);
  assert.equal((await call(base, "GET", "/objects")).data.items.length, 0);
  const twice = await staff("POST", `/staff/objects/${item.id}/archive`, { expected_revision: 5, reason: "снова" });
  assert.equal(twice.error.code, "invalid_transition");
});

test("revisions: stale 409, original_planned_end locked after first publish", async (t) => {
  const { mock, base } = await start(t);
  const staff = as(base, await login(base));
  const sched = { planned_start: "2026-10-14", original_planned_end: "2026-10-20", current_planned_end: "2026-10-20" };
  const id = (await staff("POST", "/staff/objects", { ...DRAFT, schedule: sched })).data.item.id;

  // Before publication the original deadline is freely editable, no reason needed.
  const draftEdit = await staff("POST", `/staff/objects/${id}/update`, {
    expected_revision: 1, changes: { schedule: { original_planned_end: "2026-10-21", current_planned_end: "2026-10-21" } },
  });
  assert.equal(draftEdit.data.item.revision, 2);
  await staff("POST", `/staff/objects/${id}/publish`, { expected_revision: 2, reason: "Публикация" });

  const other = mock.hooks.mutate(id, { status: "in_progress" });
  assert.equal(other.revision, 4);
  const stale = await staff("POST", `/staff/objects/${id}/update`, {
    expected_revision: 3, changes: { title: "Моя правка" }, reason: "уточнение",
  });
  assert.equal(stale.status, 409);
  assert.equal(stale.error.code, "stale_revision");
  assert.equal(stale.error.current_revision, 4);
  assert.equal(mock.state.objects.get(id).title, DRAFT.title, "stale write not applied");

  const locked = await staff("POST", `/staff/objects/${id}/update`, {
    expected_revision: 4, changes: { schedule: { original_planned_end: "2026-12-01" } }, reason: "перенос",
  });
  assert.equal(locked.status, 422);
  assert.ok(locked.error.fields["schedule.original_planned_end"]);
  const noReason = await staff("POST", `/staff/objects/${id}/update`, {
    expected_revision: 4, changes: { schedule: { current_planned_end: "2026-12-15" } },
  });
  assert.equal(noReason.status, 422);
  assert.ok(noReason.error.fields.reason);
  const ok = await staff("POST", `/staff/objects/${id}/update`, {
    expected_revision: 4, changes: { schedule: { current_planned_end: "2026-12-15" } }, reason: "Подрядчик сдвинул срок",
  });
  assert.equal(ok.data.item.revision, 5);
  assert.deepEqual(ok.data.item.schedule, {
    planned_start: "2026-10-14", original_planned_end: "2026-10-21", current_planned_end: "2026-12-15", actual_end: null,
  }, "nested keys merged, original kept");

  const readonly = await staff("POST", `/staff/objects/${id}/update`, { expected_revision: 5, changes: { revision: 10, publication: "draft" }, reason: "x" });
  assert.equal(readonly.status, 422);
  assert.ok(readonly.error.fields.revision && readonly.error.fields.publication);
  assert.equal((await staff("POST", `/staff/objects/${id}/update`, { expected_revision: 5, changes: {}, reason: "x" })).error.code, "no_changes");
  assert.equal((await staff("POST", `/staff/objects/${id}/update`, { expected_revision: 5, changes: { status: "in_progress" }, reason: "x" })).error.code, "no_changes");
  assert.equal((await staff("POST", "/staff/objects/obj-999/update", { expected_revision: 1, changes: { title: "x" } })).error.code, "not_found");

  const pubHistory = (await call(base, "GET", `/objects/${id}`)).data.history;
  assert.deepEqual(pubHistory[0].changed_fields, ["schedule.current_planned_end"]);
  assert.equal(pubHistory[0].reason, "Подрядчик сдвинул срок");
  assert.ok(!JSON.stringify(pubHistory).includes("other-editor"));
});

test("lists: newest first, cursor pagination, public filters and date validation", async (t) => {
  const seed = [
    { id: "p-old", title: "Старый", kind: "roadworks", evidence_type: "observed", publication: "published",
      updated_at: "2026-09-01T00:00:00Z", schedule: { planned_start: "2026-01-10", current_planned_end: "2026-03-01" } },
    { id: "p-open", title: "Без даты окончания", kind: "landscaping", evidence_type: "derived", publication: "published",
      updated_at: "2026-09-02T00:00:00Z", schedule: { planned_start: "2026-10-01" } },
    { id: "p-nodates", title: "Даты неизвестны", kind: "roadworks", evidence_type: "hypothesis", publication: "published",
      updated_at: "2026-09-03T00:00:00Z" },
    { id: "d-draft", title: "Черновик", kind: "roadworks", evidence_type: "synthetic", updated_at: "2026-09-04T00:00:00Z" },
  ];
  const { mock, base } = await start(t, { pageSize: 2, seed });

  const p1 = await call(base, "GET", "/objects");
  assert.deepEqual(p1.data.items.map((i) => i.id), ["p-nodates", "p-open"]);
  assert.equal(typeof p1.data.next_cursor, "string");
  const p2 = await call(base, "GET", `/objects?cursor=${encodeURIComponent(p1.data.next_cursor)}`);
  assert.deepEqual(p2.data.items.map((i) => i.id), ["p-old"]);
  assert.equal(p2.data.next_cursor, null);

  const ids = async (q) => (await call(base, "GET", `/objects?${q}`)).data.items.map((i) => i.id).sort();
  assert.deepEqual(await ids("kind=roadworks"), ["p-nodates", "p-old"]);
  assert.deepEqual(await ids("from=2026-02-01&to=2026-02-28"), ["p-old"]);
  assert.deepEqual(await ids("from=2026-03-01&to=2026-03-01"), ["p-old"], "inclusive bound");
  assert.deepEqual(await ids("from=2026-12-01"), ["p-open"], "open-ended interval, unknown dates excluded");
  for (const q of ["from=2026-02-30", "to=06.10.2026", "kind=bogus", "from=2026-05-01&to=2026-04-01", "cursor=%%%"]) {
    const r = await call(base, "GET", `/objects?${q}`);
    assert.equal(r.status, 400, q);
    assert.equal(r.error.code, "bad_request");
  }

  const staff = as(base, await login(base));
  assert.deepEqual((await staff("GET", "/staff/objects?publication=draft")).data.items.map((i) => i.id), ["d-draft"]);
  assert.equal((await staff("GET", "/staff/objects")).data.items[0].id, "d-draft");
  mock.hooks.reset();
  assert.equal(mock.state.objects.size, 4, "reset restores the seed");
  assert.equal(mock.hooks.requests.length, 0);
});

test("fault hooks: drop, drop after commit, html500, delay", async (t) => {
  const { mock, base } = await start(t);
  const staff = as(base, await login(base));

  mock.hooks.failNext({ method: "POST", pathPrefix: "/staff/objects", mode: "drop" });
  await assert.rejects(staff("POST", "/staff/objects", DRAFT), TypeError);
  assert.equal(mock.state.objects.size, 0, "plain drop does not commit");
  assert.equal(mock.hooks.requests.at(-1).status, 0);

  mock.hooks.failNext({ method: "POST", pathPrefix: "/api/civic/v1/staff/objects", mode: "drop", afterCommit: true });
  await assert.rejects(staff("POST", "/staff/objects", DRAFT), TypeError);
  assert.equal(mock.state.objects.size, 1, "afterCommit drop created the object");
  assert.equal(mock.state.history[0].action, "create");
  assert.equal((await staff("POST", "/staff/objects", DRAFT)).status, 200, "faults are one-shot");

  mock.hooks.failNext({ method: "GET", pathPrefix: "/session", mode: "html500" });
  const html = await fetch(`${base}/api/civic/v1/session`);
  assert.equal(html.status, 500);
  assert.match(html.headers.get("content-type"), /^text\/html/);
  assert.match(await html.text(), /<html>/);
  assert.equal((await call(base, "GET", "/session")).status, 200);

  mock.hooks.failNext({ pathPrefix: "/session", mode: "delay:150" });
  const t0 = Date.now();
  assert.equal((await call(base, "GET", "/session")).status, 200);
  assert.ok(Date.now() - t0 >= 140);
  assert.throws(() => mock.hooks.failNext({ mode: "explode" }));
});

test("transport errors are JSON: 413, unknown path, wrong method", async (t) => {
  const { base } = await start(t);
  const s = await login(base);
  const big = await call(base, "POST", "/staff/objects", {
    body: { ...DRAFT, description: "я".repeat(40 * 1024) }, cookie: s.cookie, csrf: s.csrf, origin: base,
  });
  assert.equal(big.status, 413);
  assert.equal(big.error.code, "too_large");
  for (const p of ["/nope", "/staff/objects/obj-1/delete", "/../../etc/passwd"]) {
    const r = await call(base, "GET", p);
    assert.equal(r.status, 404, p);
    assert.equal(r.error.code, "not_found");
  }
  const outside = await fetch(`${base}/api/other`);
  assert.equal(outside.status, 404);
  assert.match(outside.headers.get("content-type"), /^application\/json/);
  const del = await call(base, "DELETE", "/staff/objects/obj-1", { cookie: s.cookie, csrf: s.csrf });
  assert.equal(del.status, 405);
  assert.equal(del.error.code, "method_not_allowed");
  assert.equal(del.headers.get("allow"), "GET");
});

test("static: exact map, prefix dir, traversal rejected", async (t) => {
  const repoRoot = path.resolve(__dirname, "../../..");
  const indexHtml = path.join(repoRoot, "web/index.html");
  const { base } = await start(t, {
    static: { "/": indexHtml, "/mock.js": path.join(__dirname, "contract_mock.cjs") },
    staticDirs: [{ prefix: "/r04/", dir: __dirname }],
  });
  const root = await fetch(`${base}/`);
  assert.equal(root.status, 200);
  assert.match(root.headers.get("content-type"), /^text\/html/);
  assert.match((await fetch(`${base}/mock.js`)).headers.get("content-type"), /^text\/javascript/);
  assert.equal((await fetch(`${base}/r04/contract_mock.cjs`)).status, 200);
  const missing = await fetch(`${base}/r04/missing.js`);
  assert.equal(missing.status, 404);
  assert.match(missing.headers.get("content-type"), /^text\/plain/);

  // Raw requests (fetch would normalise dot segments client-side).
  assert.ok(fs.existsSync(path.join(repoRoot, "README.md")));
  const rawGet = (p) => new Promise((resolve, reject) => {
    const { hostname, port } = new URL(base);
    http.get({ hostname, port, path: p }, (res) => { res.resume(); resolve(res.statusCode); }).on("error", reject);
  });
  for (const p of ["/r04/../../../README.md", "/r04/..%2f..%2f..%2fREADME.md", "/r04/%2e%2e/%2e%2e/%2e%2e/README.md", "/r04/%2Fetc%2Fpasswd"]) {
    assert.equal(await rawGet(p), 404, p);
  }
});
