"""R15 раунд 15+ (П3) · R04 «ИИ-разбор пачки обращений» — THREATS_R15 §11a, T-R04-20…30.

Контракт R04 (INTEGRATION R04 п. 9, 16 окт 17:40): from ui.civic_ml_api import intake_analyze, intake_sample,
intake_commit. Шлюз R01 зовёт их с телом запроса целиком (body=…): POST intake/analyze {texts | sample}, GET intake/sample,
POST intake/commit {batch_id, task_ids}; staff=True у всех трёх — это проверяет test_r15_round15_gateway.py
(CONTRACT_STAFF: таблица шлюза и HTTP без сессии), здесь — сами функции, как их вызовет шлюз.
П3 для R15: «только сотрудник, пределы размера, тексты не уходят наружу, личные данные не в журнале и не на экране итога».
- пределы 500 текстов / 300 КБ — отказ сразу (ValueError -> 400), в тексте отказа нет текстов жителя (T-R04-21);
- плохие типы и пустая пачка — 400, не 500; имя примера — из своего списка, не путь к файлу (T-R04-21, T-R04-30);
- без сети, без внешних процессов и без записи файлов — и с ключом языковой модели в окружении (T-R04-22);
- ПДн из текстов — нигде в ответе разбора (итог, задачи, «почему так», адрес) (T-R04-23), не в журнале и не в выводе
  процесса (T-R04-24); у задач нет готовой разметки — экран выводит текстом, это проба r15_round15.cjs (T-R04-27);
- враждебные 300 КБ и 500 похожих обращений об одном месте — быстро (T-R04-28); пример «за ночь» — demo (T-R04-26);
- commit (хранилище R09 на временной базе): выдуманный batch_id и плохие поля — 4xx; задача не из пачки не создаётся;
  повтор того же batch_id — без новых жалоб; жалобы demo и без ПДн; задача без места не создаётся (T-R04-25, T-R04-29).
Нет функции — NOT_RUN. Все тексты выдуманы: номер телефона, ИИН (верная контрольная цифра), карта и e-mail — не чьи-то.
"""

from __future__ import annotations

import builtins
from contextlib import closing
import gc
import importlib
import inspect
import io
import logging
import os
import re
import socket
import sqlite3
import subprocess
import time

import pytest

from r15_round15 import CARD, CARD_SPACED, IIN, XSS, data, dump, module, not_run

PHONE = "+7 701 123 45 67"
EMAIL = "r15.resident@mail.kz"
# Места — из индекса R12 (web/civic/map/search_index.json: «Двор: ЖК Инжу Арена», «улица Кенесары»): по ним commit
# создаст жалобы. Последний текст — без места («адрес уточнить»): по нему жалоба не создаётся (T-R04-29).
PII_TEXTS = [
    f"Не горит фонарь во дворе ЖК Инжу Арена, звоните {PHONE}",
    f"Яма на дороге на улице Кенесары, мой ИИН {IIN}, прошу исправить",
    f"Течёт вода из люка на улице Кенесары, пишите на {EMAIL}",
    f"Мусор не вывозят во дворе ЖК Инжу Арена, переведу на карту {CARD_SPACED} за уборку",
    "Сломана скамейка во дворе ЖК Инжу Арена",
    "Не работает светофор, стоим третий день",
]
PII_NEEDLES = [PHONE, "701 123 45 67", "7011234567", IIN, EMAIL, "r15.resident", CARD_SPACED, CARD]
PII_DIGITS = [re.sub(r"\D", "", s) for s in (PHONE, IIN, CARD)]
LLM_ENV = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CIVIC_LLM_API_KEY", "CIVIC_ASSISTANT_API_KEY", "BIRGE_LLM_API_KEY")
LOGGERS = ("ui", "ui.civic_ml_api", "ui.civic_ml_api.intake", "civic_ml_api", "ml", "ml.civic_dedup")


def _fn(name: str):
    """Функция R04 из ui.civic_ml_api (контракт п. 9.1) или из ui.civic_ml_api.intake; нет — NOT_RUN."""
    api = module("ui.civic_ml_api", "R04")
    fn = getattr(api, name, None)
    if not callable(fn):
        try:
            fn = getattr(importlib.import_module("ui.civic_ml_api.intake"), name, None)
        except ModuleNotFoundError as exc:
            if exc.name != "ui.civic_ml_api.intake":
                raise
    if not callable(fn):
        not_run(f"в ui.civic_ml_api нет {name} (R04, П3, INTEGRATION R04 п. 9.1)")
    return fn


def _via_body(fn):
    """Вызов, как у шлюза (п. 9.2: arguments() передаёт тело целиком, body=…); без параметра body — по именам полей."""
    params = inspect.signature(fn).parameters

    def call(body):
        if "body" in params:
            kwargs = {"body": body}
            for name, param in params.items():
                if (name != "body" and param.default is inspect.Parameter.empty
                        and param.kind in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY)):
                    kwargs[name] = body.get(name) if isinstance(body, dict) else None
            return fn(**kwargs)
        return fn(**{key: value for key, value in (body or {}).items() if key in params})
    return call


def _gateway(call):
    """(код, тело) — что ответит шлюз R01 на вызов функции (web_server, CivicV2Gateway): исключение с status — этот код,
    LookupError — 404, ValueError — 400 и str(exc)[:300] клиенту, PermissionError — 403, любое другое — 500."""
    try:
        out = call()
    except PermissionError as exc:
        return 403, str(exc)
    except Exception as exc:  # noqa: BLE001 — так же широко, как шлюз
        status = getattr(exc, "status", None)
        if isinstance(status, int) and not isinstance(status, bool) and 400 <= status <= 599:
            return status, str(getattr(exc, "message", None) or exc)[:300]
        if isinstance(exc, LookupError):
            return 404, "Запись не найдена."
        if isinstance(exc, ValueError):
            return 400, str(exc)[:300]
        return 500, f"{type(exc).__name__}: {str(exc)[:200]}"
    if isinstance(out, tuple) and len(out) == 2 and isinstance(out[0], int) and not isinstance(out[0], bool):
        return out
    return 200, out


def _ok(reply) -> dict:
    status, body = reply
    assert status == 200, f"разбор: {status} {str(body)[:200]}"
    body = data(body)
    assert isinstance(body, dict) and isinstance(body.get("tasks"), list), f"ответ без tasks: {str(body)[:200]}"
    return body


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield str(key)
            yield from _strings(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            yield from _strings(value)


def _pii_in(obj) -> list:
    """ПДн в объекте: строки как есть и 7+ цифр подряд из номера, ИИН или карты в любой его строке (маска — целиком)."""
    text = dump(obj)
    found = [needle for needle in PII_NEEDLES if needle in text]
    for value in _strings(obj):
        digits = re.sub(r"\D", "", value)
        if any(secret[i:i + 7] in digits for secret in PII_DIGITS for i in range(len(secret) - 6)):
            found.append(f"7+ цифр номера/ИИН/карты в «{value[:60]}»")
    return found


def _benign(n: int) -> list:
    base = ["Не горит фонарь у дома {i} на улице Кенесары", "Яма на дороге у остановки Кенесары көшесі, номер {i}",
            "Не вывозят мусор во дворе ЖК Инжу Арена, подъезд {i}", "Сломана скамейка в сквере, место {i}"]
    return [base[i % len(base)].format(i=i + 1) for i in range(n)]


@pytest.fixture(scope="module")
def analyze():
    return _fn("intake_analyze")


@pytest.fixture(scope="module")
def run(analyze):
    return _via_body(analyze)


# ------------------------------------------------------------------ пределы и ввод (T-R04-21, T-R04-30)
TOO_BIG = [
    ("501 текст", {"texts": _benign(501)}),
    ("330 КБ латиницей", {"texts": ["x" * 1100] * 300}),
    ("330 тыс. знаков кириллицей", {"texts": ["я" * 1100] * 300}),
    ("одна строка 400 КБ", {"texts": "x" * 400_000}),
    ("[{id, text}] на 330 КБ", {"texts": [{"id": f"r15-{i}", "text": "x" * 1100} for i in range(300)]}),
]


def test_batch_size_limits_are_refused_fast(run, analyze):
    """T-R04-21: больше 500 текстов или 300 КБ — отказ сразу (без разбора), и в теле запроса, и прямым вызовом."""
    started = time.perf_counter()
    for name, body in TOO_BIG:
        status, _reply = _gateway(lambda b=body: run(b))
        assert status in (400, 413), f"{name}: {status} — предел П3 500 текстов / 300 КБ, ждём 400"
    status, _reply = _gateway(lambda: analyze(_benign(501)))
    assert status in (400, 413), f"analyze(501 текст): {status}"
    assert time.perf_counter() - started < 3, "отказ по размеру занял больше 3 с — пачка разбиралась"


def test_refusal_message_does_not_quote_texts(run):
    """T-R04-21/23: текст отказа шлюз отдаёт клиенту (str(exc)[:300]) — в нём нет текстов жителей и их ПДн."""
    for body in ({"texts": [PII_TEXTS[0]] * 501}, {"texts": [PII_TEXTS[1] + " " + "x" * 400_000]},
                 {"texts": [{"id": "r15-1", "text": PII_TEXTS[2] + "я" * 310_000}]}):
        status, message = _gateway(lambda b=body: run(b))
        assert status in (400, 413), status
        quoted = [t[:30] for t in PII_TEXTS if t[:30] in str(message)]
        assert not _pii_in(message) and not quoted, f"в отказе: {str(message)[:200]}"


MUST_400 = [
    ("пустое тело", {}), ("пустой список", {"texts": []}), ("число", {"texts": 42}), ("словарь", {"texts": {"a": "b"}}),
    ("None в списке", {"texts": [None]}), ("число в списке", {"texts": [42]}), ("список в списке", {"texts": [["x"]]}),
    ("text не строка", {"texts": [{"id": "r15-1", "text": None}]}),
    ("text — список", {"texts": [{"id": "r15-1", "text": ["Яма на дороге"]}]}),
    ("sample — число", {"sample": 1}),
]
NOT_500 = [("sample — неизвестный", {"sample": "r15-unknown"}),   # 400 или 404 — как решит R04
           ("id — словарь", {"texts": [{"id": {"$ne": 1}, "text": "Яма на дороге"}]}),
           ("id на 5000 знаков", {"texts": [{"id": "r" * 5000, "text": "Яма на дороге"}]}),
           ("texts и sample вместе", {"texts": ["Яма на дороге"], "sample": "night"})]


@pytest.mark.parametrize("name,body", MUST_400 + NOT_500, ids=[n for n, _b in MUST_400 + NOT_500])
def test_bad_input_is_400_not_500(run, name, body):
    """T-R04-21: неверный ввод — понятный 400 (шлюз: ValueError), а не 500 с трассой в журнале."""
    status, reply = _gateway(lambda: run(body))
    if (name, body) in MUST_400:
        assert status == 400, (name, status, str(reply)[:200])
    else:
        assert status < 500, (name, status, str(reply)[:200])


TRAVERSAL = ["../../../../etc/passwd", "..\\..\\..\\windows\\win.ini", "night/../../../../etc/passwd", "/etc/passwd",
             "night\x00.json", "%2e%2e%2f%2e%2e%2fetc%2fpasswd"]


@pytest.mark.parametrize("name", TRAVERSAL)
def test_sample_name_is_not_a_file_path(run, name, monkeypatch):
    """T-R04-30: имя примера — только из списка R04 («night»); путь или «../» не читает файл с диска (400/404)."""
    sample = _fn("intake_sample")
    opened = []
    real_open = io.open

    def watched(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", watched)
    monkeypatch.setattr(io, "open", watched)
    for reply in (_gateway(lambda: sample(name)), _gateway(lambda: run({"sample": name}))):
        status, body = reply
        assert status in (400, 404), (name, status, str(body)[:200])
        assert "root:" not in dump(body) and "[fonts]" not in dump(body), (name, str(body)[:200])
    monkeypatch.undo()
    outside = [p for p in opened if "passwd" in p or "win.ini" in p]
    assert not outside, f"имя примера открыло файл: {outside}"


# ------------------------------------------------------------------ тексты не уходят наружу (T-R04-22)
def test_analyze_stays_in_process(run, monkeypatch):
    """T-R04-22: разбор в процессе — без соединений, внешних процессов и записи файлов, и с ключом модели в окружении."""
    attempts, writes = [], []
    run({"texts": _benign(4)})   # модели и индексы загружаются при первом вызове (чтение) — это до проверки

    def blocked(kind, what):
        attempts.append((kind, str(what)[:80]))
        raise OSError("R15: сеть и процессы запрещены в тесте")

    class NoPopen(subprocess.Popen):
        def __init__(self, args, *a, **k):  # noqa: D401 — заглушка
            blocked("process", args)

    real_open, real_connect = io.open, sqlite3.connect

    def watched_open(file, mode="r", *args, **kwargs):
        if any(flag in str(mode) for flag in "wax+"):
            writes.append(str(file))
        return real_open(file, mode, *args, **kwargs)

    def watched_sqlite(database, *args, **kwargs):
        writes.append(f"sqlite:{database}")
        return real_connect(database, *args, **kwargs)

    for name in LLM_ENV:
        monkeypatch.setenv(name, "r15-fake-key-not-real")
    with monkeypatch.context() as patch:
        patch.setattr(socket.socket, "connect", lambda self, addr: blocked("connect", addr))
        patch.setattr(socket.socket, "connect_ex", lambda self, addr: blocked("connect", addr))
        patch.setattr(socket, "create_connection", lambda addr, *a, **k: blocked("connect", addr))
        patch.setattr(socket, "getaddrinfo", lambda host, *a, **k: blocked("dns", host))
        patch.setattr(subprocess, "Popen", NoPopen)
        patch.setattr(os, "system", lambda cmd: blocked("process", cmd))
        patch.setattr(builtins, "open", watched_open)
        patch.setattr(io, "open", watched_open)
        patch.setattr(sqlite3, "connect", watched_sqlite)
        result = _ok(_gateway(lambda: run({"texts": _benign(30) + PII_TEXTS})))
        sample = _gateway(lambda: run({"sample": "night"}))
    assert result["tasks"], "разбор без сети не дал задач"
    assert sample[0] in (200, 404), f"пример «за ночь» без сети: {sample[0]} {str(sample[1])[:200]}"
    assert not attempts, f"разбор пытался выйти наружу: {attempts[:3]}"
    assert not writes, f"разбор писал на диск (тексты жителей с ПДн): {writes[:3]}"


# ------------------------------------------------------------------ ПДн не на экране итога и не в журнале (T-R04-23/24)
def test_analysis_has_no_personal_data(run):
    """T-R04-23: телефон, ИИН, e-mail и карта из текстов — нигде в ответе разбора (итог, задачи, «почему так», адрес,
    тексты для экрана): наружу — только тексты после moderate() (контракт п. 9.1)."""
    result = _ok(_gateway(lambda: run({"texts": PII_TEXTS})))
    assert not _pii_in(result), f"ПДн в ответе разбора: {_pii_in(result)[:4]}"
    as_dicts = _ok(_gateway(lambda: run({"texts": [{"id": f"r15-{i}", "text": t} for i, t in enumerate(PII_TEXTS)]})))
    assert not _pii_in(as_dicts), f"ПДн в ответе разбора [{{id, text}}]: {_pii_in(as_dicts)[:4]}"


def test_log_and_console_have_no_texts_or_personal_data(run, caplog, capsys):
    """T-R04-24: в журнале сервера и в выводе процесса — числа и id, не тексты обращений и не ПДн (и при отказе)."""
    caplog.set_level(logging.DEBUG)
    extra = [logging.getLogger(name) for name in LOGGERS]
    for logger in extra:
        logger.addHandler(caplog.handler)
    try:
        run({"texts": PII_TEXTS})
        _gateway(lambda: run({"texts": PII_TEXTS * 90}))            # 540 — отказ по пределу
        _gateway(lambda: run({"texts": PII_TEXTS + [None]}))        # плохой элемент — отказ
    finally:
        for logger in extra:
            logger.removeHandler(caplog.handler)
    out = capsys.readouterr()
    for where, text in (("журнал", caplog.text), ("stdout", out.out), ("stderr", out.err)):
        leaked = [needle for needle in PII_NEEDLES if needle in text]
        raw = [t[:40] for t in PII_TEXTS if t[:40] in text]
        assert not leaked and not raw, f"{where}: ПДн {leaked}, тексты {raw[:2]}"


def test_text_without_place_gets_no_guessed_point(run):
    """T-R04-29: место — только из индекса R12; у текста без места — «адрес уточнить», точка и цель null (не угадываем:
    commit создаёт жалобы только с точкой, угаданная точка — жалоба «не там»)."""
    texts = [{"id": f"r15-{i}", "text": text} for i, text in enumerate(PII_TEXTS)]
    result = _ok(_gateway(lambda: run({"texts": texts})))
    alone = [task for task in result["tasks"] if (task.get("text_ids") or []) == [f"r15-{len(PII_TEXTS) - 1}"]]
    if not alone:
        not_run("нет отдельной задачи для текста без места (text_ids) — проверить нельзя")
    for task in alone:
        assert task.get("point") is None and task.get("target") is None, (task.get("point"), task.get("target"))


def test_tasks_carry_no_ready_markup(run):
    """T-R04-27: HTML-нагрузка в тексте — данные, а не разметка: у задач нет полей *html*, экран выводит текстом."""
    result = _ok(_gateway(lambda: run({"texts": [f"Не горит фонарь {XSS} во дворе ЖК Инжу Арена",
                                                 "Яма на дороге на улице Кенесары"]})))
    for task in result["tasks"]:
        assert not [key for key in task if "html" in str(key).lower()], task
    assert not [key for key in result if "html" in str(key).lower()], list(result)


HOSTILE = (["8 " * 450, "@" * 900, "(" * 900, "a." * 450] * 72)[:290]    # ≈ 261 КБ — в пределах П3
SAME_PLACE = [f"Яма на дороге на улице Кенесары у дома {i}, " + "колёса бьём каждый день, " * 8 for i in range(500)]


@pytest.mark.parametrize("name,texts", [("hostile", HOSTILE), ("same-place-500", SAME_PLACE)])
def test_large_batch_is_still_fast(run, name, texts):
    """T-R04-28: 260 КБ враждебного текста (цифры через пробел, «@», скобки) и 500 похожих обращений об одном месте
    (повторы попарно) не занимают сервер надолго; отказ по пределу — тоже ответ."""
    gc.collect()
    started = time.perf_counter()
    status, reply = _gateway(lambda: run({"texts": texts}))
    spent = time.perf_counter() - started
    assert status in (200, 400), (name, status, str(reply)[:200])
    assert spent < 30, f"{name}: {spent:.1f} с"


def test_sample_is_demo():
    """T-R04-26: пример «обращения за ночь» помечен demo: true — и сам набор, и его разбор."""
    sample = _fn("intake_sample")
    status, body = _gateway(lambda: sample())
    assert status == 200, (status, str(body)[:200])
    assert data(body).get("demo") is True, "пример «за ночь» без demo: true"
    analysis = _ok(_gateway(lambda: _via_body(_fn("intake_analyze"))({"sample": "night"})))
    assert analysis.get("demo") is True, "разбор примера «за ночь» без demo: true"


# ------------------------------------------------------------------ commit (T-R04-25, T-R04-29)
@pytest.fixture()
def store(tmp_path):
    r09 = module("ui.civic_feedback.v2", "R09")
    api = module("ui.civic_ml_api", "R04")
    connect = getattr(api, "connect_store", None)
    if not callable(connect):
        not_run("в ui.civic_ml_api нет connect_store — commit без хранилища R09 не проверить")
    db_path = tmp_path / "civic.sqlite3"
    st = r09.ComplaintStore(str(db_path))
    params = inspect.signature(connect).parameters
    kwargs = {key: value for key, value in (("warm", False), ("feedback_path", tmp_path / "dedup_feedback.jsonl"))
              if key in params}
    connect(st, **kwargs)
    try:
        yield st, db_path
    finally:
        reset = getattr(api, "reset", None)
        if callable(reset):
            reset()
        st.close()


def _count(db_path) -> int:
    with closing(sqlite3.connect(db_path)) as db:
        return db.execute("SELECT COUNT(*) FROM complaints_v2").fetchone()[0]


@pytest.fixture()
def commit():
    return _via_body(_fn("intake_commit"))


BAD_COMMIT = [{}, {"batch_id": None}, {"batch_id": ["b-r15"]}, {"batch_id": "b" * 5000},
              {"batch_id": "b-r15-unknown-0001", "task_ids": "t-1"},
              {"batch_id": "b-r15-unknown-0001", "task_ids": [{"$ne": 1}]},
              {"batch_id": "b-r15-unknown-0001", "task_ids": ["t-r15-x"]}]


def test_commit_with_unknown_batch_or_bad_fields_is_refused(commit, store):
    """T-R04-25: выдуманный batch_id, чужие или кривые поля — 4xx (404 «разбор устарел» или 400), не 200 и не 500."""
    _st, db_path = store
    for body in BAD_COMMIT:
        status, reply = _gateway(lambda b=body: commit(b))
        assert 400 <= status < 500, (body if len(str(body)) < 80 else "batch_id 5000", status, str(reply)[:200])
    assert _count(db_path) == 0, "отказной commit создал жалобы"


def test_commit_creates_demo_records_once_without_personal_data(run, commit, store):
    """T-R04-25/29: commit пишет только функцией R09 — жалобы demo и без ПДн; задача не из пачки и задача без места
    не создаются; повтор того же batch_id не создаёт новых жалоб (request_id «in-<batch>-<n>»)."""
    st, db_path = store
    analysis = _ok(_gateway(lambda: run({"texts": PII_TEXTS})))
    batch = analysis.get("batch_id")
    if not batch:
        not_run("ответ разбора без batch_id — commit проверить нельзя")
    tasks = analysis["tasks"]
    task_ids = [task["id"] for task in tasks]
    unplaced = {task["id"] for task in tasks if not task.get("point")}
    if len(unplaced) == len(tasks):
        not_run("ни одна задача пачки R15 не получила места — commit проверить нельзя")
    status, reply = _gateway(lambda: commit({"batch_id": batch, "task_ids": ["t-r15-not-in-batch"]}))
    if status == 503:
        not_run("intake_commit: 503 — хранилище R09 не подключено")
    assert status < 500 and _count(db_path) == 0, f"задача не из пачки: {status}, жалоб {_count(db_path)}"
    status, first = _gateway(lambda: commit({"batch_id": batch, "task_ids": task_ids}))
    assert status in (200, 201), (status, str(first)[:200])
    first = data(first)
    records = first.get("records") or []
    created = [r.get("complaint_id") for r in records if isinstance(r, dict) and r.get("complaint_id")]
    after = _count(db_path)
    assert after >= 1 and created, f"commit не создал жалоб: {str(first)[:200]}"
    assert not {r.get("task_id") for r in records if isinstance(r, dict)} & unplaced, \
        "жалоба создана по задаче без места — точку угадали (T-R04-29)"
    assert not _pii_in(first), f"ПДн в ответе commit: {_pii_in(first)[:3]}"
    for complaint_id in created:
        record = st.get(complaint_id)
        assert record is not None, complaint_id
        assert record.get("demo") is True, f"{complaint_id}: жалоба из разбора не demo"
        assert not _pii_in(record), f"{complaint_id}: ПДн в жалобе: {_pii_in(record)[:3]}"
    status, second = _gateway(lambda: commit({"batch_id": batch, "task_ids": task_ids}))
    assert status in (200, 201, 409), (status, str(second)[:200])
    assert _count(db_path) == after, f"повторный commit того же batch_id создал {_count(db_path) - after} жалоб"
