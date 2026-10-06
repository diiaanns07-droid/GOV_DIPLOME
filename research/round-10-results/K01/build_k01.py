"""K01 round 10: детерминированный сборщик пакета школ Шымкента (school-access-case-v1).

Входы (только чтение):
  - web/govtech/core/data.js и evidence.js из закреплённого коммита (git show <code_sha>:<path>), без изменения;
  - inputs/manual_review.json (ручной обзор K01), inputs/fetch_log.json (попытки открыть первоисточники).
Выходы рядом: sources.json, schools.json, match-review.json, evidence.json, shymkent.case.json.
Одинаковые входы → побайтно одинаковые выходы и ID (нет времени запуска, случайности, сетевых запросов).

Запуск из корня репозитория:
  python3 research/round-10-results/K01/build_k01.py --code-sha d2ff344c5ec9b9a729ea59df50ec81f981e619de
  python3 research/round-10-results/K01/build_k01.py --data-js PATH --evidence-js PATH --code-sha <sha>   # из копии
"""
import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
CITY = "shymkent"
CASE_SCHEMA = "school-access-case-v1"
R_EARTH = 6371008.8
GRID = (4, 3)            # точки анализа: 4 столбца × 3 ряда внутри bbox
CAND_GRID = (9, 7)       # сетка поиска мест для гипотез (не совпадает с точками анализа)
N_CANDIDATES = 3
MIN_CAND_SEP_M = 400     # гипотезы не ближе 400 м друг к другу
THRESHOLD_M = 500        # пользовательский порог по умолчанию, НЕ норматив


def load_js(text, var):
    m = re.search(r"window\." + var + r"\s*=\s*", text)
    if not m:
        raise SystemExit(f"нет window.{var}")
    body = text[m.end():].strip()
    if body.endswith(";"):
        body = body[:-1]
    return json.loads(body)


def read_inputs(args):
    if args.data_js:
        data_txt = Path(args.data_js).read_text(encoding="utf-8")
        ev_txt = Path(args.evidence_js).read_text(encoding="utf-8")
    else:
        show = lambda p: subprocess.check_output(["git", "show", f"{args.code_sha}:{p}"]).decode("utf-8")
        data_txt, ev_txt = show("web/govtech/core/data.js"), show("web/govtech/core/evidence.js")
    return data_txt, ev_txt


def hav_m(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--code-sha", required=True)
    ap.add_argument("--data-js")
    ap.add_argument("--evidence-js")
    args = ap.parse_args()
    data_txt, ev_txt = read_inputs(args)
    data, ev = load_js(data_txt, "CITY_EVIDENCE"), load_js(ev_txt, "CITY_OBS")
    review = json.loads((HERE / "inputs/manual_review.json").read_text(encoding="utf-8"))
    fetch = json.loads((HERE / "inputs/fetch_log.json").read_text(encoding="utf-8"))
    c, e = data["cities"][CITY], ev["cities"][CITY]
    bbox = c["bbox"]
    places = sorted([p for p in c["places"] if p["group"] == "school"], key=lambda p: p["id"])
    rev = {r["id"]: r for r in review["records"]}
    if set(rev) != {p["id"] for p in places}:
        raise SystemExit("ручной обзор не покрывает ровно все школьные записи среза — пересмотреть inputs/manual_review.json")
    places_sha = c["files"]["places_social"]["sha256"]
    review_sha = sha(json.dumps(review, ensure_ascii=False, sort_keys=True))
    data_sha, ev_sha = sha(data_txt), sha(ev_txt)

    # ---------- sources ----------
    sources = [
        {"id": "SRC-OVERTURE-PLACES", "url": "https://docs.overturemaps.org/guides/places/", "publisher": "Overture Maps Foundation",
         "title": f"Overture places (social), срез K10 «{c['label']}», release {c['release']}", "published_at": None, "data_period": f"release {c['release']}",
         "retrieved_at": c["retrieved_utc"], "verification_status": "secondary_only", "license": "CDLA-Permissive-2.0 (по записям; upstream dataset meta)",
         "content_sha256": places_sha, "note": f"Файл {c['files']['places_social']['path']} пакета K10 {data['inputs']['k10_sha']}; в репозитории кодовой базы — web/govtech/core/data.js @ {args.code_sha} (sha256 {data_sha})."},
        {"id": "SRC-CORE-QA", "url": f"git:{args.code_sha}:web/govtech/core/evidence.js", "publisher": "GOV_DIPLOME (сборка, K05/K03 QA)",
         "title": "QA среза: colocated, possible_duplicates, category_doubt; привязка к районам K03 (OSM, не официально)", "published_at": None, "data_period": f"release {c['release']}",
         "retrieved_at": None, "verification_status": "secondary_only", "license": "unknown", "content_sha256": ev_sha},
        {"id": "SRC-K01-REVIEW", "url": "research/round-10-results/K01/inputs/manual_review.json", "publisher": "K01 round 10", "title": "Ручной обзор типа записей и роли в кейсе",
         "published_at": review["reviewed_at"], "data_period": None, "retrieved_at": None, "verification_status": "secondary_only", "license": "unknown", "content_sha256": review_sha},
    ]
    seen = set()
    for a in fetch["attempts"]:
        if a["source_id"] in seen:
            continue
        seen.add(a["source_id"])
        sources.append({"id": a["source_id"], "url": a["url"], "publisher": None, "title": None, "published_at": None, "data_period": None,
                        "retrieved_at": None, "verification_status": "not_fetched", "license": "unknown", "content_sha256": None,
                        "attempts": [{"method": x["method"], "error": x["error"], "attempted_at": fetch["attempted_at"]} for x in fetch["attempts"] if x["source_id"] == a["source_id"]]})
    official_ids = [s["id"] for s in sources if s["verification_status"] == "not_fetched" and not s["id"].startswith(("SRC-OSM", "SRC-WIKI", "SRC-GITHUB"))]

    # ---------- schools ----------
    coloc = {}
    for g in e["qa"]["colocated"]:
        for i in g["ids"]:
            coloc[i] = len(g["ids"])
    dup = {i for g in e["qa"].get("possible_duplicates", []) for i in g.get("ids", [])}
    conflicts = {i: cf["id"] for cf in review["conflicts"] for i in cf["record_ids"]}
    schools, rows = [], []
    for p in places:
        r, s0 = rev[p["id"]], p["sources"][0]
        qa = []
        if p["id"] in e["qa"]["category_doubt"]:
            qa.append("category_doubt:" + e["qa"]["category_doubt"][p["id"]]["rule"])
        if p["id"] in coloc:
            qa.append(f"colocated:{coloc[p['id']]}_records_same_point")
        if p["id"] in dup:
            qa.append("possible_duplicate")
        if p["id"] in conflicts:
            qa.append("conflict:" + conflicts[p["id"]])
        qa.append("official_status:not_verified")
        sid = "overture:" + p["id"]
        district = e["place_district"].get(p["id"])
        schools.append({
            "id": sid, "label": p["name"], "lon": p["lon"], "lat": p["lat"], "kind": "observed_secondary", "category": "school",
            "verification_status": "conflict" if p["id"] in conflicts else "secondary_only",
            "access_eligibility": "unknown", "capacity": None, "capacity_source_ids": [],
            "source_ids": ["SRC-OVERTURE-PLACES", "SRC-K01-REVIEW"] + (["SRC-CORE-QA"] if len(qa) > 1 else []),
            "field_provenance": {
                "label": {"source_id": "SRC-OVERTURE-PLACES", "method": "Overture names.primary", "upstream": f"{s0['dataset']}:{s0['record_id']}", "upstream_update_time": s0.get("update_time")},
                "lon_lat": {"source_id": "SRC-OVERTURE-PLACES", "method": "Overture geometry (вторичный источник; не официальная координата)"},
                "address": {"source_id": "SRC-OVERTURE-PLACES", "value": p.get("address")},
                "overture_category": {"source_id": "SRC-OVERTURE-PLACES", "value": p["category"], "confidence": p["confidence"]},
                "type_assessment": {"source_id": "SRC-K01-REVIEW", "value": r["type_assessment"], "method": "ручной обзор по названию/категории/адресу/QA"},
                "district": {"source_id": "SRC-CORE-QA", "value": district and district.get("district"), "method": "K03 assign по границам OSM/Overture — не официальная принадлежность"},
                "official_match": {"source_ids": official_ids, "status": "not_fetched"},
                "access_eligibility": {"value": "unknown", "reason": "официальный статус/правила приёма не открыты"},
                "capacity": {"value": None, "reason": "источник вместимости не найден"}},
            "qa": qa, "case_role": r["case_role"]})
        rows.append({"id": sid, "label": p["name"], "address": p.get("address"), "overture_category": p["category"], "confidence": p["confidence"],
                     "upstream": f"{s0['dataset']}:{s0['record_id']}", "upstream_update_time": s0.get("update_time"),
                     "type_assessment": r["type_assessment"], "case_role": r["case_role"], "reason": r["reason"], "qa": qa,
                     "official_match": {"status": "unmatched_not_fetched", "official_id": None, "source_ids": official_ids},
                     "osm_match": {"status": "unmatched_not_fetched", "osm_id": None, "source_ids": ["SRC-OSM-OVERPASS"]},
                     "conflict_id": conflicts.get(p["id"])})
    targets = [s for s in schools if s["case_role"] == "target"]

    # ---------- origins: регулярная сетка точек анализа (derived, равные веса, не жители) ----------
    W, S, E, N = bbox
    cols, rws = GRID
    origins = []
    for j in range(rws):
        for i in range(cols):
            lon = round(W + (E - W) * (i + 0.5) / cols, 6)
            lat = round(S + (N - S) * (j + 0.5) / rws, 6)
            origins.append({"id": f"shy-o-r{j + 1}c{i + 1}", "label": f"Точка анализа ряд {j + 1}, столбец {i + 1}", "lon": lon, "lat": lat, "kind": "derived",
                            "weight": 1, "source_ids": ["SRC-K01-REVIEW"],
                            "field_provenance": {"lon_lat": {"method": f"регулярная сетка {cols}×{rws}, центры ячеек внутри bbox среза", "parent_source_id": None}},
                            "qa": ["not_a_household", "not_population_weighted", "may_fall_on_street_or_empty_lot"]})

    # ---------- кандидаты: гипотезы, удалённые от известных школ (жадно, детерминированно) ----------
    cc, cr = CAND_GRID
    # Только внутренние узлы (без внешнего кольца): у краёв «далеко от школ» часто означает лишь школы за границей bbox (нет буфера).
    pool = [(round(W + (E - W) * (i + 0.5) / cc, 6), round(S + (N - S) * (j + 0.5) / cr, 6)) for j in range(1, cr - 1) for i in range(1, cc - 1)]
    chosen = []
    for k in range(N_CANDIDATES):
        best = None
        for lon, lat in pool:
            if any(hav_m(lon, lat, a, b) < MIN_CAND_SEP_M for a, b in chosen):
                continue
            d = min(hav_m(lon, lat, t["lon"], t["lat"]) for t in targets)
            key = (-round(d * 1000), lon, lat)
            if best is None or key < best[0]:
                best = (key, lon, lat, d)
        chosen.append((best[1], best[2]))
    candidates = [{"id": f"shy-h-{k + 1}", "label": f"Гипотетическое место {'ABC'[k]}", "lon": lon, "lat": lat, "kind": "hypothesis", "category": "school",
                   "cost": None, "land_status": "unknown", "source_ids": ["SRC-K01-REVIEW"],
                   "field_provenance": {"lon_lat": {"method": f"внутренний узел сетки {cc}×{cr} (без внешнего кольца) с наибольшим расстоянием по прямой до ближайшей target-школы, не ближе {MIN_CAND_SEP_M} м к другим гипотезам"},
                                        "land_status": {"value": "unknown", "reason": "наличие свободного участка не проверялось"}},
                   "qa": ["hypothetical_location", "not_a_land_plot", "no_cost_data", "no_capacity_data"]}
                  for k, (lon, lat) in enumerate(chosen)]

    # ---------- кейс ----------
    snapshot_id = f"shymkent-{c['release']}-" + sha(json.dumps([places_sha, bbox, review_sha, ev_sha], sort_keys=True))[:16]
    case = {
        "schema_version": CASE_SCHEMA, "case_id": "shymkent-k10r3-schools-v1", "city_id": CITY,
        "title": "Шымкент, участок ~2×2 км: удалённость точек анализа от известных школ (учебный пример на вторичных данных)",
        "bbox": bbox, "snapshot_id": snapshot_id, "sources": sources,
        "schools": [{k: v for k, v in s.items() if k != "case_role"} for s in targets],
    }
    meta = {"schema": "k01-case-meta-v1", "case_id": case["case_id"], "snapshot_id": snapshot_id,
        "note": "Дополнение к shymkent.case.json вне полей CONTRACT (кейс остаётся строго по контракту): исключённые записи, пробелы данных, provenance сборки.",
        "excluded_school_records": [{"id": s["id"], "label": s["label"], "reason": rev[s["id"].split(":", 1)[1]]["reason"], "qa": s["qa"]} for s in schools if s["case_role"] != "target"],
    }
    case.update({"origins": origins, "candidates": candidates, "selected_candidate_ids": [],
        "parameters": {"distance_method": "geodesic", "routing_policy_id": None, "threshold_m": THRESHOLD_M, "max_new_objects": 1},
        "model_assumptions": [
            "Все школы — вторичные записи Overture (upstream meta); официальный перечень, принадлежность и правила приёма не проверены (NOT_FETCHED).",
            "Из 15 записей группы school в расчёт включены 5 (по названию похожи на общеобразовательные); остальные показаны как исключённые с причиной.",
            "Две включённые записи (ALEM мектебі / Алем мектеп) — возможный дубль CONFLICT-ALEM-01; на минимальные расстояния не влияет.",
            "Baiterek School исключена: координата — точка-заглушка; если это действующая школа, расстояния для её окрестности завышены.",
            "Точки анализа — регулярная сетка, равные веса; не дома, не дети, не население.",
            "Гипотетические места выбраны алгоритмом как удалённые от известных школ; это не свободные участки, стоимость и вместимость неизвестны.",
            "Расстояние по прямой (geodesic) — не пеший путь; школы вне bbox не учтены, поэтому у краёв участка расстояния могут быть завышены.",
            "Подтверждение реальной проблемы пользователя (нехватка доступных школ) этим пакетом не доказано: он показывает только наличие/отсутствие школьных точек в данных."]})
    meta.update({
        "parameter_notes": {"threshold_m": "пользовательский параметр анализа, не норматив доступности"},
        "data_gaps": [{"id": "GAP-OFFICIAL-LIST", "text": "Нет официального перечня школ Шымкента (источники NOT_FETCHED).", "source_ids": official_ids},
                      {"id": "GAP-CAPACITY", "text": "Нет вместимости и контингента; capacity=null.", "source_ids": []},
                      {"id": "GAP-BUFFER", "text": "Школы за пределами bbox не загружены (нет буфера); расстояния у краёв — верхняя оценка.", "source_ids": ["SRC-OVERTURE-PLACES"]},
                      {"id": "GAP-OSM-GEOMETRY", "text": "Геометрия OSM зданий школ не загружена (Overpass NOT_FETCHED).", "source_ids": ["SRC-OSM-OVERPASS"]}],
        "provenance": {"code_sha": args.code_sha, "data_js_sha256": data_sha, "evidence_js_sha256": ev_sha, "manual_review_sha256": review_sha,
                       "builder": "research/round-10-results/K01/build_k01.py", "k10_sha": data["inputs"]["k10_sha"]}})

    # ---------- evidence (факты пакета) ----------
    from collections import Counter
    by_type = Counter(r["type_assessment"] for r in rows)
    facts = [
        {"id": "F-RECORDS", "statement": "Записей группы school в срезе", "value": len(places), "unit": "records", "kind": "observed_secondary", "source_ids": ["SRC-OVERTURE-PLACES"]},
        {"id": "F-TARGETS", "statement": "Записей, включённых в расчёт как школы", "value": len(targets), "unit": "records", "kind": "derived", "source_ids": ["SRC-K01-REVIEW"]},
        {"id": "F-EXCLUDED-BY-TYPE", "statement": "Распределение ручной оценки типа", "value": dict(sorted(by_type.items())), "unit": "records", "kind": "derived", "source_ids": ["SRC-K01-REVIEW", "SRC-CORE-QA"]},
        {"id": "F-OFFICIAL-MATCHED", "statement": "Записей, сверенных с официальным перечнем", "value": None, "unit": "records", "kind": "derived",
         "missing_reason": "official_sources_not_fetched (это НЕ 0 официальных школ)", "source_ids": official_ids},
        {"id": "F-CONFLICTS", "statement": "Нерешённые коллизии", "value": [cf["id"] for cf in review["conflicts"]], "unit": "ids", "kind": "derived", "source_ids": ["SRC-K01-REVIEW", "SRC-CORE-QA"]},
        {"id": "F-UPSTREAM-DATE", "statement": "Дата обновления upstream-записей (meta) по Overture", "value": sorted({r["upstream_update_time"] for r in rows}), "unit": "iso8601", "kind": "observed_secondary", "source_ids": ["SRC-OVERTURE-PLACES"]},
        {"id": "F-CAPACITY", "statement": "Вместимость школ", "value": None, "unit": "places", "kind": "derived", "missing_reason": "no_source", "source_ids": []},
    ]
    evidence = {"schema": "k01-evidence-v1", "city_id": CITY, "snapshot_id": snapshot_id, "code_sha": args.code_sha, "facts": facts,
                "user_problem_confirmation": {"status": "not_confirmed", "note": "Наличие школьных точек в данных не подтверждает реальную проблему доступности; нужна проверка с пользователями (K09) и официальные данные."}}
    match_review = {"schema": "k01-match-review-v1", "city_id": CITY, "snapshot_id": snapshot_id, "official_list_status": "not_fetched",
                    "records": rows, "conflicts": review["conflicts"]}
    out = {"sources.json": {"schema": "k01-sources-v1", "sources": sources}, "schools.json": {"schema": "k01-schools-v1", "city_id": CITY, "snapshot_id": snapshot_id, "schools": schools},
           "match-review.json": match_review, "evidence.json": evidence, "shymkent.case.json": case, "shymkent.case.meta.json": meta}
    for name, obj in out.items():
        (HERE / name).write_text(dump(obj), encoding="utf-8")
    print("snapshot_id", snapshot_id, "| targets", len(targets), "| excluded", len(schools) - len(targets), "| candidates", [(x["id"], x["lon"], x["lat"]) for x in candidates])


if __name__ == "__main__":
    main()
