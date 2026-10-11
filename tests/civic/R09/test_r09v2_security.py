"""R09 раунд 14 (ночь): находки ревью безопасности R15 по жалобам v2 — S03, S04, S05, S06, S12.

Каждый тест воспроизводит находку R15 (SECURITY_REVIEW.md, ветка claude/r14-R15) и проверяет исправление.
Карта R12 подменяется функцией lookup с тем же контрактом, что engine.civic_geo.target_geometry:
lookup({"kind", "id"}) -> {"geometry", "label_ru", "label_kk", "approximate"} | None.
"""

import json
import sys
import types

import pytest

from ui.civic_feedback.v2 import ComplaintStore, ComplaintsV2Service, record as rec
from ui.civic_feedback.v2.integration import geo_target_lookup, make_service

P = "/api/civic/v2"
DEV_A = "dev-aaaaaaaaaaaaaaaa"
DEV_B = "dev-bbbbbbbbbbbbbbbb"
POINT = [71.413512, 51.091537]                      # точка жителя (6 знаков, как присылает телефон)
STOP_ID = "osm-node-123456"
MAP = {  # «карта R12»: остановка в ~20 м от точки, парк-многоугольник вокруг точки, далёкая остановка в ~10 км
    STOP_ID: {"geometry": {"type": "Point", "coordinates": [71.4138, 51.0915]},
              "label_ru": "Остановка «Нура»", "label_kk": "«Нұра» аялдамасы", "approximate": False},
    "osm-way-777": {"geometry": {"type": "Polygon", "coordinates": [[[71.410, 51.089], [71.417, 51.089],
                                                                    [71.417, 51.094], [71.410, 51.094],
                                                                    [71.410, 51.089]]]},
                    "label_ru": "Парк «Тест»", "label_kk": "«Тест» саябағы", "approximate": False},
    "osm-node-999": {"geometry": {"type": "Point", "coordinates": [71.55, 51.10]},
                     "label_ru": "Остановка «Далеко»", "label_kk": "«Алыс» аялдамасы", "approximate": False},
}


def lookup(target):
    return MAP.get(target["id"])


class Staff:
    is_staff = True
    username = "operator1"

    def check_csrf(self, value):
        return value == "tok"


class StaffWithoutCsrf:
    """Будущий формат сессии без check_csrf (R15 S05)."""
    is_staff = True
    username = "operator2"


def ctx(device=DEV_A, csrf=None):
    headers = {"X-Birge-Device": device}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return {"headers": headers, "host_allowed": True, "is_same_origin": True}


@pytest.fixture
def api(tmp_path):
    store = ComplaintStore(tmp_path / "s.sqlite3")
    store.target_lookup = lookup
    yield ComplaintsV2Service(store)
    store.close()


def call(api, method, path, body=None, principal=None, context=None, query=None):
    raw = json.dumps(body).encode() if body is not None else None
    reply = api.handle(method, P + path, query, raw, principal, context or ctx())
    return reply["status"], reply["body"]


def create(api, target, device=DEV_A, point=POINT):
    return call(api, "POST", "/complaints", {"text": "Не убран снег на остановке", "category": "snow_ice",
                                             "point": point, "target": target}, context=ctx(device))


# ---- S03: другим жителям — точка не точнее 3 знаков; автору — точно ----

def test_s03_public_views_coarsen_the_point_author_sees_exact(api):
    _, body = create(api, {"kind": "object", "id": STOP_ID})
    mine = body["data"]["complaint"]
    assert mine["point"] == POINT                                     # автору — своё место точно
    cid = mine["id"]
    _, other = call(api, "GET", "/complaints/" + cid, context=ctx(DEV_B))
    _, listing = call(api, "GET", "/complaints", query="bbox=71.3,51.0,71.5,51.2", context=ctx(DEV_B))
    _, metoo = call(api, "POST", f"/complaints/{cid}/metoo", {}, context=ctx(DEV_B))
    _, mine_b = call(api, "GET", "/complaints/mine", context=ctx(DEV_B))
    coarse = [round(POINT[0], 3), round(POINT[1], 3)]
    for view in (other["data"]["complaint"], listing["data"]["items"][0], metoo["data"]["complaint"],
                 mine_b["data"]["items"][0]):
        assert view["point"] == coarse, view["point"]
    assert "413512" not in json.dumps([other, listing, metoo, mine_b])
    _, staff = call(api, "GET", "/complaints", principal=Staff(), context=ctx(csrf="tok"))
    assert staff["data"]["items"][0]["point"] == POINT                # сотруднику — точно (выезд на место)
    stored = api.store.list()[0]
    assert stored["point"] == POINT                                   # карта R07 берёт записи хранилища целиком


# ---- S04: подписи цели — только с карты, не из запроса ----

def test_s04_label_from_request_is_never_stored(api):
    _, body = create(api, {"kind": "object", "id": STOP_ID, "label_ru": "Акимат берёт взятки",
                           "label_kk": "Пара алады"})
    target = body["data"]["complaint"]["target"]
    assert target["label_ru"] == "Остановка «Нура»" and target["label_kk"] == "«Нұра» аялдамасы"
    assert "взятки" not in json.dumps(api.store.list())


def test_s04_without_map_labels_from_request_are_dropped(tmp_path):
    store = ComplaintStore(tmp_path / "n.sqlite3")             # R09 один, без R12: target_lookup = None
    api = ComplaintsV2Service(store)
    _, body = create(api, {"kind": "object", "id": STOP_ID, "label_ru": "Акимат берёт взятки"})
    target = body["data"]["complaint"]["target"]
    assert target == {"kind": "object", "id": STOP_ID}
    store.close()


# ---- S12: цель не дальше 300 м от точки и известна карте ----

@pytest.mark.parametrize("target", [
    {"kind": "object", "id": "osm-node-999"},                         # ~10 км от точки
    {"kind": "object", "id": "osm-node-404404"},                      # карте неизвестна
    {"kind": "area", "id": "cell-500-500", "approximate": True},      # чужая ячейка далеко
])
def test_s12_far_or_unknown_target_becomes_approximate_place_at_the_point(api, target):
    _, body = create(api, target)
    saved = body["data"]["complaint"]["target"]
    assert saved == rec.cell_target(*POINT)
    assert saved["approximate"] is True


def test_s12_inside_area_and_near_object_are_kept(api):
    _, park = create(api, {"kind": "object", "id": "osm-way-777"})
    assert park["data"]["complaint"]["target"]["id"] == "osm-way-777"          # точка внутри парка: 0 м
    _, stop = create(api, {"kind": "object", "id": STOP_ID}, device=DEV_B)
    assert stop["data"]["complaint"]["target"]["label_ru"] == "Остановка «Нура»"


def test_s12_neighbour_cell_without_map_is_checked_by_r09_grid(tmp_path):
    store = ComplaintStore(tmp_path / "c.sqlite3")
    own = rec.cell_target(*POINT)["id"]
    col, row = (int(x) for x in own.split("-")[1:])
    near = {"kind": "area", "id": f"cell-{col + 1}-{row}", "approximate": True}
    far = {"kind": "area", "id": f"cell-{col + 40}-{row}", "approximate": True}
    api = ComplaintsV2Service(store)
    _, a = create(api, near)
    _, b = create(api, far, device=DEV_B)
    assert a["data"]["complaint"]["target"]["id"] == near["id"]
    assert b["data"]["complaint"]["target"]["id"] == own
    store.close()


def test_s12_broken_map_answer_does_not_lose_the_complaint(api):
    def broken(target):
        if target["id"] == "osm-node-1":
            raise RuntimeError("граф не загрузился")
        return {"geometry": {"type": "Polygon", "coordinates": "мусор"}}
    api.store.target_lookup = broken
    for tid in ("osm-node-1", "osm-node-2"):
        status, body = create(api, {"kind": "object", "id": tid})
        assert status == 201 and body["data"]["complaint"]["target"]["approximate"] is True


@pytest.mark.parametrize("geometry,expected", [
    ({"type": "Point", "coordinates": [71.4138, 51.0915]}, (15, 30)),
    ({"type": "LineString", "coordinates": [[71.40, 51.0920], [71.42, 51.0920]]}, (45, 60)),
    ({"type": "MultiPolygon", "coordinates": [[[[71.40, 51.00], [71.41, 51.00], [71.41, 51.01], [71.40, 51.00]]],
                                              [[[71.41, 51.09], [71.42, 51.09], [71.42, 51.095], [71.41, 51.095],
                                                [71.41, 51.09]]]]}, (0, 0)),
    ({"type": "GeometryCollection", "coordinates": []}, None),
])
def test_distance_to_geometry(geometry, expected):
    d = rec.distance_to_geometry_m(POINT, geometry)
    if expected is None:
        assert d is None
    else:
        assert expected[0] <= d <= expected[1], d


# ---- S05: сотрудник без проверки CSRF -> отказ ----

def test_s05_principal_without_csrf_check_is_refused(api):
    _, body = create(api, {"kind": "object", "id": STOP_ID})
    cid = body["data"]["complaint"]["id"]
    status, err = call(api, "POST", f"/complaints/{cid}/status", {"status": "accepted"},
                       principal=StaffWithoutCsrf(), context=ctx(csrf="tok"))
    assert status == 403 and err["error"]["code"] == "csrf_failed"
    status, _ = call(api, "POST", f"/complaints/{cid}/status", {"status": "accepted"},
                     principal=Staff(), context=ctx(csrf="tok"))
    assert status == 200


# ---- S06: days только из ASCII-цифр ----

@pytest.mark.parametrize("days", ["²", "١٢", "１４", "14x", "99999", ""])
def test_s06_non_ascii_days_fall_back_instead_of_500(api, days):
    create(api, {"kind": "object", "id": STOP_ID})
    status, body = call(api, "GET", "/complaints/summary", query=f"target_id={STOP_ID}&days={days}")
    assert status == 200 and body["data"]["reporters"] == 1


# ---- подключение карты R12 в make_service ----

def test_make_service_wires_r12_when_present(tmp_path, monkeypatch):
    fake = types.ModuleType("engine.civic_geo")
    fake.target_geometry = lookup
    monkeypatch.setitem(sys.modules, "engine.civic_geo", fake)
    assert geo_target_lookup() is lookup
    svc = make_service(tmp_path / "w.sqlite3", target_lookup="auto")
    assert svc.store.target_lookup is lookup
    plain = make_service(tmp_path / "x.sqlite3")          # по умолчанию карту подключает хост (R01 wire())
    assert plain.store.target_lookup is None
    svc.store.close()
    plain.store.close()


def test_make_service_without_r12(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "engine.civic_geo", None)       # import -> ImportError
    assert geo_target_lookup() is None
    svc = make_service(tmp_path / "y.sqlite3", target_lookup="auto")
    assert svc.store.target_lookup is None
    svc.store.close()
