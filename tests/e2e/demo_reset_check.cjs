// R10 · раунд 14 · демо «как в первый раз»: после репетиции и через две недели (BUGS.md B-048, B-049).
//
//   node tests/e2e/demo_reset_check.cjs --root <папка сборки> [--out <папка отчёта>] [--age-days 13]
//
// Сервер — как run-city.bat: ОДНА постоянная база (во временной папке), каждый «запуск» = init → seed-demo → app.py
// с CIVIC_DEMO=1. Проверка — как форма жалобы R09 (complaint.js: похожие и «сообщили N человек» за 14 дней) у остановки
// DEMO_SCRIPT «Хан Шатыр» по тексту «Аялдамада жарық жоқ, вечером на остановке темно»:
//   1. свежая база — есть похожая демо-жалоба (значит, на шаге 2 будет «Я тоже»);
//   2. «репетиция»: жалоба + «Я тоже» + сотрудник закрывает все жалобы остановки (как карточка R07 на шаге 6);
//      перезапуск — похожие снова есть (демо вернулось само) — B-048;
//   3. «через две недели»: время демо-жалоб в базе сдвигается на 13 дней назад (так стареет база на ноутбуке);
//      перезапуск — похожие есть — B-049.
// Ничего не пишет в репозиторий; база и сотрудник временные. Только HTTP API, без браузера (~1 мин).
"use strict";
const { spawn, execFileSync } = require("child_process");
const fs = require("fs"), path = require("path"), os = require("os"), net = require("net");

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => {
  if (a.startsWith("--")) acc.push([a.slice(2), all[i + 1] && !all[i + 1].startsWith("--") ? all[i + 1] : true]);
  return acc;
}, []));
const ROOT = path.resolve(args.root || path.join(__dirname, "../.."));
const OUT = path.resolve(args.out || path.join(os.tmpdir(), "r10-demo-reset"));
const PY = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const STOP = { kind: "object", id: "osm-node-4109037549", point: [71.406553, 51.131155] };  // «Хан Шатыр», Нура
const TEXT = "Аялдамада жарық жоқ, вечером на остановке темно";                              // DEMO_SCRIPT шаг 2
const BBOX = "71.400,51.128,71.413,51.134";
const DAYS = 14;                                                                              // как complaint.js
const AGE_DAYS = Number(args["age-days"] || 13);  // шаг 3: на сколько дней «состарить» демо-жалобы (контроль: 10 → PASS)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const add = (step, name, ok, detail) => {
  const status = ok === null ? "NOT_RUN" : ok ? "PASS" : "FAIL";
  results.push({ step, name, status, detail });
  console.log(`${status.padEnd(7)} ${step} ${name}` + (detail ? " — " + JSON.stringify(detail).slice(0, 300) : ""));
};
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no);
  s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r10-reset-"));
const db = path.join(tmp, "civic.sqlite3");
const env = { ...process.env, CIVIC_DB_PATH: db, PYTHONDONTWRITEBYTECODE: "1", CIVIC_DEMO: "1" };
const cli = (argv, input) => execFileSync(PY, ["-B", "-m", "ui.civic_store", "--db", db, ...argv],
  { cwd: ROOT, env, input, stdio: [input ? "pipe" : "ignore", "pipe", "pipe"] }).toString();

let srv = null, base = null;
async function start() {             // = двойной щелчок по run-city.bat (run.bat: init → seed-demo → app.py)
  cli(["init"]);
  cli(["seed-demo", "--package", "data/civic/astana/demo_synthetic.json"]);
  const port = await freePort();
  base = `http://127.0.0.1:${port}`;
  srv = spawn(PY, ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: "ignore" });
  for (let i = 0; i < 150; i++) { try { if ((await fetch(base + "/api/health")).ok) break; } catch {} await sleep(200); }
  await call("GET", `/api/civic/v2/heat?bbox=${BBOX}&days=30&zoom=16`);  // как страница: подключает /similar (B-032)
  await sleep(1500);
}
async function stop() { if (srv) { srv.kill(); await new Promise((r) => srv.once("exit", r)); srv = null; } }

let cookie = null, csrf = null;
async function call(method, p, body, staff) {
  const headers = { "Content-Type": "application/json", Origin: base };
  if (staff && cookie) { headers.Cookie = cookie; headers["X-CSRF-Token"] = csrf; }
  try {
    const res = await fetch(base + p, { method, headers, body: body ? JSON.stringify(body) : undefined });
    const text = await res.text(); let json = null; try { json = JSON.parse(text); } catch {}
    const data = json && json.ok !== undefined && json.data !== undefined ? json.data : json;
    return { status: res.status, data, res };
  } catch (e) { return { status: 0, data: { error: String(e) } }; }
}
async function login(user, pass) {
  cookie = csrf = null;
  const r = await call("POST", "/api/civic/v1/session/login", { username: user, password: pass });
  const set = r.res && r.res.headers.get("set-cookie");
  if (r.status === 200 && set) { cookie = set.split(";")[0]; csrf = r.data && (r.data.csrf_token || (r.data.session && r.data.session.csrf_token)); }
  return !!csrf;
}
// То, что видит житель на шаге 2: похожие (R04, как форма — за 14 дней, та же цель) и «сообщили N человек».
async function demoState() {
  const s = await call("POST", "/api/civic/v2/similar", { text: TEXT, point: STOP.point, days: DAYS, target: { kind: STOP.kind, id: STOP.id } });
  const m = (s.data && s.data.matches) || [];
  const sum = await call("GET", `/api/civic/v2/complaints/summary?target_id=${STOP.id}&category=lighting&days=${DAYS}`);
  return { similar_status: s.status, matches: m.length, first: m[0] && m[0].complaint_id, reporters: sum.data && sum.data.reporters };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const user = "r10-reset", pass = "Qv7-" + Math.random().toString(36).slice(2) + "-Kz9!";  // пароль без логина (правило R02)
  try {
    cli(["init"]);
    cli(["create-editor", user, "--password-stdin"], pass + "\n");

    // 1. Свежая база
    await start();
    const s1 = await demoState();
    add("1", "свежая база: у «Хан Шатыра» есть похожая жалоба за 14 дней (на шаге 2 будет «Я тоже»)", s1.matches > 0, s1);

    // 2. Репетиция: шаги 1–2 и 6 через API так же, как их делает интерфейс
    const dev = "r10-reset-device-" + Date.now();
    const cr = await call("POST", "/api/civic/v2/complaints", { text: TEXT, lang: "mixed", category: "lighting", category_source: "resident",
      point: STOP.point, target: { kind: STOP.kind, id: STOP.id }, device_id: dev });
    if (s1.first) await call("POST", `/api/civic/v2/complaints/${s1.first}/metoo`, { device_id: dev + "-2" });
    const staffOk = await login(user, pass);
    const list = await call("GET", `/api/civic/v2/complaints?bbox=${BBOX}&days=90`);
    const open = ((list.data && (list.data.items || list.data.complaints)) || [])
      .filter((c) => c.target && c.target.id === STOP.id && !["fixed", "rejected"].includes(c.status));
    let fixed = 0;
    for (const c of open) {
      if (c.status === "new") await call("POST", `/api/civic/v2/complaints/${c.id}/status`, { status: "in_progress" }, true);
      const r = await call("POST", `/api/civic/v2/complaints/${c.id}/status`, { status: "fixed" }, true);
      if ([200, 201].includes(r.status)) fixed++;
    }
    add("2", "репетиция: жалоба, «Я тоже», сотрудник закрыл все жалобы остановки", [200, 201].includes(cr.status) && staffOk && fixed > 0 && fixed === open.length,
      { complaint: cr.status, staff: staffOk, open: open.length, fixed });
    await stop();
    await start();
    const s2 = await demoState();
    add("2", "после репетиции и перезапуска (как run-city.bat) похожие снова есть — демо вернулось (B-048)", s2.matches > 0, s2);
    await stop();

    // 3. Две недели спустя — на НОВОЙ базе без репетиции (иначе это снова B-048): первый запуск засевает демо,
    //    затем время демо-жалоб −13 дней (как если бы ноутбук настроили за 13 дней до показа) и ещё один запуск.
    for (const f of fs.readdirSync(tmp)) fs.rmSync(path.join(tmp, f), { force: true });
    await start();
    await stop();
    const aged = execFileSync(PY, ["-c", `
import sqlite3, json, sys
from datetime import datetime, timedelta
c = sqlite3.connect(sys.argv[1]); S = int(sys.argv[2]) * 86400; n = 0
def back(v):
    return (datetime.fromisoformat(v.replace("Z", "+00:00")) - timedelta(seconds=S)).isoformat()
for rid, ts, rj in list(c.execute("select rowid, created_ts, record_json from complaints_v2 where demo=1")):
    r = json.loads(rj)
    for k in ("created_at", "updated_at", "due_at"):
        if r.get(k): r[k] = back(r[k])
    for h in r.get("status_history") or []:
        if h.get("at"): h["at"] = back(h["at"])
    c.execute("update complaints_v2 set created_ts=?, record_json=? where rowid=?", (ts - S, json.dumps(r, ensure_ascii=False), rid)); n += 1
c.commit(); print(n)
`, db, String(AGE_DAYS)], { env }).toString().trim();
    await start();
    const s3 = await demoState();
    add("3", `через ${AGE_DAYS} дней после первого запуска похожие есть (демо-жалобы не устарели) (B-049)`, s3.matches > 0, { aged_rows: Number(aged), ...s3 });
  } catch (e) {
    add("*", "прогон", false, String(e.stack || e).slice(0, 400));
  } finally {
    await stop();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  const counts = { PASS: 0, FAIL: 0, NOT_RUN: 0 }; results.forEach((r) => counts[r.status]++);
  let sha = ""; try { sha = execFileSync("git", ["-C", ROOT, "rev-parse", "--short", "HEAD"]).toString().trim(); } catch {}
  fs.writeFileSync(path.join(OUT, "RESET_RESULT.json"), JSON.stringify({ root: ROOT, sha, when: new Date().toISOString(), counts, results }, null, 1));
  fs.writeFileSync(path.join(OUT, "RESET_RESULT.md"), [`# R10 · демо после репетиции и через две недели · ${sha}`, "",
    `Итого: PASS ${counts.PASS}, FAIL ${counts.FAIL}, NOT_RUN ${counts.NOT_RUN}`, "", "| Шаг | Проверка | Итог | Подробно |", "|---|---|---|---|",
    ...results.map((r) => `| ${r.step} | ${r.name} | **${r.status}** | ${JSON.stringify(r.detail || "").replace(/\|/g, "/").slice(0, 220)} |`)].join("\n") + "\n");
  console.log("ИТОГ:", counts, "→", OUT);
  process.exit(counts.FAIL ? 1 : 0);
})();
