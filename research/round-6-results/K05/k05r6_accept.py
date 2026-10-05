#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K05 round 6: приёмка контракта НОВОЙ сборки (k05-obs-v1.2+k12r4) — адаптер к новому расположению модулей.

Отличия от research/round-5-results/K05/k05r5_compat.py (test source @ fb2dea6), из-за которых он
TEST_INCOMPATIBLE на 064ed25:
  * r5 грузил v1.1 из inputs/k05_root (в новой сборке это неизменённый оригинал, не рабочий контракт),
    а v1.2 — из своей папки; здесь оба берутся из СБОРКИ через её tools/contract.py
    (inputs/contract/research/..., K12-патч применён tools/setup_contract.py);
  * r5 D08 валидировал записи v1.1-валидатором; в новой сборке записи v1.2 → contract.validate (C4);
  * старые EXPECTED_FAIL не применяются: любое падение — FAIL.
Фикстуры и проверки данных переиспользуются из k05r5_compat (без изменений правил).

  python k05r6_accept.py --app-root <checkout>/prototypes/city-evidence [--json OUT]
  python k05r6_accept.py --url http://127.0.0.1:8765/ --app-root <checkout>/prototypes/city-evidence
(--url берёт evidence.js с сервера; контракт всё равно из --app-root.)
Код выхода 0 — все инварианты PASS; 1 — есть FAIL.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
R5 = HERE.parents[1] / "round-5-results" / "K05"
sys.path.insert(0, str(R5))
import k05r5_compat as T  # noqa: E402  (fixtures v11_base/v12_square, loads_strict, parse_evidence)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_build_contract(app):
    spec = importlib.util.spec_from_file_location("build_contract", app / "tools" / "contract.py")
    K = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(K)
    return K


def git_head(path):
    try:
        return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:  # noqa: BLE001
        return None


def codes(msgs):
    return {m.split(":")[0] for m in msgs}


def run(app, url):
    K = load_build_contract(app)
    C4, C3 = K.C4, K.C3
    man = json.loads((app / "inputs/contract/CONTRACT_MANIFEST.json").read_text(encoding="utf-8"))
    res = []

    def inv(iid, title, fn, note=""):
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"{type(e).__name__}: {e}"
        res.append({"id": iid, "title": title, "verdict": "PASS" if ok else "FAIL", "detail": str(detail)[:400],
                    **({"note": note} if note else {})})

    text = T.evidence_text(None if url else app, url)
    ev = T.parse_evidence(text)
    allobs = [(c, o) for c, v in ev["cities"].items() for o in v["observations"]]

    # --- данные новой сборки (реальные) ---
    inv("D01_strict_json", "evidence.js — строгий JSON", lambda: (True, f"{len(text)} символов, {len(allobs)} записей"))
    inv("D02_unique_obs_id", "obs_id уникальны", lambda: (
        len({o['obs_id'] for _, o in allobs}) == len(allobs), f"{len(allobs)} записей"))
    inv("D03_null_iff_missing", "value=null ⇔ статус отсутствия", lambda: (
        not [o for _, o in allobs if (o["value"] is None) != (o["value_status"] in ("missing", "suppressed", "not_applicable"))], ""))
    inv("D04_honest_zero", "reported_zero только при coverage.complete", lambda: (
        not [o["obs_id"] for _, o in allobs if o["value_status"] == "reported_zero" and not o["coverage"]["complete"]],
        f"reported_zero: {sum(o['value_status'] == 'reported_zero' for _, o in allobs)}"))
    inv("D05_counts_integer", "records/segments — целые ≥ 0", lambda: (
        not [o["obs_id"] for _, o in allobs if o["value"] is not None and o["unit"] in ("records", "segments", "count")
             and (o["value"] < 0 or o["value"] != int(o["value"]))], ""))
    inv("D06_city", "город раздела = city_id/geo_unit_id", lambda: (
        not [o["obs_id"] for c, o in allobs if o["city_id"] != f"kz.{c}" or not o["geo_unit_id"].startswith(f"kz.{c}")], ""))
    inv("D07_contract_validate_all", "contract.validate_all сборки по каждому городу: 0 ошибок", lambda: (
        not [e for c in ev["cities"].values() for e in K.validate_all(c["observations"], ev["as_of"])[0]], ""))

    # --- инварианты задания (на реальном контракте сборки) ---
    sq = T.v12_square("kz.shymkent.sq_a", [69.59, 42.30, 69.61, 42.32], value=2)

    def sq_b_same_layer(value=3):
        # вторая непересекающаяся bbox с той же boundary_version: изолирует правило от дефекта I3 (BOUNDARY_MIX)
        return T.v12_square("kz.shymkent.sq_b", [69.70, 42.40, 69.72, 42.42], value=value, bv=sq["boundary_version"])

    def count_domain():
        out = {}
        for unit in ("count", "records", "segments"):
            for v in (-3, 2.5):
                out[f"{unit}={v}"] = "COUNT_DOMAIN" in codes(K.validate(dict(sq, unit=unit, value=v), "2026-10-05")[0])
        return all(out.values()), out
    inv("I1_count_domain_records_segments", "COUNT_DOMAIN для count, records и segments (−3 и 2.5 отклоняются)", count_domain)

    def expected_units():
        r = C4.aggregate_sum([sq], expected_units=["kz.shymkent.sq_a", "kz.shymkent.sq_b"])
        return r.get("value_status") == "missing" and r.get("missing_units") == ["kz.shymkent.sq_b"], r
    inv("I2_expected_units_via_v12", "C4.aggregate_sum принимает expected_units и помечает неполную географию", expected_units)

    def disjoint():
        b = T.v12_square("kz.shymkent.sq_b", [69.70, 42.40, 69.72, 42.42], value=3)
        r = C4.aggregate_sum([sq, b])
        return r.get("value") == 5, r
    inv("I3_disjoint_bboxes_no_boundary_mix", "две непересекающиеся bbox одного города складываются без BOUNDARY_MIX", disjoint)

    # --- остальная матрица r5 на реальном контракте ---
    inv("M01_nan", "NaN/±Inf отклоняются (v1.2 → v1.1+K12)", lambda: (
        all("VALUE_NOT_FINITE" in codes(K.validate(dict(sq, value=v), "2026-10-05")[0]) for v in (float("nan"), float("inf"))), ""))

    def m03():
        try:
            C4.aggregate_sum([dict(sq, value=float("nan")), sq_b_same_layer()])
            return False, "принято"
        except ValueError as e:
            return "VALUE_NOT_FINITE" in str(e), str(e)[:120]
    inv("M03_nan_aggregate", "NaN в агрегате отклоняется (VALUE_NOT_FINITE, не другая ошибка)", m03,
        note="вторая bbox в том же слое границ, чтобы не маскировать проверку BOUNDARY_MIX")

    def m04():
        dist = dict(sq, geo_unit_id="kz.shymkent.enbekshi", obs_id="d", spatial_unit={"type": "district_polygon", "crs": "EPSG:4326"})
        try:
            C4.aggregate_sum([sq, dist])
            return False, "сложено"
        except ValueError as e:
            return "SPATIAL_MIX" in str(e), str(e)[:100]
    inv("M04_bbox_vs_district", "bbox + район → SPATIAL_MIX", m04)

    def m05():
        try:
            C4.aggregate_sum([sq, T.v11_base(geo_unit_id="kz.shymkent.enbekshi", obs_id="legacy")])
            return False, "сложено"
        except ValueError as e:
            return "LEGACY_UNIT" in str(e), str(e)[:100]
    inv("M05_legacy_district", "запись v1.1 без spatial_unit не смешивается", m05)

    def m06():
        part = dict(sq["coverage"], complete=False)
        a = dict(sq, unit="count_change", value=5, coverage=part)
        b = sq_b_same_layer(value=-5)
        b.update(unit="count_change", coverage=part)
        r = C4.aggregate_sum([a, b])
        return r.get("value_status") == "missing", r
    inv("M06_zero_partial_aggregate", "сумма 0 при неполном охвате → missing", m06,
        note="вторая bbox в том же слое границ (изолировано от I3)")

    def m07():
        z = dict(sq, value=0, value_status="reported_zero")
        ok = K.validate(z, "2026-10-05")[0] == []
        fv = "FALSE_VALUE" in codes(K.validate(dict(sq, value=0, value_status="missing", missing_reason="not_collected"), "2026-10-05")[0])
        zp = "ZERO_ON_PARTIAL" in codes(K.validate(dict(z, coverage=dict(sq["coverage"], complete=False)), "2026-10-05")[0])
        return ok and fv and zp, {"honest_zero_ok": ok, "zero_with_missing_rejected": fv, "zero_on_partial_rejected": zp}
    inv("M07_zero_vs_missing", "честный 0 / 0 при missing / 0 при partial", m07)

    inv("M08_duplicate_obs_id", "повтор obs_id с другим значением → ошибка validate_all", lambda: (
        any("DUPLICATE_OBS_ID" in e for e in K.validate_all([sq, dict(sq, value=4)], "2026-10-05")[0]), ""))

    def m11():
        try:
            C4.aggregate_sum([sq, T.v12_square("kz.shymkent.sq_b", [69.60, 42.31, 69.63, 42.33])])
            return False, "сложено"
        except ValueError as e:
            return "OVERLAP" in str(e), str(e)[:100]
    inv("M11_overlap", "пересекающиеся bbox → OVERLAP", m11)

    return {
        "target": {"app_root": str(app), "git_head": git_head(app), "url": url,
                   "contract_id": K.CONTRACT_ID,
                   "contract_files_used_sha256": {f["path"]: f["used_sha256"] for f in man["files"]},
                   "contract_files_actual_sha256": {f["path"]: sha(app / "inputs/contract" / f["path"]) for f in man["files"]}},
        "results": res,
        "summary": {v: sum(r["verdict"] == v for r in res) for v in ("PASS", "FAIL")},
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", type=Path, required=True)
    ap.add_argument("--url")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    out = run(a.app_root.resolve(), a.url)
    out["test_source"] = {"k05r6_accept.py": sha(__file__), "k05r5_compat.py": sha(R5 / "k05r5_compat.py")}
    print(f"target {out['target']['git_head']} contract {out['target']['contract_id']}")
    for r in out["results"]:
        print(f"{r['verdict']:5} {r['id']:36} {r['detail'][:150]}")
    print(out["summary"])
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(out, ensure_ascii=False, indent=1, allow_nan=False, default=str) + "\n", encoding="utf-8")
    return 1 if out["summary"]["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
