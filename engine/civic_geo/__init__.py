"""R12 · точность карты: привязка к улицам и объектам OSM (только стандартная библиотека).

Главное для соседей:
    targets(lon, lat, category)        -> {"candidates": [...]}  кандидаты привязки жалобы (CONTRACT §4, §7)
    target_geometry({"kind", "id"})    -> {"geometry", "label_ru", "label_kk", "approximate"} | None  (R07, R08)
    street_segment(graph, a, b)        -> участок улицы по рёбрам графа
    api.handle(path, query)            -> (код, тело) для маршрутов /api/civic/v2/... (подключает R01)
Подробности — engine/civic_geo/README.md.
"""
from __future__ import annotations

from .api import geo_status, objects_near, segment_between, street_snap, yard_at  # noqa: F401
from .targets import targets  # noqa: F401  (шлюз R01: targets(lon, lat, category=None))


def seed_world(db_path=None, records=None, now=None) -> dict:
    """Демо-мир R02 (CONTRACT §11): R01 зовёт с уже материализованным миром и одним now на все модули.
    R12 записей не хранит — запоминает работы и задуманные конфликты для «Календаря работ» (works_calendar)."""
    from .works_calendar import remember_world
    return remember_world(records, now)


def target_geometry(target: dict) -> dict | None:
    """Форма и подпись цели по её id: объект OSM, ребро графа, двор или ячейка. None — цель неизвестна."""
    from . import geo
    from .graph import get_graph
    from .objects import get_layers
    from .targets import _street_near, cell_target, object_target, segment_street, segment_target, yard_target

    kind, tid = (target or {}).get("kind"), str((target or {}).get("id") or "")
    if not tid:
        return None
    objects, yards, cells = get_layers()
    if kind == "object" or tid.startswith("osm-node-") or tid.startswith("osm-way-") or tid.startswith("osm-relation-"):
        f = objects.find(tid)  # и выбывший узел старого снимка OSM: старые ссылки находятся (R10 B-103)
        if f is None:
            return None
        t = object_target(f)
        g = {"type": "Polygon", "coordinates": f.polygon} if f.polygon else {"type": "Point", "coordinates": geo.round_coord(f.point)}
        out = {"geometry": g, "point": geo.round_coord(f.point), "label_ru": t["label_ru"], "label_kk": t["label_kk"],
               "object_kind": f.kind, "approximate": False}
        if f.raw.get("retired"):
            out["retired"] = True
            if f.raw.get("replaced_by"):
                out["replaced_by"] = f.raw["replaced_by"]
        return out
    if tid.startswith("yard-"):
        f = yards.by_id.get(tid)
        if f is None:
            return None
        t = yard_target(f, _street_near(get_graph(), f.point))
        return {"geometry": {"type": "Polygon", "coordinates": f.polygon}, "point": f.point,
                "label_ru": t["label_ru"], "label_kk": t["label_kk"], "approximate": False}
    if tid.startswith("cell-"):
        try:
            poly = cells.polygon(tid)
        except ValueError:
            return None
        center = cells.center(tid)
        t = cell_target(tid, _street_near(get_graph(), center))
        return {"geometry": {"type": "Polygon", "coordinates": poly}, "point": center,
                "label_ru": t["label_ru"], "label_kk": t["label_kk"], "approximate": True}
    if kind == "segment" or tid.startswith("osm-w"):
        e = get_graph().by_id.get(tid)
        if e is None:
            return None
        t = segment_target(e, segment_street(get_graph(), e))
        coords = [geo.round_coord(c) for c in e.geometry]
        return {"geometry": {"type": "LineString", "coordinates": coords}, "point": coords[len(coords) // 2],
                "label_ru": t["label_ru"], "label_kk": t["label_kk"], "approximate": False}
    return None


# ---------- QR-паспорт объекта (POLISH_WAVE_2 п. 6): /?report=<target_id> ----------
import re as _re

# Только эти формы id попадают в ссылку и на табличку (защита от подмены: ничего, кроме id цели).
REPORT_ID_RE = _re.compile(r"^(osm-(node|way|relation)-[0-9]{1,15}|osm-w[0-9]{1,15}-[0-9]{1,6}|"
                           r"yard-r?[0-9]{1,15}(-[0-9]{1,3})?|cell--?[0-9]{1,6}--?[0-9]{1,6})$")


def target_kind(target_id: str) -> str | None:
    """Вид цели по id: object / segment / area; None — не id цели."""
    if not isinstance(target_id, str) or not REPORT_ID_RE.match(target_id):
        return None
    if target_id.startswith("osm-w"):
        return "segment"
    if target_id.startswith(("yard-", "cell-")):
        return "area"
    return "object"


def object_number(target_id: str) -> str:
    """Номер объекта на табличке: цифры id OSM («10185771782», «693873790-4»); двор — «Д-…», ячейка — «К-…»."""
    if target_id.startswith("osm-w"):
        return target_id[len("osm-w"):]
    if target_id.startswith("osm-"):
        return target_id.split("-", 2)[2]
    if target_id.startswith("yard-"):
        return "Д-" + target_id[len("yard-"):]
    return "К-" + target_id[len("cell-"):]


def target_info(target_id: str) -> dict:
    """Карточка цели для QR-паспорта: {target:{kind,id,label_ru,label_kk,object_kind?}, number, point, geometry,
    approximate, street?:{ru,kk}}. Неизвестный id — исключение со status 404 (шлюз R01 отвечает 404), неверный — 400."""
    from .targets import TargetError

    kind = target_kind(target_id)
    if kind is None:
        raise TargetError("bad_target_id", "Неверный номер объекта в ссылке.")
    got = target_geometry({"kind": kind, "id": target_id})
    if not got:
        err = TargetError("target_not_found", "Объект не найден. Возможно, ссылка или QR-код устарели.")
        err.status = 404
        raise err
    target = {"kind": kind, "id": target_id, "label_ru": got["label_ru"], "label_kk": got["label_kk"]}
    if got.get("object_kind"):
        target["object_kind"] = got["object_kind"]
    out = {"target": target, "number": object_number(target_id), "point": got.get("point"),
           "geometry": got["geometry"], "approximate": bool(got.get("approximate"))}
    if got.get("retired"):  # узла нет в свежем снимке OSM; replaced_by — свежий узел того же вида рядом (B-103)
        out["retired"] = True
        if got.get("replaced_by"):
            out["replaced_by"] = got["replaced_by"]
    street = _info_street(kind, got)
    if street:
        out["street"] = street
    return out


def _info_street(kind: str, got: dict) -> dict | None:
    """Улица рядом для подписи карточки (эталон A: «Остановки и транспорт · пр. Туран»): ближайшая улица с названием
    в 150 м; только если её ещё нет в названии (у светофора, перехода, участка, «Двор — улица» она уже там)."""
    from . import names
    from .graph import get_graph
    from .targets import LABEL_STREET_RADIUS_M, STREET_POINT_KINDS

    if kind == "segment" or got.get("object_kind") in STREET_POINT_KINDS or not got.get("point"):
        return None
    # Только проезжие улицы (у парка ближайшая «улица» — лыжероллерная трасса или аллея — подписи не помогает).
    s_ru = s_kk = None
    for _, e, _ in get_graph().nearest(got["point"], LABEL_STREET_RADIUS_M, accept=lambda e: bool(e.name) and e.group == "road"):
        s_ru, s_kk = e.name, e.label_kk()
        break
    if not s_ru or s_ru in got["label_ru"] or (s_kk and s_kk in (got.get("label_kk") or "")):
        return None
    return {"ru": names.ru_short(s_ru), "kk": s_kk or s_ru}
