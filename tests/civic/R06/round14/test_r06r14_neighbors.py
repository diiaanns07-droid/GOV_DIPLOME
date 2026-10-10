"""R06 раунд 14 · запросы соседей: R05 (3D-предложения), R08 («Картина дня»).

R05 (research/round-14-results/R05/INTEGRATION.txt §2): POST /proposals с полями 3D (status, year, district,
near_street, target, rotation_deg), ответ «предложение или {proposal}», DELETE /proposals/{id}, «Отменить» после
«Удалить» — повторный POST с теми же полями, лимит — code "limit".
R08 (research/round-14-results/R08/INTEGRATION.txt §6): функции akim_objects / akim_proposals в пакете ui.civic_store.
"""

import importlib.util
import os
from pathlib import Path
import sys

import pytest

from ui.civic_store import proposals as propmod
from ui.civic_store import v2 as v2mod
from r06r14_helpers import ESIL_POINT, NURA_POINT, call, context, device

R05_DRAFT = {  # как отправляет build3d-core.js R05 (createApiStore.create)
    "kind": "lighting",
    "geometry": {"type": "LineString", "coordinates": [[71.3695148, 51.1376971], [71.369295, 51.1371074]]},
    "status": "proposal", "rotation_deg": 0, "year": 2027, "district": "esil", "near_street": "улица Ильяса Омарова",
    "target": {"kind": "segment", "id": "osm-w1482578141-0", "ids": ["osm-w1482578141-0", "osm-w1482578141-1"],
               "label_ru": "Участок ул. Ильяса Омарова", "label_kk": "Ілияс Омаров көшесінің бөлігі"},
    "demo": False,
}


def r05_one(body):
    """Как функция one() клиента R05: предложение — data.proposal или сам ответ."""
    return body["proposal"] if "proposal" in body else body


def test_r05_create_with_3d_fields_and_response_shape(staff):
    result = staff.call("POST", "/proposals", R05_DRAFT)
    assert result["status"] == 201, result
    p = r05_one(result["body"]["data"])
    assert p["id"].startswith("p-") and p["votes_up"] == 0 and p["status"] == "proposal"
    assert p["year"] == 2027 and p["near_street"] == "улица Ильяса Омарова"
    assert p["target"]["kind"] == "segment" and p["target"]["ids"] == R05_DRAFT["target"]["ids"]
    assert p["district"] == "nura"  # район считает сервер по полигонам OSM, а не берёт из запроса
    listed = call(staff.v2, "GET", "/proposals")["body"]["data"]["items"]
    assert listed[0]["target"]["id"] == "osm-w1482578141-0"


def test_r05_vote_response_has_proposal(staff):
    p = staff.create_proposal()
    data = call(staff.v2, "POST", f"/proposals/{p['id']}/vote", {"value": 1, "device_id": "dev-mgk3x9a1-abc12"})["body"]["data"]
    one = r05_one(data)
    assert one["votes_up"] == 1 and one["my_vote"] == 1  # короткий id R05 «dev-…» принимается


def test_r05_delete_then_undo_keeps_votes_and_id(staff):
    p = staff.create_proposal()
    call(staff.v2, "POST", f"/proposals/{p['id']}/vote", {"value": 1, "device_id": device(1)})
    anon = call(staff.v2, "DELETE", f"/proposals/{p['id']}")
    assert anon["status"] == 401
    deleted = staff.call("DELETE", f"/proposals/{p['id']}")
    assert deleted["status"] == 200 and deleted["body"]["data"]["withdrawn"] == p["id"]
    assert call(staff.v2, "GET", f"/proposals/{p['id']}")["status"] == 404
    # «Отменить»: клиент R05 шлёт копию предложения целиком (без my_vote) — сервер возвращает то же предложение.
    copy = {k: v for k, v in p.items() if k != "my_vote"}
    undo = staff.call("POST", "/proposals", copy)
    assert undo["status"] == 201, undo
    data = undo["body"]["data"]
    assert data["restored"] is True and data["proposal"]["id"] == p["id"] and data["proposal"]["votes_up"] == 1
    assert "votes_up" in data["ignored_fields"]
    # Второй раз — уже не снятое: создаётся новое (не дублируем голоса).
    again = staff.call("POST", "/proposals", copy)["body"]["data"]
    assert again["restored"] is False and again["proposal"]["id"] != p["id"]


@pytest.mark.parametrize("override,field", [
    ({"status": "approved"}, "status"),
    ({"year": 1990}, "year"),
    ({"target": {"kind": "street", "id": "x"}}, "target"),
    ({"target": {"kind": "segment", "id": "osm-w1-0", "evil": 1}}, "target"),
    ({"near_street": "<b>x</b>"}, "near_street"),
])
def test_r05_field_validation(staff, override, field):
    result = staff.call("POST", "/proposals", {**R05_DRAFT, **override})
    assert result["status"] == 422 and field in result["body"]["error"]["fields"]


def test_limit_per_district(staff, monkeypatch):
    monkeypatch.setattr(propmod, "MAX_OPEN_PER_DISTRICT", 2)
    staff.create_proposal()
    staff.create_proposal()
    third = staff.call("POST", "/proposals", {"kind": "square", "geometry": {"type": "Point", "coordinates": NURA_POINT}})
    assert third["status"] == 409 and third["body"]["error"]["code"] == "limit"
    other = staff.call("POST", "/proposals", {"kind": "square", "geometry": {"type": "Point", "coordinates": ESIL_POINT}})
    assert other["status"] == 201  # в другом районе можно


# --- R08 -----------------------------------------------------------------------------------

@pytest.fixture
def bound(stack):
    svc, _ = stack
    v2mod.bind(svc)
    yield
    v2mod._BOUND = None


def test_akim_functions_found_by_r08_names(staff, bound):
    import ui.civic_store as store
    late = staff.create_object()
    staff.set_stage(late["id"], 0, stage="construction", planned_end="2026-10-01", forecast_end="2026-10-25")
    staff.create_proposal()
    objects = getattr(store, "akim_objects")(district="nura")
    assert objects and {"id", "kind", "title_ru", "title_kk", "district", "stage", "planned_end", "forecast_end",
                        "delay_days", "stale", "updated_at", "demo", "geometry"} <= set(objects[0])
    assert objects[0]["delay_days"] == 24 and objects[0]["district"] == "nura"
    props = getattr(store, "akim_proposals")(district="nura")
    assert {"id", "kind", "title_ru", "title_kk", "district", "status", "created_at", "votes_up", "votes_down",
            "demo"} <= set(props[0])
    assert store.akim_objects(district="esil") == []


def test_akim_functions_unbound_raise_for_r08_fallback():
    v2mod._BOUND = None
    import ui.civic_store as store
    with pytest.raises(v2mod.V2Error) as exc:
        store.akim_objects(district=None)
    assert exc.value.status == 503


def load_r08():
    root = os.environ.get("R06_R08_ROOT")  # корень выгрузки ветки R08: git archive origin/claude/r14-R08 ui/civic_akim
    if not root:
        return None
    spec = importlib.util.spec_from_file_location("ui.civic_akim", Path(root) / "ui" / "civic_akim" / "__init__.py",
                                                  submodule_search_locations=[str(Path(root) / "ui" / "civic_akim")])
    module = importlib.util.module_from_spec(spec)
    sys.modules["ui.civic_akim"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(not os.environ.get("R06_R08_ROOT"), reason="задайте R06_R08_ROOT (выгрузка ui/civic_akim из ветки R08)")
def test_real_r08_summary_uses_r06_functions(staff, bound):
    akim = load_r08()
    from ui.civic_akim import sources, summary  # noqa: F401 — модули R08 из выгрузки
    late = staff.create_object()
    staff.set_stage(late["id"], 0, stage="construction", planned_end="2026-10-01", forecast_end="2026-10-25")
    staff.create_proposal()
    objects, name = sources.default_objects()
    proposals, pname = sources.default_proposals()
    assert name == "r06" and pname == "r06"
    from datetime import date
    rows = objects("nura", date(2026, 10, 11))
    norm = [sources.normalize_object(o, __import__("datetime").datetime(2026, 10, 11, 12, tzinfo=sources.ASTANA_TZ)) for o in rows]
    assert norm[0]["delay_days"] == 24 and norm[0]["title_ru"] and norm[0]["has_place"] is True
    assert proposals("nura", date(2026, 10, 11))[0]["status"] == "proposal"
