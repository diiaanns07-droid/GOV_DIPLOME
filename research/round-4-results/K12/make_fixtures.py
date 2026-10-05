"""K12 round 4 REVIEW: builds FIXTURES.json — SYNTHETIC stress cases for the K05 data model
(k05-obs-v1.1, claude/optimistic-davinci-1oiqs9 @ d913554). Stdlib only, no network.

Every record is invented: obs_id starts with SYNTHETIC-FIXTURE, geo units are kz.<city>.fixture_*
(not real districts), source_id = k12r4-synthetic-fixture. Some cases use kind="observed" ONLY to
exercise the validator's measurement path; they are not observations of any city.

"expect" is the reviewer's reading of the contract's own rules (K05 REPORT/docstrings), not what
the current code does. Non-finite numbers cannot be written in strict JSON, so they are encoded
as {"$float": "nan" | "inf" | "-inf"} and decoded by stress_runner.py.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAN, INF, NINF = {"$float": "nan"}, {"$float": "inf"}, {"$float": "-inf"}

SYN = {
    "schema_version": "k05-obs-v1.1", "obs_id": "SYNTHETIC-FIXTURE.base", "city_id": "kz.shymkent",
    "geo_unit_id": "kz.shymkent.fixture_a", "indicator_id": "fixture.object_count", "period": "2026-09",
    "release": None, "value": 5, "unit": "count", "value_status": "reported", "missing_reason": None,
    "kind": "synthetic",
    "source": {"source_id": "k12r4-synthetic-fixture", "url": None, "path": None, "retrieved_at": None,
               "locator": "research/round-4-results/K12/FIXTURES.json", "sha256": "0" * 64,
               "license": None, "evidence": None},
    "data_version": "synthetic:k12r4", "boundary_version": "fixture:r1@1",
    "coverage": {"complete": True, "scope": "fixture unit", "selection": "all invented objects",
                 "area_fraction": 1.0, "cap_per_group": None},
    "method": {"id": "fixture", "steps": ["invented by K12 round 4 review"], "parameters": {}},
    "max_age_days": None, "derivation": None, "note": "SYNTHETIC: выдумано для стресс-проверки валидатора",
}
# same record on the measurement path (kind observed) — still invented
OBS = dict(SYN, kind="observed", data_version="k12r4-fixture-not-real",
           source=dict(SYN["source"], retrieved_at="2026-10-01T00:00:00+00:00"),
           note="SYNTHETIC: kind=observed только чтобы проверить путь измерений; не наблюдение города")
PARTIAL = {"complete": False, "scope": "fixture unit", "selection": "invented sample",
           "area_fraction": 0.6, "cap_per_group": None}


def rec(case_id, category, base, set_=None, unset=None, accept=True, codes=(), new=False, why=""):
    return {"id": case_id, "category": category, "base": base, "set": set_ or {}, "unset": list(unset or []),
            "expect": {"accept": accept, "codes": list(codes)}, "new_vs_k05_tests": new, "rationale": why}


RECORDS = [
    # --- controls: rules K05 already implements -------------------------------------------
    rec("R01", "control", "synthetic", accept=True, codes=["NOT_MEASUREMENT"], why="валидная синтетика: допускается с пометкой"),
    rec("R02", "control", "observed", accept=True, why="валидная запись пути измерений"),
    rec("R03", "missing_field", "observed", unset=["coverage"], accept=False, codes=["MISSING_FIELD"], why="нет coverage"),
    rec("R04", "missing_field", "observed", unset=["value"], accept=False, codes=["MISSING_FIELD"], why="нет ключа value — не то же, что value=null"),
    rec("R05", "null", "observed", {"value": None}, accept=False, codes=["NULL_REPORTED"], why="reported с null"),
    rec("R06", "null", "observed", {"value": None, "value_status": "missing", "missing_reason": "not_collected"}, accept=True,
        why="правильное отсутствие"),
    rec("R07", "null", "observed", {"value": None, "value_status": "missing"}, accept=True, codes=["MISSING_REASON"],
        why="отсутствие без причины — предупреждение"),
    rec("R08", "zero", "observed", {"value": 0, "value_status": "missing"}, accept=False, codes=["FALSE_VALUE"], why="missing с нулём"),
    rec("R09", "zero", "observed", {"value": 0}, accept=False, codes=["IMPLICIT_ZERO"], why="ноль без reported_zero"),
    rec("R10", "zero", "observed", {"value": 0, "value_status": "reported_zero"}, accept=True, why="настоящий ноль при полном охвате"),
    rec("R11", "zero", "observed", {"value": 0, "value_status": "reported_zero", "coverage": PARTIAL}, accept=False,
        codes=["ZERO_ON_PARTIAL"], why="ноль при неполном охвате"),
    rec("R12", "city", "observed", {"city_id": "kz.astana"}, accept=False, codes=["CITY_MIX"], why="территория другого города"),
    rec("R13", "city", "observed", {"city_id": "kz.almaty", "geo_unit_id": "kz.almaty.fixture_a"}, accept=False, codes=["CITY"],
        why="город вне контракта"),
    rec("R14", "unit", "observed", {"unit": "   "}, accept=False, codes=["UNIT"], why="единица из пробелов (схема minLength её пропускает)"),
    rec("R15", "period", "observed", {"period": "unknown"}, accept=False, codes=["PERIOD_UNKNOWN"], why="число без периода"),
    rec("R16", "period", "observed", {"period": "unknown", "value": None, "value_status": "missing", "missing_reason": "not_collected"},
        accept=True, codes=["PERIOD_UNKNOWN"], why="отсутствие с неизвестным периодом — предупреждение"),
    rec("R17", "type", "observed", {"value": True}, accept=False, codes=["VALUE_TYPE"], why="bool не число"),
    rec("R18", "type", "observed", {"value": "5"}, accept=False, codes=["VALUE_TYPE"], why="строка не число"),
    rec("R19", "coverage", "observed", {"coverage": dict(SYN["coverage"], area_fraction=0.5)}, accept=False, codes=["COVERAGE"],
        why="complete=true при доле 0,5"),
    # --- new edge cases -----------------------------------------------------------------
    rec("R20", "nan_inf", "observed", {"value": NAN}, accept=False, codes=["VALUE_NOT_FINITE"], new=True,
        why="NaN — тип float, проходит isinstance и jsonschema type=number"),
    rec("R21", "nan_inf", "observed", {"value": INF}, accept=False, codes=["VALUE_NOT_FINITE"], new=True, why="+Infinity"),
    rec("R22", "nan_inf", "observed", {"value": NINF}, accept=False, codes=["VALUE_NOT_FINITE"], new=True, why="-Infinity"),
    rec("R23", "nan_inf", "synthetic", {"value": NAN}, accept=False, codes=["VALUE_NOT_FINITE"], new=True,
        why="NaN в синтетике тоже не число"),
    rec("R24", "nan_inf", "observed", {"value": NAN, "value_status": "reported_zero"}, accept=False, codes=["ZERO_STATUS"],
        why="контроль: NaN != 0 уже ловится как ZERO_STATUS"),
    rec("R25", "period", "observed", {"period": "2025-02-30"}, accept=False, codes=["PERIOD_INVALID_DATE"], new=True,
        why="несуществующая дата проходит regex и схему; давность молча не считается"),
    rec("R26", "period", "observed", {"period": "2025-02-99"}, accept=False, codes=["PERIOD_INVALID_DATE"], new=True, why="день 99"),
    rec("R27", "period", "observed", {"period": "0000"}, accept=False, codes=["PERIOD_INVALID_DATE"], new=True,
        why="год 0000 — внутренняя замена unknown в K05, но как вход выглядит обычным годом"),
    rec("R28", "period", "observed", {"period": "2026/2025"}, accept=False, codes=["PERIOD_REVERSED"], new=True, why="интервал наоборот"),
    rec("R29", "period", "observed", {"period": "2025-Q4/2026-01"}, accept=True, why="контроль: смешанная запись интервала допустима"),
    rec("R30", "unit", "observed", {"value": -3}, accept=False, codes=["COUNT_DOMAIN"], new=True, why="отрицательный счётчик"),
    rec("R31", "unit", "observed", {"value": 2.5}, accept=False, codes=["COUNT_DOMAIN"], new=True, why="дробный счётчик"),
    rec("R32", "unit", "observed", {"value": -3, "unit": "count_change"}, accept=True,
        why="контроль: отрицательное значение допустимо для не-счётчика"),
    rec("R33", "source", "observed", {"source.retrieved_at": "вчера"}, accept=False, codes=["RETRIEVED_AT_INVALID"], new=True,
        why="retrieved_at проверяется только на непустоту"),
    rec("R34", "type", "observed", {"value": 10 ** 400}, accept=True, new=True,
        why="контроль устойчивости: огромное целое конечно; проверка конечности не должна падать с OverflowError"),
]

JSON_TEXT = [
    {"id": "J01", "text": '{"value": NaN}', "expect": {"accept": False, "codes": ["JSON_NONFINITE"]}, "new_vs_k05_tests": True,
     "rationale": "json.loads по умолчанию принимает нестандартный токен NaN"},
    {"id": "J02", "text": '{"value": Infinity}', "expect": {"accept": False, "codes": ["JSON_NONFINITE"]}, "new_vs_k05_tests": True,
     "rationale": "токен Infinity"},
    {"id": "J03", "text": '{"value": -Infinity}', "expect": {"accept": False, "codes": ["JSON_NONFINITE"]}, "new_vs_k05_tests": True,
     "rationale": "токен -Infinity"},
    {"id": "J04", "text": '{"value": 1e999}', "expect": {"accept": False, "codes": ["JSON_NONFINITE"]}, "new_vs_k05_tests": True,
     "rationale": "строго валидный JSON, но float переполняется до inf"},
    {"id": "J05", "text": '{"value": 5, "value_status": "reported", "value_status": "missing"}',
     "expect": {"accept": False, "codes": ["JSON_DUPLICATE_KEY"]}, "new_vs_k05_tests": True,
     "rationale": "повтор ключа: json.loads молча оставляет последний"},
    {"id": "J06", "text": '{"value": 5, "value_status": "reported"}', "expect": {"accept": True, "codes": []},
     "new_vs_k05_tests": False, "rationale": "контроль"},
]


def a(geo, value=5, **over):
    return dict({"geo_unit_id": f"kz.shymkent.{geo}" if geo else "kz.shymkent", "obs_id": f"SYNTHETIC-FIXTURE.{geo or 'city'}",
                 "value": value}, **over)


AGG = [
    {"id": "A01", "category": "control", "records": [a("fixture_a"), a("fixture_b", 7)],
     "expect": {"value": 12, "value_status": "reported", "coverage_complete": True}, "rationale": "две полные территории"},
    {"id": "A02", "category": "null", "records": [a("fixture_a"), a("fixture_b", None, value_status="missing", missing_reason="not_collected")],
     "expect": {"value": None, "value_status": "missing", "coverage_complete": False}, "rationale": "null не превращается в 0"},
    {"id": "A03", "category": "city", "records": [a("fixture_a"), dict(a("fixture_b"), city_id="kz.astana", geo_unit_id="kz.astana.fixture_b")],
     "expect": {"raises": "CITY_MIX"}, "rationale": "контроль"},
    {"id": "A04", "category": "unit", "records": [a("fixture_a"), a("fixture_b", unit="шт")],
     "expect": {"raises": "UNIT_MIX"}, "rationale": "контроль: разные написания единицы"},
    {"id": "A05", "category": "period", "records": [a("fixture_a"), a("fixture_b", period="2026-09-30")],
     "expect": {"raises": "PERIOD_MIX"}, "rationale": "контроль: месяц и день"},
    {"id": "A06", "category": "duplicate_id", "records": [a("fixture_a"), a("fixture_a", 7, obs_id="SYNTHETIC-FIXTURE.a2")],
     "expect": {"raises": "DUPLICATE_UNIT"}, "rationale": "контроль"},
    {"id": "A07", "category": "boundary", "records": [a("fixture_a"), a("fixture_b", boundary_version="fixture:r1@2")],
     "expect": {"raises": "BOUNDARY_MIX"}, "new_vs_k05_tests": True,
     "rationale": "docstring k05r3_contract обещает проверку смешения границ в агрегате, aggregate_sum её не делает"},
    {"id": "A08", "category": "partial_geography", "records": [a(None, 12), a("fixture_a")],
     "expect": {"raises": "NESTED_UNIT"}, "new_vs_k05_tests": True,
     "rationale": "город целиком + его район: двойной счёт, DUPLICATE_UNIT видит только равные id"},
    {"id": "A09", "category": "partial_geography", "records": [a("fixture_a"), a("fixture_b")],
     "expected_units": ["kz.shymkent.fixture_a", "kz.shymkent.fixture_b", "kz.shymkent.fixture_c"],
     "expect": {"value": None, "value_status": "missing", "coverage_complete": False, "missing_units": ["kz.shymkent.fixture_c"]},
     "new_vs_k05_tests": True, "rationale": "2 из 3 территорий выдаются как полная городская сумма"},
    {"id": "A10", "category": "partial_geography", "records": [a("fixture_a"), a("fixture_b")],
     "expect": {"value": 10, "value_status": "reported", "geography_checked": False}, "new_vs_k05_tests": True,
     "rationale": "без эталонного списка территорий итог должен явно говорить, что полнота географии не проверена"},
    {"id": "A11", "category": "nan_inf", "records": [a("fixture_a"), a("fixture_b", NAN)],
     "expect": {"raises": "VALUE_NOT_FINITE"}, "new_vs_k05_tests": True, "rationale": "NaN даёт reported NaN"},
    {"id": "A12", "category": "zero", "records": [a("fixture_a", 5, unit="count_change", coverage=PARTIAL),
                                                    a("fixture_b", -5, unit="count_change", coverage=PARTIAL)],
     "expect": {"value": None, "value_status": "missing", "coverage_complete": False, "missing_reason": "zero_in_partial_coverage"},
     "new_vs_k05_tests": True,
     "rationale": "сумма 0 при неполном охвате выдаётся как reported_zero, хотя validate запрещает такой ноль у записи"},
]

DATASETS = [
    {"id": "S01", "category": "duplicate_id", "records": [{}, {"value": 7}],
     "expect": {"accept": False, "codes": ["DUPLICATE_OBS_ID"]}, "new_vs_k05_tests": True,
     "rationale": "один obs_id с разными значениями; validate проверяет записи поодиночке"},
    {"id": "S02", "category": "duplicate_id", "records": [{}, {}],
     "expect": {"accept": True, "codes": ["DUPLICATE_RECORD"]}, "new_vs_k05_tests": True, "rationale": "точный повтор — предупреждение"},
    {"id": "S03", "category": "duplicate_id", "records": [{}, {"obs_id": "SYNTHETIC-FIXTURE.other", "value": 9}],
     "expect": {"accept": False, "codes": ["CONFLICTING_OBSERVATION"]}, "new_vs_k05_tests": True,
     "rationale": "разные obs_id, одна территория/показатель/период/версия, разные значения"},
    {"id": "S04", "category": "control", "records": [{}, {"obs_id": "SYNTHETIC-FIXTURE.b", "geo_unit_id": "kz.shymkent.fixture_b"}],
     "expect": {"accept": True, "codes": []}, "new_vs_k05_tests": False, "rationale": "разные территории"},
]

if __name__ == "__main__":
    doc = {
        "fixture_set": "k12r4-k05-stress-v1",
        "kind": "synthetic",
        "target": {"contract": "k05-obs-v1.1", "branch": "claude/optimistic-davinci-1oiqs9",
                   "commit": "d913554bf2617a74d921af260ab8c22743ccb4b5",
                   "files": ["research/round-3-results/K05/k05r3_contract.py",
                             "research/round-3-results/K05/schema/k05-obs-v1.1.schema.json",
                             "research/next-round/K05/k05_validator.py"]},
        "notice": "СИНТЕТИКА. Все записи выдуманы для проверки валидатора; это не данные Шымкента или Астаны. "
                  "kind=observed в части случаев нужен только для пути проверки измерений.",
        "encoding": {"marker": "$float", "values": ["nan", "inf", "-inf"],
                     "note": "объект с единственным ключом $float — нестандартное число; раскодирует stress_runner.py"},
        "expect_semantics": "accept=true: нет ошибок (предупреждения допустимы); codes должны встретиться среди ошибок/предупреждений",
        "bases": {"synthetic": SYN, "observed": OBS},
        "record_cases": RECORDS, "json_text_cases": JSON_TEXT, "aggregate_cases": AGG,
        "aggregate_base": "observed", "dataset_cases": DATASETS, "dataset_base": "observed",
    }
    text = json.dumps(doc, indent=1, ensure_ascii=False, allow_nan=False) + "\n"
    (HERE / "FIXTURES.json").write_text(text, encoding="utf-8")
    print({"records": len(RECORDS), "json_text": len(JSON_TEXT), "aggregate": len(AGG), "datasets": len(DATASETS)})
