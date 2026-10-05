"""K03: реестр территорий Астаны и Шымкента из сохранённых файлов, без сети.

Запуск из корня (после k03_geometry.py):
  python research/next-round/K03/build_registry.py
Пишет territory_registry.json и territory_registry.csv рядом со скриптом.
Отсутствующие полигоны не создаются: geometry = none.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GEO = json.loads((HERE / "geometry_result.json").read_text(encoding="utf-8"))
OSM_FILE = "data/geo_sources/astana_districts_overpass.json"
OSM_BASE = GEO["osm_base"]
OFFICIAL = "not_verified: adilet.zan.kz, stat.gov.kz — host_not_allowed (proxy CONNECT 403) 2026-10-05"
A10 = "research/govtech-results/10_safety/A10_sample_kpssu_shymkent_aggregates.json"
ASTANA = {3479876: "esil", 3482819: "almaty", 3486954: "saryarka", 8593081: "baikonur",
          20593940: "nura", 19733918: "saraishyk"}


def sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def osm_rows():
    conflicts = {c["astana_district"]: c for c in GEO["area_conflicts_with_neighbours"]}
    rows = []
    for rid_s, r in sorted(GEO["relations"].items(), key=lambda kv: (int(kv[0]) not in ASTANA, kv[1]["name"])):
        rid = int(rid_s)
        slug = ASTANA.get(rid)
        notes = []
        if r["admin_level"] == "8" and slug:
            notes.append("admin_level=8, у остальных районов 6")
        if len(r["parts_km2"]) > 1:
            notes.append(f"частей: {len(r['parts_km2'])}, км²: {r['parts_km2']}")
        if slug in conflicts:
            c = conflicts[slug]
            notes.append(f"площадной конфликт {c['overlap_km2']} км² с relation {c['neighbour_relation']} "
                         f"({c['neighbour_name']}), точка {c['sample_point_lonlat']}")
        if slug and r["kato_tag"] is None:
            notes.append("нет тега kato в OSM")
        if not slug:
            notes.append("сосед вне города; попадает в bbox-запрос; в агрегаты Астаны не включать")
        if slug == "saraishyk":
            rel = GEO["saraishyk_api_relation"]
            notes.append(f"relation v{rel['version']} от {rel['timestamp']}; в city_data.json ТЗ отсутствует")
        if slug and "product_vs_raw_iou" in r:
            notes.append(f"IoU слоя продукта и сырого OSM = {r['product_vs_raw_iou']}")
        rows.append({
            "city": "astana" if slug else "akmola_region_neighbour",
            "unit_type": "district" if slug else ("rural_administration" if r["admin_level"] == "8" else "district_or_city_admin"),
            "stable_id_proposed": f"kz.astana.district.{slug}" if slug else f"osm:relation/{rid}",
            "legacy_id": slug,
            "name_ru": r["name_ru"], "name_kk_or_osm_name": r["name_kk"] or r["name"],
            "osm_relation": rid, "admin_level": r["admin_level"],
            "kato": r["kato_tag"], "kato_origin": "osm_tag_kato" if r["kato_tag"] else None,
            "wikidata": r["wikidata"], "kpssu_code": None,
            "date": OSM_BASE, "date_kind": "osm_base_timestamp",
            "geometry": "osm_community_polygon",
            "area_km2_geodesic": r["area_km2_geodesic"],
            "provenance": f"{OSM_FILE} sha256={sha(OSM_FILE)[:16]}…",
            "geometry_check": "valid, rebuilt independently by K03",
            "official_status": OFFICIAL,
            "status": "observed_osm",
            "notes": "; ".join(notes)})
    return rows


def shymkent_rows():
    data = json.loads((ROOT / A10).read_text(encoding="utf-8"))
    years: dict[str, list[int]] = {}
    for code, year, _ in data["queries"]["shymkent_by_district_year"]["rows"]:
        years.setdefault(str(code), []).append(year)
    rows = [{
        "city": "shymkent", "unit_type": "city", "stable_id_proposed": "kz.shymkent", "legacy_id": None,
        "name_ru": "Шымкент", "name_kk_or_osm_name": None, "osm_relation": None, "admin_level": None,
        "kato": None, "kato_origin": None, "wikidata": None, "kpssu_code": "1979",
        "date": data["retrieved_at"], "date_kind": "retrieved_at (A10 via WebFetch)",
        "geometry": "none", "area_km2_geodesic": None,
        "provenance": f"{A10} sha256={sha(A10)[:16]}…",
        "geometry_check": "нет сохранённой геометрии ни в одном файле репозитория",
        "official_status": OFFICIAL, "status": "observed_code_only (A10, не перепроверено K03)",
        "notes": ("ISO KZ-79 — гипотеза A12-F018. Состав районов «Абайский, Аль-Фарабийский, Енбекшинский, "
                  "Каратауский, Туранский» — гипотеза A12-F016 (память модели), с кодами не сопоставлен.")}]
    for code in sorted(years):
        ys = sorted(years[code])
        rows.append({
            "city": "shymkent", "unit_type": "district_code", "stable_id_proposed": None, "legacy_id": None,
            "name_ru": None, "name_kk_or_osm_name": None, "osm_relation": None, "admin_level": None,
            "kato": None, "kato_origin": None, "wikidata": None, "kpssu_code": code,
            "date": f"{ys[0]}–{ys[-1]}", "date_kind": "годы, в которых код встречается в слое ДТП",
            "geometry": "none", "area_km2_geodesic": None,
            "provenance": f"{A10} sha256={sha(A10)[:16]}…; поле fd1r06p2",
            "geometry_check": "нет", "official_status": OFFICIAL,
            "status": "observed_code_only (A10, не перепроверено K03)",
            "notes": ("название района неизвестно: справочник кодов КПСиСУ не найден"
                      + ("; код появляется только с 2023 — вероятно изменение границ/учёта" if ys[0] >= 2023 else ""))})
    return rows


def astana_city_row():
    nom = "data/geo_sources/sara_nominatim.json"
    union = GEO["astana_union"]
    return {
        "city": "astana", "unit_type": "city", "stable_id_proposed": "kz.astana", "legacy_id": None,
        "name_ru": "Астана", "name_kk_or_osm_name": "Астана", "osm_relation": None, "admin_level": None,
        "kato": None, "kato_origin": None, "wikidata": None, "kpssu_code": None,
        "date": OSM_BASE, "date_kind": "osm_base_timestamp",
        "geometry": "derived_union_of_6_osm_districts", "area_km2_geodesic": union["area_km2"],
        "provenance": f"{OSM_FILE}; ISO KZ-71 из {nom} sha256={sha(nom)[:16]}…",
        "geometry_check": f"объединение 6 районов, частей {len(union['parts_km2'])}: {union['parts_km2']}",
        "official_status": OFFICIAL, "status": "derived_from_osm",
        "notes": "relation самого города в снимке нет (запрос admin_level 5–9); ISO3166-2-lvl4 KZ-71 по Nominatim"}


def main() -> None:
    rows = [astana_city_row()] + osm_rows() + shymkent_rows()
    (HERE / "territory_registry.json").write_text(
        json.dumps({"generated_from": ["geometry_result.json", OSM_FILE, A10], "rows": rows},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with open(HERE / "territory_registry.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(len(rows), "rows")


if __name__ == "__main__":
    main()
