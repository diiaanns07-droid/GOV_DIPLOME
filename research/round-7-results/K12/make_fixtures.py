"""K12 round 7: builds stress fixtures for the city-whatif-v1 scenario importer (FEATURE_SPEC.txt).

Writes fixtures/*.json (raw import TEXTS, many deliberately invalid) and FIXTURES_INDEX.json.
Stdlib only. Nothing here is executed or fetched: URLs are inert strings, HTML is inert text.

All coordinates, IDs and labels are SYNTHETIC test inputs (not real objects, not population).
Placeholders, substituted by the test module with values from the importer under test:
    "__SNAPSHOT__"                 snapshot(city, category) of this fixture's city/category
    "__SNAPSHOT_OTHER_CITY__"      snapshot(other city, same category)
    "__SNAPSHOT_OTHER_CATEGORY__"  snapshot(same city, other category)
so the fixtures do not depend on how the future build computes its fingerprint.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "fixtures"
MAX_BYTES = 256 * 1024
BBOX = {"shymkent": [69.593365, 42.306645, 69.617658, 42.324611],   # data.js @ c58a3b2 (K10 slice)
        "astana": [71.418372, 51.163033, 71.447, 51.181]}
PTS = {"shymkent": [(69.600, 42.310), (69.605, 42.315), (69.612, 42.320)], "astana": [(71.430, 51.170)]}
PROJ = {"shymkent": (69.608, 42.312), "astana": (71.440, 51.175)}


def scenario(city="shymkent", category="school", n=None, project=True, **over):
    pts = PTS[city] if n is None else [(BBOX[city][0] + 0.001 + i * 0.0015, BBOX[city][1] + 0.002) for i in range(n)]
    s = {"schema_version": "city-whatif-v1", "city_id": city, "source_snapshot": "__SNAPSHOT__", "category": category,
         "control_points": [{"id": f"cp{i + 1}", "lon": lon, "lat": lat} for i, (lon, lat) in enumerate(pts)],
         "proposed_object": ({"id": "proj1", "lon": PROJ[city][0], "lat": PROJ[city][1], "category": category,
                              "kind": "hypothetical"} if project else None)}
    s.update(over)
    return s


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1)


def with_token(obj, path, token):
    """Put a sentinel at `path`, dump, then swap it for a raw (possibly non-JSON) token."""
    o = json.loads(json.dumps(obj))
    target = o
    for k in path[:-1]:
        target = target[k]
    target[path[-1]] = "__K12_RAW__"
    text = dumps(o)
    assert text.count('"__K12_RAW__"') == 1
    return text.replace('"__K12_RAW__"', token)


def dup_key(obj, path, key, first, second):
    """Object at `path` gets `key` twice: first value, then second (JSON.parse keeps the second)."""
    o = json.loads(json.dumps(obj))
    target = o
    for k in path:
        target = target[k]
    target.pop(key, None)
    target["__K12_DUP__"] = 0
    text = dumps(o)
    old = '"__K12_DUP__": 0'
    assert text.count(old) == 1
    return text.replace(old, f'{json.dumps(key)}: {json.dumps(first, ensure_ascii=False)}, '
                             f'{json.dumps(key)}: {json.dumps(second, ensure_ascii=False)}')


def recipe_text(base_text, recipe):
    """Large fixtures are not committed: the test module rebuilds them from P01 with the same string
    operations and checks sha256. pad: spaces before the final '}' up to total_bytes (UTF-8).
    insert_label: after the first '"id": "cp1",' insert ' "label": "<char * count>",'."""
    if recipe["op"] == "pad":
        body, tail = base_text[:-1], base_text[-1]
        pad = recipe["total_bytes"] - len(base_text.encode("utf-8"))
        assert pad >= 0
        out = body + " " * pad + tail
        assert len(out.encode("utf-8")) == recipe["total_bytes"]
        return out
    if recipe["op"] == "insert_label":
        anchor = '"id": "cp1",'
        assert base_text.count(anchor) == 1
        return base_text.replace(anchor, anchor + ' "label": "' + recipe["char"] * recipe["count"] + '",', 1)
    raise ValueError(recipe)


F = []  # (id, slug, text, expect, codes, spec, rationale, advisory)


def add(fid, slug, text, expect, codes=(), spec="", why="", advisory=False, city="shymkent", category="school", recipe=None):
    """city/category: for placeholder substitution only (the importer must not trust them).
    recipe: large fixture rebuilt from P01 by the test module (file kept out of git)."""
    F.append({"id": fid, "file": f"fixtures/{'generated/' if recipe else ''}{fid}_{slug}.json", "text": text,
              "expect": expect, "expected_codes": list(codes), "spec": spec, "rationale": why, "advisory": advisory,
              "city": city, "category": category, "recipe": recipe})


base = scenario()
# ---- positive controls (must be accepted; values must be RECOMPUTED, not taken from the file) ----
add("P01", "valid_shymkent_school", dumps(base), "accept", spec="контракт city-whatif-v1",
    why="3 контрольные точки, один условный объект школы внутри bbox Шымкента; база для проверки неизменности состояния")
add("P02", "valid_astana_clinic_no_project", dumps(scenario("astana", "outpatient_clinic", project=False)), "accept",
    spec="proposed_object может быть null", why="без проекта: after = before, delta = 0",
    city="astana", category="outpatient_clinic")
tampered = dict(base, results={"rows": [{"id": "cp1", "before_m": 1.0, "after_m": 0.5, "delta_m": 999999.0}],
                               "note": "SYNTHETIC: подделанные выводимые значения"})
add("P03", "tampered_results_are_ignored", dumps(tampered), "accept", spec="импорт результатов не доверенный: вычислить заново",
    why="поле results допускается как выводимое, но значения должны быть пересчитаны; 999999 не должно появиться")
add("P04", "ten_points_boundary", dumps(scenario(n=10)), "accept", spec="контрольных точек 1..10", why="граница 10")
R_P05 = {"op": "pad", "from": "P01", "total_bytes": MAX_BYTES}
add("P05", "exactly_256_KiB", recipe_text(dumps(base), R_P05), "accept", spec="JSON импорта до 256 KiB",
    why="ровно 262144 байта UTF-8, валидный JSON с пробелами", recipe=R_P05)
same = scenario(project=True)
same["proposed_object"].update(lon=same["control_points"][0]["lon"], lat=same["control_points"][0]["lat"])
add("P06", "project_on_control_point", dumps(same), "accept", spec="расстояния одинаковой точки дают честный 0",
    why="after для cp1 = 0, delta = before")

# ---- non-finite numbers ----
add("N01", "nan_token_lon", with_token(base, ["control_points", 0, "lon"], "NaN"), "reject", ["invalid_json", "nonfinite_number"],
    "не принимать NaN", "токен NaN — не JSON, но некоторые парсеры его принимают")
add("N02", "infinity_token_lat", with_token(base, ["control_points", 1, "lat"], "Infinity"), "reject",
    ["invalid_json", "nonfinite_number"], "не принимать Infinity", "")
add("N03", "minus_infinity_project", with_token(base, ["proposed_object", "lon"], "-Infinity"), "reject",
    ["invalid_json", "nonfinite_number"], "не принимать Infinity", "")
add("N04", "1e999_lon", with_token(base, ["control_points", 0, "lon"], "1e999"), "reject", ["nonfinite_number"],
    "не принимать 1e999", "строго валидный JSON; JSON.parse даёт Infinity")
# ---- duplicate keys / IDs ----
add("N05", "duplicate_key_category", dup_key(base, [], "category", "school", "outpatient_clinic"), "reject", ["duplicate_key"],
    "строгая валидация", "JSON.parse молча берёт последнее значение")
add("N06", "duplicate_key_in_point", dup_key(base, ["control_points", 0], "lon", 69.600, 70.5), "reject", ["duplicate_key"],
    "строгая валидация", "второй lon вне bbox; last-wins подменил бы координату")
add("N07", "duplicate_key_proposed", dup_key(base, [], "proposed_object", None, base["proposed_object"]), "reject",
    ["duplicate_key"], "число проектов >1 / строгая валидация", "null, затем объект: проект появляется через повтор ключа")
dup_ids = scenario()
dup_ids["control_points"][1]["id"] = "cp1"
add("N08", "duplicate_point_ids", dumps(dup_ids), "reject", ["duplicate_id"], "ID уникальны", "")
clash = scenario()
clash["proposed_object"]["id"] = "cp1"
add("N09", "project_id_equals_point_id", dumps(clash), "reject", ["duplicate_id"], "ID уникальны", "ID общий для сценария")
add("N10", "id_too_long", dumps(scenario(control_points=[{"id": "p" * 300, "lon": 69.6, "lat": 42.31}])), "reject",
    ["bad_id"], "ID ограничены по длине", "")
# ---- snapshot / city / version / category ----
add("N11", "foreign_snapshot_other_city", dumps(dict(base, source_snapshot="__SNAPSHOT_OTHER_CITY__")), "reject",
    ["foreign_snapshot"], "чужой snapshot", "отпечаток Астаны в сценарии Шымкента")
add("N12", "foreign_snapshot_wrong_hash", dumps(dict(base, source_snapshot="sha256:" + "0" * 64)), "reject",
    ["foreign_snapshot"], "чужой snapshot", "правдоподобный, но не совпадающий отпечаток")
add("N13", "snapshot_is_file_name", dumps(dict(base, source_snapshot="web/data.js")), "reject", ["foreign_snapshot"],
    "имя файла не подтверждает версию", "")
add("N14", "snapshot_is_url", dumps(dict(base, source_snapshot="https://example.invalid/snapshot.json")), "reject",
    ["foreign_snapshot", "external_reference"], "не загружать адреса из текста", "URL нельзя открывать")
add("N15", "snapshot_other_category", dumps(dict(base, source_snapshot="__SNAPSHOT_OTHER_CATEGORY__")), "reject",
    ["foreign_snapshot"], "отпечаток включает параметры расчёта",
    "advisory: отказ ожидается, если категория входит в параметры отпечатка", advisory=True)
add("N16", "unknown_city", dumps(dict(base, city_id="almaty")), "reject", ["unknown_city"], "неизвестный город", "")
add("N17", "lookalike_city", dumps(dict(base, city_id="shymkеnt")), "reject", ["unknown_city"], "неизвестный город",
    "кириллическая «е» в shymkent")
astana_with_shym_points = dict(scenario(), city_id="astana")
add("N18", "city_astana_points_in_shymkent", dumps(astana_with_shym_points), "reject", ["outside_bbox", "foreign_snapshot"],
    "не переносить точки между городами", "город сменён, координаты остались шымкентские", city="astana")
add("N19", "unknown_schema_version", dumps(dict(base, schema_version="city-whatif-v2")), "reject", ["unknown_version"],
    "неизвестная версия", "")
no_ver = dict(base)
no_ver.pop("schema_version")
add("N20", "missing_schema_version", dumps(no_ver), "reject", ["missing_field", "unknown_version"], "обязательные поля", "")
add("N21", "category_not_in_mvp", dumps(scenario(category="hospital")), "reject", ["bad_category"], "категории MVP: school, outpatient_clinic", "")
mis = scenario()
mis["proposed_object"]["category"] = "outpatient_clinic"
add("N22", "project_category_mismatch", dumps(mis), "reject", ["category_mismatch"], "категория проекта совпадает с category", "")
real = scenario()
real["proposed_object"]["kind"] = "observed"
add("N23", "project_kind_not_hypothetical", dumps(real), "reject", ["bad_project"], "kind: hypothetical",
    "условный объект нельзя выдать за существующий")
# ---- bbox / coordinates ----
out1 = scenario()
out1["control_points"][0].update(lon=69.65, lat=42.31)
add("N24", "point_outside_bbox", dumps(out1), "reject", ["outside_bbox"], "вне bbox отклонять", "")
out2 = scenario()
out2["proposed_object"].update(lon=69.65, lat=42.31)
add("N25", "project_outside_bbox", dumps(out2), "reject", ["outside_bbox"], "вне bbox отклонять", "")
swapped = scenario()
swapped["control_points"][0].update(lon=42.31, lat=69.60)
add("N26", "lat_lon_swapped", dumps(swapped), "reject", ["outside_bbox", "bad_coordinate"], "вход [longitude, latitude]",
    "перепутанный порядок даёт lat=69.6 — вне диапазона/bbox")
add("N27", "lon_out_of_range", dumps(scenario(control_points=[{"id": "cp1", "lon": 200.0, "lat": 42.31}])), "reject",
    ["bad_coordinate", "outside_bbox"], "координаты конечные в диапазоне", "")
add("N28", "coordinate_as_string", dumps(scenario(control_points=[{"id": "cp1", "lon": "69.60", "lat": 42.31}])), "reject",
    ["bad_coordinate"], "координаты — числа", "")
add("N29", "coordinate_as_bool", dumps(scenario(control_points=[{"id": "cp1", "lon": True, "lat": 42.31}])), "reject",
    ["bad_coordinate"], "координаты — числа", "")
# ---- counts / projects ----
add("N30", "eleven_points", dumps(scenario(n=11)), "reject", ["too_many_points"], "контрольных точек 1..10", "")
add("N31", "zero_points", dumps(scenario(control_points=[])), "reject", ["no_points"], "1..10 для расчёта/экспорта",
    "пустое состояние UI допустимо, но не импорт пустого сценария")
two = scenario()
two["proposed_object"] = [two["proposed_object"], dict(two["proposed_object"], id="proj2", lon=69.61)]
add("N32", "two_projects_array", dumps(two), "reject", ["multiple_projects", "bad_project"], "число проектов >1", "")
add("N33", "two_projects_extra_key", dumps(dict(base, proposed_objects=[dict(base["proposed_object"], id="proj2")])), "reject",
    ["multiple_projects", "unknown_field"], "число проектов >1", "")
# ---- size ----
R_N34 = {"op": "pad", "from": "P01", "total_bytes": MAX_BYTES + 1}
add("N34", "over_256_KiB", recipe_text(dumps(base), R_N34), "reject", ["too_large"], "JSON импорта до 256 KiB",
    "на 1 байт больше; размер проверяется до разбора", recipe=R_N34)
R_N35 = {"op": "insert_label", "from": "P01", "char": "Ж", "count": 140000}
add("N35", "over_256_KiB_multibyte", recipe_text(dumps(base), R_N35), "reject", ["too_large"], "JSON импорта до 256 KiB",
    "около 140 тыс. символов, но >256 KiB в UTF-8: считать байты, а не символы", recipe=R_N35)
# ---- HTML / code / URLs / prototype ----
add("N36", "html_in_point_id", dumps(scenario(control_points=[{"id": "<img src=x onerror=alert(1)>", "lon": 69.6, "lat": 42.31}])),
    "reject", ["bad_id"], "строки безопасно как текст; ID ограничены", "HTML-подобный ID")
add("N37", "html_label_field", dumps(scenario(control_points=[{"id": "cp1", "lon": 69.6, "lat": 42.31,
                                                                "label": "<script>window.__K12_PWNED__=1</script>"}])),
    "reject", ["unknown_field", "unsafe_text"], "не принимать внешний код",
    "если поле label поддерживается — только как текст; эталон отклоняет неизвестное поле")
add("N38", "url_instead_of_points", dumps(dict(base, control_points="https://example.invalid/points.json")), "reject",
    ["bad_points", "external_reference"], "не загружать адреса из текста", "")
add("N39", "proto_pollution", dumps(base).replace('{\n "schema_version"', '{\n "__proto__": {"k12_polluted": true},\n "schema_version"', 1),
    "reject", ["unknown_field"], "строгая валидация", "ключ __proto__ не должен менять прототип объектов")
add("N40", "top_level_array", dumps([base]), "reject", ["bad_root"], "контракт — объект", "")
add("N41", "truncated_json", dumps(base)[:-20], "reject", ["invalid_json"], "строгая валидация", "")
add("N42", "utf8_bom", "﻿" + dumps(base), "reject_or_accept", [], "строгая валидация",
    "advisory: файл из Windows с BOM; допустимо снять BOM или отказать, но не падать", advisory=True)

if __name__ == "__main__":
    (OUT / "generated").mkdir(parents=True, exist_ok=True)
    index = []
    for f in F:
        p = HERE / f["file"]
        p.write_bytes(f["text"].encode("utf-8"))
        b = p.read_bytes()
        index.append({k: v for k, v in f.items() if k != "text"} | {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()})
    doc = {"fixture_set": "k12r7-city-whatif-import-stress-v1", "kind": "synthetic",
           "spec": "research/round-7/FEATURE_SPEC.txt @ codex/research-import-2026-10-05 7927fa8",
           "notice": "СИНТЕТИКА: точки, ID и подписи выдуманы; это не дома, не население и не реальные проекты. "
                     "Файлы не исполнять, адреса не открывать.",
           "bbox_at": {"build": "claude/beautiful-clarke-sbzomj@c58a3b2", "bbox": BBOX},
           "placeholders": ["__SNAPSHOT__", "__SNAPSHOT_OTHER_CITY__", "__SNAPSHOT_OTHER_CATEGORY__"],
           "max_bytes": MAX_BYTES,
           "invariant": "после любого отказа: активный сценарий, вычисленные строки и объяснение те же, что до импорта; "
                        "входной объект состояния не изменён; нет сетевых обращений; Object.prototype не изменён; "
                        "новые глобальные переменные не появились",
           "fixtures": index}
    (HERE / "FIXTURES_INDEX.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print({"fixtures": len(index), "accept": sum(f["expect"] == "accept" for f in F),
           "reject": sum(f["expect"] == "reject" for f in F)})
