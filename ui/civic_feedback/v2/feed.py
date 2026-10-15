"""События ленты уведомлений R06 по жалобам жителя (CONTRACT §5.8) — integration.updates(device, since).

Источник — тот же список, что «Что изменилось» в «Моих обращениях» (lifecycle.changes): одно событие = одна строка,
id и ссылка совпадают (#mine/event=<id> открывает именно это изменение). Без имён сотрудников и причин передач.
"""

from __future__ import annotations

from . import lifecycle

_STATUS = {
    "accepted": ("Обращение {code} принято", "{code} өтініші қабылданды"),
    "in_progress": ("Обращение {code} в работе", "{code} өтініші орындалуда"),
    "fixed": ("Служба сообщила: исправлено — проверьте", "Қызмет түзетілгенін хабарлады — тексеріңіз"),
    "rejected": ("Обращение {code} отклонено", "{code} өтініші қабылданбады"),
    "new": ("Обращение {code} снова открыто", "{code} өтініші қайта ашылды"),
}
_KIND = {
    "reopened": ("Жители вернули в работу", "Тұрғындар жұмысқа қайтарды"),
    "verified": ("Проверено жителями", "Тұрғындар тексерді"),
    "note": ("Сообщение службы", "Қызмет хабарламасы"),
    "passport": ("План решения обновлён", "Шешу жоспары жаңартылды"),
    "services": ("Работают {n} службы", "{n} қызмет жұмыс істейді"),
}
_PART = {"todo": ("ждёт", "күтуде"), "in_progress": ("в работе", "орындалуда"), "done": ("сделано", "орындалды")}


def _service(sid, lang: int) -> str:
    names = lifecycle.SERVICES.get(sid or "", {})
    return names.get("kk" if lang else "ru") or ""


def titles(event: dict, code: str | None) -> tuple[str, str]:
    """(title_ru, title_kk) одной строки ленты."""
    kind, code = event.get("kind"), code or ""
    if kind == "status":
        ru, kk = _STATUS.get(event.get("status"), _STATUS["accepted"])
        return ru.format(code=code).replace("  ", " "), kk.format(code=code).replace("  ", " ")
    if kind == "handoff":
        return f"Передано: {_service(event.get('service'), 0)}", f"Берілді: {_service(event.get('service'), 1)}"
    if kind == "part":
        state = _PART.get(event.get("part_status"), _PART["in_progress"])
        return f"{_service(event.get('service'), 0)} — {state[0]}", f"{_service(event.get('service'), 1)} — {state[1]}"
    if kind == "services":
        n = len(event.get("services") or []) or 1
        ru, kk = _KIND["services"]
        if n == 1:
            return f"Отвечает {_service((event.get('services') or [None])[0], 0)}", \
                f"Жауапты: {_service((event.get('services') or [None])[0], 1)}"
        return ru.format(n=n), kk.format(n=n)
    ru, kk = _KIND.get(kind, _KIND["note"])
    return ru, kk


def feed_events(records: list[dict], since: str | None) -> list[dict]:
    """Записи «Моих обращений» устройства (store.mine) → события §5.8, новые сверху."""
    changes = lifecycle.changes(records, since)
    out = []
    for item in changes["items"]:
        title_ru, title_kk = titles(item, item.get("code"))
        out.append({"id": "r09." + item["id"], "at": item["at"], "module": "R09", "kind": "complaint.update",
                    "target": item.get("target") or {}, "title_ru": title_ru, "title_kk": title_kk,
                    "link": "#mine/event=" + item["id"], "complaint_id": item.get("complaint_id"),
                    "code": item.get("code"), "event": item["kind"]})
    return out
