// K02 r9: envelope-фикстуры city-resilience-v1 из r8 сценариев (inputs/r8) и data.js сборки. Детерминированно.
//   node make_resilience_fixtures.cjs --app-root <prototypes/city-evidence> --build-sha <sha>
const fs = require("fs"), path = require("path"), crypto = require("crypto");
const { F, PL, r8, ctxFor, scenarioFor, arg, APP } = require("./tests/common.cjs");
const SHA = arg("--build-sha") || "unknown", OUT = path.join(__dirname, "fixtures"); fs.mkdirSync(OUT, { recursive: true });
const sha = (p) => crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex");
function nearestOf(ctx, sc, pointId) { const ev = PL.evaluatePlan(ctx, sc, []); return ev.rows.find((r) => r.id === pointId).nearest_before.id; }
function make(name, fxName, casesFn, note) {
  const fx = r8(fxName), { ctx, sc } = scenarioFor(fx);
  const plan = { ...fx.scenario, source_snapshot: ctx.source_snapshot };
  const env = { schema_version: "city-resilience-v1", plan, cases: casesFn(ctx, sc) };
  const prov = fx.provenance.kind === "synthetic" ? { kind: "synthetic", note } : { kind: "real_slice_with_synthetic_candidates_and_user_cases", build_sha: SHA,
    data_js_sha256: sha(path.join(APP, "web/data.js")), plan_js_sha256: sha(path.join(APP, "web/plan.js")), from_r8_fixture: fxName, note };
  fs.writeFileSync(path.join(OUT, name + ".json"), JSON.stringify({ name, provenance: prov, envelope: env }, null, 1) + "\n");
  console.log("wrote", name, env.cases.map((c) => `${c.id}:${c.disabled_source_ids.length}`).join(" "));
}
const allSrc = (ctx, sc) => ctx.places.filter((p) => p.group === sc.category).map((p) => p.id).sort();
make("res_shymkent_school", "real_shymkent_school", (ctx, sc) => {
  const a = nearestOf(ctx, sc, "двор-север"), b = nearestOf(ctx, sc, "двор-юг"), c = nearestOf(ctx, sc, "остановка");
  return [{ id: "без-ближайшей-север", label: "Условно не учитываем ближайшую школу к точке «двор-север»", disabled_source_ids: [a] },
    { id: "юг-и-остановка", label: "Не учитываем две записи (юг, остановка)", disabled_source_ids: [...new Set([b, c])] },
    { id: "дубль-север", label: "Тот же набор, что и первый случай", disabled_source_ids: [a] },
    { id: "все-записи", label: "Все записи категории условно не учитываются", disabled_source_ids: allSrc(ctx, sc) }];
}, "Исключения — допущение пользователя для анализа, не подтверждение закрытия. Кандидаты/веса/стоимости — synthetic demo.");
make("res_astana_clinic", "real_astana_clinic", (ctx, sc) => {
  const a = nearestOf(ctx, sc, "p4"), b = nearestOf(ctx, sc, "p2");
  return [{ id: "p4-без-ближайшей", label: "Не учитываем ближайшую поликлинику к p4", disabled_source_ids: [a] },
    { id: "p2-p4", label: "Не учитываем ближайшие к p2 и p4", disabled_source_ids: [...new Set([a, b])] }];
}, "Исключения — допущение пользователя для анализа. Кандидаты/веса/стоимости — synthetic demo.");
make("res_synthetic_infeasible", "synthetic_infeasible_required", (ctx, sc) => [{ id: "off", label: "Единственная запись выключена", disabled_source_ids: allSrc(ctx, sc) }],
  "Синтетика: required дороже бюджета — infeasible.");
make("res_synthetic_tie", "synthetic_tie_same_winners", (ctx, sc) => [{ id: "off", label: "Единственная запись выключена", disabled_source_ids: allSrc(ctx, sc) }],
  "Синтетика: равные кандидаты; обычный и устойчивый совпадают.");
