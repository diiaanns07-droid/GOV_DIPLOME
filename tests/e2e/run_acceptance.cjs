// R10 · раунд 14 · полная приёмка сборки одной командой (B1 / B2 / FINAL; повтор Codex на ноутбуке владельца).
//
//   node tests/e2e/run_acceptance.cjs --root <папка сборки> --out <папка отчёта> [--label FINAL]
//
// Что делает (ничего не пишет в репозиторий, база — временная):
//   1. точность карты:  <PY> tests/civic/R10/accuracy.py --root <сборка> --json <out>/accuracy.json  (+ pytest tests/civic/R10)
//   2. сервер сборки:   init → seed-demo → seed-r14-demo (если есть) → сотрудник r10-operator → app.py на свободном порту
//                       с CIVIC_DEMO=1, как run-city.bat (--no-demo — без синтетического набора R07)
//   3. сценарий демо:   tests/e2e/demo_flow.cjs --url <сервер> (API + UI, 1366/375 × ru/kk) → <out>/e2e/
//   4. UX по экранам:   tests/e2e/ux_screens.cjs --screens tests/e2e/screens_build.json → <out>/ux/
//   5. сводка:          <out>/SUMMARY.md — числа PASS/FAIL/NOT_RUN по каждому блоку и список FAIL
// Тесты R10 берутся из ЭТОЙ папки (tests/e2e рядом со скриптом), сборка — из --root: так можно проверять любой SHA.
// Нужно: Python 3.11+ (переменная PYTHON, например .venv\Scripts\python), Node 20+, Playwright с Chromium
// (NODE_PATH="$(npm root -g)" или npm i playwright в папке).
"use strict";
const { spawn, spawnSync, execFileSync } = require("child_process");
const fs = require("fs"), path = require("path"), os = require("os"), net = require("net");

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => {
  if (a.startsWith("--")) acc.push([a.slice(2), all[i + 1] && !all[i + 1].startsWith("--") ? all[i + 1] : true]);
  return acc;
}, []));
const HERE = __dirname;                                   // tests/e2e этой ветки (R10)
const R10 = path.resolve(HERE, "../civic/R10");
const ROOT = path.resolve(args.root || path.join(HERE, "../.."));
const OUT = path.resolve(args.out || path.join(os.tmpdir(), "r10-acceptance"));
const LABEL = String(args.label || "build");
const PY = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no);
  s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

function run(cmd, argv, opts = {}) {
  // Запуск шага с логом в файл; возвращает код выхода (не бросает исключение — сводка всё равно нужна).
  const log = path.join(OUT, opts.log);
  const r = spawnSync(cmd, argv, { cwd: opts.cwd || ROOT, env: { ...process.env, ...(opts.env || {}) }, encoding: "utf8", maxBuffer: 64 << 20 });
  fs.writeFileSync(log, (r.stdout || "") + (r.stderr || "") + (r.error ? "\n" + r.error : ""));
  return r.status;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  let sha = "unknown";
  try { sha = execFileSync("git", ["rev-parse", "--short", "HEAD"], { cwd: ROOT }).toString().trim(); } catch {}
  const summary = [`# R10 · приёмка ${LABEL} · сборка ${sha}`, "", `Папка сборки: ${ROOT}`, `Когда: ${new Date().toISOString()} · Node ${process.version} · Python: ${PY}`, ""];

  // 1. Точность карты (CONTRACT §8)
  run(PY, ["-B", path.join(R10, "accuracy.py"), "--root", ROOT, "--json", path.join(OUT, "accuracy.json")], { log: "accuracy.log" });
  const pyt = run(PY, ["-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", R10], { log: "accuracy_pytest.log", env: { R10_ROOT: ROOT } });
  let acc = null; try { acc = JSON.parse(fs.readFileSync(path.join(OUT, "accuracy.json"), "utf8")); } catch {}
  summary.push("## 1. Точность карты (CONTRACT §8)", "", acc ? `PASS ${acc.counts.PASS} · FAIL ${acc.counts.FAIL} · NOT_RUN ${acc.counts.NOT_RUN} (pytest код ${pyt})` : "отчёт не получен — см. accuracy.log", "");
  if (acc) acc.checks.filter((c) => c.status === "FAIL").forEach((c) => summary.push(`- FAIL [${c.owner}] ${c.name}: ${JSON.stringify(c.detail).slice(0, 200)}`));

  // 2. Сервер сборки с временной базой
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r10-acc-"));
  const db = path.join(tmp, "civic.sqlite3");
  // Как на демо (run-city.bat): CIVIC_DEMO=1 — к жалобам добавляется синтетический набор R07 (помечен «Пример»).
  // --no-demo — чистая база без него.
  const DEMO = args["no-demo"] ? "" : "1";
  const env = { ...process.env, CIVIC_DB_PATH: db, PYTHONDONTWRITEBYTECODE: "1", CIVIC_DEMO: DEMO };
  const cli = (argv, input) => spawnSync(PY, ["-B", "-m", "ui.civic_store", "--db", db, ...argv], { cwd: ROOT, env, input, encoding: "utf8" });
  const seeds = [];
  for (const step of [["init"], ["seed-demo", "--package", "data/civic/astana/demo_synthetic.json"]]) { const r = cli(step); seeds.push(`${step[0]}:${r.status}`); }
  if (/seed-r14-demo/.test(cli(["--help"]).stdout || "")) seeds.push(`seed-r14-demo:${cli(["seed-r14-demo"]).status}`);
  const user = "r10-operator", pass = "R10-acc-" + Math.random().toString(36).slice(2) + "-Aa1!";
  const ed = cli(["create-editor", user, "--password-stdin"], pass + "\n");
  const port = await freePort();
  const base = `http://127.0.0.1:${port}/`;
  // Вывод сервера — сразу в файл, не в трубу: шаги ниже идут синхронно (spawnSync), трубу никто не читает,
  // её буфер переполняется и сервер зависает на записи лога.
  const srvFd = fs.openSync(path.join(OUT, "server.log"), "w");
  const srv = spawn(PY, ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: ["ignore", srvFd, srvFd] });
  let up = false;
  for (let i = 0; i < 150 && !up; i++) { try { up = (await fetch(base + "api/health")).ok; } catch {} if (!up) await sleep(200); }
  summary.push("", "## 2. Сервер сборки", "", `${up ? "запущен" : "НЕ ЗАПУСТИЛСЯ"} на ${base}; CIVIC_DEMO=${DEMO || "(нет)"}; база: ${seeds.join(", ")}; сотрудник: ${ed.status === 0 ? "создан" : "ошибка " + (ed.stderr || "").slice(0, 120)}`);
  try {
    const m = await (await fetch(base + "api/civic/v2/modules")).json();
    const mods = (m.data || m).modules || {};
    summary.push("", "| Маршрут v2 | Роль | Статус |", "|---|---|---|", ...Object.entries(mods).map(([k, v]) => `| ${k} | ${v.role} | ${v.status} |`));
  } catch (e) { summary.push(`- /api/civic/v2/modules недоступен: ${e.message}`); }

  if (up) {
    // 3. Сценарий демо
    const nodeEnv = { NODE_PATH: process.env.NODE_PATH || "", PYTHON: PY };
    run(process.execPath, [path.join(HERE, "demo_flow.cjs"), "--root", ROOT, "--url", base, "--user", user, "--pass", pass, "--out", path.join(OUT, "e2e")],
      { log: "e2e.log", env: nodeEnv });
    // 4. UX по экранам
    run(process.execPath, [path.join(HERE, "ux_screens.cjs"), "--screens", path.join(HERE, "screens_build.json"), "--base", base, "--out", path.join(OUT, "ux")],
      { log: "ux.log", env: nodeEnv });
  }
  srv.kill();
  await sleep(500);
  fs.closeSync(srvFd);
  fs.rmSync(tmp, { recursive: true, force: true });

  // 5. Сводка
  const read = (f) => { try { return JSON.parse(fs.readFileSync(path.join(OUT, f), "utf8")); } catch { return null; } };
  const e2e = read("e2e/RESULT.json"), ux = read("ux/UX_RESULT.json");
  summary.push("", "## 3. Сценарий демо (tests/e2e/demo_flow.cjs)", "", e2e ? `PASS ${e2e.counts.PASS} · FAIL ${e2e.counts.FAIL} · NOT_RUN ${e2e.counts.NOT_RUN} — подробно e2e/RESULT.md` : "не выполнен — см. e2e.log");
  if (e2e) {
    const steps = {};
    e2e.results.forEach((r) => { const k = r.step; steps[k] = steps[k] || { PASS: 0, FAIL: 0, NOT_RUN: 0 }; steps[k][r.status]++; });
    summary.push("", "| Шаг | PASS | FAIL | NOT_RUN |", "|---|---|---|---|", ...Object.entries(steps).sort().map(([k, v]) => `| ${k} | ${v.PASS} | ${v.FAIL} | ${v.NOT_RUN} |`));
    e2e.results.filter((r) => r.status === "FAIL").forEach((r) => summary.push(`- FAIL ${r.layer} шаг ${r.step}: ${r.name}`));
  }
  summary.push("", "## 4. UX по экранам (tests/e2e/ux_screens.cjs)", "", ux ? `PASS ${ux.counts.PASS} · FAIL ${ux.counts.FAIL} · NOT_RUN ${ux.counts.NOT_RUN || 0} — подробно ux/UX_RESULT.md` : "не выполнен — см. ux.log");
  if (ux) ux.rows.filter((r) => r.status === "FAIL").forEach((r) => summary.push(`- FAIL [${r.owner}] ${r.screen} ${r.size} ${r.lang}: ${r.check}`));
  fs.writeFileSync(path.join(OUT, "SUMMARY.md"), summary.join("\n") + "\n");
  console.log(summary.slice(0, 12).join("\n"));
  console.log("Сводка:", path.join(OUT, "SUMMARY.md"));
})().catch((e) => { console.error(e); process.exit(2); });
