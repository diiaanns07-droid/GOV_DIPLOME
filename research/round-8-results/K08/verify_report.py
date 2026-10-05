"""K08 R8: проверка report.json (roundtrip, устаревший срез, подмена, происхождение).

verify_report(meta, ctx) -> {"status": "ok"|"stale"|"tampered"|"rejected", "problems": [...], ...}
  1. версия: report_schema и scenario_schema должны быть известны (контракт без новой версии не меняется);
  2. сценарий извлекается из отчёта как недоверенный импорт (derived_results допускаются, но игнорируются);
     strict JSON roundtrip + validate_plan_scenario против текущего среза;
  3. snapshot не совпадает → "stale" с указанием, что изменилось (data.js / файл мест / release);
  4. все derived-поля пересчитываются и сравниваются → расхождения = "tampered" (путь поля);
  5. происхождение: sources каждой исходной записи = data.js = исходный GeoJSON пакета K10 (inputs/k10/...).
CLI: python verify_report.py --app-root APP REPORT.json
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import planlib as P  # noqa: E402
import report as R  # noqa: E402

KNOWN_REPORT = {R.REPORT_SCHEMA}
KNOWN_SCENARIO = {P.SCHEMA}
SCENARIO_KEYS = sorted(P.TOP_KEYS)
DERIVED_PATHS = ("plans", "optimization", "sensitivity", "scenario_digest", "problem_digest", "comparison")


def extract_scenario(meta, with_derived=True):
    """Сценарий для импорта: только поля контракта (+ derived_results как недоверенные данные)."""
    sc = {k: meta["scenario"][k] for k in SCENARIO_KEYS if k in meta["scenario"]}
    if with_derived:
        sc["derived_results"] = {"plans": meta.get("plans"), "optimization": meta.get("optimization")}
    return sc


def _diff(a, b, path="", out=None, limit=20):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}.{k}: поле только в одной версии")
            else:
                _diff(a[k], b[k], f"{path}.{k}", out, limit)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: длина {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            _diff(x, y, f"{path}[{i}]", out, limit)
    elif a != b:
        out.append(f"{path}: {str(a)[:60]} != {str(b)[:60]}")
    return out


def raw_sources(ctx, city):
    """sources[] записей из исходного GeoJSON пакета K10 (как скопировано в inputs/k10)."""
    pf = ctx.city(city)["files"]["places_social"]
    fc = json.loads((ctx.root / pf["path"]).read_text(encoding="utf-8"))
    return {f["id"]: f["properties"].get("sources") or [] for f in fc["features"]}


def _norm_sources(ss, keep_property):
    keys = ("dataset", "license", "record_id", "update_time") + (("property",) if keep_property else ())
    return [{k: s.get(k) for k in keys} for s in ss]


def verify_report(meta, ctx):
    probs = []
    if meta.get("report_schema") not in KNOWN_REPORT:
        return {"status": "rejected", "problems": [f"неизвестная report_schema {meta.get('report_schema')!r}"]}
    if meta.get("scenario_schema") not in KNOWN_SCENARIO or (meta.get("scenario") or {}).get("schema_version") not in KNOWN_SCENARIO:
        return {"status": "rejected", "problems": ["неизвестная версия сценария"]}
    if meta.get("metric_version") != P.METRIC_VERSION or meta.get("formula") != P.FORMULA:
        return {"status": "rejected", "problems": ["metric_version/formula не поддерживаются этой версией"]}
    # roundtrip как недоверенный импорт
    text = json.dumps(extract_scenario(meta), ensure_ascii=False, allow_nan=False)
    try:
        sc = P.validate_plan_scenario(P.loads_strict(text), ctx)
    except P.PlanError as e:
        if e.code == "foreign_snapshot":
            city = meta["scenario"]["city_id"]
            c = ctx.city(city) if city in ctx.data["cities"] else {}
            what = []
            if meta["source"].get("data_js_sha256") != ctx.data_js_sha256:
                what.append("data.js изменён")
            if (meta["source"].get("places_file") or {}).get("sha256") != ((c.get("files") or {}).get("places_social") or {}).get("sha256"):
                what.append("файл мест изменён")
            if meta["source"].get("release") != c.get("release"):
                what.append("другой выпуск Overture")
            return {"status": "stale", "problems": ["отчёт построен на другом срезе: " + (", ".join(what) or "изменились записи")],
                    "report_snapshot": meta["scenario"]["source_snapshot"], "current_snapshot": P.source_snapshot(ctx, city)}
        return {"status": "rejected", "problems": [f"{e.code}: {e.message}"]}
    fresh = R.build_report(P.plan_result(ctx, sc), meta.get("generated_utc"))
    for k in DERIVED_PATHS:
        probs += _diff(meta.get(k), fresh.get(k), k)
    warnings = []
    ctx_keys = ("data_js_sha256", "evidence_js_sha256")
    for k in ctx_keys:  # общий файл сборки мог измениться из-за другого города; срез этого отчёта проверяет snapshot
        if (meta.get("source") or {}).get(k) != fresh["source"].get(k):
            warnings.append(f"source.{k}: файл сборки изменился, срез отчёта (snapshot) тот же")
    probs += _diff({k: v for k, v in (meta.get("source") or {}).items() if k not in ctx_keys},
                   {k: v for k, v in fresh["source"].items() if k not in ctx_keys}, "source")
    rec_diff = _diff(meta.get("source_records"), fresh.get("source_records"), "source_records")
    qa_diff = [d for d in rec_diff if ".qa" in d]
    probs += [d for d in rec_diff if ".qa" not in d]
    probs += _diff(meta.get("scenario"), fresh.get("scenario"), "scenario")
    # происхождение до исходного GeoJSON K10
    raw = raw_sources(ctx, sc["city_id"])
    for r in meta.get("source_records") or []:
        rs = raw.get(r["id"])
        if rs is None:
            probs.append(f"source_records {r['id']}: нет в исходном GeoJSON пакета")
            continue
        # data.js хранит sources (возможно без property); каждая запись должна совпадать с одной из исходных
        raw_n = _norm_sources(rs, False)
        for s in _norm_sources(r.get("sources") or [], False):
            if s not in raw_n:
                probs.append(f"source_records {r['id']}: источник {s.get('dataset')}/{s.get('license')} не совпадает с исходным GeoJSON")
    if probs:
        return {"status": "tampered", "problems": probs, "warnings": warnings}
    if qa_diff:
        return {"status": "stale", "problems": ["QA-метки сборки изменились после построения отчёта"] + qa_diff, "warnings": warnings}
    return {"status": "ok", "problems": [], "warnings": warnings, "scenario_digest": fresh["scenario_digest"],
            "problem_digest": fresh["problem_digest"], "source_snapshot": sc["source_snapshot"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("report")
    a = ap.parse_args()
    ctx = P.Context(a.app_root)
    try:
        meta = P.loads_strict(Path(a.report).read_bytes())
    except P.PlanError as e:
        print(json.dumps({"status": "rejected", "problems": [f"{e.code}: {e.message}"]}, ensure_ascii=False))
        return 2
    res = verify_report(meta, ctx)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
