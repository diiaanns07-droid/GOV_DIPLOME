"""K10 round 10: build the Astana school-access package from the committed pinned inputs (deterministic).

    python research/round-10-results/K10/scripts/build_astana_package.py [--out DIR]

Inputs (research/round-10-results/K10/): inputs/*.jsonl|json (make_inputs.py), review/review_decisions.json.
Outputs (default package/): sources.json, schools.json, evidence.json, match-review.json, astana.case.json, MANIFEST.json.
Needs shapely + pyproj (geometry tests only); distances use the spherical formula of k10case.py so that the
validator reproduces every buffer decision.
"""
import hashlib
import json
import math
import re
import sys
from pathlib import Path

import shapely
import shapely.ops
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parent))
import k10case as KC  # noqa: E402

K = Path(__file__).resolve().parents[1]
IN = K / "inputs"
BBOX = [71.418372, 51.163033, 71.447, 51.181]
RELEASE = "2026-09-23.1"
CODE_SHA = "d2ff344c5ec9b9a729ea59df50ec81f981e619de"
DETOUR_F = 1.5          # assumption (not measured): network distance ≤ 1.5 × straight distance for the nearest school
GRID_M = 25             # sampling step inside the bbox for the buffer distance D
THRESHOLD_M = 800       # user parameter by default, not a norm
UTM = Transformer.from_crs(4326, 32642, always_xy=True)
SRC = {"places": "ov-places-2026-09-23.1", "landuse": "osm-landuse-via-overture-2026-09-23.1", "bedu": "ov-buildings-edu-2026-09-23.1",
       "bres": "ov-buildings-res-bbox-2026-09-23.1", "ball": "ov-buildings-all-bbox-2026-09-23.1", "app": "app-slice-astana-d2ff344",
       "egov": "egov-school-contacts", "govkz": "gov-kz-astana-bilim", "bilim": "astana-bilim-school-sites",
       "lead8a": "lead-informburo-sh8-closed", "lead8b": "lead-informburo-sh8-repair", "leadagis": "lead-forbes-agis"}
NOT_SCHOOL = re.compile(r"центр|center|centre|academy|академ|курс|колледж|college|арена|гимнаст|робот|роботи|\bart\b|дизайн|design|музык|music|балет|ballet|\bAI\b|support|танц|dance|спорт", re.I)
PRESCHOOL = re.compile(r"детск\w* сад|балабақша|kindergarten|ясли", re.I)
UNRESOLVED_HINT = re.compile(r"english|language|smart|merey|harmony|мирас|vinetka", re.I)
SCHOOL_WORD = re.compile(r"школ|мектеп|лицей|гимназ|school|litsey|shkola", re.I)
GENERAL = re.compile(r"(№|N\s|#|No\.?)\s*\d|\d+\s*(-?ші\s*)?(мектеп|орта)|(школа|лицей|гимназия|school)[-\s]*\d|орта мектеп|средняя|общеобразоват|жалпы орта|ГУ ", re.I)
RESTRICTED = [("special_school", re.compile(r"арнайы|специальн", re.I)),
              ("school_for_gifted", re.compile(r"дарын|одар[её]н|зерде|интернат|мамандандырылған|специализированн", re.I)),
              ("school_private_international", re.compile(r"international|халықаралық|международн|private|частн", re.I)),
              ("evening_school", re.compile(r"кешкі|вечерн", re.I))]
NUM = re.compile(r"(?:№|\bN|#|\bNo\.?)\s*(\d{1,3})\b|(?:школа|лицей|гимназия|school)[-\s]+(\d{1,3})\b|\b(\d{1,3})\s*(?:-?\s*ші\s*)?(?:мектеп|орта мектеп)", re.I)


def jl(name):
    with open(IN / name, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def proj(g):
    return shapely.ops.transform(lambda x, y, z=None: UTM.transform(x, y), g)


def nums(*names):
    out = set()
    for n in names:
        for m in NUM.finditer(n or ""):
            out.add(next(x for x in m.groups() if x))
    return sorted(out, key=int)


def names_of(r):
    n = r.get("names") or {}
    common = dict(n.get("common") or [])
    return n.get("primary"), common.get("ru")


def osm_ref(r):
    for s in r.get("sources") or []:
        if s.get("dataset") == "OpenStreetMap":
            return s.get("record_id"), s.get("update_time")
    s = (r.get("sources") or [{}])[0]
    return s.get("record_id"), s.get("update_time")


def classify(text):
    """name rule -> (category, eligibility, rule id)"""
    for cat, rx in RESTRICTED:
        if rx.search(text):
            return cat, "known_restricted", "R-" + cat
    if GENERAL.search(text) and SCHOOL_WORD.search(text):
        return "general_school", "known_public", "R-general-numbered"
    return "school_unknown_type", "unknown", "R-unknown-type"


def m1(v):
    return round(v, 1)


def main(a):
    out = Path(a[a.index("--out") + 1]) if "--out" in a else K / "package"
    out.mkdir(parents=True, exist_ok=True)
    review = json.loads((K / "review/review_decisions.json").read_text(encoding="utf-8"))
    app = json.loads((IN / "app_slice_astana.json").read_text(encoding="utf-8"))
    LU, BE, PL, BR, BA = jl("osm_landuse_education.jsonl"), jl("osm_buildings_education.jsonl"), jl("overture_places_education.jsonl"), jl("buildings_bbox_residential.jsonl"), jl("buildings_bbox_all.jsonl")
    prov_in = json.loads((IN / "provenance/inputs_manifest.json").read_text(encoding="utf-8"))
    raw_prov = {f: json.loads((IN / "provenance" / (f + ".provenance.json")).read_text(encoding="utf-8")) for f in ("astana_places_q3km.jsonl", "astana_land_use_q3km.jsonl", "astana_buildings_q3km.jsonl")}
    box = shapely.box(*BBOX)

    # ---------- entities from OSM school grounds and OSM school buildings ----------
    ents, excluded_osm = {}, []
    lu_school = [r for r in LU if r["class"] == "school"]
    lu_geo = {}
    for r in lu_school:
        ref, upd = osm_ref(r)
        g = shapely.from_wkt(r["geometry_wkt"])
        c = g.centroid if g.centroid.within(g) else g.representative_point()
        kk, ru = names_of(r)
        eid = "ast-sch-osm-" + ref.split("@")[0]
        cat, el, rule = classify(f"{kk or ''} {ru or ''}")
        ents[eid] = {"id": eid, "origin": "osm_grounds", "ref": ref, "osm_update_time": upd, "names": {"osm": kk, "osm_ru": ru}, "lon": round(c.x, 7), "lat": round(c.y, 7),
                     "point_method": "centroid of OSM school grounds polygon" if g.centroid.within(g) else "representative point of OSM school grounds polygon",
                     "source": SRC["landuse"], "category": cat, "eligibility": el, "rule": rule, "numbers": nums(kk, ru), "tags": dict(r["source_tags"]),
                     "geom_m": proj(g), "buildings": [], "meta": [], "conflicts": [], "qa": [], "review": None}
        lu_geo[eid] = ents[eid]["geom_m"]
    for b in BE:
        if b["class"] != "school":
            continue
        ref, upd = osm_ref(b)
        g = shapely.from_wkt(b["geometry_wkt"])
        gm = proj(g)
        host = [eid for eid, lg in lu_geo.items() if lg.distance(gm.centroid) < 15]
        kk, ru = names_of(b)
        if host:
            ents[host[0]]["buildings"].append({"ref": ref, "name": kk, "num_floors": b.get("num_floors")})
            continue
        eid = "ast-sch-osmb-" + ref.split("@")[0]
        if kk and NOT_SCHOOL.search(f"{kk} {ru or ''}"):
            excluded_osm.append({"layer": "osm_building", "record_id": ref, "entity": None, "name": ru or kk, "distance_to_bbox_m": None, "decision": "not_school",
                                 "decided_by": "rule:R-not-school-name", "reason": "building=school, but the name shows an arts/sport/other non-general school", "lonlat": [g.centroid.x, g.centroid.y]})
            continue
        c = g.centroid if g.centroid.within(g) else g.representative_point()
        cat, el, rule = classify(f"{kk or ''} {ru or ''}") if kk else ("school_unknown_type", "unknown", "R-unnamed-building")
        ents[eid] = {"id": eid, "origin": "osm_building", "ref": ref, "osm_update_time": upd, "names": {"osm": kk, "osm_ru": ru}, "lon": round(c.x, 7), "lat": round(c.y, 7),
                     "point_method": "centroid of OSM building=school footprint", "source": SRC["bedu"], "category": cat, "eligibility": el, "rule": rule,
                     "numbers": nums(kk, ru), "tags": {}, "geom_m": gm, "buildings": [{"ref": ref, "name": kk, "num_floors": b.get("num_floors")}], "meta": [], "conflicts": [], "qa": [], "review": None}

    # ---------- Meta / Overture places of the school group ----------
    def is_school_group(p):
        h = (p.get("taxonomy") or {}).get("hierarchy") or []
        return h[:3] == ["education", "place_of_learning", "school"] and "preschool" not in h
    places = {p["id"]: p for p in PL}
    slice_ids = {p["id"] for p in app["places_school_and_preschool"] if p["group"] == "school"}
    missing = slice_ids - set(review["slice_records"])
    assert not missing, f"slice school records without a manual decision: {missing}"
    manual = dict(review["slice_records"])
    for k, v in review["other_records"].items():
        if not k.startswith("osm:"):
            full = [pid for pid in places if pid.startswith(k)]
            assert len(full) == 1, k
            manual[full[0]] = v
    rows = []  # match-review rows
    meta_only, duplicates = {}, []
    for pid in sorted(set(p["id"] for p in PL if is_school_group(p)) | slice_ids):
        p = places[pid]
        pt = shapely.Point(p["lon"], p["lat"])
        ptm = proj(pt)
        name = p["names"]["primary"] or ""
        n = nums(name)
        near = sorted(((e["geom_m"].distance(ptm), eid) for eid, e in ents.items()), key=lambda x: (x[0], x[1]))[:3]
        same_num = sorted(((ents[eid]["geom_m"].distance(ptm), eid) for eid in ents if n and set(n) & set(ents[eid]["numbers"])), key=lambda x: x[0])[:2]
        row = {"layer": "overture_places", "record_id": pid, "name": name, "lon": p["lon"], "lat": p["lat"], "category_by_source": (p.get("taxonomy") or {}).get("primary"),
               "confidence": round(p["confidence"], 3) if p.get("confidence") is not None else None, "in_app_slice": pid in slice_ids,
               "distance_to_bbox_m": m1(KC.dist_to_bbox_m(p["lon"], p["lat"], BBOX)), "numbers_in_name": n,
               "nearest_osm_school_entities": [{"entity": eid, "distance_m": m1(d)} for d, eid in near],
               "same_number_osm_entities": [{"entity": eid, "distance_m": m1(d)} for d, eid in same_num]}
        if pid in manual:
            dec = manual[pid]
            row.update({"decision": dec["decision"], "decided_by": "manual_review", "reason": dec["reason"]})
            ent_ref = dec.get("entity")
            if dec["decision"] == "attach":
                eid = "ast-sch-osm-" + ent_ref.split(":")[1]
                ents[eid]["meta"].append({"record_id": pid, "name": name, "distance_m": m1(ents[eid]["geom_m"].distance(ptm)), "update_time": p["sources"][0]["update_time"]})
                row["entity"] = eid
            elif dec["decision"] == "conflict_not_target":
                eid = "ast-sch-osm-" + ent_ref.split(":")[1]
                ents[eid]["conflicts"].append({"record_id": pid, "name": name, "distance_m": m1(ents[eid]["geom_m"].distance(ptm)), "reason": dec["reason"]})
                row["entity"] = eid
            elif dec["decision"] == "include_meta_only":
                eid = "ast-sch-meta-" + pid[:8]
                meta_only[eid] = {"id": eid, "origin": "meta_poi", "ref": pid, "names": {"meta": name}, "lon": p["lon"], "lat": p["lat"], "point_method": "Overture/Meta POI point",
                                  "source": SRC["places"], "category": dec["category"], "eligibility": dec["access_eligibility"], "rule": "manual_review", "numbers": n,
                                  "meta_update_time": p["sources"][0]["update_time"], "confidence": p.get("confidence"), "address": [x["freeform"] for x in p["addresses"]][:1],
                                  "geom_m": ptm, "buildings": [], "meta": [], "conflicts": [], "qa": list(dec.get("qa", [])), "review": dec["reason"]}
                row["entity"] = eid
            elif dec["decision"] == "duplicate_of":
                row["entity"] = "ast-sch-meta-" + ent_ref.split(":")[1]
                duplicates.append((row["entity"], {"record_id": pid, "name": name, "lon": p["lon"], "lat": p["lat"], "reason": dec["reason"]}))
            rows.append(row)
            continue
        # automatic rules: non-school names first (a kindergarten or arts school next to a school is a separate place)
        inside = [eid for d, eid in near if d <= 75 and (not n or not ents[eid]["numbers"] or set(n) & set(ents[eid]["numbers"]))]
        general = bool(SCHOOL_WORD.search(name) and GENERAL.search(name))
        if NOT_SCHOOL.search(name) or (PRESCHOOL.search(name) and not general):
            row.update({"decision": "not_school", "decided_by": "rule:R-not-school-name", "reason": "name indicates a non-school place (centre, course, kindergarten, college, arts, sport …)"})
        elif inside:
            eid = inside[0]
            ents[eid]["meta"].append({"record_id": pid, "name": name, "distance_m": m1(ents[eid]["geom_m"].distance(ptm)), "update_time": p["sources"][0]["update_time"]})
            row.update({"decision": "attach", "decided_by": "rule:R-attach-75m-number-compatible", "entity": eid,
                        "reason": "POI within 75 m of OSM school geometry, school numbers compatible"})
        elif same_num and SCHOOL_WORD.search(name):
            d, eid = same_num[0]
            ents[eid]["conflicts"].append({"record_id": pid, "name": name, "distance_m": m1(d), "reason": "same school number, POI farther than 75 m"})
            row.update({"decision": "conflict_not_target", "decided_by": "rule:R-same-number-far", "entity": eid,
                        "reason": f"Same school number as {eid} at {m1(d)} m: location conflict, not a second school"})
        elif (general and not UNRESOLVED_HINT.search(name)) or classify(name)[1] == "known_restricted":
            eid = "ast-sch-meta-" + pid[:8]
            cat, el, rule = classify(name)
            meta_only[eid] = {"id": eid, "origin": "meta_poi", "ref": pid, "names": {"meta": name}, "lon": p["lon"], "lat": p["lat"], "point_method": "Overture/Meta POI point",
                              "source": SRC["places"], "category": cat if el == "known_restricted" else "school_unverified", "eligibility": el if el == "known_restricted" else "unknown",
                              "rule": "R-meta-only-" + rule[2:], "numbers": n, "meta_update_time": p["sources"][0]["update_time"], "confidence": p.get("confidence"),
                              "address": [x["freeform"] for x in p["addresses"]][:1], "geom_m": ptm, "buildings": [], "meta": [], "conflicts": [], "qa": [], "review": None}
            row.update({"decision": "include_meta_only", "decided_by": "rule:R-meta-only-school-name", "entity": eid,
                        "reason": "school name without OSM school geometry: kept as an existing school with eligibility " + meta_only[eid]["eligibility"]})
        else:
            row.update({"decision": "unresolved_excluded", "decided_by": "rule:R-unresolved", "reason": "category from the POI source only; the name does not show a general school; no OSM school geometry"})
        rows.append(row)
    for eid, e in meta_only.items():
        ents[eid] = e
    for eid, d in duplicates:
        ents[eid]["conflicts"].append({"record_id": d["record_id"], "name": d["name"], "distance_m": m1(KC.haversine_m(d["lon"], d["lat"], ents[eid]["lon"], ents[eid]["lat"])), "reason": d["reason"]})
    for k, v in review["other_records"].items():
        if k.startswith("osm:"):
            eid = "ast-sch-osm-" + k.split(":")[1]
            ents[eid]["eligibility"] = v["access_eligibility"]
            ents[eid]["rule"] = "manual_review"
            ents[eid]["qa"] += v.get("qa", [])
            ents[eid]["review"] = v["reason"]

    # ---------- buffer: D over known_public entities, B = ceil100(f·D) ----------
    pub = [(e["lon"], e["lat"]) for e in ents.values() if e["eligibility"] == "known_public"]
    lat0 = (BBOX[1] + BBOX[3]) / 2
    nx = int(KC.haversine_m(BBOX[0], lat0, BBOX[2], lat0) // GRID_M) + 1
    ny = int(KC.haversine_m(BBOX[0], BBOX[1], BBOX[0], BBOX[3]) // GRID_M) + 1
    D, at = 0.0, None
    for i in range(nx + 1):
        x = BBOX[0] + (BBOX[2] - BBOX[0]) * i / nx
        for j in range(ny + 1):
            y = BBOX[1] + (BBOX[3] - BBOX[1]) * j / ny
            dm = min(KC.haversine_m(x, y, a_, b_) for a_, b_ in pub)
            if dm > D:
                D, at = dm, (round(x, 7), round(y, 7))
    B = int(math.ceil(DETOUR_F * D / 100.0) * 100)
    extract_half = min(KC.dist_to_bbox_m(x, y, BBOX) for x, y in ((71.3754, lat0), (71.4900, lat0), ((BBOX[0] + BBOX[2]) / 2, 51.1360), ((BBOX[0] + BBOX[2]) / 2, 51.2080)))
    assert B < extract_half, f"buffer {B} m exceeds the pinned extract ({extract_half:.0f} m): extract again with a larger box"
    for r in rows:
        r["within_package_buffer"] = r["distance_to_bbox_m"] <= B
    in_pkg = {eid: e for eid, e in ents.items() if KC.dist_to_bbox_m(e["lon"], e["lat"], BBOX) <= B}
    # every school-group POI inside the buffer must have a decision; every in-bbox app record too
    assert all("decision" in r for r in rows)

    # ---------- sources ----------
    def s(id_, url, pub_, title, period, retrieved, status, lic, content):
        return {"id": id_, "url": url, "publisher": pub_, "title": title, "published_at": None, "data_period": period, "retrieved_at": retrieved,
                "verification_status": status, "license": lic, "content_sha256": content}
    bucket = "https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/release/" + RELEASE
    rp = raw_prov
    sources = [
        s(SRC["places"], bucket + "/theme=places/type=place/", "Overture Maps Foundation (POI records from Meta and other contributors)",
          "Overture places, education records around the Astana slice (bbox + ~3 km)", f"release {RELEASE}; Meta record update_time 2026-08/09",
          rp["astana_places_q3km.jsonl"]["started_utc"], "secondary_only", "CDLA-Permissive-2.0 (per record; see inputs)", sha(IN / "overture_places_education.jsonl")),
        s(SRC["landuse"], bucket + "/theme=base/type=land_use/", "OpenStreetMap contributors via Overture Maps Foundation",
          "OSM education land use (amenity=school/kindergarten/college/university) with source tags", f"OSM snapshot used by Overture {RELEASE} (record version 2026-09-06)",
          rp["astana_land_use_q3km.jsonl"]["started_utc"], "secondary_only", "ODbL-1.0", sha(IN / "osm_landuse_education.jsonl")),
        s(SRC["bedu"], bucket + "/theme=buildings/type=building/", "OpenStreetMap contributors via Overture Maps Foundation",
          "OSM buildings with an education class (building=school etc.)", f"Overture {RELEASE}", rp["astana_buildings_q3km.jsonl"]["started_utc"], "secondary_only",
          "ODbL-1.0", sha(IN / "osm_buildings_education.jsonl")),
        s(SRC["bres"], bucket + "/theme=buildings/type=building/", "OpenStreetMap contributors via Overture Maps Foundation",
          "Residential building footprints with centroid in the slice bbox (origin pool)", f"Overture {RELEASE}", rp["astana_buildings_q3km.jsonl"]["started_utc"],
          "secondary_only", "ODbL-1.0", sha(IN / "buildings_bbox_residential.jsonl")),
        s(SRC["ball"], bucket + "/theme=buildings/type=building/", "OpenStreetMap contributors and Microsoft ML Buildings via Overture Maps Foundation",
          "All building footprints intersecting the slice bbox (used only to flag hypothesis points on existing footprints)", f"Overture {RELEASE}",
          rp["astana_buildings_q3km.jsonl"]["started_utc"], "secondary_only", "ODbL-1.0 (OSM); Microsoft ML Buildings licence per record", sha(IN / "buildings_bbox_all.jsonl")),
        s(SRC["app"], f"git:diiaanns07-droid/GOV_DIPLOME@{CODE_SHA}:web/govtech/core/data.js", "GOV_DIPLOME (pinned app slice of Overture/OSM)",
          "Astana slice of the current main site (school group, 8 records)", f"Overture {app['release']}, retrieved {app['retrieved_utc']}", app["retrieved_utc"],
          "secondary_only", "CDLA-Permissive-2.0 / ODbL-1.0 (see web/govtech/core/attribution)", app["data_js_sha256"]),
        s(SRC["egov"], "https://egov.kz/cms/ru/articles/2Fspisok_wkol_rk", "eGov.kz (по домену; страница не открыта)",
          "Контакты общеобразовательных школ городов Астана, Алматы, Шымкент и областных центров РК (заголовок из результата поиска)", None, None, "not_fetched", "unknown", None),
        s(SRC["govkz"], "https://www.gov.kz/memleket/entities/astana-bilim", "gov.kz (по URL — управление образования г. Астаны; страница не открыта)",
          "Страница управления образования г. Астаны (не открыта)", None, None, "not_fetched", "unknown", None),
        s(SRC["bilim"], "https://astana-bilim.kz/", "astana-bilim.kz (сайты школ, на которые указывают теги website в OSM; не открыт)",
          "Сайты школ вида N.astana-bilim.kz (не открыты)", None, None, "not_fetched", "unknown", None),
        s(SRC["lead8a"], "https://informburo.kz/novosti/v-astane-shkoly-8-zakryli-a-detey-otpravili-po-drugim-uchebnym-zavedeniyam.html", "informburo.kz (СМИ; страница не открыта)",
          "Наводка из поиска: «в Астане школу №8 закрыли, а детей отправили по другим учебным заведениям» (по адресу страницы)", None, None, "not_fetched", "unknown", None),
        s(SRC["lead8b"], "https://informburo.kz/novosti/ucheniki-ssh-8-astany-hodyat-na-zanyatiya-v-tri-drugie-shkoly-zdaniyu-trebuetsya-kapremont.html", "informburo.kz (СМИ; страница не открыта)",
          "Наводка из поиска: «ученики СШ №8 Астаны ходят на занятия в три другие школы, зданию требуется капремонт» (по адресу страницы)", None, None, "not_fetched", "unknown", None),
        s(SRC["leadagis"], "https://forbes.kz/ranking/object/1146", "forbes.kz (рейтинг; страница не открыта)",
          "Наводка из поиска: Astana Garden International School в рейтинге частных школ", None, None, "not_fetched", "unknown", None),
    ]
    by_src = {x["id"]: x for x in sources}

    # ---------- schools (package view and CONTRACT records) ----------
    def qa_items(e):
        q = [{"code": "no_official_verification", "text": "Официальный перечень не открыт из этой среды (NOT_FETCHED); запись — вторичные открытые данные."}]
        if e["eligibility"] == "known_public":
            q.append({"code": "eligibility_inferred_from_name", "text": "Общедоступность выведена из номерного названия общеобразовательной школы, не из реестра; правила приёма не проверены."})
        if e["origin"] == "meta_poi":
            q.append({"code": "single_poi_source", "text": "Только точка POI (Overture/Meta); геометрии школы в OSM рядом нет."})
        if e["origin"] == "osm_building" and not e["names"]["osm"]:
            q.append({"code": "unnamed_school_building", "text": "Здание с тегом building=school без названия: тип и доступность неизвестны."})
        if not e["meta"] and e["origin"] != "meta_poi":
            q.append({"code": "osm_only", "text": "Нет подтверждающей точки POI второго поставщика (только OSM)."})
        for c in e["conflicts"]:
            q.append({"code": "location_conflict", "text": f"Другой источник называет ту же школу в {c['distance_m']:.0f} м отсюда: «{c['name'][:80]}». Конфликт не разрешён."})
        if "identity_conflict" in e["qa"]:
            q.append({"code": "identity_conflict", "text": "Название и местоположение расходятся между источниками; есть непроверенная наводка о закрытии здания школы №8 в 2017 г. (NOT_FETCHED)."})
        if "possible_same_site" in e["qa"]:
            q.append({"code": "possible_same_site", "text": "Возможно, то же место, что и участок «№8 мектеп-лицей» в OSM (~100 м)."})
        if e["eligibility"] == "known_restricted":
            q.append({"code": "restricted_by_type", "text": "Специальная, профильная для одарённых, частная/международная или вечерняя школа по названию: не считается общедоступной целью."})
        if KC.dist_to_bbox_m(e["lon"], e["lat"], BBOX) > 0:
            q.append({"code": "outside_bbox_in_buffer", "text": f"Вне участка, в буфере {B} м: нужна для ближайшей школы у границы."})
        return sorted(q, key=lambda x: x["code"])

    def label(e):
        if e["origin"] == "meta_poi":
            return e["names"]["meta"].strip('"').replace('""', '"')[:200]
        if e["names"]["osm_ru"]:
            return e["names"]["osm_ru"][:200]
        if e["names"]["osm"]:
            return e["names"]["osm"][:200]
        return f"Здание школы без названия (OSM {e['ref'].split('@')[0]})"

    def ownership(e):
        t = " ".join(filter(None, [e["names"].get("osm"), e["names"].get("osm_ru"), e["names"].get("meta")] + [m["name"] for m in e["meta"]]))
        if re.search(r"\bГУ\b|УО г\. Астаны|State School|коммунальн", t):
            return {"value": "state_inferred", "method": "название в POI («ГУ … УО г. Астаны» / State School)", "verification_status": "secondary_only", "confidence": "medium"}
        if e["category"] == "school_private_international":
            return {"value": "private_inferred", "method": "название (international/private)", "verification_status": "secondary_only", "confidence": "low"}
        if e["eligibility"] == "known_public":
            return {"value": "state_inferred", "method": "номерное название общеобразовательной школы (вывод, не реестр)", "verification_status": "secondary_only", "confidence": "low"}
        return {"value": None, "method": None, "verification_status": "not_fetched", "confidence": None}

    case_schools, pkg_schools = [], []
    for eid in sorted(in_pkg):
        e = in_pkg[eid]
        srcs = sorted({e["source"]} | ({SRC["places"]} if e["meta"] else set()) | ({SRC["bedu"]} if e["buildings"] and e["origin"] == "osm_grounds" else set())
                      | ({SRC["app"]} if any(m["record_id"] in slice_ids for m in e["meta"]) or (e["origin"] == "meta_poi" and e["ref"] in slice_ids) else set()))
        leads = [SRC["lead8a"], SRC["lead8b"]] if "identity_conflict" in e["qa"] else [SRC["leadagis"]] if e["category"] == "school_private_international" and e["ref"].startswith("a4483f53") else []
        fp = {
            "label": {"source_id": e["source"], "record": e["ref"], "field": "names.primary (meta)" if e["origin"] == "meta_poi" else ("names.common.ru" if e["names"].get("osm_ru") else "names.primary"), "verification_status": "secondary_only"},
            "coordinates": {"source_id": e["source"], "record": e["ref"], "method": e["point_method"], "verification_status": "secondary_only",
                            "confidence": "medium" if e["origin"] != "meta_poi" else "low", "note": "модельная точка (центр участка/здания или точка POI), не вход"},
            "category": {"value": e["category"], "method": e["rule"], "verification_status": "secondary_only", "confidence": "medium" if e["rule"].startswith("R-general") else "low"},
            "access_eligibility": {"value": e["eligibility"], "method": e["rule"], "verification_status": "secondary_only", "confidence": "low" if e["eligibility"] != "known_public" or e["conflicts"] else "medium",
                                   "official_source_ids": [SRC["egov"], SRC["govkz"]], "official_status": "not_fetched"},
            "ownership": ownership(e),
            "admission_rules": {"value": None, "verification_status": "not_fetched", "note": "закрепление территорий/правила приёма не получены"},
            "operating_status": {"value": "conflict" if e["conflicts"] or "identity_conflict" in e["qa"] else None, "verification_status": "secondary_only" if e["conflicts"] else "not_fetched", "lead_source_ids": leads},
            "period": {"overture_release": RELEASE, "osm_last_edit": e.get("osm_update_time"), "poi_update_time": e.get("meta_update_time") or (e["meta"][0]["update_time"] if e["meta"] else None)},
            "capacity": {"value": None, "verification_status": "not_fetched", "note": "источника вместимости нет"},
            "corroboration": [{"source_id": SRC["places"], "record": m["record_id"], "distance_m": m["distance_m"]} for m in e["meta"]]
                             + [{"source_id": SRC["bedu"], "record": b["ref"], "relation": "building inside grounds"} for b in e["buildings"] if e["origin"] == "osm_grounds"],
        }
        rec = {"id": eid, "label": label(e), "lon": e["lon"], "lat": e["lat"], "kind": "observed_secondary", "source_ids": srcs, "field_provenance": fp, "qa": qa_items(e),
               "category": e["category"], "access_eligibility": e["eligibility"], "capacity": None, "capacity_source_ids": []}
        case_schools.append(rec)
        pkg = dict(rec)
        pkg.update({"names": e["names"], "distance_to_bbox_m": m1(KC.dist_to_bbox_m(e["lon"], e["lat"], BBOX)), "in_bbox": KC.dist_to_bbox_m(e["lon"], e["lat"], BBOX) == 0,
                    "school_numbers": e["numbers"], "osm_school_buildings": e["buildings"], "poi_records": e["meta"], "conflicts": e["conflicts"], "review_note": e["review"],
                    "verification_status": "conflict" if e["conflicts"] or "identity_conflict" in e["qa"] else "secondary_only"})
        pkg_schools.append(pkg)

    # ---------- origins: residential footprints, one per 5×5 cell (largest area) ----------
    cells = {}
    for r in BR:
        i = min(4, int((r["lon"] - BBOX[0]) / (BBOX[2] - BBOX[0]) * 5))
        j = min(4, int((r["lat"] - BBOX[1]) / (BBOX[3] - BBOX[1]) * 5))
        best = cells.get((i, j))
        if best is None or (r["footprint_area_m2"], r["id"]) > (best["footprint_area_m2"], best["id"]):
            cells[(i, j)] = r
    origins = []
    for (i, j) in sorted(cells):
        r = cells[(i, j)]
        ref = r["sources"][0]["record_id"]
        origins.append({"id": f"ast-org-c{j}{i}", "label": f"Жилое здание ({r['class']}) — ячейка {j + 1}-{i + 1}", "lon": r["lon"], "lat": r["lat"], "kind": "derived",
                        "source_ids": [SRC["bres"]], "field_provenance": {"coordinates": {"source_id": SRC["bres"], "record": ref, "method": r["point_method"] + " of the building footprint", "verification_status": "secondary_only"},
                                                                            "selection": {"method": "крупнейшая по площади жилая постройка (классы apartments/residential/house/detached/dormitory…) в ячейке сетки 5×5 участка", "footprint_area_m2": r["footprint_area_m2"], "class": r["class"]},
                                                                            "weight": {"value": 1, "method": "равные веса первого сценария"}},
                        "qa": [{"code": "not_population", "text": "Точка анализа — центр здания, а не жители или дети; численность неизвестна."}],
                        "weight": 1, "parent_source_id": SRC["bres"], "method": f"центр контура здания OSM {ref}; выбор: крупнейшее жилое здание ячейки {j + 1}-{i + 1} сетки 5×5"})
    empty_cells = sorted(f"{j + 1}-{i + 1}" for i in range(5) for j in range(5) if (i, j) not in cells)

    # ---------- hypothesis points: farthest cell centres (10×10) from known_public schools, ≥ 600 m apart ----------
    pubs = [(x["lon"], x["lat"]) for x in case_schools if x["access_eligibility"] == "known_public"]
    allb = [(shapely.from_wkt(b["geometry_wkt"]), b) for b in BA]
    school_geoms = [e["geom_m"] for e in in_pkg.values() if e["origin"] != "meta_poi"]
    cand_pool = []
    for i in range(10):
        for j in range(10):
            x = round(BBOX[0] + (BBOX[2] - BBOX[0]) * (i + 0.5) / 10, 7)
            y = round(BBOX[1] + (BBOX[3] - BBOX[1]) * (j + 0.5) / 10, 7)
            pm = proj(shapely.Point(x, y))
            if any(g.distance(pm) < 50 for g in school_geoms):
                continue
            if not any(KC.haversine_m(x, y, o["lon"], o["lat"]) <= 300 for o in origins):
                continue  # keep hypotheses next to analysed residential buildings
            cand_pool.append((min(KC.haversine_m(x, y, a_, b_) for a_, b_ in pubs), x, y))
    cand_pool.sort(key=lambda t: (-t[0], t[1], t[2]))
    picked = []
    for d, x, y in cand_pool:
        if all(KC.haversine_m(x, y, px, py) >= 600 for _, px, py in picked):
            picked.append((d, x, y))
        if len(picked) == 3:
            break
    candidates = []
    for k, (d, x, y) in enumerate(picked):
        letter = "ABC"[k]
        on = sorted(b["id"] for g, b in allb if g.contains(shapely.Point(x, y)))
        q = [{"code": "not_a_land_plot", "text": "Гипотетическая точка для сравнения, а не свободный или утверждённый участок; статус земли и стоимость неизвестны."}]
        if on:
            q.append({"code": "on_existing_building_footprint", "text": f"Точка попадает на контур существующего здания ({on[0][:13]}…): как место строительства не проверена."})
        candidates.append({"id": f"ast-hyp-{letter.lower()}", "label": f"Гипотеза {letter}: точка для сравнения (не участок)", "lon": x, "lat": y, "kind": "hypothesis", "source_ids": [],
                           "field_provenance": {"coordinates": {"method": "центр ячейки сетки 10×10 участка не далее 300 м от точки анализа, с наибольшим расстоянием по прямой до ближайшей школы known_public; не ближе 50 м к школе; точки не ближе 600 м друг к другу; правило K10",
                                                                "nearest_known_public_m_at_selection": m1(d)}, "cost": {"value": None, "verification_status": "not_fetched"}, "land_status": {"value": "unknown", "verification_status": "not_fetched"}},
                           "qa": sorted(q, key=lambda t: t["code"]), "cost": None, "land_status": "unknown"})

    assumptions = [
        {"id": "A-realm", "text": "Реальный участок Астаны по открытым вторичным данным. Не учебная модель 52.56 и не synthetic demo: числа отсюда не переносятся в учебный Score."},
        {"id": "A-data", "text": f"Школы — OSM (через Overture {RELEASE}) и POI Overture/Meta. Официальный перечень (eGov, управление образования) из среды подготовки не открыт — NOT_FETCHED. Наличие записи не подтверждает работу школы."},
        {"id": "A-eligibility", "text": "known_public — вывод K10: геометрия школы в OSM и номерное название общеобразовательной школы. Это не официальное подтверждение; закрепление территорий и правила приёма не проверены. Специальные, для одарённых, частные/международные и вечерние школы — known_restricted по названию; прочие — unknown."},
        {"id": "A-point", "text": "Точка школы — центр участка школы или здания в OSM либо точка POI; не вход и не калитка."},
        {"id": "A-origins", "text": "Точки анализа — центры жилых зданий OSM: по одному самому крупному в каждой ячейке сетки 5×5 участка, равные веса. Это не жители, не дети и не численность; неклассифицированные здания OSM в выбор не входят."},
        {"id": "A-candidates", "text": "Гипотезы A/B/C — точки, выбранные правилом K10 для сравнения; не участки, не проекты, стоимость и статус земли неизвестны."},
        {"id": "A-buffer", "text": f"Школы включены в участок и буфер {B} м. D = {D:.0f} м — наибольшее расстояние по прямой от точки сетки {GRID_M} м внутри участка до ближайшей школы known_public; B = ceil100({DETOUR_F}·D). Множитель {DETOUR_F} — допущение об обходе по улицам, не измерение: если пешеходный маршрут до ближайшей школы длиннее B, буфер недостаточен и нужен новый срез."},
        {"id": "A-method", "text": f"Метод по умолчанию — расстояние по прямой (geodesic), без улиц. Порог {THRESHOLD_M} м — пользовательский параметр, не норматив."},
        {"id": "A-capacity", "text": "Вместимость, наполненность и дефицит мест неизвестны: результат описывает только пространственную близость к известным школам."},
    ]
    case = {"schema_version": KC.SCHEMA, "case_id": "astana-school-access-k10-r10-v1", "city_id": "astana",
            "title": "Астана: близость к известным школам в участке ≈2×2 км (открытые данные OSM/Overture, не официальный реестр)",
            "bbox": BBOX, "snapshot_id": f"astana-ov{RELEASE}-app{CODE_SHA[:7]}-bbox-r17c7-buf{B}m-k10r10",
            "sources": sources, "schools": case_schools, "origins": origins, "candidates": candidates, "selected_candidate_ids": [],
            "parameters": {"distance_method": "geodesic", "routing_policy_id": None, "threshold_m": THRESHOLD_M, "max_new_objects": 1},
            "model_assumptions": assumptions}
    summary = KC.validate_case(case, max_school_buffer_m=B)

    # ---------- evidence statements ----------
    ev = []
    for p in pkg_schools:
        ev.append({"id": f"ev-{p['id']}-geom", "subject_id": p["id"], "field": "coordinates", "value": [p["lon"], p["lat"]], "source_id": p["field_provenance"]["coordinates"]["source_id"],
                   "record": p["field_provenance"]["coordinates"]["record"], "kind": "observed_secondary", "method": p["field_provenance"]["coordinates"]["method"]})
        ev.append({"id": f"ev-{p['id']}-name", "subject_id": p["id"], "field": "label", "value": p["label"], "source_id": p["field_provenance"]["label"]["source_id"],
                   "record": p["field_provenance"]["label"]["record"], "kind": "observed_secondary", "method": p["field_provenance"]["label"]["field"]})
        ev.append({"id": f"ev-{p['id']}-eligibility", "subject_id": p["id"], "field": "access_eligibility", "value": p["access_eligibility"], "source_id": None, "record": None,
                   "kind": "derived", "method": p["field_provenance"]["access_eligibility"]["method"]})
        for c in p["field_provenance"]["corroboration"]:
            ev.append({"id": f"ev-{p['id']}-corr-{c['record'][:13]}", "subject_id": p["id"], "field": "existence", "value": c.get("distance_m", c.get("relation")), "source_id": c["source_id"],
                       "record": c["record"], "kind": "observed_secondary", "method": "independent layer agrees (distance m or relation)"})
        for c in p["conflicts"]:
            ev.append({"id": f"ev-{p['id']}-conflict-{c['record_id'][:8]}", "subject_id": p["id"], "field": "location", "value": c["distance_m"], "source_id": SRC["places"],
                       "record": c["record_id"], "kind": "observed_secondary", "method": "conflicting POI: " + c["reason"][:200]})
    for lid in (SRC["lead8a"], SRC["lead8b"], SRC["leadagis"]):
        ev.append({"id": f"ev-lead-{lid}", "subject_id": None, "field": "lead", "value": by_src[lid]["title"], "source_id": lid, "record": None, "kind": "lead_not_fetched",
                   "method": "search result title/URL only; page not opened; not used as a fact"})
    ev.append({"id": "ev-buffer-D", "subject_id": None, "field": "buffer", "value": {"D_m": m1(D), "at": at, "B_m": B, "detour_assumption": DETOUR_F, "grid_m": GRID_M, "targets_known_public": len(pub)},
               "source_id": None, "record": None, "kind": "derived", "method": "spherical distance (k10case.haversine_m) from grid points of the bbox to the nearest known_public school"})
    ev.sort(key=lambda x: x["id"])

    # ---------- match review ----------
    osm_rows = []
    for eid, e in sorted(ents.items()):
        if e["origin"] == "meta_poi":
            continue
        d = KC.dist_to_bbox_m(e["lon"], e["lat"], BBOX)
        osm_rows.append({"layer": "osm_grounds" if e["origin"] == "osm_grounds" else "osm_building", "record_id": e["ref"], "entity": eid, "name": e["names"]["osm_ru"] or e["names"]["osm"],
                         "distance_to_bbox_m": m1(d), "within_package_buffer": d <= B, "in_app_slice": False,
                         "app_slice_has_poi": any(m["record_id"] in slice_ids for m in e["meta"]),
                         "decision": "include" if d <= B else "outside_buffer", "decided_by": e["rule"], "category": e["category"], "access_eligibility": e["eligibility"],
                         "poi_attached": [m["record_id"] for m in e["meta"]], "conflicts": [c["record_id"] for c in e["conflicts"]]})
    for r in excluded_osm:
        lon, lat = r.pop("lonlat")
        r["distance_to_bbox_m"] = m1(KC.dist_to_bbox_m(lon, lat, BBOX))
        r["within_package_buffer"] = r["distance_to_bbox_m"] <= B
        osm_rows.append(r)
    in_bbox_osm = [r for r in osm_rows if r["distance_to_bbox_m"] == 0 and r["decision"] == "include"]
    mr = {"schema": "k10-match-review-v1", "city_id": "astana", "bbox": BBOX, "package_buffer_m": B,
          "summary": {"app_slice_school_records": len(slice_ids),
                      "app_slice_decisions": {k: sum(1 for r in rows if r["in_app_slice"] and r["decision"] == k) for k in sorted({r["decision"] for r in rows if r["in_app_slice"]})},
                      "osm_school_entities_in_bbox": len(in_bbox_osm),
                      "osm_school_entities_in_bbox_missing_from_app_slice": sorted(r["entity"] for r in in_bbox_osm if not r["app_slice_has_poi"]),
                      "osm_records_excluded_as_not_school": sorted(r["record_id"] for r in excluded_osm),
                      "package_schools": len(case_schools), "package_schools_by_eligibility": summary["eligibility"],
                      "poi_records_reviewed_within_buffer": sum(1 for r in rows if r["within_package_buffer"]),
                      "unresolved_or_excluded_within_buffer": sum(1 for r in rows if r["within_package_buffer"] and r["decision"] in ("unresolved_excluded", "not_school")),
                      "verified_against_official_source": 0},
          "note": "Desk matching of independent secondary layers (OSM via Overture vs Overture/Meta POI) plus NOT_FETCHED official targets. 0 records are verified against an official source; the count of valid JSON records is not a count of verified schools.",
          "poi_records": sorted(rows, key=lambda r: (not r["in_app_slice"], r["distance_to_bbox_m"], r["record_id"])),
          "osm_entities": sorted(osm_rows, key=lambda r: (r["distance_to_bbox_m"], r["record_id"]))}

    files = {
        "sources.json": {"schema": "k10-sources-v1", "city_id": "astana", "sources": sources, "access_log": "sources/access_log.json"},
        "schools.json": {"schema": "k10-schools-v1", "city_id": "astana", "bbox": BBOX, "package_buffer_m": B, "realm": "real Astana, observed_secondary (not 52.56 training model, not synthetic)", "schools": pkg_schools},
        "evidence.json": {"schema": "k10-evidence-v1", "city_id": "astana", "statements": ev},
        "match-review.json": mr,
        "astana.case.json": case,
    }
    for name, obj in files.items():
        (out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    manifest = {"schema": "k10-package-manifest-v1", "generator": "research/round-10-results/K10/scripts/build_astana_package.py", "code_base_sha": CODE_SHA, "overture_release": RELEASE,
                "inputs": prov_in["outputs"], "review_decisions_sha256": sha(K / "review/review_decisions.json"),
                "outputs": {n: sha(out / n) for n in files}, "case_digest_k10": KC.case_digest_k10(case), "case_digest_note": "k10-canon-v1 proposal; BUILD's canonical case_digest is authoritative",
                "buffer": {"D_m": m1(D), "D_at": at, "B_m": B, "detour_assumption": DETOUR_F, "grid_m": GRID_M}, "validation": summary,
                "origins": {"count": len(origins), "empty_grid_cells": empty_cells}, "candidates": [c["id"] for c in candidates]}
    (out / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"schools": len(case_schools), "eligibility": summary["eligibility"], "origins": len(origins), "candidates": len(candidates), "B_m": B, "D_m": m1(D),
                      "digest": manifest["case_digest_k10"][:16]}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
