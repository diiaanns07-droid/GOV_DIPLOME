"""K10 round 8: command-line preview of city-plan-v2 packs and scenarios (stdlib only; reads, never writes inputs).

    python3 -m k10plan.cli preview PACK.json [--app-root ROOT] [--plan mean] [--format text|json|html] [--out FILE]
    python3 -m k10plan.cli run SCENARIO.json --app-root ROOT [--city shymkent|astana] [--format text|json|html] [--out FILE]
    python3 -m k10plan.cli export-case PACK.json CASE_ID --out FILE
    python3 -m k10plan.cli verify-inputs --app-root ROOT [--index packs/INDEX.json] [--git-sha SHA] [--k10-package DIR]

preview/run always recompute with k10plan.oracle; a pack's stored "expected" is only compared, never shown as the answer.
With --app-root the real slice is read from the BUILD (and checked against the pack's copy); otherwise the pack's own
read-only copy is used. Exit codes: 0 ok, 1 check failed, 2 scenario refused.
"""
import argparse
import hashlib
import html
import json
import math
import subprocess
import sys
from pathlib import Path

from . import oracle as O
from . import packs as P
from . import slice as S

PLAN_LABEL = {"manual": "текущий (ручной)", "baseline": "без новых объектов", "mean": "среднее (mean)",
              "minimax": "худшая точка (minimax)", "coverage": "охват (coverage)"}
REASON_RU = {"count_exceeds_max_selected": "выбрано больше max_selected", "cost_exceeds_budget": "стоимость больше бюджета",
             "required_missing": "не выбран обязательный кандидат", "excluded_selected": "выбран исключённый кандидат",
             "required_count_exceeds_max_selected": "обязательных кандидатов больше, чем max_selected",
             "required_cost_exceeds_budget": "обязательные кандидаты стоят больше бюджета",
             "no_subset_satisfies_constraints": "ни один набор не проходит ограничения"}
LIMITS = ["Стоимости — условные единицы (SYNTHETIC), не тенге и не смета; бюджет тоже условный.",
          "Веса точек — приоритет пользователя, не число жителей.",
          "Расстояния — по прямой (гаверсинус) до записей этого среза; не пешее время и не транспорт.",
          "Вместимость, загрузка, население и социальный эффект не оцениваются.",
          "Оптимум — только среди введённых кандидатов, не лучший план города."]


def m(mm):
    return "—" if mm is None else f"{mm / 1000:.3f}"


def diff(mm):
    """A difference of distances in words; sub-metre gaps are shown in millimetres so that 'equal' is never implied."""
    a = abs(mm)
    return f"{a:.1f} мм" if a < 1000 else f"{a / 1000:.3f} м"


def plan_name(ids):
    return "+".join(ids) if ids else "(пусто)"


# ---------------------------------------------------------------- computation
def context_for(pack, app_root):
    if app_root and pack["kind"] == "real_slice":
        ctx = S.load_context(app_root, pack["city_id"])
        cat = pack["category"]
        now = sorted([q["id"], q["lon"], q["lat"]] for q in ctx["records"] if q["group"] == cat)
        was = sorted([q["id"], q["lon"], q["lat"]] for q in pack["source_copy"]["category_records"])
        same = now == was and ctx["source_snapshot"] == pack["provenance"]["source_snapshot"]
        return ctx, ("app-root совпадает с копией пакета" if same else "app-root ОТЛИЧАЕТСЯ от копии пакета (пакет устарел)"), same
    if pack["kind"] == "real_slice":
        prov = pack["provenance"]
        return ({"city_id": pack["city_id"], "bbox": prov["bbox"], "source_snapshot": prov["source_snapshot"],
                 "records": pack["source_copy"]["category_records"]}, "копия среза из пакета (только чтение)", True)
    s = pack["synthetic_slice"]
    return ({"city_id": pack["city_id"], "bbox": s["bbox"], "source_snapshot": s["source_snapshot"], "synthetic": True,
             "records": s["records"]}, "SYNTHETIC геометрия, не данные города", True)


def explain(exp, sc):
    """Sentences built only from computed values."""
    opt, plans, refs = exp["optimize"], exp["plans"], exp["plan_refs"]
    out = []
    base = plans[refs["baseline"]]
    if base["baseline_records_in_category"] == 0:
        out.append("В срезе нет исходных записей этой категории: «до» = null, изменение не вычисляется. "
                   "Нулевой охват здесь не доказывает отсутствие услуги в городе.")
    man = plans[refs["manual"]]
    if not man["feasibility"]["feasible"]:
        out.append("Ручной план недопустим: " + "; ".join(REASON_RU.get(c, c) for c in man["feasibility"]["reasons"]) + ".")
    if opt["status"] == "infeasible":
        out.append("Допустимых наборов нет: " + "; ".join(REASON_RU.get(c, c) for c in opt["infeasible_reasons"]) +
                   ". Ограничения не снимаются молча — измените бюджет, max_selected или список обязательных.")
        return out
    ob = opt["objectives"]
    sets = {k: tuple(v["selected_ids"]) for k, v in ob.items()}
    if len(set(sets.values())) == 1:
        out.append(f"Все три цели выбрали один и тот же набор {plan_name(ob['mean']['selected_ids'])}: это одно решение, а не три.")
    else:
        a, b, c = ob["mean"], ob["minimax"], ob["coverage"]
        if sets["mean"] != sets["minimax"]:
            out.append(f"mean выбирает {plan_name(a['selected_ids'])}, minimax — {plan_name(b['selected_ids'])}: у minimax худшая точка "
                       f"короче на {diff(a['max_mm'] - b['max_mm'])} ({m(b['max_mm'])} м), а средневзвешенное расстояние длиннее на "
                       f"{diff(b['weighted_mean_mm'] - a['weighted_mean_mm'])} ({m(b['weighted_mean_mm'])} м).")
        if sets["coverage"] != sets["mean"]:
            out.append(f"coverage выбирает {plan_name(c['selected_ids'])}: в радиусе {sc['coverage_radius_m']} м вес {c['covered_weight']} "
                       f"против {a['covered_weight']} у mean, средневзвешенное расстояние длиннее на "
                       f"{diff(c['weighted_mean_mm'] - a['weighted_mean_mm'])}.")
    if base["metrics"]["unknown_count"] == 0 and ob["mean"]["unknown_count"] == 0:
        gain = base["metrics"]["weighted_sum_mm"] - ob["mean"]["weighted_sum_mm"]
        out.append(f"Против плана без новых объектов mean сокращает взвешенную сумму расстояний на {m(gain)} м·вес "
                   f"за {ob['mean']['cost']} усл. ед.; это расстояние по прямой, не время и не вместимость.")
    if opt["pareto_note"]:
        out.append("Наборы с неизвестным расстоянием (unknown_count > 0) не ставятся на график стоимость→расстояние.")
    return out


def compute(pack, app_root=None):
    ctx, src_note, src_ok = context_for(pack, app_root)
    sc = dict(pack["scenario"])
    if not src_ok:
        return {"pack_id": pack["pack_id"], "source": src_note, "source_ok": False}
    exp = P.expected_for(ctx, sc)
    same = json.dumps(exp, sort_keys=True) == json.dumps(pack.get("expected"), sort_keys=True)
    return {"pack_id": pack["pack_id"], "kind": pack["kind"], "city_id": pack["city_id"], "category": pack["category"],
            "source": src_note, "source_ok": True, "matches_stored_expected": same if "expected" in pack else None,
            "scenario": sc, "result": exp, "explanation": explain(exp, sc), "limits": LIMITS,
            "names": {r["id"]: r.get("name") for r in ctx["records"]}}


# ---------------------------------------------------------------- text
def table(rows, head):
    w = [max(len(str(x)) for x in col) for col in zip(head, *rows)] if rows else [len(h) for h in head]
    line = lambda r: "  " + "  ".join(str(x).ljust(n) for x, n in zip(r, w))  # noqa: E731
    return "\n".join([line(head)] + [line(r) for r in rows])


def to_text(v, plan="mean"):
    if not v["source_ok"]:
        return f"{v['pack_id']}: {v['source']}"
    sc, exp = v["scenario"], v["result"]
    opt, plans, refs = exp["optimize"], exp["plans"], exp["plan_refs"]
    flags = lambda c: ",".join(f for f, on in (("required", c in sc["required_ids"]), ("excluded", c in sc["excluded_ids"]),  # noqa: E731
                                                     ("ручной", c in sc["selected_ids"])) if on)
    out = [f"Пакет {v['pack_id']} ({v['kind']}): {v['city_id']}, {v['category']}",
           f"Срез: {v['source']}; source_snapshot {sc['source_snapshot'][:23]}…; исходных записей категории: "
           f"{plans[refs['baseline']]['baseline_records_in_category']}",
           f"SYNTHETIC: точки, веса, кандидаты, стоимости; бюджет {sc['budget']} усл. ед., max_selected {sc['max_selected']}, "
           f"радиус анализа {sc['coverage_radius_m']} м (не норматив)",
           f"Пересчёт оракулом = ожидаемое в пакете: {'да' if v['matches_stored_expected'] else 'НЕТ' if v['matches_stored_expected'] is False else '—'}",
           f"Статус поиска: {opt['status']}; перебрано {opt['evaluated']}, допустимо {opt['feasible_count']}; "
           f"problem_digest {opt['problem_digest'][:23]}…", "", "Кандидаты (cost — условные единицы):",
           table([[c["id"], f"{c['lon']:.6f}", f"{c['lat']:.6f}", c["cost"], flags(c["id"])] for c in sc["candidates"]],
                 ["id", "lon", "lat", "cost", "флаги"]), "", "Сравнение планов:"]
    rows, seen = [], {}
    for key in ("manual", "mean", "minimax", "coverage", "baseline"):
        if key not in refs:
            continue
        pk = refs[key]
        met = plans[pk]["metrics"]
        same = f"= {PLAN_LABEL[seen[pk]]}" if pk in seen else ""
        seen.setdefault(pk, key)
        rows.append([PLAN_LABEL[key], plan_name(met["selected_ids"]), met["cost"], m(met["weighted_mean_mm"]), m(met["max_mm"]),
                     f"{met['covered_weight']} ({met['coverage_fraction'] * 100:.1f}%)", met["unknown_count"],
                     "да" if plans[pk]["feasibility"]["feasible"] else "нет", same])
    out.append(table(rows, ["план", "набор", "cost", "среднее, м", "худшая, м", "вес в радиусе", "неизв.", "допустим", ""]))
    key = plan if plan in refs else "manual"
    out += ["", f"Точки (план: {PLAN_LABEL[key]}, {plan_name(plans[refs[key]]['metrics']['selected_ids'])}):"]
    prow = []
    for r in plans[refs[key]]["rows"]:
        na = r["nearest_after"]
        who = "—" if na is None else (f"кандидат {na['id']}" if na["kind"] == "hypothetical" else
                                      f"источник {na['id'][:8]} {v['names'].get(na['id']) or ''}".strip())
        qa = ",".join(r.get("nearest_before_qa_flags") or [])
        ties = len(r.get("tied_before_ids") or [])
        prow.append([r["control_point_id"], r["weight"], m(r["before_mm"]), m(r["after_mm"]), m(r["delta_mm"]), who,
                     (qa + (f" ничья×{ties}" if ties > 1 else "")).strip()])
    out.append(table(prow, ["точка", "вес", "до, м", "после, м", "Δ, м", "ближайший после", "QA / ничья"]))
    if opt["pareto"]:
        out += ["", "Парето (стоимость → взвешенная сумма, только полностью известные наборы):",
                table([[q["cost"], m(q["weighted_sum_mm"]), plan_name(q["selected_ids"])] for q in opt["pareto"]],
                      ["cost", "сумма, м·вес", "набор"])]
    out += ["", "Изменение бюджета (остальное без изменений):",
            table([[s["budget"], s["status"]] + ([plan_name(s["objectives"][k]["selected_ids"]) for k in ("mean", "minimax", "coverage")]
                                                 if s["objectives"] else ["; ".join(s["infeasible_reasons"] or [])] * 3)
                   for s in opt["sensitivity"]], ["бюджет", "статус", "mean", "minimax", "coverage"])]
    out += ["", "Объяснение (из вычисленных значений):"] + [f"  - {x}" for x in v["explanation"]]
    out += ["", "Ограничения:"] + [f"  - {x}" for x in v["limits"]]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- html (all strings escaped; ids and names are plain text)
def to_html(v, plan="mean"):
    e = html.escape
    if not v["source_ok"]:
        return f"<!doctype html><meta charset='utf-8'><p>{e(v['pack_id'])}: {e(v['source'])}</p>"
    sc, exp = v["scenario"], v["result"]
    plans, refs = exp["plans"], exp["plan_refs"]
    key = plan if plan in refs else "manual"
    chosen = plans[refs[key]]
    sel = set(chosen["metrics"]["selected_ids"])
    pts = [(p["lon"], p["lat"]) for p in sc["control_points"]] + [(c["lon"], c["lat"]) for c in sc["candidates"]]
    recs = [(r["id"], r["lon"], r["lat"]) for r in v.get("_records", [])]
    pts += [(lo, la) for _, lo, la in recs]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    kx = math.cos(math.radians((y0 + y1) / 2))  # equal metres per pixel on both axes
    span = max((x1 - x0) * kx, y1 - y0) or 1
    pad, scale = 24, 512 / span
    W, H = round((x1 - x0) * kx * scale) + 2 * pad, round((y1 - y0) * scale) + 2 * pad
    sx = lambda lo: pad + (lo - x0) * kx * scale  # noqa: E731
    sy = lambda la: H - pad - (la - y0) * scale  # noqa: E731
    pos = {("source", i): (lo, la) for i, lo, la in recs}
    pos.update({("hypothetical", c["id"]): (c["lon"], c["lat"]) for c in sc["candidates"]})
    svg = []
    for p, r in zip(sc["control_points"], chosen["rows"]):
        na = r["nearest_after"]
        if na and (na["kind"], na["id"]) in pos:
            q = pos[(na["kind"], na["id"])]
            svg.append(f"<line x1='{sx(p['lon']):.1f}' y1='{sy(p['lat']):.1f}' x2='{sx(q[0]):.1f}' y2='{sy(q[1]):.1f}' class='ln'/>")
    for i, lo, la in recs:
        svg.append(f"<circle cx='{sx(lo):.1f}' cy='{sy(la):.1f}' r='4' class='src'><title>{e(i)} {e(v['names'].get(i) or '')}</title></circle>")
    for c in sc["candidates"]:
        cls = "cand on" if c["id"] in sel else "cand"
        svg.append(f"<rect x='{sx(c['lon']) - 5:.1f}' y='{sy(c['lat']) - 5:.1f}' width='10' height='10' class='{cls}'>"
                   f"<title>{e(c['id'])} · {c['cost']} усл. ед.</title></rect>"
                   f"<text x='{sx(c['lon']) + 7:.1f}' y='{sy(c['lat']) - 6:.1f}'>{e(c['id'])}</text>")
    for p in sc["control_points"]:
        svg.append(f"<circle cx='{sx(p['lon']):.1f}' cy='{sy(p['lat']):.1f}' r='{3 + p['weight'] ** 0.5:.1f}' class='cp'>"
                   f"<title>{e(p['id'])} · вес {p['weight']}</title></circle>")
    text = to_text(v, plan)
    return ("<!doctype html><html lang='ru'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>План {e(v['pack_id'])}</title><style>"
            ":root{--bg:#fbfaf7;--ink:#1d2329;--mut:#6b7280;--src:#6b7280;--cand:#b4442c;--cp:#2459a8;--ln:#9aa5b1}"
            "@media (prefers-color-scheme:dark){:root{--bg:#15181b;--ink:#e6e8ea;--mut:#9aa1a9;--src:#9aa1a9;--cand:#e0775f;--cp:#7aa7e6;--ln:#4b5560}}"
            "body{background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,sans-serif;margin:0 auto;max-width:1100px;padding:16px}"
            "svg{max-width:100%;height:auto;border:1px solid var(--ln)}.src{fill:var(--src)}.cand{fill:none;stroke:var(--cand);stroke-width:2}"
            ".cand.on{fill:var(--cand)}.cp{fill:none;stroke:var(--cp);stroke-width:2}.ln{stroke:var(--ln);stroke-dasharray:3 3}"
            "text{font-size:10px;fill:var(--cand)}pre{overflow-x:auto;font-size:12px;background:transparent}"
            ".note{color:var(--mut)}</style></head><body>"
            f"<h1>{e(v['pack_id'])}</h1><p class='note'>Предпросмотр K10 (оракул пересчитан). SYNTHETIC: точки, веса, кандидаты, стоимости. "
            f"План на схеме: {e(PLAN_LABEL[key])}. Серые — исходные записи категории, квадраты — кандидаты (залиты — выбраны), "
            "синие круги — контрольные точки, пунктир — ближайший объект после плана.</p>"
            f"<svg viewBox='0 0 {W} {H}' role='img' aria-label='схема плана'>{''.join(svg)}</svg>"
            f"<pre>{e(text)}</pre></body></html>\n")


# ---------------------------------------------------------------- commands
def emit(text, out):
    if out:
        Path(out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def render(v, fmt, plan, ctx_records):
    v["_records"] = ctx_records
    if fmt == "json":
        return json.dumps({k: x for k, x in v.items() if k not in ("_records",)}, ensure_ascii=False, indent=1) + "\n"
    if fmt == "html":
        return to_html(v, plan)
    return to_text(v, plan)


def cmd_preview(a):
    pack = json.loads(Path(a.pack).read_text(encoding="utf-8"))
    if "invalid_cases" in pack:
        lines = [f"{pack['pack_id']}: {len(pack['invalid_cases'])} случаев неверного ввода"]
        for c in pack["invalid_cases"]:
            ex = c["expected"]
            lines.append(f"  {c['case_id']:28s} {'отказ: ' + ex['code'] if ex['rejected'] else 'принять'}  {c['note']}")
        emit("\n".join(lines) + "\n", a.out)
        return 0
    v = compute(pack, a.app_root)
    if not v["source_ok"]:
        emit(f"{v['pack_id']}: {v['source']}\n", a.out)
        return 1
    ctx, _, _ = context_for(pack, a.app_root)
    recs = [r for r in ctx["records"] if r["group"] == pack["category"]]
    emit(render(v, a.format, a.plan, recs), a.out)
    return 0 if v["matches_stored_expected"] is not False else 1


def cmd_run(a):
    raw = Path(a.scenario).read_bytes()
    try:
        obj = O.parse_strict(raw)
        city = a.city or (obj.get("city_id") if isinstance(obj, dict) else None)  # --city = the city currently open
        if city not in O.CITIES:
            raise O.PlanError("bad_city", str(city)[:40])
        ctx = S.load_context(a.app_root, city)
        sc = O.validate_plan_scenario(obj, ctx)
    except O.PlanError as e:
        emit(json.dumps({"rejected": True, "code": e.code, "detail": str(e.detail)[:200],
                         "note": "отказ до расчёта; состояние не меняется"}, ensure_ascii=False) + "\n", a.out)
        return 2
    exp = P.expected_for(ctx, sc)
    v = {"pack_id": Path(a.scenario).name, "kind": "scenario_file", "city_id": city, "category": sc["category"],
         "source": f"app-root {a.app_root}", "source_ok": True, "matches_stored_expected": None, "scenario": sc,
         "result": exp, "explanation": explain(exp, sc), "limits": LIMITS, "names": {r["id"]: r.get("name") for r in ctx["records"]}}
    emit(render(v, a.format, a.plan, [r for r in ctx["records"] if r["group"] == sc["category"]]), a.out)
    return 0


def cmd_export_case(a):
    pack = json.loads(Path(a.pack).read_text(encoding="utf-8"))
    case = next((c for c in pack.get("invalid_cases", []) if c["case_id"] == a.case_id), None)
    if case is None:
        print(f"нет случая {a.case_id}", file=sys.stderr)
        return 1
    Path(a.out).write_bytes(P.case_text(case).encode("utf-8"))
    print(json.dumps({"case_id": a.case_id, "bytes": Path(a.out).stat().st_size, "expected": case["expected"]}, ensure_ascii=False))
    return 0


def cmd_verify_inputs(a):
    app = Path(a.app_root)
    now = S.input_manifest(app)
    rep = {"app_root": str(app), "data_files": {}, "code_files": {}, "ok": True}
    rec = json.loads(Path(a.index).read_text(encoding="utf-8"))["input_manifest"] if a.index else {}
    for rel in S.DATA_FILES:
        row = {"sha256": now[rel]}
        if rec:
            row["matches_index"] = now[rel] == rec.get(rel)
            rep["ok"] &= row["matches_index"]
        rep["data_files"][rel] = row
    for rel in S.CODE_FILES:
        rep["code_files"][rel] = {"sha256": now[rel], "same_as_index": (now[rel] == rec.get(rel)) if rec else None,
                                  "note": "code may differ between builds; informational"}
    if a.git_sha:
        for rel in S.DATA_FILES:
            blob = subprocess.run(["git", "show", f"{a.git_sha}:prototypes/city-evidence/{rel}"], capture_output=True)
            ok = blob.returncode == 0 and hashlib.sha256(blob.stdout).hexdigest() == now[rel]
            rep["data_files"][rel]["matches_git"] = ok
            rep["ok"] &= ok
        rep["git_sha"] = a.git_sha
    if a.k10_package:
        k = Path(a.k10_package)
        for city in O.CITIES:
            rel = f"inputs/k10/data/{city}/places_social.geojson"
            ok = (k / "data" / city / "places_social.geojson").exists() and S.sha256_file(k / "data" / city / "places_social.geojson") == now[rel]
            rep["data_files"][rel]["matches_k10_package"] = ok
            rep["ok"] &= ok
        rep["k10_package"] = str(k)
    rep["unchanged_while_checking"] = S.input_manifest(app) == now
    rep["ok"] &= rep["unchanged_while_checking"]
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0 if rep["ok"] else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="k10plan.cli", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preview")
    p.add_argument("pack")
    p.add_argument("--app-root")
    p.add_argument("--plan", default="mean", choices=list(PLAN_LABEL))
    p.add_argument("--format", default="text", choices=["text", "json", "html"])
    p.add_argument("--out")
    p.set_defaults(fn=cmd_preview)
    p = sub.add_parser("run")
    p.add_argument("scenario")
    p.add_argument("--app-root", required=True)
    p.add_argument("--city", choices=list(O.CITIES), help="city currently open (default: the file's city_id)")
    p.add_argument("--plan", default="mean", choices=list(PLAN_LABEL))
    p.add_argument("--format", default="text", choices=["text", "json", "html"])
    p.add_argument("--out")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("export-case")
    p.add_argument("pack")
    p.add_argument("case_id")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_export_case)
    p = sub.add_parser("verify-inputs")
    p.add_argument("--app-root", required=True)
    p.add_argument("--index")
    p.add_argument("--git-sha")
    p.add_argument("--k10-package")
    p.set_defaults(fn=cmd_verify_inputs)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
