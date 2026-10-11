/* Shared browser-test helpers for the R04 round-13 suites (contract mock stand + harness page).
 * Same helpers as in e2e.test.cjs, extracted so new suites do not copy them again.
 */
"use strict";
const path = require("path");
const { execSync } = require("child_process");

function loadPlaywright() {
  for (const p of ["playwright", "/opt/node-tools/node_modules/playwright"]) { try { return require(p); } catch (e) { /* next */ } }
  try { return require(path.join(execSync("npm root -g").toString().trim(), "playwright")); } catch (e) { return null; }
}
const fk = (k) => `[data-fk="${k}"]`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function makeKit(env) {
  const { stand, browser, pages, shotsDir } = env;
  const H = () => stand.mock.hooks;
  const objects = () => [...stand.mock.state.objects.values()];
  const posts = (apiPath) => H().requests.filter((r) => r.method === "POST" && r.apiPath === apiPath);

  async function newPage(viewport) {
    const ctx = await browser.newContext({ viewport: viewport || { width: 1280, height: 860 } });
    const p = await ctx.newPage();
    p.errors = [];
    p.on("pageerror", (e) => p.errors.push(e.message));
    pages.push(p);
    return p;
  }
  async function open(viewport, query, opts) {
    const o = opts || {};
    if (!o.keepState) H().reset();
    const p = o.page || (await newPage(viewport));
    await p.goto(stand.url + "/" + (query || ""));
    await p.waitForFunction(() => window.__mapState);
    if (!o.noWait) await p.waitForSelector(fk("login-user"));
    return p;
  }
  async function login(p, who) {
    const c = who === 2 ? stand.creds2 : stand.creds;
    await p.fill(fk("login-user"), c.username);
    await p.fill(fk("login-pass"), c.password);
    await p.press(fk("login-pass"), "Enter");
  }
  async function loginToList(p, who) { await login(p, who); await p.waitForSelector(fk("new")); }
  async function fillDraft(p, o) {
    await p.click(fk("new"));
    await p.waitForSelector(fk("title"));
    await p.fill(fk("title"), o.title);
    await p.selectOption(fk("kind"), o.kind || "roadworks");
    await p.check(`input[type=radio][value=${o.evidence || "synthetic"}]`);
    if (o.description) await p.fill(fk("description"), o.description);
  }
  async function saveOk(p, text) {
    await p.click(fk("save"));
    await p.waitForSelector(`.civic-r04-msg-ok:has-text("${text || "ред."}")`);
  }
  const shot = async (p, name) => { if (process.env.R04_SCREENSHOTS === "1") await p.screenshot({ path: path.join(shotsDir, name + ".png") }); };
  const value = (p, k) => p.$eval(fk(k), (x) => x.value);
  const errorText = (p, k) => p.$eval(fk(k), (x) => { const id = (x.getAttribute("aria-describedby") || "").split(" ").find((s) => s.endsWith("-err")); return id ? document.getElementById(id).textContent : ""; });
  // Node-side API client (separate session, same contract) for seeding and for "another editor".
  async function apiClient(who) {
    let cookie = "", csrf = null;
    const req = async (method, p, body) => {
      const headers = { "Content-Type": "application/json", Origin: stand.url };
      if (cookie) headers.Cookie = cookie;
      if (csrf && method !== "GET") headers["X-CSRF-Token"] = csrf;
      const r = await fetch(stand.url + "/api/civic/v1" + p, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
      const sc = r.headers.get("set-cookie");
      if (sc) cookie = sc.split(";")[0];
      const j = await r.json();
      if (!j.ok) throw Object.assign(new Error(j.error.code), { status: r.status, error: j.error });
      return j.data;
    };
    csrf = (await req("POST", "/session/login", who === 2 ? stand.creds2 : stand.creds)).csrf_token;
    return req;
  }
  const BASE_BODY = {
    title: "Демонстрационный ремонт прохода", kind: "roadworks", evidence_type: "synthetic", status: "planned",
    description: "Синтетическая запись для проверки интерфейса.", geometry: { type: "Point", coordinates: [71.43, 51.17] }, geometry_precision: "approximate",
    schedule: { planned_start: "2026-10-14", original_planned_end: "2026-10-20", current_planned_end: "2026-10-20", actual_end: null },
  };
  async function seedDraft(over) {
    const req = await apiClient();
    return (await req("POST", "/staff/objects", Object.assign({}, BASE_BODY, over || {}))).item;
  }
  async function seedPublished(over) {
    const req = await apiClient();
    const c = await req("POST", "/staff/objects", Object.assign({}, BASE_BODY, over || {}));
    return (await req("POST", "/staff/objects/" + c.item.id + "/publish", { expected_revision: c.item.revision, reason: "Первая публикация (тест)" })).item;
  }
  const publicGet = async (p) => { const r = await fetch(stand.url + "/api/civic/v1" + p); return { status: r.status, json: await r.json() }; };
  return { H, objects, posts, newPage, open, login, loginToList, fillDraft, saveOk, shot, value, errorText, apiClient, seedDraft, seedPublished, publicGet };
}

module.exports = { loadPlaywright, makeKit, fk, sleep };
