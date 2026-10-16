"""R15 раунд 15+ (П3) · R04 «ИИ-разбор пачки обращений» (ui.civic_ml_api.intake) — THREATS_R15 §11a, T-R04-20…29.

П3: analyze(texts) — в процессе, без сети: модерация -> категория -> службы -> место -> повторы -> срочность -> задачи;
предел — 500 текстов / 300 КБ; маршруты intake/analyze, intake/sample, intake/commit — только сотрудник + CSRF; commit пишет
записи только функциями R09, повтор того же batch_id — без дублей, у примера demo: true.
Проверяем (то, что относится к безопасности):
- пределы размера — отказ сразу, без расчёта (T-R04-21);
- без сети: разбор при запрещённых соединениях работает и не пытается соединиться — и с ключом модели в окружении (T-R04-22);
- ПДн из текстов не попадают в задачи и итог (T-R04-23); тексты и ПДн — не в журнал (T-R04-24);
- в задачах нет готовой разметки (вывод — текстом, браузер — r15_round15.cjs) (T-R04-27); враждебные 300 КБ — быстро (T-R04-28);
- сервис (если есть make_service): только сотрудник с CSRF и своим Origin (T-R04-20), commit без дублей и не по чужому
  batch_id (T-R04-25), пример — demo (T-R04-26).
Нет модуля или функции — NOT_RUN. Все тексты выдуманы: номера телефонов, ИИН (верная контрольная цифра) и карта — не чьи-то.
"""

from __future__ import annotations

import gc
import json
import logging
import socket
import time

import pytest

from r15_round15 import CARD, DEVICES, IIN, Svc, XSS, data, dump, module, not_run

PHONE = "+7 701 123 45 67"
EMAIL = "r15.resident@mail.kz"
PII_TEXTS = [
    f"Не горит фонарь у дома 5 по улице Кенесары, звоните {PHONE}",
    f"Яма на дороге у остановки, мой ИИН {IIN}, прошу исправить",
    f"Течёт вода в подъезде, пишите на {EMAIL}",
    f"Мусор не вывозят третий день, переведу на карту {CARD} за уборку",
    "Сломана скамейка во дворе ЖК Инжу Арена",
    "Не работает светофор на пересечении Туран и Сыганак",
]
PII_NEEDLES = [PHONE, "701 123 45 67", "7011234567", IIN, EMAIL, CARD, CARD.replace(" ", "")]
TASK_TEXT_FIELDS = ("title_ru", "title_kk", "why_ru", "why_kk", "address_text", "urgent_why")
LLM_ENV = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CIVIC_LLM_API_KEY", "CIVIC_ASSISTANT_API_KEY", "BIRGE_LLM_API_KEY")


@pytest.fixture(scope="module")
def intake():
    return module("ui.civic_ml_api.intake", "R04")


@pytest.fixture(scope="module")
def analyze(intake):
    fn = getattr(intake, "analyze", None)
    if not callable(fn):
        not_run("в ui.civic_ml_api.intake нет analyze(texts) (R04, П3)")
    return fn


def _refused(call) -> bool:
    """Отказ ввода: ValueError, исключение со status 4xx или ответ с ошибкой 4xx (TypeError — это 500 у шлюза, не отказ)."""
    try:
        out = call()
    except ValueError:
        return True
    except Exception as exc:  # noqa: BLE001
        status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
        return isinstance(status, int) and 400 <= status < 500
    if isinstance(out, tuple) and out and isinstance(out[0], int):
        return 400 <= out[0] < 500
    if isinstance(out, dict):
        status = out.get("status")
        return bool(out.get("error")) or (isinstance(status, int) and 400 <= status < 500)
    return False


def _result(out) -> dict:
    """Ответ analyze: dict {summary, tasks, …} или (status, body) / {"ok", "data"}."""
    if isinstance(out, tuple) and len(out) == 2:
        out = out[1]
    out = data(out)
    assert isinstance(out, dict) and "tasks" in out, f"analyze вернул не {{summary, tasks}}: {str(out)[:200]}"
    return out


def _task_texts(result) -> str:
    parts = [json.dumps(result.get("summary") or {}, ensure_ascii=False)]
    for task in result.get("tasks") or []:
        parts += [str(task.get(field) or "") for field in TASK_TEXT_FIELDS]
    return "\n".join(parts)


def _benign(n: int) -> list:
    base = ["Не горит фонарь у дома {i} на улице Кенесары", "Яма на дороге у остановки Байтерек, номер {i}",
            "Не вывозят мусор во дворе дома {i}", "Сломана скамейка в сквере, место {i}"]
    return [base[i % len(base)].format(i=i + 1) for i in range(n)]


def test_batch_size_limits_are_enforced_fast(analyze):
    """T-R04-21: больше 500 текстов или больше 300 КБ — отказ сразу (без разбора)."""
    started = time.perf_counter()
    assert _refused(lambda: analyze(_benign(501))), "501 текст принят — предел П3 500"
    assert _refused(lambda: analyze(["x" * 1100] * 300)), "330 КБ приняты — предел П3 300 КБ"
    assert time.perf_counter() - started < 3, "отказ по размеру занял больше 3 с — пачка разбиралась"


def test_analyze_makes_no_network_connections(analyze, monkeypatch):
    """T-R04-22: разбор в процессе, без сети — даже если в окружении есть ключ языковой модели."""
    attempts = []

    def blocked(*args, **kwargs):
        attempts.append(args[1:2] or kwargs.get("address"))
        raise OSError("R15: сеть запрещена в тесте")

    monkeypatch.setattr(socket.socket, "connect", lambda self, addr: blocked(self, addr))
    monkeypatch.setattr(socket.socket, "connect_ex", lambda self, addr: blocked(self, addr))
    monkeypatch.setattr(socket, "create_connection", lambda addr, *a, **k: blocked(None, addr))
    for name in LLM_ENV:
        monkeypatch.setenv(name, "r15-fake-key-not-real")
    result = _result(analyze(_benign(30)))
    assert result.get("tasks"), "разбор без сети не дал задач"
    assert not attempts, f"разбор пытался соединиться: {attempts[:3]}"


def test_tasks_and_summary_do_not_echo_personal_data(analyze):
    """T-R04-23: телефон, ИИН, e-mail и карта из текстов — не в заголовках, «почему так», адресе и итоге."""
    text = _task_texts(_result(analyze(PII_TEXTS)))
    leaked = [needle for needle in PII_NEEDLES if needle in text]
    assert not leaked, f"ПДн в задачах или итоге: {leaked}"


def test_log_has_no_texts_or_personal_data(analyze, caplog):
    """T-R04-24: в журнале сервера — числа и id, не тексты обращений и не ПДн."""
    caplog.set_level(logging.DEBUG)
    analyze(PII_TEXTS)
    leaked = [needle for needle in PII_NEEDLES if needle in caplog.text]
    raw = [t[:40] for t in PII_TEXTS if t[:40] in caplog.text]
    assert not leaked and not raw, f"в журнале: ПДн {leaked}, тексты {raw[:2]}"


def test_tasks_carry_no_ready_markup(analyze):
    """T-R04-27: HTML-нагрузка в тексте — данные, а не разметка: у задач нет полей *html*, экран выводит текстом."""
    result = _result(analyze([f"Не горит фонарь {XSS}", "Яма на дороге у остановки"]))
    for task in result.get("tasks") or []:
        assert not [k for k in task if "html" in str(k).lower()], task


def test_hostile_batch_is_still_fast(analyze):
    """T-R04-28: 300 КБ враждебного текста (цифры через пробел, «@», скобки) не занимают сервер надолго."""
    hostile = (["8 " * 450, "@" * 900, "(" * 900, "a." * 450] * 72)[:290]
    gc.collect()
    started = time.perf_counter()
    try:
        analyze(hostile)
    except ValueError:
        pass
    assert time.perf_counter() - started < 30, "враждебная пачка разбиралась дольше 30 с"


# ------------------------------------------------------------------ сервис (маршруты intake/* через make_service)
@pytest.fixture()
def svc(intake, tmp_path):
    if not callable(getattr(intake, "make_service", None)):
        not_run("в ui.civic_ml_api.intake нет make_service (маршруты intake/* — у шлюза R01 иначе)")
    return Svc(intake, tmp_path / "civic.sqlite3")


ROUTES = [("POST", "/intake/analyze", {"sample": "night"}), ("GET", "/intake/sample", None),
          ("POST", "/intake/commit", {"batch_id": "b-r15probe0001", "task_ids": ["t-1"]})]


@pytest.mark.parametrize("who", ["anon", "resident", "no_csrf", "bad_csrf", "cross_origin"])
@pytest.mark.parametrize("method,path,body", ROUTES, ids=[r[1] for r in ROUTES])
def test_intake_routes_need_staff_with_csrf(svc, who, method, path, body):
    """T-R04-20: разбор и создание задач — только сотрудник с сессией, CSRF и своим Origin."""
    if who == "anon":
        status, reply = svc.anon(method, path, body)
    elif who == "resident":
        status, reply = svc.resident(method, path, body, device=DEVICES[40])
    elif who == "no_csrf":
        status, reply = svc.staff(method, path, body, csrf=None)
    elif who == "bad_csrf":
        status, reply = svc.staff(method, path, body, csrf="r15-wrong-csrf-" + "0" * 28)
    else:
        status, reply = svc.staff(method, path, body, origin=False)
    if method == "GET" and who in ("no_csrf", "bad_csrf", "cross_origin"):
        assert status in (200, 401, 403), (who, status)   # чтение сотрудника — по сессии (как R01 5529d819)
        return
    assert status in (401, 403), (who, method, path, status, dump(reply)[:200])


def _staff_analyze(svc):
    status, reply = svc.staff("POST", "/intake/analyze", {"sample": "night"})
    if status == 404:
        not_run("сервис intake не знает маршрута analyze")
    assert status == 200, (status, dump(reply)[:200])
    body = data(reply)
    batch = body.get("batch_id") or (body.get("batch") or {}).get("id")
    if not batch:
        not_run("ответ analyze без batch_id — commit проверить нельзя")
    return body, batch


def test_sample_is_demo_and_commit_is_idempotent(svc):
    """T-R04-25/26: пример «за ночь» — demo; повторный commit того же batch_id не создаёт второй набор записей."""
    body, batch = _staff_analyze(svc)
    assert body.get("demo") is True, "пример «обращения за ночь» без demo: true"
    task_ids = [t["id"] for t in body.get("tasks") or []][:3]
    first_status, first = svc.staff("POST", "/intake/commit", {"batch_id": batch, "task_ids": task_ids})
    if first_status in (404, 503):
        not_run(f"commit недоступен ({first_status}): R09 нет в этой сборке")
    assert first_status in (200, 201), (first_status, dump(first)[:200])
    second_status, second = svc.staff("POST", "/intake/commit", {"batch_id": batch, "task_ids": task_ids})
    assert second_status in (200, 201, 409), second_status
    ids_first = {str(x) for x in (data(first).get("created") or data(first).get("records") or []) if x}
    ids_second = {str(x) for x in (data(second).get("created") or data(second).get("records") or []) if x}
    assert second_status == 409 or ids_second <= ids_first, f"повторный commit создал новые записи: {ids_second - ids_first}"


def test_commit_with_unknown_batch_is_refused(svc):
    """T-R04-25: выдуманный batch_id или task_ids не из пачки — отказ, не 200 и не 500."""
    status, _reply = svc.staff("POST", "/intake/commit", {"batch_id": "b-r15-unknown-0001", "task_ids": ["t-r15-x"]})
    assert status in (400, 404, 409, 422), status
