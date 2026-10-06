"""K01 round 10: валидатор пакета школ Шымкента (school-access-case-v1) и проверка воспроизводимости.

  python3 research/round-10-results/K01/validate_k01.py --code-sha d2ff344c5ec9b9a729ea59df50ec81f981e619de [--json out.json]
Проверки: поля CONTRACT, kind/verification_status, ссылки source_ids, bbox, уникальность ID, null≠0, покрытие обзора,
отсутствие персональных контактов, воспроизводимость (пересборка во временной копии = те же байты/ID).
Дополнительно: справочный предпросмотр geodesic до/после для каждой гипотезы (не авторитетный расчёт BUILD).
"""
import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
KINDS = {"observed", "observed_secondary", "derived", "hypothesis", "synthetic"}
VSTAT = {"primary_checked", "secondary_only", "conflict", "not_fetched"}
SRC_FIELDS = ["id", "url", "publisher", "title", "retrieved_at", "verification_status", "license"]
REC_FIELDS = ["id", "label", "lon", "lat", "kind", "source_ids", "field_provenance", "qa"]
OUTPUTS = ["sources.json", "schools.json", "match-review.json", "evidence.json", "shymkent.case.json", "shymkent.case.meta.json"]
results = []


def check(name, ok, detail=""):
    results.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f" — {detail}"))


def hav_mm(a, b):
    p1, p2 = math.radians(a[1]), math.radians(b[1])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2
    return math.floor(2 * 6371008.8 * math.asin(math.sqrt(min(1.0, max(0.0, h)))) * 1000 + 0.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--code-sha", required=True)
    ap.add_argument("--json")
    args = ap.parse_args()
    load = lambda n: json.loads((HERE / n).read_text(encoding="utf-8"))
    case, schools, mr, srcs = load("shymkent.case.json"), load("schools.json"), load("match-review.json"), load("sources.json")

    # 1. структура кейса
    top = ["schema_version", "case_id", "city_id", "title", "bbox", "snapshot_id", "sources", "schools", "origins", "candidates",
           "selected_candidate_ids", "parameters", "model_assumptions"]
    check("case: обязательные поля CONTRACT", all(k in case for k in top), [k for k in top if k not in case])
    check("case: нет полей верхнего уровня вне CONTRACT (строгий импорт)", set(case) == set(top), sorted(set(case) - set(top)))
    check("parameters: только поля CONTRACT", set(case["parameters"]) == {"distance_method", "routing_policy_id", "threshold_m", "max_new_objects"}, sorted(case["parameters"]))
    meta = load("shymkent.case.meta.json")
    check("case: schema_version/city_id", case["schema_version"] == "school-access-case-v1" and case["city_id"] in ("shymkent", "astana"))
    W, S, E, N = case["bbox"]
    check("case: bbox корректен", W < E and S < N and all(isinstance(x, (int, float)) for x in case["bbox"]))
    sids = {s["id"] for s in case["sources"]}
    check("sources: поля и verification_status", all(all(k in s for k in SRC_FIELDS) and s["verification_status"] in VSTAT for s in case["sources"]))
    check("sources: not_fetched имеют URL и ошибку попытки", all(s["url"] and s.get("attempts") for s in case["sources"] if s["verification_status"] == "not_fetched"))
    recs = case["schools"] + case["origins"] + case["candidates"]
    check("записи: обязательные поля", all(all(k in r for k in REC_FIELDS) for r in recs), [r["id"] for r in recs if not all(k in r for k in REC_FIELDS)])
    check("записи: kind из допустимого набора", all(r["kind"] in KINDS for r in recs))
    check("записи: source_ids существуют", all(r["source_ids"] and set(r["source_ids"]) <= sids for r in recs))
    ids = [r["id"] for r in recs]
    check("ID уникальны", len(ids) == len(set(ids)))
    check("координаты внутри bbox и конечны", all(math.isfinite(r["lon"]) and math.isfinite(r["lat"]) and W <= r["lon"] <= E and S <= r["lat"] <= N for r in recs))
    check("школы: category/access_eligibility/capacity по CONTRACT",
          all(r["category"] == "school" and r["access_eligibility"] in ("known_public", "known_restricted", "unknown") and r["capacity"] is None and r["capacity_source_ids"] == [] for r in case["schools"]))
    check("школы: нет официального статуса без первоисточника", all(r["verification_status"] in ("secondary_only", "conflict") and r["kind"] == "observed_secondary" for r in case["schools"]))
    check("origins: derived, равные веса, не жители", all(o["kind"] == "derived" and o["weight"] == 1 and "not_a_household" in o["qa"] for o in case["origins"]))
    check("candidates: hypothesis, cost=null, land_status=unknown", all(c["kind"] in ("hypothesis", "synthetic") and c["cost"] is None and c["land_status"] == "unknown" for c in case["candidates"]))
    check("candidates: 2–3 гипотезы, origins ≤ 25, candidates ≤ 16", 2 <= len(case["candidates"]) <= 3 and len(case["origins"]) <= 25)
    p = case["parameters"]
    check("parameters: geodesic, порог > 0, max_new_objects=1", p["distance_method"] in ("geodesic", "pedestrian-v1") and p["threshold_m"] > 0 and p["max_new_objects"] == 1)

    # 2. покрытие всех записей среза и пакет схем
    all_ids = {s["id"] for s in schools["schools"]}
    check("schools.json: все записи имеют source/период/проверку", all(s["source_ids"] and s["field_provenance"]["label"].get("upstream_update_time") and s["verification_status"] for s in schools["schools"]))
    check("match-review: все записи среза, официальное сопоставление явно not_fetched",
          {r["id"] for r in mr["records"]} == all_ids and all(r["official_match"]["status"] == "unmatched_not_fetched" for r in mr["records"]))
    check("case.schools ⊆ schools.json target", {s["id"] for s in case["schools"]} == {s["id"] for s in schools["schools"] if s["case_role"] == "target"})
    check("исключённые записи перечислены с причиной (meta)", len(meta["excluded_school_records"]) + len(case["schools"]) == len(all_ids) and all(x["reason"] for x in meta["excluded_school_records"]) and meta["snapshot_id"] == case["snapshot_id"])
    ev = load("evidence.json")
    om = next(f for f in ev["facts"] if f["id"] == "F-OFFICIAL-MATCHED")
    check("null ≠ 0: официальная сверка null с причиной", om["value"] is None and "not_fetched" in om["missing_reason"])
    check("подтверждение проблемы пользователя отделено", ev["user_problem_confirmation"]["status"] == "not_confirmed")

    # 3. персональные данные
    blob = "".join((HERE / n).read_text(encoding="utf-8") for n in OUTPUTS)
    pii = re.findall(r"(?<![\d:])\+?[78][\s(-]*7\d{2}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)|[\w.+-]+@[\w-]+\.[\w.]+|\bИИН\b|\b\d{12}\b", blob)
    check("нет телефонов/e-mail/ИИН в выходах", not pii, pii[:3])

    # 4. воспроизводимость: пересборка во временной копии
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "K01"
        shutil.copytree(HERE, tmp, ignore=shutil.ignore_patterns(*OUTPUTS, "runs", "__pycache__"))
        repo = HERE.parents[2]
        subprocess.check_call([sys.executable, str(tmp / "build_k01.py"), "--code-sha", args.code_sha], cwd=repo, stdout=subprocess.DEVNULL)
        same = {n: hashlib.sha256((tmp / n).read_bytes()).hexdigest() == hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in OUTPUTS}
    check("воспроизводимость: те же входы → те же байты и ID", all(same.values()), same)

    # 5. справочный предпросмотр (geodesic, мм) — не авторитетный расчёт
    T = [(s["lon"], s["lat"]) for s in case["schools"]]
    before = [min(hav_mm((o["lon"], o["lat"]), t) for t in T) for o in case["origins"]]
    thr = p["threshold_m"] * 1000
    preview = {"note": "справочно: прямые расстояния до 5 target-школ, мм; BUILD считает compareCase сам", "now": {"sum_mm": sum(before), "max_mm": max(before), "within": sum(b <= thr for b in before)}}
    for c in case["candidates"]:
        after = [min(b, hav_mm((o["lon"], o["lat"]), (c["lon"], c["lat"]))) for b, o in zip(before, case["origins"])]
        preview[c["id"]] = {"sum_mm": sum(after), "max_mm": max(after), "within": sum(a <= thr for a in after), "improved_points": sum(a < b for a, b in zip(after, before))}
    print(json.dumps(preview, ensure_ascii=False))
    check("предпросмотр: хотя бы одна гипотеза меняет расстояния (кейс не вырожден)", any(v["improved_points"] > 0 for k, v in preview.items() if k.startswith("shy-h")))
    failed = sum(r["status"] == "FAIL" for r in results)
    print(f"{len(results) - failed} PASS, {failed} FAIL")
    if args.json:
        Path(args.json).write_text(json.dumps({"code_sha": args.code_sha, "snapshot_id": case["snapshot_id"], "results": results, "preview": preview}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
