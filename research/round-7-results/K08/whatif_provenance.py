"""K08 R7: эталон полей происхождения для сценария city-whatif-v1 и карточки результата.

Не интегрирован в прототип: отдельный модуль по FEATURE_SPEC. Только stdlib, без сети.
Читает из --app-root (извлечённая prototypes/city-evidence):
  web/data.js                        — записи мест, bbox, release, attribution (observed_secondary)
  web/evidence.js                    — QA-метки сборки (derived)
  inputs/k10/package_manifest.json   — sha256/bytes файла мест (для source_snapshot)
  inputs/k10/<path места>            — сам файл: его sha256 сверяется с manifest

Usage:
  python whatif_provenance.py --app-root DIR snapshot CITY
  python whatif_provenance.py --app-root DIR card SCENARIO.json [--out CARD.json]
"""
import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

SCHEMA = "city-whatif-v1"
CITIES = ("shymkent", "astana")
CATEGORIES = ("school", "outpatient_clinic")
R_EARTH = 6371008.8
CALC = {"method": "haversine", "earth_radius_m": R_EARTH, "input_order": "[longitude,latitude]",
        "clamp": [0, 1], "rounding": "только при выводе"}
MAX_POINTS, MAX_ID, MAX_BYTES = 10, 64, 256 * 1024
ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,%d}$" % MAX_ID)
LIMITATIONS = [
    "Расстояние по прямой (гаверсинус), не путь по улицам и не время в пути.",
    "База — записи Overture внутри сохранённого квадрата; ближайшая запись в срезе не обязательно ближайшее учреждение в городе.",
    "Срез неполон: отсутствие записи не означает отсутствие учреждения; ошибки координат могут менять результат.",
    "QA-флаги — правила сборки; запись с флагом не удаляется, запись без флага не считается проверенной.",
    "Контрольная точка — выбранное место, не дом с известным населением; население и мощность учреждений не учитываются.",
    "Условный объект — гипотеза пользователя; сценарий не доказывает пользу строительства и не является решением акимата.",
]
STATUS_TEXT = "Гипотетический сценарий. Не решение акимата и не доказательство пользы строительства"
NO_BASE_TEXT = "В срезе нет исходных записей; улучшение не вычисляется"


class ScenarioError(ValueError):
    pass


def load_window_json(path, var):
    txt = Path(path).read_text(encoding="utf-8")
    m = re.search(r"window\.%s\s*=\s*(\{.*\})\s*;?\s*$" % var, txt, re.S)
    if not m:
        raise ScenarioError(f"{path}: нет window.{var}")
    return json.loads(m.group(1))


class App:
    def __init__(self, root):
        self.root = Path(root)
        self.data = load_window_json(self.root / "web/data.js", "CITY_EVIDENCE")
        ev = self.root / "web/evidence.js"
        self.obs = load_window_json(ev, "CITY_OBS") if ev.exists() else None
        self.manifest = json.loads((self.root / "inputs/k10/package_manifest.json").read_text(encoding="utf-8"))

    def city(self, city_id):
        return self.data["cities"][city_id]

    def places_file(self, city_id):
        f = self.manifest["cities"][city_id]["files"]["places_social"]
        p = self.root / "inputs/k10" / f["path"]
        b = p.read_bytes()
        actual = hashlib.sha256(b).hexdigest()
        if actual != f["sha256"] or len(b) != f["bytes"]:
            raise ScenarioError(f"{city_id}: файл мест не совпадает с package_manifest.json (sha256/bytes)")
        return f, actual

    def snapshot(self, city_id):
        """Отпечаток среза: из фактических байтов файла мест (сверенных с manifest) и параметров расчёта."""
        c = self.city(city_id)
        f, actual = self.places_file(city_id)
        basis = {"schema_version": SCHEMA, "city_id": city_id, "release": c["release"], "bbox": c["bbox"],
                 "places_file": {"path": f["path"], "sha256": actual, "bytes": f["bytes"]},
                 "package_sha": self.data["inputs"].get("k10_sha"), "calc": CALC}
        canon = json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest(), basis

    def qa(self, city_id, rec_id):
        if not self.obs:
            return {"available": False}
        q = self.obs["cities"][city_id]["qa"]
        flags = []
        if rec_id in q.get("category_doubt", {}):
            flags.append({"rule": q["category_doubt"][rec_id]["rule"], "reason": q["category_doubt"][rec_id]["reason"]})
        for d in q.get("possible_duplicates", []):
            if rec_id in (d.get("a"), d.get("b")):
                flags.append({"rule": "possible_duplicate:" + d.get("rule", ""), "other": d["b"] if d.get("a") == rec_id else d["a"],
                              "distance_m": d.get("distance_m")})
        for g in q.get("colocated", []):
            ids = g.get("ids") if isinstance(g, dict) else g
            if ids and rec_id in ids:
                flags.append({"rule": "colocated"})
        return {"available": True, "flags": flags,
                "note": "нет флагов ≠ проверено" if not flags else "запись не удалена и не переклассифицирована"}


def haversine_m(a, b):
    """a, b — [lon, lat] в градусах. Без округления."""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    h = min(1.0, max(0.0, h))
    return 2 * R_EARTH * math.asin(math.sqrt(h))


def _finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _reject_constants(tok):
    raise ScenarioError(f"недопустимое число {tok}")


def loads_strict(text):
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ScenarioError("JSON больше 256 KiB")

    def no_dups(pairs):
        keys = [k for k, _ in pairs]
        if len(keys) != len(set(keys)):
            raise ScenarioError("дубликат ключа")
        return dict(pairs)
    obj = json.loads(text, parse_constant=_reject_constants, object_pairs_hook=no_dups,
                     parse_float=lambda s: _chk_float(s))
    return obj


def _chk_float(s):
    v = float(s)
    if not math.isfinite(v):
        raise ScenarioError(f"недопустимое число {s}")
    return v


def validate(app, sc):
    """Строгая проверка полей контракта. Поля report/distances из импорта игнорируются (пересчёт)."""
    if not isinstance(sc, dict):
        raise ScenarioError("сценарий должен быть объектом")
    if sc.get("schema_version") != SCHEMA:
        raise ScenarioError("неизвестная schema_version")
    city = sc.get("city_id")
    if city not in CITIES:
        raise ScenarioError("неизвестный город")
    if sc.get("category") not in CATEGORIES:
        raise ScenarioError("неизвестная категория")
    snap, _ = app.snapshot(city)
    if sc.get("source_snapshot") != snap:
        raise ScenarioError("чужой source_snapshot: сценарий построен на другом срезе")
    bb = app.city(city)["bbox"]

    def point(p, what):
        if not isinstance(p, dict) or not isinstance(p.get("id"), str) or not ID_RE.match(p["id"]):
            raise ScenarioError(f"{what}: неверный id")
        if not (_finite(p.get("lon")) and _finite(p.get("lat"))):
            raise ScenarioError(f"{what} {p['id']}: координаты не конечные числа")
        if not (bb[0] <= p["lon"] <= bb[2] and bb[1] <= p["lat"] <= bb[3]):
            raise ScenarioError(f"{what} {p['id']}: вне квадрата среза — точка отклонена")
    cps = sc.get("control_points")
    if not isinstance(cps, list) or not 1 <= len(cps) <= MAX_POINTS:
        raise ScenarioError("контрольных точек должно быть 1..10")
    for p in cps:
        point(p, "контрольная точка")
    ids = [p["id"] for p in cps]
    po = sc.get("proposed_object")
    if isinstance(po, list):
        raise ScenarioError("проектный объект может быть только один")
    if po is not None:
        point(po, "проектный объект")
        if po.get("kind") != "hypothetical" or po.get("category") != sc["category"]:
            raise ScenarioError("проектный объект: kind=hypothetical и category = категории сценария")
        ids.append(po["id"])
    if len(ids) != len(set(ids)):
        raise ScenarioError("дубликаты id")
    return snap


def _nearest(target, recs):
    best = None
    for r in sorted(recs, key=lambda r: r["id"]):  # стабильная ничья по ID
        d = haversine_m(target, [r["lon"], r["lat"]])
        if best is None or d < best[0]:
            best = (d, r)
    return best


def _rec_view(app, city, r):
    return {"kind": "source_record", "id": r["id"], "name": r.get("name"), "category": r.get("category"),
            "lon": r["lon"], "lat": r["lat"], "confidence": r.get("confidence"), "overture_version": r.get("overture_version"),
            "sources": r.get("sources"), "qa": app.qa(city, r["id"])}


def build_card(app, sc):
    snap = validate(app, sc)
    city, cat = sc["city_id"], sc["category"]
    c = app.city(city)
    recs = [p for p in c["places"] if p["group"] == cat]
    po = sc.get("proposed_object")
    f, actual = app.places_file(city)
    rows = []
    for cp in sc["control_points"]:
        t = [cp["lon"], cp["lat"]]
        nb = _nearest(t, recs)
        before = nb[0] if nb else None
        dp = haversine_m(t, [po["lon"], po["lat"]]) if po else None
        if po is None:
            after, nearest = before, (_rec_view(app, city, nb[1]) if nb else {"kind": "none"})
        elif before is None:
            after, nearest = dp, {"kind": "proposed_object", "id": po["id"], "lon": po["lon"], "lat": po["lat"]}
        else:
            # ничья проект/исходная запись: длина одинакова; выбор по ID для стабильности
            use_po = dp < before or (dp == before and po["id"] < nb[1]["id"])
            after = min(before, dp)
            nearest = ({"kind": "proposed_object", "id": po["id"], "lon": po["lon"], "lat": po["lat"]} if use_po
                       else _rec_view(app, city, nb[1]))
        delta = (before - after) if (before is not None and after is not None) else None
        rows.append({"control_point": {"id": cp["id"], "lon": cp["lon"], "lat": cp["lat"]},
                     "before_m": before, "after_m": after, "delta_m": delta,
                     "nearest_before": _rec_view(app, city, nb[1]) if nb else {"kind": "none"},
                     "nearest": nearest,
                     "note": NO_BASE_TEXT if before is None else None})
    return {
        "card_schema": "k08-r7-whatif-card/v1 (выводимое представление city-whatif-v1; при импорте не принимается)",
        "scenario": {"schema_version": SCHEMA, "city_id": city, "category": cat, "status": STATUS_TEXT,
                     "proposed_object": po},
        "source": {"snapshot": snap, "release": c["release"], "retrieved_utc": c.get("retrieved_utc"),
                   "package": f"{app.data['inputs'].get('k10_branch')}@{app.data['inputs'].get('k10_sha')}",
                   "places_file": f["path"], "places_file_sha256": actual},
        "scope": {"bbox": c["bbox"], "records_in_slice": len(recs), "statement": "Срез — не полный реестр города"},
        "rows": rows,
        "attribution": c.get("attribution"),
        "calc": CALC,
        "limitations": LIMITATIONS,
        "field_classes": "provenance_fields.json",
    }


def fmt_m(x):
    return "—" if x is None else f"{x:,.0f}".replace(",", " ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("snapshot"); s1.add_argument("city")
    s2 = sub.add_parser("card"); s2.add_argument("scenario"); s2.add_argument("--out")
    a = ap.parse_args()
    app = App(a.app_root)
    try:
        if a.cmd == "snapshot":
            snap, basis = app.snapshot(a.city)
            print(json.dumps({"source_snapshot": snap, "basis": basis}, ensure_ascii=False, indent=1))
            return 0
        sc = loads_strict(Path(a.scenario).read_text(encoding="utf-8"))
        card = build_card(app, sc)
    except ScenarioError as e:
        print(f"ОТКЛОНЕНО: {e}", file=sys.stderr)
        return 2
    out = json.dumps(card, ensure_ascii=False, indent=1, allow_nan=False)
    if a.out:
        Path(a.out).write_text(out + "\n", encoding="utf-8")
    for r in card["rows"]:
        n = r["nearest"]
        print(f"{r['control_point']['id']}: до {fmt_m(r['before_m'])} м, после {fmt_m(r['after_m'])} м, "
              f"разница {fmt_m(r['delta_m'])} м; ближайшая: {n.get('kind')} {n.get('name') or n.get('id', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
