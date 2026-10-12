"""Round 13: повторная отправка при слабой сети, общий NAT, 429 с понятным временем, казахский текст.

Идентичность автора не отслеживается: нет cookie жителя и отпечатков устройства. Повтор
распознаётся только по случайному client_request_id формы; IP — лишь грубый лимит потока.
"""

import json
import unicodedata

import pytest

from r06_helpers import queue_items, submit
from ui.civic_feedback import FeedbackService
from ui.civic_feedback.fixtures import fixture_context, fixture_object_lookup

REQUEST = "5b0c7a1e-3f4d-4e6a-9b8c-0d1e2f3a4b5c"


def count(service):
    return len(queue_items(service, moderation="all"))


def test_retry_after_network_switch_is_idempotent(service):
    first = submit(service, ip="100.64.1.10", client_request_id=REQUEST)       # мобильная сеть (CGNAT)
    assert first["status"] == 201
    for ip in ("100.64.1.10", "192.0.2.44", "2001:db8::7"):                   # ответ потерялся, сеть сменилась
        again = submit(service, ip=ip, client_request_id=REQUEST)
        assert again["status"] == 200 and again["body"]["data"]["replayed"] is True
        assert again["body"]["data"]["receipt_id"] == first["body"]["data"]["receipt_id"]
    assert count(service) == 1


def test_changed_consent_on_retry_is_a_conflict_not_a_silent_replay(service):
    first = submit(service, client_request_id=REQUEST, consent_public=True)
    changed = submit(service, ip="192.0.2.45", client_request_id=REQUEST, consent_public=False)
    assert changed["status"] == 409
    error = changed["body"]["error"]
    assert error["code"] == "request_id_conflict"
    assert error["previous_receipt"]["receipt_id"] == first["body"]["data"]["receipt_id"]
    assert error["previous_receipt"]["consent_public"] is True     # житель видит, что нужно отозвать согласие
    assert count(service) == 1


@pytest.mark.parametrize("weak", ["aaaaaaaaaaaaaaaa", "0000000000000000-0000", "abababababababab"])
def test_low_entropy_request_id_is_rejected(service, weak):
    response = submit(service, client_request_id=weak)
    assert response["status"] == 422 and "client_request_id" in response["body"]["error"]["fields"]


def test_shared_nat_neighbours_are_independent(service):
    a = submit(service, ip="198.51.100.1", client_request_id="11111111-aaaa-4bbb-8ccc-dddddddddddd")
    b = submit(service, ip="198.51.100.1", client_request_id="22222222-eeee-4fff-8aaa-bbbbbbbbbbbb",
               text="На остановке разбит павильон, нет навеса от дождя и снега.")
    assert a["status"] == b["status"] == 201
    assert a["body"]["data"]["receipt_id"] != b["body"]["data"]["receipt_id"]
    # Сосед за тем же NAT пишет тот же текст: предупреждение без чужой квитанции и без подробностей.
    same_text = submit(service, ip="198.51.100.1", client_request_id="33333333-cccc-4ddd-8eee-ffffffffffff")
    error = same_text["body"]["error"]
    assert same_text["status"] == 409 and error["code"] == "duplicate_warning" and error["can_confirm"] is True
    assert "previous_receipt" not in error and "receipt" not in json.dumps(error)
    assert "этой сети" in error["message"]
    confirmed = submit(service, ip="198.51.100.1", client_request_id="33333333-cccc-4ddd-8eee-ffffffffffff",
                       confirm_duplicate=True)
    assert confirmed["status"] == 201
    items = queue_items(service, moderation="all")
    assert all(item["antispam"]["note"].startswith("Совпадение сетевого адреса не доказывает") for item in items)
    assert max(item["antispam"]["same_network_24h"] for item in items) == 2


def test_rate_limit_reports_real_retry_time(tmp_path, clock):
    svc = FeedbackService(tmp_path / "rl.sqlite3", fixture_object_lookup, clock,
                          limits={"per_sender_max": 2, "per_sender_window_s": 600})
    try:
        assert submit(svc, text="Первое сообщение: яма у въезда во двор.")["status"] == 201
        clock.advance(seconds=100)
        assert submit(svc, text="Второе сообщение: нет освещения во дворе.")["status"] == 201
        clock.advance(seconds=100)
        limited = submit(svc, text="Третье сообщение: сломана скамейка у подъезда.")
        assert limited["status"] == 429
        assert limited["headers"]["Retry-After"] == "400"            # первое выйдет из окна через 400 с
        error = limited["body"]["error"]
        assert error["retry_after_s"] == 400 and error["limit"] == "per_sender"
        assert "через 7 мин" in error["message"] and "общим" in error["message"]
        assert "спам" not in error["message"].lower()
        # Другой адрес не ограничен лимитом этого адреса.
        assert submit(svc, ip="10.9.9.9", text="Другая сеть: сломан бордюр на переходе.")["status"] == 201
        clock.advance(seconds=399)
        assert submit(svc, text="Третье сообщение: сломана скамейка у подъезда.")["headers"]["Retry-After"] == "1"
        clock.advance(seconds=1)
        assert submit(svc, text="Третье сообщение: сломана скамейка у подъезда.")["status"] == 201
    finally:
        svc.close()


def test_global_limit_retry_time(tmp_path, clock):
    svc = FeedbackService(tmp_path / "global.sqlite3", fixture_object_lookup, clock,
                          limits={"global_max": 2, "global_window_s": 60})
    try:
        submit(svc, ip="10.0.0.1", text="Сообщение один: яма на дороге у школы.")
        clock.advance(seconds=20)
        submit(svc, ip="10.0.0.2", text="Сообщение два: нет света у остановки.")
        limited = submit(svc, ip="10.0.0.3", text="Сообщение три: сломан павильон остановки.")
        assert limited["status"] == 429 and limited["headers"]["Retry-After"] == "40"
        assert limited["body"]["error"]["limit"] == "global" and "через 40 с" in limited["body"]["error"]["message"]
    finally:
        svc.close()


def test_replay_does_not_count_against_rate_limit(tmp_path, clock):
    svc = FeedbackService(tmp_path / "replay.sqlite3", fixture_object_lookup, clock,
                          limits={"per_sender_max": 1})
    try:
        assert submit(svc, client_request_id=REQUEST)["status"] == 201
        for _ in range(5):
            assert submit(svc, client_request_id=REQUEST)["status"] == 200
    finally:
        svc.close()


KAZAKH = "Аялдамада жарық жоқ, кешке қараңғы. Балалар мектептен қайтқанда қорқады."


def test_kazakh_text_round_trip(service):
    decomposed = unicodedata.normalize("NFD", KAZAKH)          # иная форма Юникода от клавиатуры/телефона
    response = submit(service, text=decomposed, category="lighting")
    assert response["status"] == 201
    item = queue_items(service, moderation="all")[0]
    assert item["text"] == KAZAKH and item["language"] == "kk"
    replay = submit(service, text=KAZAKH, category="lighting")
    assert replay["status"] == 409 and replay["body"]["error"]["code"] == "duplicate_warning"


def test_no_identity_tracking_in_resident_responses(service):
    response = submit(service, client_request_id=REQUEST)
    assert "Set-Cookie" not in response["headers"]
    dumped = json.dumps(response["body"], ensure_ascii=False)
    assert "127.0.0.1" not in dumped and "client" not in dumped and REQUEST not in dumped
    status = service.handle("POST", "/api/civic/v1/feedback/receipt", {},
                            {"receipt_id": response["body"]["data"]["receipt_id"]}, None, fixture_context("10.0.0.1"))
    assert "Set-Cookie" not in status["headers"]
