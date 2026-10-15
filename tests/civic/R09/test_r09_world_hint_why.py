"""Подсказка мира R02 «нужны 2 службы» получает объяснение R04 при засеве (patch R04 r09_world_hint_why.patch)."""

from ui.civic_feedback.v2 import world_seed as ws


def _record():
    return {"text": "Раскопали дорогу и так и бросили", "category": "roads", "subtopic": "pothole",
            "point": [71.43, 51.12],
            "route_hint": {"services": ["water", "road"], "joint": True, "source": "rules", "model_version": None}}


def test_world_hint_gets_r04_explanation():
    rec = _record()

    def route(**kw):
        assert kw["text"] and kw["category"] == "roads" and kw["point"] == [71.43, 51.12]
        return {"services": [{"service": "water", "role": "lead"}, {"service": "road", "role": "partner"}],
                "joint": True, "why_ru": "Раскопки без восстановления покрытия.",
                "why_kk": "Қалпына келтірілмеген қазба."}

    assert ws.explain_hint(rec, route)
    assert rec["route_hint"]["why_ru"] == "Раскопки без восстановления покрытия."
    assert rec["route_hint"]["why_kk"] == "Қалпына келтірілмеген қазба."
    assert rec["route_hint"]["services"] == ["water", "road"]


def test_world_hint_unchanged_without_r04_or_when_it_disagrees():
    def other(**kw):
        return {"services": [{"service": "road"}], "joint": False, "why_ru": "Яма на дороге."}

    def down(**kw):
        raise RuntimeError("R04 недоступен")

    for lookup in (None, other, down):
        rec = _record()
        assert not ws.explain_hint(rec, lookup)
        assert "why_ru" not in rec["route_hint"]


def test_seed_by_path_takes_route_of_the_build(tmp_path, monkeypatch):
    """Шлюз R01 передаёт в seed_world путь к базе — у своего хранилища нет route_lookup; объяснение берётся у route()
    R04 из сборки (integration.r04_route_lookup), а без R04 подсказка мира остаётся как есть."""
    import json
    from pathlib import Path
    from ui.civic_feedback.v2 import ComplaintStore, integration
    from ui.civic_feedback.v2.integration import seed_world

    world = json.loads((Path(__file__).parent / "fixtures" / "world_sample_r09.json").read_text(encoding="utf-8"))

    def route(**kw):
        return {"services": [{"service": "water", "role": "lead"}, {"service": "road", "role": "partner"}],
                "joint": True, "why_ru": "Раскопки сетей: Водоканал — засыпка, Дорожная служба — покрытие.",
                "why_kk": "Желілер қазбасы."}

    monkeypatch.setattr(integration, "r04_route_lookup", lambda: route)
    db = tmp_path / "w.sqlite3"
    seed_world(str(db), world)
    store = ComplaintStore(db)
    try:
        pit = next(r for r in store.list() if (r.get("target") or {}).get("id") == "osm-w123-4")
        assert pit["route_hint"]["why_ru"].startswith("Раскопки сетей") and pit["route_hint"]["why_kk"]
    finally:
        store.close()
    monkeypatch.setattr(integration, "r04_route_lookup", lambda: None)
    db2 = tmp_path / "w2.sqlite3"
    seed_world(str(db2), world)
    store = ComplaintStore(db2)
    try:
        pit = next(r for r in store.list() if (r.get("target") or {}).get("id") == "osm-w123-4")
        assert "why_ru" not in pit["route_hint"]
    finally:
        store.close()
