"""Round 13: R06 + настоящий классификатор R08 (ml.civic_classifier), а не FIXTURE.

Выполняется только в сборке, где есть ml/civic_classifier (поставка R08 9660885 поверх
56538a3); в ветке R06 модуля нет — тест пропускается с причиной, а не «проходит».
Сбои (ошибка, таймаут, некорректный ответ) имитируются обёрткой ВОКРУГ настоящего
classify: сама модель R08 не подменяется.
"""

import json
import threading
import time

import pytest

r08 = pytest.importorskip("ml.civic_classifier", reason="ml.civic_classifier (R08) нет в этой сборке")

from r06_helpers import queue_items, staff, submit  # noqa: E402
from ui.civic_feedback import FeedbackService  # noqa: E402
from ui.civic_feedback.classifier_adapter import r08_status  # noqa: E402
from ui.civic_feedback.fixtures import FIXTURE_OBJECTS, fixture_object_lookup  # noqa: E402
from ui.civic_feedback.integration import build_feedback_service  # noqa: E402

RU_LIGHT = "Во дворе не горят фонари, вечером на дорожке совсем темно."
KK_LIGHT = "Аулада шамдар жанбайды, кешке жол қараңғы."
EN_TEXT = "Streetlights are broken near the bus stop, it is dark at night."


class FixtureCivic:
    """FIXTURE вместо R02 только для объектов: проверяется путь integration.build_feedback_service."""

    class objects:  # noqa: N801
        @staticmethod
        def get_staff(object_id):
            item = fixture_object_lookup(object_id)
            if item is None:
                raise type("NotFound", (Exception,), {})()
            return {"item": item}


def make(tmp_path, clock, classifier, **options):
    return FeedbackService(tmp_path / "pair.sqlite3", fixture_object_lookup, clock, classifier=classifier, **options)


def only_item(svc):
    items = queue_items(svc, moderation="all")
    assert len(items) == 1
    return items[0]


def test_real_r08_passes_contract_probe():
    status = r08_status()
    assert status["available"] is True, status
    assert status["training_data_status"].startswith("synthetic")       # обучена на синтетике
    assert status["score_kind"] == "softmax_max_uncalibrated"           # не вероятность


def test_auto_integration_connects_real_r08_and_labels_source(tmp_path, clock):
    svc = build_feedback_service(tmp_path / "auto.sqlite3", FixtureCivic(), clock=clock)
    try:
        assert svc.classifier is r08.classify and svc.classifier_source == "r08"
        assert submit(svc, category="roads", text=RU_LIGHT)["status"] == 201
        item = only_item(svc)
        clf = item["classifier"]
        assert clf["status"] == "ok" and clf["source"] == "r08" and clf["language"] == "ru"
        sug = clf["suggestion"]
        assert sug["label"] == "lighting" and sug["model_version"].startswith("civic-clf-")
        # Обязательная проверка человеком: модель обучена только на синтетике.
        assert sug["needs_review"] is True and sug["synthetic_only"] is True
        assert "training_not_evaluated_on_real_messages" in sug["review_reasons"]
        # Число модели не показывается и не хранится: softmax_max_uncalibrated — не вероятность.
        assert sug["score"] is None and sug["score_shown"] is False
        assert sug["score_kind"] == "softmax_max_uncalibrated"
        with svc._lock:
            stored = json.loads(svc._db.execute("SELECT classifier_json FROM feedback_messages").fetchone()[0])
        assert "score" not in stored
        # Категория жителя, категория сотрудника и решение — отдельно от подсказки.
        assert item["category"] == "roads" and item["staff_category"] is None
        assert item["moderation"] == "pending" and item["handling_status"] == "new"
        queue = staff(svc, "GET", "/staff/feedback", query={"moderation": "all"})["body"]["data"]
        assert queue["classifier"] == {"source": "r08", "source_label": "Модель R08 (ml.civic_classifier)",
                                       "connected": True}
    finally:
        svc.close()


def test_kazakh_and_unknown_language_reach_real_model(tmp_path, clock):
    svc = make(tmp_path, clock, r08.classify, classifier_source="r08")
    try:
        assert submit(svc, category="other", text=KK_LIGHT)["status"] == 201
        assert submit(svc, ip="10.0.0.2", category="other", text=EN_TEXT)["status"] == 201
        items = {item["text"]: item for item in queue_items(svc, moderation="all")}
        kk = items[KK_LIGHT]["classifier"]
        assert kk["status"] == "ok" and kk["language"] == "kk" and kk["suggestion"]["needs_review"] is True
        unknown = items[EN_TEXT]["classifier"]
        assert unknown["status"] == "ok" and unknown["language"] == "unknown"
        # R08 сама требует проверки для неизвестного языка; R06 это сохраняет.
        assert "model_flag" in unknown["suggestion"]["review_reasons"]
        assert all(item["category"] == "other" for item in items.values())
    finally:
        svc.close()


def test_disabled_model_saves_message(tmp_path, clock):
    svc = make(tmp_path, clock, None)
    try:
        response = submit(svc, text=RU_LIGHT)
        assert response["status"] == 201 and "classifier" not in response["body"]["data"]
        clf = only_item(svc)["classifier"]
        assert clf["status"] == "unavailable" and clf["source"] == "disabled" and clf["suggestion"] is None
        assert svc.classifier_info() == {"source": "disabled", "source_label": "AI-подсказка выключена",
                                         "connected": False}
    finally:
        svc.close()


def test_real_model_error_does_not_lose_message(tmp_path, clock):
    def failing(text, language):
        r08.classify(text, language)          # настоящая модель вызывается…
        raise RuntimeError("R08 crashed")     # …и «падает» после вызова (имитация сбоя)

    svc = make(tmp_path, clock, failing, classifier_source="r08")
    try:
        response = submit(svc, category="roads", text=RU_LIGHT)
        assert response["status"] == 201 and response["body"]["data"]["category"] == "roads"
        clf = only_item(svc)["classifier"]
        assert clf["status"] == "error" and clf["suggestion"] is None and clf["source"] == "r08"
    finally:
        svc.close()


def test_real_model_timeout_returns_receipt_quickly(tmp_path, clock):
    release = threading.Event()

    def slow(text, language):
        release.wait(5)
        return r08.classify(text, language)

    svc = make(tmp_path, clock, slow, classifier_source="r08",
               limits={"classifier_timeout_s": 0.2, "classifier_max_inflight": 1})
    try:
        started = time.monotonic()
        first = submit(svc, text=RU_LIGHT)
        assert first["status"] == 201 and time.monotonic() - started < 2
        # Модель всё ещё занята: второй вызов не порождает новый зависший поток.
        second = submit(svc, ip="10.0.0.3", text="На остановке разбит павильон, нет навеса от дождя.")
        assert second["status"] == 201
        statuses = sorted(item["classifier"]["status"] for item in queue_items(svc, moderation="all"))
        assert statuses == ["busy", "timeout"]
    finally:
        release.set()
        svc.close()


@pytest.mark.parametrize("mutate", [
    lambda value: dict(value, label="urgent_call_akim"),
    lambda value: dict(value, score=float("nan")),
    lambda value: [value],
    lambda value: None,
])
def test_invalid_model_result_is_dropped(tmp_path, clock, mutate):
    svc = make(tmp_path, clock, lambda text, language: mutate(r08.classify(text, language)),
               classifier_source="r08")
    try:
        assert submit(svc, category="lighting", text=RU_LIGHT)["status"] == 201
        item = only_item(svc)
        assert item["classifier"]["status"] == "invalid" and item["classifier"]["suggestion"] is None
        assert item["category"] == "lighting"
    finally:
        svc.close()


def test_hint_never_reaches_resident_or_public(tmp_path, clock):
    svc = make(tmp_path, clock, r08.classify, classifier_source="r08")
    try:
        receipt = submit(svc, text=RU_LIGHT)["body"]["data"]
        status = svc.handle("POST", "/api/civic/v1/feedback/receipt", {}, {"receipt_id": receipt["receipt_id"]},
                            None, {"is_same_origin": True, "client_ip": "127.0.0.1"})["body"]["data"]
        item = only_item(svc)
        staff(svc, "POST", f"/staff/feedback/{item['id']}/moderate",
              {"expected_revision": item["revision"], "action": "approve", "reason": "Проверено"})
        public = svc.handle("GET", f"/api/civic/v1/objects/{FIXTURE_OBJECTS['demo-astana-work-01']['id']}/feedback",
                            {}, None, None, {"is_same_origin": True})["body"]["data"]
        for payload in (receipt, status, public):
            dumped = json.dumps(payload, ensure_ascii=False)
            assert "civic-clf" not in dumped and "classifier" not in dumped and "lighting" not in dumped
    finally:
        svc.close()
