"""R02 · раунд 15 · демо-мир: проверка файла, воспроизводимость, относительное время, проверка ловит ошибки,
засев в хранилище R09 даёт те же числа, что EXPECTED (карта R07, «Обращения» R09, «Картина дня» R08).

Все данные — синтетика мира (demo: true); цели — OSM через карту R12 (только чтение).
"""

import copy
import hashlib
import json
import socket
from datetime import datetime, timedelta, timezone

import pytest

from ml.datasets import demo_world as gen
from ml.datasets import demo_world_check as check
from ml.datasets import demo_world_expected as exp
from ml.datasets import demo_world_io as wio
from ml.datasets.demo_world_seed import complaint_rows, seed_world

NOW = datetime.fromisoformat(gen.REFERENCE_NOW)
ASTANA = timezone(timedelta(hours=5))


@pytest.fixture(scope="module")
def world():
    return wio.load_world()


@pytest.fixture(scope="module")
def sample():
    return wio.load_world(wio.SAMPLE_PATH)


@pytest.fixture(scope="module")
def expected(world):
    return exp.expected(world, NOW)


# ---------------------------------------------------------------- файл мира
def test_world_passes_check(world):
    rep = check.check_world(world, geo=True, now=NOW, heat=True)
    assert rep.errors == []


def test_sample_passes_check_and_is_subset(world, sample):
    rep = check.check_world(sample, geo=True, now=NOW, heat=False)
    check.check_sample(rep, sample, world)
    assert rep.errors == []
    for key in ("complaints", "works", "ideas", "initiatives", "yards", "incidents", "meetings", "questions"):
        assert 3 <= len(sample[key]) <= 40, key


def test_world_sizes_and_shares(world):
    cs = world["complaints"]
    assert 600 <= len(cs) <= 900
    nura = sum(1 for c in cs if c["district"] == "nura") / len(cs)
    assert 0.30 <= nura <= 0.40                                  # «Нура ~35 %»
    verified = sum(1 for c in cs if (c.get("resolution") or {}).get("state") == "verified") / len(cs)
    assert 0.07 <= verified <= 0.15                              # «~10 % проверено жителями»
    joint = sum(1 for c in cs if c.get("services")) / len(cs)
    assert 0.03 <= joint <= 0.08                                 # «~5 % совместных»
    assert any(h.get("reopened_by_residents") for c in cs for h in c["status_history"])   # «вернули жители»
    assert 30 <= len(world["works"]) <= 60
    assert 3 <= len(world["planned_conflicts"]) <= 5
    assert 10 <= len(world["ideas"]) <= 15 and 8 <= len(world["initiatives"]) <= 12
    assert 20 <= len(world["yards"]) <= 40 and len(world["meetings"]) == 3 and len(world["questions"]) == 10
    langs = {c["lang"] for c in cs}
    assert langs == {"ru", "kk", "mixed"}


def test_snow_only_in_episodes(world):
    """Сезон: снег в октябрьском окне — только в эпизоды (первый снег, гололёд, буран)."""
    snow = [c for c in world["complaints"] if c["category"] == "snow_ice"]
    assert snow and all(c.get("event") for c in snow)
    buran = [c for c in snow if c["event"] == "ev-w15-buran"]
    assert sum(1 for c in buran if c["district"] == "nura") > len(buran) / 2


def test_step2_matches_r09_demo_seed(world):
    """Шаг 2 FINAL-4 не ломается: те же id и тексты, что у R09 demo_seed («сообщили 3 человека»)."""
    from ui.civic_feedback.v2 import demo_seed
    by_id = {c["id"]: c for c in world["complaints"]}
    for item in demo_seed.DEMO_COMPLAINTS:
        c = by_id[demo_seed._demo_id(item["key"])]
        assert c["text"] == item["text"] and c["category"] == item["category"]
        assert 1 + c["metoo"] == item["people"] and c["status"] == "new"
        assert c["target"]["id"] == demo_seed.KHAN_SHATYR["id"]


# ---------------------------------------------------------------- воспроизводимость
def test_generator_reproducible_and_matches_file(world, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("генератор не должен ходить в сеть")
    monkeypatch.setattr(socket, "socket", no_network)
    text1 = gen.dump(gen.build_world(gen.SEED))
    text2 = gen.dump(gen.build_world(gen.SEED))
    assert text1 == text2
    have = wio.WORLD_PATH.read_text(encoding="utf-8")
    assert hashlib.sha256(text1.encode()).hexdigest() == hashlib.sha256(have.encode()).hexdigest(), \
        "world_v1.json устарел: python3 -m ml.datasets.demo_world"


# ---------------------------------------------------------------- относительное время
def test_materialize_rules():
    now = datetime(2026, 10, 16, 12, 0, tzinfo=ASTANA)          # пятница
    rec = {"a": {"ago_hours": 30.5}, "b": {"in_days": 2}, "c": {"day": -12}, "d": {"season": {"month": 5, "day": 4}},
           "e": {"next_weekday": {"weekday": 5, "hour": 10, "minute": 0}}, "f": "2026-01-01T00:00:00+05:00",
           "g": [{"ago_days": 1}], "h": {"ago_hours": 1, "x": 2}}
    out = wio.materialize(rec, now)
    assert out["a"] == "2026-10-15T05:30:00+05:00"
    assert out["b"] == "2026-10-18T12:00:00+05:00"
    assert out["c"] == "2026-10-04"
    assert out["d"] == "2027-05-04"                               # октябрь → следующий сезон
    assert out["e"] == "2026-10-17T10:00:00+05:00"                # завтра суббота, через 22 ч
    assert out["f"] == rec["f"] and out["g"] == ["2026-10-15T12:00:00+05:00"]
    assert out["h"] == rec["h"]                                   # не объект времени — не трогаем
    assert rec["a"] == {"ago_hours": 30.5}                        # исходник не изменён
    assert wio.materialize(out, now) == out                       # повторно — то же


def test_materialize_edges():
    feb = datetime(2027, 2, 10, 9, 0, tzinfo=ASTANA)
    assert wio.resolve({"season": {"month": 5, "day": 4}}, feb) == "2027-05-04"   # зимой — этот год
    sat_morning = datetime(2026, 10, 17, 9, 0, tzinfo=ASTANA)                    # суббота 09:00
    assert wio.resolve({"next_weekday": {"weekday": 5, "hour": 10, "minute": 0}}, sat_morning) \
        == "2026-10-24T10:00:00+05:00"                                             # «через час» нельзя
    utc = datetime(2026, 10, 16, 7, 0, tzinfo=timezone.utc)
    assert wio.resolve({"ago_hours": 0}, utc) == "2026-10-16T12:00:00+05:00"     # по Астане
    assert not wio.is_reltime({"ago_hours": True})        # bool — не число
    assert not wio.is_reltime({"day": 1.5})               # дата — только целое число дней
    assert wio.is_reltime({"day": -3}) and wio.is_reltime({"ago_days": 1.5})


def test_load_world_errors(tmp_path):
    bad = tmp_path / "w.json"
    bad.write_text("{}", encoding="utf-8")
    with pytest.raises(wio.WorldError):
        wio.load_world(bad)
    with pytest.raises(wio.WorldError):
        wio.load_world(tmp_path / "нет.json")


# ---------------------------------------------------------------- проверка ловит ошибки
def _broken(sample, mutate):
    w = copy.deepcopy(sample)
    mutate(w)
    rep = check.check_world(w, geo=True, now=NOW, heat=False)
    return " | ".join(rep.errors)


@pytest.mark.parametrize("mutate, needle", [
    (lambda w: w["complaints"][0].update(text="Звоните +7 701 123 45 67, разберёмся"), "телефон"),
    (lambda w: w["complaints"][0].update(text="Мой ИИН 900101300123, проверьте"), "ИИН"),
    (lambda w: w["initiatives"][0].update(text="Пишите на sosed@mail.kz"), "e-mail"),
    (lambda w: w["complaints"][1].update(id=w["complaints"][0]["id"]), "повторяется"),
    (lambda w: w["complaints"][0]["target"].update(id="osm-node-1"), "неизвестна карте"),
    (lambda w: w["complaints"][0].update(metoo=w["complaints"][0]["metoo"] + 1), "metoo"),
    (lambda w: w["complaints"][0].pop("demo"), "demo"),
    (lambda w: w["works"][0].update(segments=["osm-w1-1"]), "не ребро графа"),
    (lambda w: w["initiatives"][0]["target"].update(id="yard-1"), "не из yards"),
    (lambda w: w["complaints"][0].update(created_at="2026-10-16T10:00:00+05:00"), "относительного времени"),
])
def test_checker_catches(sample, mutate, needle):
    assert needle in _broken(sample, mutate)


def test_checker_catches_joint_fixed_with_open_part(sample):
    def mutate(w):
        c = next(c for c in w["complaints"] if c.get("services"))
        c["services"][1]["status"] = "in_progress"
        c["status"] = "fixed"
        c["status_history"].append({"at": {"ago_hours": 0.1}, "status": "fixed"})
    assert "все части" in _broken(sample, mutate)


# ---------------------------------------------------------------- засев R09 → те же числа
def test_seed_r09_same_numbers_as_expected(world, expected, tmp_path):
    from ui.civic_feedback.v2 import lifecycle
    from ui.civic_feedback.v2.store import ComplaintStore
    from ui.civic_heat.service import HeatService
    db = tmp_path / "complaints.sqlite3"
    first = seed_world(db, world, NOW)
    assert first == {"inserted": len(world["complaints"]), "skipped": 0, "reset": 0}
    again = seed_world(db, world, NOW)                            # повторный запуск — без дублей
    assert again == {"inserted": 0, "skipped": 0, "reset": len(world["complaints"])}
    store = ComplaintStore(db, clock=lambda: NOW)
    try:
        records = store.list()
        assert len(records) == len(world["complaints"])
        assert lifecycle.inbox(records, NOW)["counts"] == expected["inbox"]["city"]
        nura = [r for r in records if r["district"] == "nura"]
        assert lifecycle.inbox(nura, NOW)["counts"] == expected["inbox"]["nura"]
        heat = HeatService(source=lambda since: store.list(), metoo_times=store.metoo_times, clock=lambda: NOW)
        got = {it["district"]: it["count"] for it in heat.districts(days=14, now=NOW)}
        assert got["nura"] == expected["heat"]["districts_14d"]["nura"]["people"]
        # «Я тоже» шага 2: R09 считает людей по месту и категории за 14 дней
        from ui.civic_feedback.v2 import demo_seed
        light = store.get(demo_seed._demo_id("khan-shatyr-lighting"))
        assert store.place_reporters(light) == 3
    finally:
        store.close()


def test_seed_keeps_real_records(world, tmp_path):
    """Настоящую жалобу с тем же id засев не трогает (reset только для demo: true)."""
    from ui.civic_feedback.v2.store import ComplaintStore
    db = tmp_path / "c.sqlite3"
    record, devices = complaint_rows(world, NOW)[0]
    store = ComplaintStore(db, clock=lambda: NOW)
    real = dict(record, demo=False, text="Настоящая жалоба жителя")
    assert store.import_record(real)
    store.close()
    report = seed_world(db, world, NOW)
    assert report["skipped"] == 1
    store = ComplaintStore(db, clock=lambda: NOW)
    assert store.get(record["id"])["text"] == "Настоящая жалоба жителя"
    store.close()


# ---------------------------------------------------------------- EXPECTED
def test_expected_numbers_story(expected):
    assert expected["scenes"]["step2"] == {"lighting_people_14d": 3, "stop_people_14d": 12}
    nura = expected["akim"]["nura"]
    assert nura["decisions_source"] == "complaints" and len(nura["decisions"]) == 2
    snow = [p for p in nura["pulse"] if p["category"] == "snow_ice"]
    assert snow and snow[0]["ratio"] and 3 <= snow[0]["ratio"] <= 9          # «Снег в Нуре ×N», правдоподобно
    assert expected["heat"]["districts_14d"]["nura"]["people"] == max(
        d["people"] for d in expected["heat"]["districts_14d"].values())     # Нура — самый горячий район


def test_expected_file_is_current(world):
    path = wio.WORLD_DIR / "EXPECTED.json"
    have = json.loads(path.read_text(encoding="utf-8"))
    fresh = exp.expected(world, datetime.fromisoformat(have["now"]))
    assert have == json.loads(json.dumps(fresh, ensure_ascii=False)), \
        "EXPECTED.json устарел: python3 -m ml.datasets.demo_world_expected"
