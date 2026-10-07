"""Первый checkpoint R06: сохранение, receipt, pending не публичен."""

from r06_helpers import public_list, queue_items, submit


def test_submit_saves_message_and_returns_receipt_without_personal_data(service):
    response = submit(service)
    assert response["status"] == 201
    data = response["body"]["data"]
    assert data["moderation"] == "pending"
    assert data["receipt_id"].startswith("fbr_")
    assert data["official_registration"] is False
    assert "официальная регистрация" in data["notice"].lower()
    # Receipt не повторяет текст, IP или служебные поля.
    assert "text" not in data and "client_ip" not in data and "client_hash" not in data
    assert len(queue_items(service)) == 1


def test_pending_message_is_not_in_public_list(service):
    assert submit(service)["status"] == 201
    response = public_list(service)
    assert response["status"] == 200
    assert response["body"]["data"]["items"] == []


def test_message_survives_service_restart(tmp_path, clock):
    from ui.civic_feedback import FeedbackService
    from ui.civic_feedback.fixtures import fixture_object_lookup
    path = tmp_path / "restart.sqlite3"
    first = FeedbackService(path, fixture_object_lookup, clock)
    assert submit(first)["status"] == 201
    first.close()
    second = FeedbackService(path, fixture_object_lookup, clock)
    try:
        assert len(queue_items(second)) == 1
    finally:
        second.close()
