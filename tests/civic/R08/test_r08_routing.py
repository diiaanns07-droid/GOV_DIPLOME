"""Волна мелочей п. 7 «Кому передано»: таблица «категория / уточнение → служба», правки акимата, API."""
import json

import pytest

from ui.civic_akim import api, deadlines, routing


def test_table_matches_categories_v2():
    routing.validate()  # у каждой категории есть служба, ключи — настоящие категории и уточнения


def test_every_category_and_subtopic_has_a_service(tmp_path):
    t = routing.table(tmp_path / "none.json")
    keys = {r["key"] for r in t["rules"]}
    for c in deadlines.load_categories()["categories"]:
        assert c["id"] in keys
        for s in c.get("subtopics") or []:
            assert f"{c['id']}/{s['id']}" in keys
    for r in t["rules"]:
        assert r["service"] in t["services"], r


def test_subtopic_wins_over_category(tmp_path):
    none = tmp_path / "none.json"
    assert routing.service_for("roads", "traffic_light_broken", none)["ru"] == "Служба светофоров и разметки"
    assert routing.service_for("roads", "pothole", none)["ru"] == "Дорожная служба"
    assert routing.service_for("roads", "pothole", none)["rule"] == "category"
    assert routing.service_for("roads", None, none)["rule"] == "category"
    assert routing.service_for("utilities", "no_water", none)["id"] == "water"


def test_unknown_category_goes_to_other(tmp_path):
    s = routing.service_for("spaceships", "x", tmp_path / "none.json")
    assert s["rule"] == "fallback" and s["id"] == routing.DEFAULT_RULES["other"]
    assert s["ru"] and s["kk"]


def test_generic_names_only():
    """Реальные названия организаций не придумываем (ТОО, АО, ГКП, «Астана …» и т. п.)."""
    for sid, names in routing.SERVICES.items():
        for lang in ("ru", "kk"):
            name = names[lang]
            assert name and len(name) <= routing.NAME_MAX
            for word in ("ТОО", "АО ", "ГКП", "ГУ ", "Астана", "Нұр-Сұлтан", "«"):
                assert word not in name, (sid, lang, name)


def test_akimat_edit_persists_and_resets(tmp_path):
    path = tmp_path / "routing.json"
    routing.update({"rules": {"roads/marking": "road"}, "services": {"road": {"ru": "Отдел дорог района"}}},
                   actor="staff-1", path=path)
    s = routing.service_for("roads", "marking", path)
    assert s["id"] == "road" and s["ru"] == "Отдел дорог района" and s["edited"]
    assert s["kk"] == routing.SERVICES["road"]["kk"]  # kk не трогали — остаётся общий
    data = json.loads(path.read_text("utf-8"))
    assert data["updated_by"] == "staff-1" and data["updated_at"]
    row = next(r for r in routing.table(path)["rules"] if r["key"] == "roads/marking")
    assert row["edited"] and row["service"] == "road"
    # null — вернуть умолчание
    routing.update({"rules": {"roads/marking": None}, "services": {"road": None}}, path=path)
    s = routing.service_for("roads", "marking", path)
    assert s["id"] == "traffic" and not s["edited"]


def test_category_edit_moves_subtopics_without_own_rule(tmp_path):
    path = tmp_path / "routing.json"
    routing.update({"rules": {"yards": "akimat"}}, path=path)
    assert routing.service_for("yards", "playground", path)["id"] == "akimat"   # своего правила нет
    assert routing.service_for("yards", "trees_lawn", path)["id"] == "greenery"  # своё правило осталось


@pytest.mark.parametrize("changes,field", [
    ({"rules": {"spaceships": "road"}}, "category"),
    ({"rules": {"roads/teleport": "road"}}, "subtopic"),
    ({"rules": {"roads": "nasa"}}, "service"),
    ({"services": {"road": {"ru": "  "}}}, "services.road.ru"),
    ({"services": {"road": {"ru": "<script>"}}}, "services.road.ru"),
    ({"services": {"road": {"ru": "x" * 81}}}, "services.road.ru"),
    ({}, "body"),
    (None, "body"),
])
def test_bad_edits_rejected(tmp_path, changes, field):
    path = tmp_path / "routing.json"
    with pytest.raises(routing.RoutingError) as exc:
        routing.update(changes, path=path)
    assert exc.value.field == field
    assert not path.exists()  # ничего не записали


def test_api_get_and_put(tmp_path, monkeypatch):
    path = tmp_path / "routing.json"
    monkeypatch.setattr(routing, "OVERRIDE_PATH", path)
    code, body = api.handle_get("/api/civic/v2/akim/routing", {"category": ["roads"], "subtopic": ["marking"]})
    assert code == 200 and body["id"] == "traffic"
    code, body = api.handle_get("/api/civic/v2/akim/routing", {})
    assert code == 200 and len(body["rules"]) > 12 and "road" in body["services"]
    code, body = api.handle_put("/api/civic/v2/akim/routing", {"rules": {"roads/marking": "road"}})
    assert code == 403 and not path.exists()  # не сотрудник — нельзя
    code, body = api.handle_put("/api/civic/v2/akim/routing", {"rules": {"roads/marking": "road"}}, staff=True, actor="s")
    assert code == 200 and path.exists()
    assert api.handle_get("/api/civic/v2/akim/routing", {"category": "roads", "subtopic": "marking"})[1]["id"] == "road"
    code, body = api.handle_put("/api/civic/v2/akim/routing", {"rules": {"roads": "nasa"}}, staff=True)
    assert code == 400 and body["field"] == "service"
    assert api.handle_put("/api/civic/v2/akim/other", {}, staff=True)[0] == 404


def test_broken_override_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "routing.json"
    path.write_text("{not json", "utf-8")
    assert routing.service_for("roads", "marking", path)["id"] == "traffic"
