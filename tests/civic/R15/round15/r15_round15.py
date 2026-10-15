"""Помощники тестов R15 раунда 15: сервис роли напрямую, контекст шлюза, сотрудник R02, поиск утечек.

Сервисы раунда 15 (R16, R17, R13) устроены как «Вопрос акиму» R13: make_service(db_path).handle(method, path, query,
body, principal, context) -> {"status", "headers", "body"}. Шлюз R01 передаёт principal из сессии (без проверки CSRF)
и context с заголовками в нижнем регистре — так же их передают помощники ниже, чтобы тест видел то же, что модуль
в сборке. Сотрудник — настоящий Principal R06 (ui.civic_store.auth): CSRF проверяет сам модуль.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import json
from pathlib import Path
import time

import pytest

from r15_common import ROOT

PREFIX = "/api/civic/v2"
ASTANA = timezone(timedelta(hours=5))
CSRF = "r15-csrf-token-" + "7" * 28
STAFF_LOGIN = "r15staffmarker"   # логин-маркер: его не должно быть в ответах жителю и в журнале штаба (T-R17-07)
HOST = "127.0.0.1:8655"
ORIGIN = "http://" + HOST
YARD_ID = "yard-1026285032"      # ЖК «Инжу Арена», Нура — двор R12 из OSM (data/civic/astana/geo/yards.json)
YARD_POINT = [71.404739, 51.1111745]
MARK = "R15MARK"                 # маркер внутренних текстов: по нему ищем утечку в публичные ответы
DEVICES = tuple("r15dev-" + hashlib.sha256(f"r15-round15-{i}".encode()).hexdigest()[:24] for i in range(80))


def not_run(reason: str):
    pytest.skip("NOT_RUN: " + reason)


def xmarks(finding_id: str) -> list:
    """Пометки для pytest.param: открытая находка — [xfail(strict)], исправленная (FIXED) — [] (обычная регрессия)."""
    from r15_common import xfail
    mark = xfail(finding_id)
    return [mark] if isinstance(mark, pytest.MarkDecorator) else []


def module(name: str, role: str):
    """Модуль роли из проверяемой сборки или NOT_RUN (не FAIL), если его нет."""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        if missing and (name == missing or name.startswith(missing + ".")):
            not_run(f"нет модуля {name} ({role}) в сборке {ROOT}")
        raise


def staff_principal(*, role: str = "editor", username: str = STAFF_LOGIN, token: str = CSRF):
    """Сессия сотрудника, как её отдаёт R06 resolve_principal (CSRF-токен внутри, проверка — check_csrf)."""
    auth = module("ui.civic_store.auth", "R06")
    return auth.Principal(user_id=1, username=username, display_name="R15 Тест", role=role,
                          public_label="Сотрудник", csrf_token=token, session_hash="r15-session",
                          expires_at=time.time() + 3600)


def context(*, device=None, csrf=None, origin=True, ip="127.0.0.1", method="GET") -> dict:
    """context шлюза R01 (civic_request): origin True — свой сайт, False — чужой, None — браузер не прислал."""
    headers = {"host": HOST}
    if device:
        headers["x-birge-device"] = device
    if csrf:
        headers["x-csrf-token"] = csrf
    if origin is True:
        headers["origin"] = ORIGIN
    elif origin is False:
        headers["origin"] = "http://evil.example"
    return {"method": method, "path": "/", "headers": headers, "cookies": {}, "client_ip": ip, "host_allowed": True,
            "is_same_origin": origin, "is_https": False, "host": HOST}


class Svc:
    """Сервис роли на временной базе: вызовы от анонима, жителя (устройство) и сотрудника."""

    def __init__(self, mod, db_path, **kwargs):
        self.mod = mod
        self.db_path = Path(db_path)
        self.svc = mod.make_service(str(db_path), **kwargs)

    def call(self, method, path, body=None, *, query="", principal=None, ctx=None):
        reply = self.svc.handle(method, PREFIX + path, query, body, principal, ctx or context(method=method))
        if reply is None:
            return 404, {}
        return reply["status"], reply.get("body") or {}

    def anon(self, method, path, body=None, *, query=""):
        return self.call(method, path, body, query=query, ctx=context(method=method))

    def resident(self, method, path, body=None, *, device=DEVICES[0], query="", ip="127.0.0.1", origin=True):
        return self.call(method, path, body, query=query, ctx=context(device=device, ip=ip, origin=origin,
                                                                      method=method))

    def staff(self, method, path, body=None, *, query="", csrf=CSRF, origin=True, principal=None):
        return self.call(method, path, body, query=query, principal=principal or staff_principal(),
                         ctx=context(csrf=csrf, origin=origin, method=method))


def data(body):
    """Тело без конверта ok/data (так отвечает R09); «плоские» ответы (R13, R17) — как есть."""
    if isinstance(body, dict) and isinstance(body.get("ok"), bool) and "data" in body:
        return body["data"]
    return body


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)


def device_needles(devices) -> list:
    """Сырые id устройств и их sha256 — ни того, ни другого не должно быть в ответах (P1, P6)."""
    out = []
    for dev in devices:
        out += [dev, hashlib.sha256(dev.encode()).hexdigest()]
    return out


def leaks(obj, needles) -> list:
    text = dump(obj)
    return [n for n in needles if n and n in text]


def db_contains(db_path, needles) -> list:
    """Какие из строк лежат в файле SQLite как есть (id устройства должен храниться только солёным хэшем, P6)."""
    found = set()
    for path in (Path(db_path), Path(str(db_path) + "-wal")):
        if path.exists():
            raw = path.read_bytes()
            found |= {n for n in needles if n.encode("utf-8") in raw}
    return sorted(found)


def iso_in(days: float = 0, hours: float = 0) -> str:
    return (datetime.now(ASTANA) + timedelta(days=days, hours=hours)).replace(microsecond=0).isoformat()


def ids_in(obj, prefix: str) -> set:
    """Все значения полей id с префиксом (i-, inc-, m-, t-, o-) в любом месте ответа."""
    out = set()

    def walk(node):
        if isinstance(node, dict):
            value = node.get("id")
            if isinstance(value, str) and value.startswith(prefix):
                out.add(value)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(obj)
    return out


# ---------------------------------------------------------------- синтетические личные данные (не настоящие)
def iin(base11: str = "90010130012") -> str:
    """ИИН с верной контрольной цифрой (веса 1..11, затем 3..11,1,2). Дата 1990-01-01, номер выдуман."""
    digits = [int(c) for c in base11]
    check = sum(d * w for d, w in zip(digits, range(1, 12))) % 11
    if check == 10:
        check = sum(d * w for d, w in zip(digits, (3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2))) % 11
    assert check != 10, "выберите другой номер"
    return base11 + str(check)


def luhn(base15: str = "440043012345678") -> str:
    """Номер карты с верной контрольной цифрой Луна (номер выдуман)."""
    total = 0
    for i, ch in enumerate(reversed(base15)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            d -= 9 if d > 9 else 0
        total += d
    return base15 + str((10 - total % 10) % 10)


IIN = iin()
CARD = luhn()
CARD_SPACED = " ".join(CARD[i:i + 4] for i in range(0, 16, 4))
# Вид ПДн -> (текст, строки, которых не должно быть в публичной выдаче).
PII = {
    "phone": ("Звоните +7 701 123 45 67 вечером", ("701 123 45 67", "7011234567")),
    "phone_dashes": ("Телефон старшего 8-701-123-45-67", ("701-123-45-67", "7011234567")),
    "iin": (f"Мой ИИН {IIN}, помогите", (IIN,)),
    "email": ("Пишите на a.k.r15@mail.kz", ("a.k.r15@mail.kz",)),
    "card": (f"Скинемся на карту {CARD_SPACED}", (CARD_SPACED, CARD)),
}
XSS = '<img src=x onerror="window.__r15xss=1">'
