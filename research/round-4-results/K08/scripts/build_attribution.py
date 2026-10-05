"""K08 R4: адаптер атрибуции для пакета K10 раунда 3 (только чтение входов).

Строит атрибуцию по ФАКТИЧЕСКИМ записям sources[] каждого GeoJSON пакета,
а не по константе из scripts/download.py:177. Входные файлы не изменяются.

Пишет в <out_dir>:
  attribution.json   — по каждому файлу: sha256, число записей, поставщики/лицензии/свойства,
                       записи, у которых источник всей записи не OSM, и нужные тексты лицензий;
  ATTRIBUTION.md     — читаемая версия для размещения рядом с пакетом.
Проверяет sha256 текстов в <out_dir>/LICENSES/ по таблице LICENSE_SHA256.

Только stdlib. Сеть не используется.
Usage: python build_attribution.py <K10_package_dir> <out_dir>
"""
import glob
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict

# SPDX license-list-data @31ba1a50e5397e00a304dbadc76531740e89ee48, text/<id>.txt
SPDX_COMMIT = "31ba1a50e5397e00a304dbadc76531740e89ee48"
LICENSE_SHA256 = {
    "ODbL-1.0": "77d2692c3d64efdd4db18dce2407699baf62930e2b50d6e5ed90b48acf16b7c1",
    "CDLA-Permissive-2.0": "4531a67d443284d93ffed0803df5b10634aff21c3d77e381f2d48af01d875868",
    "Apache-2.0": "074e6e32c86a4c0ef8b3ed25b721ca23aca83df277cd88106ef7177c354615ff",
}
# Пункты первичных текстов (SPDX), которые относятся к передаче данных.
CLAUSES = {
    "ODbL-1.0": ["4.2 уведомление при публичной передаче базы/производной", "4.3 уведомление на публично используемой Produced Work",
                 "4.4 share-alike для публично используемой производной базы", "4.6 машиночитаемая копия производной базы по запросу получателя"],
    "CDLA-Permissive-2.0": ["2.1 при передаче данных сделать доступным текст соглашения", "3.1 на Results ограничений нет"],
    "Apache-2.0": ["4(a) копия лицензии", "4(b) пометка изменённых файлов", "4(c) сохранить copyright/attribution notices",
                   "4(d) NOTICE, если он есть у исходного Work (наличие не проверено)"],
}


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def analyse(pkg):
    out = []
    for path in sorted(glob.glob(os.path.join(pkg, "data", "*", "*.geojson"))):
        with open(path, encoding="utf-8") as fh:
            fc = json.load(fh)
        providers = Counter()
        props = defaultdict(set)
        whole = Counter()
        non_osm = []
        for ft in fc["features"]:
            srcs = ft["properties"].get("sources") or []
            ds_whole = sorted({s.get("dataset") for s in srcs if not s.get("property")})
            whole["+".join(ds_whole) or "(нет)"] += 1
            if ds_whole and "OpenStreetMap" not in ds_whole:
                non_osm.append({"overture_id": ft["properties"].get("overture_id"), "datasets": ds_whole,
                                "class": ft["properties"].get("class"), "k10_group": ft["properties"].get("k10_group")})
            for s in srcs:
                key = (s.get("dataset"), s.get("provider"), s.get("resource"), s.get("license"), s.get("version"))
                providers[key] += 1
                props[key].add(s.get("property") or "(вся запись)")
        lic = sorted({k[3] for k in providers})
        out.append({
            "file": os.path.relpath(path, pkg).replace(os.sep, "/"),
            "city": fc.get("city"),
            "sha256": sha256(path),
            "features": len(fc["features"]),
            "header_attribution_in_input": fc.get("attribution"),
            "header_check": header_check(fc.get("attribution"), providers),
            "providers": [{"dataset": k[0], "provider": k[1], "resource": k[2], "license": k[3], "version": k[4],
                           "properties": sorted(props[k]), "entries": v} for k, v in providers.most_common()],
            "features_by_whole_record_dataset": dict(whole),
            "features_without_osm_whole_record": non_osm,
            "licenses": lic,
            "license_texts_needed": [f"LICENSES/{l}.txt" for l in lic],
            "clauses": {l: CLAUSES.get(l, ["(нет в таблице K08)"]) for l in lic},
        })
    return out


HEADER_KEYS = {"OpenStreetMap": "OpenStreetMap", "Overture": "Overture", "Meta": "meta", "Foursquare": "Foursquare",
               "TomTom": "TomTom", "Microsoft": "Microsoft", "AllThePlaces": "AllThePlaces", "PinMeTo": "PinMeTo"}


def header_check(header, providers):
    """Сравнить поставщиков, названных в шапке attribution, с dataset в sources[] (Overture — организация выпуска, не требуется в записях)."""
    named = {ds for word, ds in HEADER_KEYS.items() for line in (header or []) if word in line}
    in_records = {k[0] for k in providers}
    missing = sorted(in_records - named - {"Overture"})
    absent = sorted(named - in_records - {"Overture"})
    return {"named_in_header": sorted(named), "datasets_in_records": sorted(in_records),
            "missing_from_header": missing, "named_but_absent_in_records": absent, "ok": not missing and not absent}


def attribution_lines(providers):
    """Строки «поставщик — лицензия» по фактическим sources (без юридических формулировок поставщиков)."""
    names = {"OpenStreetMap": "OpenStreetMap contributors", "meta": "Meta", "Foursquare": "Foursquare",
             "TomTom": "TomTom", "Overture": "Overture Maps Foundation", "Microsoft": "Microsoft",
             "AllThePlaces": "AllThePlaces", "PinMeTo": "PinMeTo"}
    return sorted({f"{names.get(k[0], k[0])} ({k[3]})" for k in providers})


def render_md(files, lic_status, pkg_label):
    L = ["# Атрибуция: компактный геопакет K10 (раунд 3), Шымкент и Астана", "",
         f"Пакет: `{pkg_label}`. Данные — вторичные (`observed_secondary`), выпуск Overture Maps `2026-09-23.1`. "
         "Это не официальный реестр и не полный реестр города.", "",
         "Строки ниже построены по полю `sources[]` каждой записи (dataset, license, property). "
         "Поле `sources.license` — указание лицензии в записи, а не полная юридическая проверка. "
         "Рекомендованные формулировки атрибуции Overture, OpenStreetMap, Meta, Foursquare и TomTom из этой среды не открывались.", "",
         "## По файлам", ""]
    for f in files:
        L.append(f"### `{f['file']}` ({f['city']}, записей: {f['features']}, sha256 `{f['sha256']}`)")
        L.append("")
        for p in f["providers"]:
            L.append(f"- {p['dataset']} (provider `{p['provider']}`, resource `{p['resource']}`, version `{p['version']}`) — "
                     f"**{p['license']}**; относится к: {', '.join(p['properties'])}; записей sources: {p['entries']}")
        if f["features_without_osm_whole_record"]:
            L.append(f"- Записей без OSM как источника всей записи: {len(f['features_without_osm_whole_record'])} "
                     f"({', '.join(sorted({'+'.join(x['datasets']) for x in f['features_without_osm_whole_record']}))}).")
        hc = f["header_check"]
        if not hc["ok"]:
            L.append(f"- **Шапка `attribution` во входном файле** ({' / '.join(f['header_attribution_in_input'] or [])}) "
                     f"не соответствует sources: не названы {hc['missing_from_header'] or '—'}; названы, но отсутствуют в записях {hc['named_but_absent_in_records'] or '—'}.")
        L.append(f"- Тексты: {', '.join(f['license_texts_needed'])}")
        L.append("")
    L += ["## Тексты лицензий", "",
          f"Каталог `LICENSES/` содержит побайтные копии `text/<id>.txt` из https://github.com/spdx/license-list-data @ `{SPDX_COMMIT}` "
          "(нормализованные тексты SPDX, а не файлы с сайтов стюардов). Тексты не изменялись.", ""]
    for l, st in lic_status.items():
        L.append(f"- `LICENSES/{l}.txt` — sha256 `{LICENSE_SHA256[l]}` — {st}")
    L += ["", "## Что относится к чему", "",
          "- **Данные** (`data/`) — условия по `sources[].license` записей (выше).",
          "- **Код K10** (`scripts/`, `selection/`, `tests/`) — лицензия кода не указана. Условия данных к коду не применяются, и наоборот.",
          "- **Производные значения K10** (`k10_group`, `k10_foot_access`, `k10_*`) — классификация K10 поверх данных. "
          "Условия производного набора для ODbL-частей — ODbL 4.4 (share-alike); для CDLA-P-2.0 — 3.1 (Results без ограничений). Юридического заключения нет.", "",
          "## Неизвестно", "",
          "- Общие условия и рекомендуемая строка атрибуции Overture Maps Foundation.",
          "- Требования к атрибуции Meta, Foursquare (включая наличие NOTICE для Apache-2.0 4(d)) и TomTom Orbis.",
          "- Точная формулировка OSM на openstreetmap.org/copyright. Строка «© OpenStreetMap contributors» взята из пакета K10 и данных продукта и не сверена с первоисточником.", ""]
    return "\n".join(L)


def main():
    pkg, out = sys.argv[1], sys.argv[2]
    files = analyse(pkg)
    needed = sorted({l for f in files for l in f["licenses"]})
    lic_status = {}
    for l in needed:
        p = os.path.join(out, "LICENSES", f"{l}.txt")
        if l not in LICENSE_SHA256:
            lic_status[l] = "НЕТ в таблице K08"
        elif not os.path.exists(p):
            lic_status[l] = "ОТСУТСТВУЕТ"
        else:
            lic_status[l] = "sha256 совпадает" if sha256(p) == LICENSE_SHA256[l] else "sha256 НЕ совпадает"
    res = {"schema": "k08-r4-attribution/v1", "package": os.path.basename(os.path.normpath(pkg)),
           "spdx_commit": SPDX_COMMIT, "license_texts": lic_status, "files": files}
    with open(os.path.join(out, "attribution.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    with open(os.path.join(out, "ATTRIBUTION.md"), "w", encoding="utf-8") as fh:
        fh.write(render_md(files, lic_status, "research/round-3-results/K10/"))
    bad = [l for l, s in lic_status.items() if s != "sha256 совпадает"]
    print(json.dumps({"files": len(files), "licenses": lic_status,
                      "header_mismatch": [f["file"] for f in files if not f["header_check"]["ok"]]}, ensure_ascii=False))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
