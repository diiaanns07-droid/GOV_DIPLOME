"""reply_draft() — черновик ответа жителю для сотрудника (CONTRACT §7: POST /api/civic/v2/reply-draft, сотрудник).

    POST /api/civic/v2/reply-draft {"complaint_id": "c-…" | "code": "B-0042", "status"?: "in_progress", "lang"?: "kk"}
    POST /api/civic/v2/reply-draft {"text": "Не горит фонарь", "status": "new", "lang": "ru"}   # без записи
    -> {"draft_ru", "draft_kk", "text", "lang", "status", "template", "facts", "facts_used", "needs_input",
        "warnings", "source": "template" | "template+llm", "version"}

Запись берётся из хранилища R09, которое шлюз уже подключил для «Я тоже» (connect_store). R09 может звать функцию
и в процессе, передав запись сам: reply_draft(record=rec, status="fixed", lang="kk").
Факты — из записи кодом (ml/civic_replies): номер, службы и их части, срок ответа в рабочих днях (календарь R09),
следующий шаг, срок устранения только из паспорта, что сделано. Текст жителя в черновик не попадает.
Языковая модель — только по желанию (polish=функция, или BIRGE_REPLY_LLM=модуль:функция) и с охраной чисел.
"""

from __future__ import annotations

import importlib
import logging
import os
import re
from datetime import datetime, timedelta, timezone

from ml.civic_replies import draft as _draft
from ml.civic_replies.guard import polish as _polish
from ui.civic_ml_api.errors import MLServiceUnavailable

LOGGER = logging.getLogger(__name__)
ASTANA_TZ = timezone(timedelta(hours=5))
COMPLAINT_ID = re.compile(r"^c-[A-Za-z0-9]{6,40}$")
COMPLAINT_CODE = re.compile(r"^B-\d{1,8}$")


def _store():
    from ui.civic_ml_api.similar_search import complaint_store
    return complaint_store()


def _working_days():
    try:
        from ui.civic_feedback.v2.workdays import deadline_info
        return deadline_info
    except Exception:  # noqa: BLE001 — без календаря R09 срок пишется только датой
        return None


def _env_llm():
    spec = os.environ.get("BIRGE_REPLY_LLM") or ""
    if ":" not in spec:
        return None
    module, _, name = spec.partition(":")
    try:
        return getattr(importlib.import_module(module), name)
    except Exception:  # noqa: BLE001
        LOGGER.warning("BIRGE_REPLY_LLM=%s не загрузилась — черновик без модели", spec)
        return None


def reply_draft(complaint_id=None, text=None, status=None, lang=None, *, code=None, category=None, subtopic=None,
                record=None, body=None, principal=None, context=None, now=None, polish=None, **_ignored) -> dict:
    """Черновик ответа. Нужен complaint_id (или code), запись record (в процессе) или текст text."""
    if isinstance(body, dict):
        complaint_id = body.get("complaint_id", complaint_id)
        code = body.get("code", code)
        text = body.get("text", text)
        status = body.get("status", status)
        lang = body.get("lang", lang)
        category = body.get("category", category)
        subtopic = body.get("subtopic", subtopic)
    if context is not None and principal is None:
        raise PermissionError("Черновик ответа доступен только сотруднику.")
    if lang not in (None, "", "ru", "kk", "mixed"):
        raise ValueError("lang: ru или kk.")
    if status not in (None, "", "new", "accepted", "in_progress", "fixed", "rejected"):
        raise ValueError("status: new, accepted, in_progress, fixed или rejected.")
    now = now or datetime.now(ASTANA_TZ)

    from ui.civic_ml_api.routing import route, service_names, table_service
    names = service_names()
    original_code = None
    if record is None and (complaint_id or code):
        if complaint_id is not None and (not isinstance(complaint_id, str) or not COMPLAINT_ID.match(complaint_id)):
            raise ValueError("complaint_id: номер вида c-….")
        if code is not None and (not isinstance(code, str) or not COMPLAINT_CODE.match(code)):
            raise ValueError("code: номер вида B-0042.")
        store = _store()
        if store is None:
            raise MLServiceUnavailable("source_not_connected", "Хранилище обращений не подключено к ML-API.")
        record = store.get(complaint_id) if complaint_id else store.get_by_code(code)
        if record is None:
            raise LookupError(complaint_id or code)
        if record.get("duplicate_of"):
            original = store.get(record["duplicate_of"])
            original_code = (original or {}).get("code")
    if record is not None:
        record = dict(record)
        if not record.get("services") and not (record.get("passport") or {}).get("assignee_id") \
                and not record.get("service"):
            hint = (record.get("route_hint") or {}).get("services")
            record["service"] = hint[0] if hint else table_service(record.get("category") or "other",
                                                                   record.get("subtopic"))[0]
        lang = lang or (record.get("lang") if record.get("lang") in ("ru", "kk") else None)
        result = _draft(record, status=status or None, lang=lang, names=names, now=now,
                        working_days=_working_days(), original_code=original_code)
    else:
        if not (isinstance(text, str) and text.strip()) and not category:
            raise ValueError("Нужен complaint_id, code или текст обращения.")
        routed = route(text=text if isinstance(text, str) and text.strip() else None, category=category,
                       subtopic=subtopic)
        rule = routed["rule"].split(".")[1] if routed["rule"].startswith("joint.") else None
        from ml.civic_replies.templates import JOINT_TOPIC
        facts = {"code": None, "category": routed["category"], "subtopic": routed["subtopic"], "status": status,
                 "topic": JOINT_TOPIC.get(rule) if rule else None,
                 "services": [{"service": s["service"], "role": s["role"], "status": status or "new",
                               "name_ru": s["name_ru"],
                               "name_kk": s["name_kk"]} for s in routed["services"]],
                 "response_due": None, "response_days_left": None, "fix_eta": None, "next_step": None,
                 "delay_reason": None, "temp_measure": None, "next_update": None, "what_done": None,
                 "handoff_to": None, "duplicate_of": None, "original_code": None, "reporters": None}
        result = _draft(None, status=status or "new", lang=lang, names=names, now=now, facts=facts)

    llm = polish if callable(polish) else _env_llm()
    if llm is not None:
        all_names = [v[k] for v in names.values() for k in ("ru", "kk") if v.get(k)]
        for key, code_lang in (("draft_ru", "ru"), ("draft_kk", "kk")):
            new, accepted, reason = _polish(result[key], code_lang, llm=llm, service_names=all_names)
            result[key] = new
            if accepted:
                result["source"] = "template+llm"
            elif reason:
                result["warnings"].append(f"Модель ({code_lang}): {reason} — оставлен шаблон.")
        result["text"] = result["draft_kk"] if result["lang"] == "kk" else result["draft_ru"]
    return result
