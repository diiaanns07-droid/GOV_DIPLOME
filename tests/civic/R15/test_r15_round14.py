"""R15: модули раунда 14 в общей сборке R01 — R06 (предложения, голоса, этапы), R07 (карта), R08 («Картина дня»),
R04 (/similar), R12 (/objects-near), R13 (/forecast), R02 (обезличивание и LLM-разметка).

Через настоящий HTTP на 127.0.0.1 и временную базу (как в test_r15_server.py). Модуля роли нет в сборке — skip.
PASS — защищено (регрессия), xfail — открытая находка из SECURITY_REVIEW.md.
"""

from __future__ import annotations

import json
import math
import sqlite3
import types
from pathlib import Path

import pytest

from r15_common import error_code, live_server, need_module, request, xfail

FAKE = "Остановка «Акимат берёт взятки»"
# Реальный объект OSM (парк в районе Алматы) рядом с этой точкой; берётся через /objects-near (R12).
NEAR = (71.4306, 51.1283)
FAR_POINT = [71.55, 51.18]  # ~10 км от NEAR


@pytest.fixture()
def srv(tmp_path):
    with live_server(tmp_path) as server:
        if not hasattr(server, "civic_v2"):
            pytest.skip("в этой сборке нет шлюза /api/civic/v2 (R01)")
        yield server


def origin(srv):
    return "http://127.0.0.1:%d" % srv.server_address[1]


def call(srv, method, path, body=None, device=None, headers=None):
    hdrs = {"Origin": origin(srv)}
    if device:
        hdrs["X-Birge-Device"] = device
    hdrs.update(headers or {})
    status, _h, data = request(srv, method, "/api/civic/v2" + path, body, headers=hdrs)
    try:
        payload = json.loads(data or b"{}")
    except ValueError:
        payload = {"raw": data[:200]}
    return status, payload


def ready(srv, *keys):
    status, data = call(srv, "GET", "/modules")
    modules = data.get("modules", {}) if status == 200 else {}
    for key in keys:
        if (modules.get(key) or {}).get("status") != "ready":
            pytest.skip(f"маршрут {key} не подключён в этой сборке")


def real_object(srv):
    """Ближайший к NEAR реальный объект OSM (R12) — id и подписи из данных карты."""
    ready(srv, "geo.objects")
    status, data = call(srv, "GET", "/objects-near?lon=%s&lat=%s" % NEAR)
    if status != 200 or not data.get("objects"):
        pytest.skip("R12 /objects-near не вернул объектов (нет данных OSM в сборке)")
    return data["objects"][0]


def create_complaint(srv, device, **extra):
    body = {"text": "Не горят фонари во дворе, вечером опасно", "category": "lighting", "point": list(NEAR)}
    body.update(extra)
    status, data = call(srv, "POST", "/complaints", body, device=device)
    return status, data


# --- 1/4. подпись цели от жителя: R09 -> R07 /heat -> R08 /akim/summary -------------------------

@xfail("S11")
def test_resident_label_does_not_rename_real_object_on_public_map(srv):
    """Одна анонимная жалоба переименовывает реальный объект OSM на публичной карте и в «Картине дня».

    Закрывается, когда исправлено S04 (R09 не хранит подписи от жителя) ИЛИ S11 (R07 берёт подпись из OSM).
    """
    ready(srv, "complaints.create", "heat", "akim.summary")
    obj = real_object(srv)
    status, data = create_complaint(srv, "device-r15-label-0000001",
                                    target={"kind": "object", "id": obj["id"], "label_ru": FAKE, "label_kk": FAKE})
    assert status in (200, 201, 422), data
    _s, heat = call(srv, "GET", "/heat?days=30")
    _s, akim = call(srv, "GET", "/akim/summary")
    shown = json.dumps(heat, ensure_ascii=False) + json.dumps(akim, ensure_ascii=False)
    assert FAKE not in shown


@xfail("S11")
def test_heat_resolver_prefers_osm_label_over_record_label():
    """R07 TargetResolver: «подписи из записи жалобы главнее автоматических» — для реального объекта это подмена."""
    targets = need_module("ui.civic_heat.targets")
    resolver = targets.TargetResolver()
    osm = resolver.resolve({"kind": "object", "id": "osm-way-258818058"})
    if not osm:
        pytest.skip("в данных R07 нет объекта osm-way-258818058")
    resolver = targets.TargetResolver()
    got = resolver.resolve({"kind": "object", "id": "osm-way-258818058", "label_ru": FAKE, "label_kk": FAKE})
    assert got["label_ru"] == osm["label_ru"] and got["label_kk"] == osm["label_kk"], got


@xfail("S12")
def test_complaint_cannot_target_object_far_from_its_point(srv):
    """Точка жалобы в 10 км от цели — R09 принимает любой id цели, лишь бы формат подходил.

    Вместе с S02/S08 это позволяет «нагреть» на карте акимата любое место города, не будучи рядом.
    """
    ready(srv, "complaints.create")
    obj = real_object(srv)
    status, data = create_complaint(srv, "device-r15-far-00000001", point=FAR_POINT,
                                    target={"kind": "object", "id": obj["id"]})
    if status == 422:
        return
    assert status in (200, 201), data
    assert data["data"]["complaint"]["target"]["id"] != obj["id"], "цель за 10 км от точки принята как есть"


# --- 4. персональные данные: что видят чужие ---------------------------------------------------

def test_heat_target_hides_real_texts_from_anonymous(srv):
    """Тексты настоящих жалоб в карточке цели — только сотруднику; параметр staff в адресе не помогает."""
    ready(srv, "complaints.create", "heat.target")
    secret = "Секретный текст жителя r15 про фонари"
    status, data = create_complaint(srv, "device-r15-texts-000001", text=secret)
    assert status in (200, 201), data
    target = data["data"]["complaint"]["target"]
    for extra in ("", "&staff=1", "&staff=true&role=akimat"):
        path = "/heat/target?kind=%s&id=%s&days=30%s" % (target["kind"], target["id"], extra)
        status, body = call(srv, "GET", path)
        assert status in (200, 404), body
        assert secret not in json.dumps(body, ensure_ascii=False)


def test_similar_returns_no_resident_text(srv):
    ready(srv, "complaints.create", "similar")
    secret = "Не горят фонари во дворе, вечером опасно, r15 секрет"
    status, data = create_complaint(srv, "device-r15-sim-00000001", text=secret)
    assert status in (200, 201), data
    status, body = call(srv, "POST", "/similar", {"text": secret, "point": list(NEAR)})
    if status == 503:
        pytest.skip("поиск похожих не подключён к хранилищу в этой сборке")
    assert status == 200, body
    assert "r15 секрет" not in json.dumps(body, ensure_ascii=False)
    for match in body.get("matches", []):
        assert not {"text", "point", "device_id", "device_hash", "code"} & set(match)


def _enu(lon, lat, lon0, lat0):
    k = 111_320.0
    return ((lon - lon0) * k * math.cos(math.radians(lat0)), (lat - lat0) * k)


@xfail("S13")
def test_similar_distance_does_not_reveal_resident_point(srv):
    """distance_m с точностью 0,1 м: три запроса /similar из разных точек -> точка жителя до метра (трилатерация).

    Огрубление точки в публичной выдаче (S03) без этого ничего не даёт.
    """
    ready(srv, "complaints.create", "similar")
    secret_point = [71.432519, 51.127311]
    text = "Во дворе не горят фонари, вечером темно и опасно"
    status, data = create_complaint(srv, "device-r15-tri-00000001", text=text, point=secret_point)
    assert status in (200, 201), data
    probes = [[71.4310, 51.1268], [71.4340, 51.1268], [71.4325, 51.1285]]
    dists = []
    for probe in probes:
        status, body = call(srv, "POST", "/similar", {"text": text, "point": probe})
        if status == 503:
            pytest.skip("поиск похожих не подключён к хранилищу в этой сборке")
        assert status == 200, body
        found = [m for m in body.get("matches", []) if m.get("distance_m") is not None]
        if not found:
            return  # расстояние не отдаётся — утечки нет
        dists.append(float(found[0]["distance_m"]))
    lon0, lat0 = probes[0]
    (x1, y1), (x2, y2), (x3, y3) = (_enu(lon, lat, lon0, lat0) for lon, lat in probes)
    r1, r2, r3 = dists
    # Разность уравнений окружностей -> линейная система 2x2.
    a, b, c = 2 * (x2 - x1), 2 * (y2 - y1), r1 ** 2 - r2 ** 2 - x1 ** 2 + x2 ** 2 - y1 ** 2 + y2 ** 2
    d, e, f = 2 * (x3 - x1), 2 * (y3 - y1), r1 ** 2 - r3 ** 2 - x1 ** 2 + x3 ** 2 - y1 ** 2 + y3 ** 2
    det = a * e - b * d
    x, y = (c * e - b * f) / det, (a * f - c * d) / det
    sx, sy = _enu(secret_point[0], secret_point[1], lon0, lat0)
    error_m = math.hypot(x - sx, y - sy)
    assert error_m > 25, "точка жителя восстановлена с ошибкой %.1f м" % error_m


def _db_bytes(srv):
    path = Path(srv.civic_v2.db_path) if getattr(getattr(srv, "civic_v2", None), "db_path", None) else None
    if path is None or not path.exists():
        pytest.skip("путь базы шлюза v2 неизвестен")
    con = sqlite3.connect(path)
    try:
        con.execute("PRAGMA wal_checkpoint(FULL)")
    finally:
        con.close()
    data = path.read_bytes()
    for extra in (path.with_name(path.name + "-wal"), path.with_name(path.name + "-journal")):
        if extra.exists():
            data += extra.read_bytes()
    return data


def test_device_ids_are_stored_hashed(srv):
    """device_id жителя (жалоба, «Я тоже», голос) в базе только хэшем — по базе не связать устройство с жалобами."""
    ready(srv, "complaints.create", "complaints.metoo")
    author, voter = "device-r15-rawid-author01", "device-r15-rawid-voter001"
    status, data = create_complaint(srv, author)
    assert status in (200, 201), data
    complaint_id = data["data"]["complaint"]["id"]
    call(srv, "POST", "/complaints/%s/metoo" % complaint_id, {}, device=voter)
    blob = _db_bytes(srv)
    assert author.encode() not in blob and voter.encode() not in blob


# --- 2. R06: действия акимата недоступны жителю и анониму ----------------------------------------

R06_STAFF = [
    ("POST", "/proposals/p-r15-0001/approve", {}),
    ("POST", "/proposals/p-r15-0001/reject", {"reason": "нет"}),
    ("POST", "/proposals/p-r15-0001/withdraw", {}),
    ("GET", "/staff/objects/o-r15-0001/stage", None),
    ("PUT", "/objects/o-r15-0001/stage", {"stage": "construction"}),
    ("POST", "/proposals", {"kind": "park", "title_ru": "Сквер r15"}),
]


@pytest.mark.parametrize("method,path,body", R06_STAFF)
def test_r06_staff_actions_refuse_anonymous(srv, method, path, body):
    status, data = call(srv, method, path, body, device="device-r15-resident-0001")
    if status == 503:
        assert error_code(data) in ("module_not_ready", "module_failed"), data
        return
    assert status in (401, 403), (status, data)


def test_r06_vote_burst_from_one_address_is_limited(srv):
    """R06: не больше 30 голосов в минуту с одного адреса — скрипт с новыми device_id упирается в 429."""
    ready(srv, "proposals.vote")
    statuses = []
    for i in range(45):
        status, _data = call(srv, "POST", "/proposals/p-r15-0001/vote",
                             {"value": 1, "device_id": "device-r15-vote-%08d" % i})
        statuses.append(status)
        if status == 429:
            break
    assert 429 in statuses, statuses[-5:]


@xfail("S08")
def test_r06_votes_with_new_device_ids_are_capped_per_address_per_day(monkeypatch, tmp_path):
    """30 голосов в минуту с адреса — это 1800 «новых жителей» в час для одного скрипта.

    Время подменяется (time.monotonic в модуле R06): 2 часа голосования за 2 секунды теста.
    """
    proposals = need_module("ui.civic_store.proposals")
    clock = {"t": 1000.0}
    monkeypatch.setattr(proposals.time, "monotonic", lambda: clock["t"])
    limiter = proposals.RateLimiter(proposals.VOTES_PER_MINUTE)
    accepted = 0
    for minute in range(120):
        clock["t"] += 61
        for i in range(40):
            if limiter.allow("198.51.100.7"):
                accepted += 1
    assert accepted <= 200, "с одного адреса за 2 часа принято %d голосов с новыми device_id" % accepted


# --- 4. R13 прогноз: только синтетика и агрегаты --------------------------------------------------

def test_forecast_is_public_aggregate_without_resident_data(srv):
    ready(srv, "forecast")
    status, body = call(srv, "GET", "/forecast")
    assert status == 200, body
    text = json.dumps(body, ensure_ascii=False)
    for key in ('"text"', '"device_id"', '"device_hash"', '"phone"', '"username"'):
        assert key not in text, key


# --- 4. R02: обезличивание перед разметкой и перед внешним LLM ------------------------------------

NAME_TEXTS = [
    ("Иванов Иван Иванович, живу рядом, во дворе яма", "Иванов"),
    ("Я, Сейткали Айгерим, прошу убрать мусор у дома", "Сейткали"),
    ("Пишет Ахметова Динара Серикқызы: нет света во дворе", "Ахметова"),
    ("Сәлем, мен Нұрлан Ерболұлы, аулада жарық жоқ", "Ерболұлы"),
]


@xfail("S07")
@pytest.mark.parametrize("text,surname", NAME_TEXTS)
def test_anonymize_removes_full_names_or_flags_review(text, surname):
    anonymize = need_module("ml.labeling.anonymize")
    clean, _counts = anonymize.anonymize(text)
    assert surname not in clean or anonymize.needs_review(clean), clean


@xfail("S14")
def test_llm_label_sends_no_names_to_external_api(tmp_path):
    """llm_label отправляет настоящие тексты (форма владельца) во внешний API после anonymize — ФИО уходят как есть."""
    llm_label = need_module("ml.labeling.llm_label")
    src = tmp_path / "form.jsonl"
    src.write_text("\n".join(json.dumps({"id": "r%d" % i, "text": t, "evidence": "real"}, ensure_ascii=False)
                             for i, (t, _s) in enumerate(NAME_TEXTS)) + "\n", encoding="utf-8")
    sent = []

    def capture(url, headers, body, timeout):
        sent.append(json.loads(body.decode("utf-8"))["messages"][-1]["content"])
        return llm_label.mock_transport(url, headers, body, timeout)

    args = llm_label.parse_args([str(src), "--mock", "--out", str(tmp_path / "labels.jsonl"),
                                 "--cache", str(tmp_path / "cache"), "--allow-outside-private"])
    llm_label.run(args, transport=capture)
    leaked = [s for _t, s in NAME_TEXTS if any(s in m for m in sent)]
    assert not leaked, leaked
