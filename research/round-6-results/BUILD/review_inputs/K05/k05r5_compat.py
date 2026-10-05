#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K05 round 5 (REVIEW): совместимость K12 patch (v1.1) + k05r4_contract (v1.2) + BUILD build_evidence.

Проверяет ГОТОВУЮ сборку prototypes/city-evidence (извлечённую копию или запущенный сервер):

  D* — данные web/evidence.js: строгий JSON, уникальность obs_id, null⇔missing, честный 0,
       конечные целые счётчики, город, отсутствие ошибок validate()/validate_dataset();
  M* — матрица контрактов: v1.1 из сборки (inputs/k05_root) и v1.2 (k05r4_contract) поверх неё:
       finite/NaN, bbox vs district, partial coverage, zero vs missing, повтор obs_id,
       expected_units, две непересекающиеся bbox, домен счётчика в единицах records.

Запуск:
  python k05r5_compat.py --app-root <путь>/prototypes/city-evidence [--k05r4 FILE] [--json OUT]
  python k05r5_compat.py --url http://127.0.0.1:8000/ --contract-root <путь к inputs/k05_root>
Сеть: только --url (обычно локальный serve.py). Без внешних запросов.

Вариант контракта определяется по sha256 inputs/k05_root/round-3-results/K05/k05r3_contract.py.
Для известных вариантов (baseline 0bf27de, baseline+K12) ожидаемые падения помечены EXPECTED;
для неизвестного (исправленная версия) ожиданий нет — каждое падение показывается как FAIL.
Код выхода: 0 — нет неожиданных результатов; 1 — есть FAIL или неожиданный PASS (XPASS).
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_K05R4 = HERE / "inputs" / "k05r4" / "k05r4_contract.py"

VARIANTS = {
    "8dc4a177f47edcdfa6753ed41b78a31e5afb652df4d79f02c73aeb5686d2f397": "baseline_v1.1@d913554",
    "b6856121d01c2046cfa2c0e8248ac4c0f107ecf60fdfa601bc04117fbf3e26a2": "v1.1+K12@3e84039",
    "7f5f76a840bfec303b3ed0d1eed5c4335c5b890fc5ede84167904b5e3b061447": "v1.1+K12+K05r5_count_units",
}
K05R4_VARIANTS = {}  # заполняется ниже по фактическим файлам (исходный @42051600 и предложенный)

# Ожидаемые падения по варианту v1.1 и варианту v1.2 (orig/compat).
EXPECTED_FAIL = {
    ("baseline_v1.1@d913554", "orig"): {
        "M01_nan_v11", "M02_nan_v12", "M03_nan_aggregate", "M06_zero_partial_aggregate",
        "M08_duplicate_obs_id", "M10_expected_units_v12", "M12_count_domain_records", "D07_validate_dataset"},
    ("v1.1+K12@3e84039", "orig"): {
        "M09_disjoint_bboxes_v12", "M10_expected_units_v12", "M12_count_domain_records"},
    ("v1.1+K12@3e84039", "compat"): {"M12_count_domain_records"},
    ("v1.1+K12+K05r5_count_units", "orig"): {"M09_disjoint_bboxes_v12", "M10_expected_units_v12"},
    ("v1.1+K12+K05r5_count_units", "compat"): set(),
    ("baseline_v1.1@d913554", "compat"): {
        "M01_nan_v11", "M02_nan_v12", "M03_nan_aggregate", "M06_zero_partial_aggregate",
        "M08_duplicate_obs_id", "M10_expected_units_v12", "M12_count_domain_records", "D07_validate_dataset"},
}


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def loads_strict(text: str):
    """Независимый строгий разбор: без NaN/Infinity, переполнения и повтора ключей."""
    def bad_const(name):
        raise ValueError(f"JSON_NONFINITE {name}")

    def fin(tok):
        v = float(tok)
        if not math.isfinite(v):
            raise ValueError(f"JSON_NONFINITE {tok}")
        return v

    def uniq(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError(f"JSON_DUPLICATE_KEY {k}")
            out[k] = v
        return out
    return json.loads(text, parse_constant=bad_const, parse_float=fin, object_pairs_hook=uniq)


def evidence_text(app_root: Path | None, url: str | None) -> str:
    if app_root:
        return (app_root / "web" / "evidence.js").read_text(encoding="utf-8")
    with urllib.request.urlopen(url.rstrip("/") + "/evidence.js", timeout=20) as r:
        return r.read().decode("utf-8")


def parse_evidence(js: str):
    start = js.index("window.CITY_OBS = ") + len("window.CITY_OBS = ")
    body = js[start:].rstrip().rstrip(";")
    return loads_strict(body)


def load_contract(k05_root: Path):
    """k05r3_contract из сборки (он сам импортирует v1 из next-round/K05)."""
    d = k05_root / "round-3-results" / "K05"
    sys.path.insert(0, str(k05_root / "next-round" / "K05"))
    sys.path.insert(0, str(d))
    spec = importlib.util.spec_from_file_location("k05r3_contract", d / "k05r3_contract.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["k05r3_contract"] = mod  # k05r4_contract импортирует именно это имя
    spec.loader.exec_module(mod)
    return mod, sha256_bytes((d / "k05r3_contract.py").read_bytes())


def load_v12(path: Path):
    spec = importlib.util.spec_from_file_location("k05r4_contract_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # sys.path вставка внутри модуля безвредна: k05r3_contract уже в sys.modules
    return mod


# ---------- шаблоны записей (синтетические фикстуры, только для проверки правил) ----------

def v11_base(**kw):
    o = {"schema_version": "k05-obs-v1.1", "obs_id": "FIXTURE.k05r5.base", "city_id": "kz.shymkent",
         "geo_unit_id": "kz.shymkent.k10r3_bbox", "indicator_id": "places.school", "period": "2026-09-23",
         "release": "2026-09-23.1", "value": 3, "unit": "records", "value_status": "reported",
         "missing_reason": None, "kind": "observed",
         "source": {"source_id": "FIXTURE", "sha256": "0" * 64, "url": None, "path": None,
                    "retrieved_at": "2026-10-05T06:18:23+00:00", "locator": "fixture", "license": None,
                    "evidence": None},
         "data_version": "overture@2026-09-23.1", "boundary_version": None,
         "coverage": {"complete": True, "scope": "фикстура", "selection": "все", "area_fraction": None,
                      "cap_per_group": None},
         "method": {"id": "fixture", "steps": ["fixture"]}, "max_age_days": None, "derivation": None,
         "note": "SYNTHETIC FIXTURE"}
    o.update(kw)
    return o


def v12_square(geo, bbox, value=3, bv=None, **kw):
    o = v11_base(schema_version="k05-obs-v1.2", geo_unit_id=geo, value=value, kind="derived",
                 derivation="fixture count", boundary_version=bv or f"k10_r3_square:{geo.split('.')[-1]}@fixture",
                 obs_id=f"FIXTURE.k05r5.{geo}")
    o["spatial_unit"] = {"type": "bbox", "crs": "EPSG:4326", "bbox": bbox, "edges_inclusive": True}
    o.update(kw)
    return o


def codes(msgs):
    return {m.split(":")[0] for m in msgs}


# ---------- проверки ----------

def run(app_root, url, contract_root, k05r4_path):
    res = []

    def check(cid, title, fn):
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001 — исключение = провал проверки, с текстом
            ok, detail = False, f"{type(e).__name__}: {e}"
        res.append({"id": cid, "title": title, "ok": bool(ok), "detail": detail})

    k05_root = contract_root or (app_root / "inputs" / "k05_root" if app_root else None)
    C = variant = None
    if k05_root:
        C, csha = load_contract(Path(k05_root))
        variant = VARIANTS.get(csha, f"unknown:{csha[:12]}")
    V12 = load_v12(k05r4_path) if (C and k05r4_path) else None
    v12sha = sha256_bytes(Path(k05r4_path).read_bytes()) if k05r4_path else None

    # --- D: данные готовой сборки ---
    text = evidence_text(app_root, url)
    data = {}
    check("D01_strict_json", "evidence.js — строгий JSON (нет NaN/Infinity/повтора ключей)",
          lambda: (data.update(parse_evidence(text)) or True, f"{len(text)} символов"))
    allobs = [(c, o) for c, v in data.get("cities", {}).items() for o in v["observations"]]

    def d02():
        ids = [o["obs_id"] for _, o in allobs]
        d = sorted({i for i in ids if ids.count(i) > 1})
        return not d, f"{len(ids)} obs_id, повторов {len(d)} {d[:3]}"
    check("D02_unique_obs_id", "obs_id уникальны во всей сборке", d02)

    def d03():
        bad = [o["obs_id"] for _, o in allobs
               if (o["value"] is None) != (o["value_status"] in ("missing", "suppressed", "not_applicable"))]
        return not bad, f"нарушений null⇔missing: {bad[:3]}"
    check("D03_null_iff_missing", "value=null ⇔ статус отсутствия", d03)

    def d04():
        bad = [o["obs_id"] for _, o in allobs if o["value_status"] == "reported_zero"
               and not o["coverage"]["complete"]]
        zeros_missing = [o["obs_id"] for _, o in allobs if o["value_status"] == "missing"
                         and o.get("missing_reason") == "zero_in_partial_coverage"]
        return not bad, f"0 при неполном охвате: {bad[:3]}; честно переведены в missing: {len(zeros_missing)}"
    check("D04_honest_zero", "reported_zero только при coverage.complete=true", d04)

    def d05():
        bad = []
        for _, o in allobs:
            v = o["value"]
            if v is None:
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)) or (isinstance(v, float) and not math.isfinite(v)):
                bad.append((o["obs_id"], "not finite"))
            elif o["unit"] in ("records", "segments", "count") and (v < 0 or v != int(v)):
                bad.append((o["obs_id"], v))
        return not bad, f"нарушений: {bad[:3]}"
    check("D05_finite_counts", "числа конечны; records/segments — целые ≥ 0", d05)

    def d06():
        bad = [o["obs_id"] for c, o in allobs
               if o["city_id"] != f"kz.{c}" or not o["geo_unit_id"].startswith(f"kz.{c}")]
        return not bad, f"чужой город: {bad[:3]}"
    check("D06_city_consistency", "city_id/geo_unit_id совпадают с городом раздела", d06)

    if C:
        def d07():
            if not hasattr(C, "validate_dataset"):
                return False, "validate_dataset отсутствует в контракте сборки"
            errs = []
            for c in data.get("cities", {}):
                e, _ = C.validate_dataset([o for cc, o in allobs if cc == c])
                errs += e
            return not errs, f"ошибок набора: {errs[:3]}"
        check("D07_validate_dataset", "validate_dataset() сборки: нет ошибок набора", d07)

        def d08():
            errs = [(o["obs_id"], e) for _, o in allobs for e in C.validate(o, as_of=data.get("as_of"))[0]]
            return not errs, f"ошибок validate: {errs[:3]}"
        check("D08_validate_all", "validate() сборки на всех наблюдениях: 0 ошибок", d08)

        # --- M: матрица контрактов ---
        nan = v11_base(value=float("nan"))
        check("M01_nan_v11", "v1.1: NaN при reported отклоняется",
              lambda: ("VALUE_NOT_FINITE" in codes(C.validate(nan)[0]), sorted(codes(C.validate(nan)[0]))))
        sq_nan = v12_square("kz.shymkent.sq_a", [69.59, 42.30, 69.61, 42.32], value=float("inf"))
        if V12:
            check("M02_nan_v12", "v1.2 поверх сборки: Infinity отклоняется",
                  lambda: ("VALUE_NOT_FINITE" in codes(V12.validate(sq_nan)[0]), sorted(codes(V12.validate(sq_nan)[0]))))
        else:
            check("M02_nan_v12", "v1.2 поверх сборки: Infinity отклоняется", lambda: (False, "v1.2 не задан"))

        def m03():
            try:
                r = C.aggregate_sum([v11_base(obs_id="a", geo_unit_id="kz.shymkent.a", value=float("nan")),
                                     v11_base(obs_id="b", geo_unit_id="kz.shymkent.b")])
                return False, f"принято: {r}"
            except ValueError as e:
                return "VALUE_NOT_FINITE" in str(e), str(e)[:80]
        check("M03_nan_aggregate", "v1.1 aggregate_sum: NaN отклоняется", m03)

        def m04():
            sq = v12_square("kz.shymkent.sq_a", [69.59, 42.30, 69.61, 42.32])
            dist = dict(sq, geo_unit_id="kz.shymkent.enbekshi", obs_id="d",
                        spatial_unit={"type": "district_polygon", "crs": "EPSG:4326"})
            try:
                V12.aggregate_sum([sq, dist])
                return False, "квадрат + район сложены"
            except ValueError as e:
                return "SPATIAL_MIX" in str(e), str(e)[:80]
        check("M04_bbox_vs_district", "v1.2: квадрат и район не складываются", m04)

        def m05():
            legacy = v11_base(geo_unit_id="kz.shymkent.enbekshi", obs_id="legacy")
            try:
                V12.aggregate_sum([v12_square("kz.shymkent.sq_a", [69.59, 42.30, 69.61, 42.32]), legacy])
                return False, "v1.1-район + v1.2-квадрат сложены"
            except ValueError as e:
                return "LEGACY_UNIT" in str(e), str(e)[:80]
        check("M05_legacy_district", "v1.2: запись без spatial_unit (E02/BUILD v1.1) не смешивается", m05)

        def m06():
            part = dict(v11_base()["coverage"], complete=False)
            a = v11_base(obs_id="a", geo_unit_id="kz.shymkent.a", value=0, value_status="missing",
                         missing_reason="zero_in_partial_coverage")
            a["value"] = None
            b = v11_base(obs_id="b", geo_unit_id="kz.shymkent.b", value=5, unit="count_change", coverage=part)
            c = v11_base(obs_id="c", geo_unit_id="kz.shymkent.c", value=-5, unit="count_change", coverage=part)
            r = C.aggregate_sum([b, c])
            return r["value_status"] == "missing", f"{r}"
        check("M06_zero_partial_aggregate", "сумма 0 при неполном охвате → missing, не reported_zero", m06)

        def m07():
            z = v11_base(value=0, value_status="reported_zero")
            fake = v11_base(value=0, value_status="missing", missing_reason="not_collected")
            ok_zero = C.validate(z)[0] == []
            rej = "FALSE_VALUE" in codes(C.validate(fake)[0])
            zp = v11_base(value=0, value_status="reported_zero",
                          coverage=dict(v11_base()["coverage"], complete=False))
            rej_p = "ZERO_ON_PARTIAL" in codes(C.validate(zp)[0])
            return ok_zero and rej and rej_p, f"honest0={ok_zero}, missing+0 отклонён={rej}, 0 при partial отклонён={rej_p}"
        check("M07_zero_vs_missing", "честный 0 принят; 0 при missing и 0 при partial отклонены", m07)

        def m08():
            if not hasattr(C, "validate_dataset"):
                return False, "validate_dataset отсутствует"
            a = v12_square("kz.shymkent.sq_a", [69.59, 42.30, 69.61, 42.32])
            b = dict(a, value=4)
            e, _ = C.validate_dataset([a, b])
            return "DUPLICATE_OBS_ID" in codes(e), sorted(codes(e))
        check("M08_duplicate_obs_id", "повтор obs_id с разным значением → DUPLICATE_OBS_ID (и для v1.2)", m08)

        def m09():
            a = v12_square("kz.shymkent.sq_a", [69.59, 42.30, 69.61, 42.32], value=2)
            b = v12_square("kz.shymkent.sq_b", [69.70, 42.40, 69.72, 42.42], value=3)
            r = V12.aggregate_sum([a, b])
            return r["value"] == 5, f"{r}"
        check("M09_disjoint_bboxes_v12", "v1.2: две непересекающиеся bbox одного города складываются", m09)

        def m10():
            a = v12_square("kz.shymkent.sq_a", [69.59, 42.30, 69.61, 42.32], value=2)
            r = V12.aggregate_sum([a], expected_units=["kz.shymkent.sq_a", "kz.shymkent.sq_b"])
            return r["value_status"] == "missing" and r.get("missing_units") == ["kz.shymkent.sq_b"], f"{r}"
        check("M10_expected_units_v12", "v1.2 передаёт expected_units в v1.1 (неполная география → missing)", m10)

        def m11():
            a = v12_square("kz.shymkent.sq_a", [69.59, 42.30, 69.61, 42.32])
            b = v12_square("kz.shymkent.sq_b", [69.60, 42.31, 69.63, 42.33])
            try:
                V12.aggregate_sum([a, b])
                return False, "пересекающиеся bbox сложены"
            except ValueError as e:
                return "OVERLAP" in str(e), str(e)[:80]
        check("M11_overlap_v12", "v1.2: пересекающиеся bbox отклоняются", m11)

        def m12():
            neg = v11_base(value=-3)
            frac = v11_base(value=2.5)
            r = ("COUNT_DOMAIN" in codes(C.validate(neg)[0]), "COUNT_DOMAIN" in codes(C.validate(frac)[0]))
            return all(r), f"records=-3 отклонён={r[0]}, records=2.5 отклонён={r[1]}"
        check("M12_count_domain_records", "домен счётчика для unit=records (единица сборки и K05 r4)", m12)

    k = (variant, "compat" if v12sha and v12sha in K05R4_VARIANTS.get("compat", set()) else "orig")
    expected = EXPECTED_FAIL.get(k, set())
    for r in res:
        exp = r["id"] in expected
        r["expected_fail"] = exp
        r["status"] = ("PASS" if r["ok"] else "FAIL") if not exp else ("EXPECTED_FAIL" if not r["ok"] else "XPASS")
    return {"contract_variant": variant, "k05r4": {"path": str(k05r4_path) if k05r4_path else None,
                                                    "sha256": v12sha, "variant": k[1]},
            "app_root": str(app_root) if app_root else None, "url": url, "results": res,
            "unexpected": [r["id"] for r in res if r["status"] in ("FAIL", "XPASS")]}


def _register_k05r4_variants():
    orig = HERE / "inputs" / "k05r4" / "k05r4_contract.py"
    prop = HERE / "proposed" / "k05r4_contract.py"
    K05R4_VARIANTS["orig"] = {sha256_bytes(orig.read_bytes())} if orig.exists() else set()
    K05R4_VARIANTS["compat"] = {sha256_bytes(prop.read_bytes())} if prop.exists() else set()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--app-root", type=Path, help="извлечённая копия prototypes/city-evidence")
    g.add_argument("--url", help="адрес запущенной сборки (папка web/), например http://127.0.0.1:8000/")
    ap.add_argument("--contract-root", type=Path, help="inputs/k05_root (обязателен для матрицы при --url)")
    ap.add_argument("--k05r4", type=Path, default=DEFAULT_K05R4, help="k05r4_contract.py для проверки v1.2")
    ap.add_argument("--json", type=Path, help="записать результат в файл")
    a = ap.parse_args(argv)
    _register_k05r4_variants()
    out = run(a.app_root.resolve() if a.app_root else None, a.url, a.contract_root, a.k05r4.resolve())
    print(f"контракт сборки: {out['contract_variant']}; v1.2: {out['k05r4']['variant']} ({(out['k05r4']['sha256'] or '')[:12]})")
    for r in out["results"]:
        print(f"{r['status']:14} {r['id']:28} {r['title']}\n{'':16}{r['detail']}")
    print("неожиданных результатов:", len(out["unexpected"]), out["unexpected"])
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(out, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")
    return 1 if out["unexpected"] else 0


if __name__ == "__main__":
    sys.exit(main())
