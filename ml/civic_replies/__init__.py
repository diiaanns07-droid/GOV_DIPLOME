"""Черновик ответа жителю (R04, раунд 15): шаблоны ru / kk, факты — из записи жалобы R09 кодом.

    from ml.civic_replies import draft
    d = draft(record, status="in_progress", lang="kk", now=now, names=service_names)
    d["draft_ru"], d["draft_kk"], d["text"]   # оба языка и запрошенный
    d["facts"]                                # что взято из записи (номер, службы, срок, шаг) — сотрудник видит основания
    d["needs_input"]                          # что сотрудник должен дописать сам (причина отказа)

Чего здесь нет нарочно: дат и сроков, которых нет в записи (срок устранения — только passport.fix_eta), имён
сотрудников, текста жителя и чужих данных. Языковая модель — по желанию (guard.polish): её текст принимается, только
если в нём нет новых чисел, дат и названий служб (как agent/evidence.py: числа считает код, а не модель).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from ml.civic_replies import templates as T

VERSION = "r04-replies-1"
ASTANA_TZ = timezone(timedelta(hours=5))
STATUSES = ("new", "accepted", "in_progress", "fixed", "rejected")
_KK_NUMBERS = {2: "екі", 3: "үш"}


def _parse(value) -> datetime | None:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str) and value:
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                moment = datetime.combine(date.fromisoformat(value[:10]), datetime.min.time())
            except ValueError:
                return None
    else:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=ASTANA_TZ)


def date_words(value) -> tuple[str, str] | None:
    """«20 октября» / «20 қазан» (дата из записи; без года, если год текущий — так короче и привычнее)."""
    moment = _parse(value)
    if moment is None:
        return None
    local = moment.astimezone(ASTANA_TZ)
    year = f" {local.year} г." if local.year != datetime.now(ASTANA_TZ).year else ""
    year_kk = f" {local.year} ж." if year else ""
    return f"{local.day} {T.MONTHS_RU[local.month - 1]}{year}", f"{local.day} {T.MONTHS_KK[local.month - 1]}{year_kk}"


def _due_state(due, now: datetime) -> str | None:
    """ok | today | overdue по датам — когда календаря R09 (workdays.deadline_info) нет."""
    moment = _parse(due)
    if moment is None:
        return None
    now = now if now.tzinfo else now.replace(tzinfo=ASTANA_TZ)
    if now > moment:
        return "overdue"
    return "today" if moment.astimezone(ASTANA_TZ).date() == now.astimezone(ASTANA_TZ).date() else "ok"


def working_days_words(n: int) -> tuple[str, str]:
    """«в течение 3 рабочих дней» — родительный падеж: 1, 21, 31 — «рабочего дня», остальное — «рабочих дней»."""
    ru = f"{n} рабочего дня" if n % 10 == 1 and n % 100 != 11 else f"{n} рабочих дней"
    return ru, f"{n} жұмыс күні"


def _topic(category: str | None, subtopic: str | None) -> tuple[str, str]:
    key = f"{category}/{subtopic}" if category and subtopic and f"{category}/{subtopic}" in T.TOPIC else category
    ru, kk = T.TOPIC.get(key or "", ("", ""))
    return (" " + ru if ru else ""), (" (" + kk + ")" if kk else "")


def _clean_line(value, limit: int = 200) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split()).strip().rstrip(".")
    return text[:limit] or None


_KK_LETTERS = set("әғқңөұүһі")


def text_lang(text: str | None) -> str | None:
    """ru | kk по буквам (для предупреждения «шаг сотрудника на другом языке»)."""
    if not text:
        return None
    return "kk" if any(ch in _KK_LETTERS for ch in text.casefold()) else "ru"


def _after_colon(text: str, keep: set) -> str:
    """Текст сотрудника после двоеточия — со строчной буквы («Следующий шаг: восстановим асфальт»), кроме названий
    служб и аббревиатур («Водоканал заменит трубу», «ЦОН»)."""
    first = text.split(" ", 1)[0]
    if first in keep or first.isupper() or not first[:1].isupper():
        return text
    return text[:1].lower() + text[1:]


def facts_from_record(record: dict, *, names: dict, now: datetime, working_days=None, original_code=None) -> dict:
    """Факты для ответа — только из записи R09 (CONTRACT §5, §5.1). working_days — функция R09 deadline_info."""
    passport = record.get("passport") or {}
    parts = []
    for part in record.get("services") or []:
        if isinstance(part, dict) and part.get("service"):
            parts.append({"service": part["service"], "role": part.get("role") or "partner",
                          "status": part.get("status") or "new"})
    handoffs = [h for h in record.get("handoffs") or [] if isinstance(h, dict) and h.get("to")]
    # Ведущая: выбор сотрудника, служба записи, части; иначе — куда передали последней передачей, потом подсказка R04.
    lead = (passport.get("assignee_id") or record.get("service")
            or (parts[0]["service"] if parts else None) or (handoffs[-1]["to"] if handoffs else None)
            or (record.get("route_hint") or {}).get("services", [None])[0])
    if not parts and lead:
        parts = [{"service": lead, "role": "lead", "status": record.get("status") or "new"}]
    for part in parts:
        item = names.get(part["service"]) or {}
        part["name_ru"], part["name_kk"] = item.get("ru") or part["service"], item.get("kk") or part["service"]
    due = record.get("due_at")
    days_left = state = None
    if due and callable(working_days):
        try:
            info = working_days(_parse(due), now, done=False) or {}
            days_left, state = info.get("working_days_left"), info.get("state")
        except Exception:  # noqa: BLE001 — календарь R09 недоступен: срок только датой
            days_left = state = None
    if due and state not in ("ok", "today", "overdue"):
        state = _due_state(due, now)
    delay = passport.get("delay") or {}
    resolution = record.get("resolution") or {}
    return {
        "code": record.get("code") or record.get("id"),
        "category": record.get("category"), "subtopic": record.get("subtopic"),
        "status": record.get("status"),
        "services": parts,
        "response_due": due, "response_days_left": days_left, "response_state": state,
        "fix_eta": passport.get("fix_eta"),
        "next_step": _clean_line(passport.get("next_step")),
        "delay_reason": _clean_line(delay.get("reason")),
        "temp_measure": _clean_line(delay.get("temp_measure")),
        "next_update": delay.get("next_update_at"),
        "what_done": _clean_line(resolution.get("what_done")),
        "handoff_to": handoffs[-1]["to"] if handoffs else None,
        "duplicate_of": record.get("duplicate_of"),
        "original_code": original_code,
        "reporters": 1 + int(record.get("metoo") or 0),
    }


# Поле «Обновление для всех» у R09 хранит до 320 знаков (lifecycle.PASSPORT_TEXT_MAX × 2): черновик длиннее
# оборвался бы на полуслове. Порядок «что отдать» — в _fit. Главное предложение (статус, службы, причина отказа)
# не трогаем никогда.
MAX_LEN = 320
_SOFT_DROP = ("thanks", "next_update", "temp_measure", "rejected_again", "hello", "no_eta")
_HARD_DROP = ("handoff", "handoff_only", "handoff_due", "due", "overdue")
_MIN_STAFF = 40                    # короче текст сотрудника не режем: смысл шага теряется


def _shorten(text: str, limit: int) -> str:
    """Текст сотрудника не длиннее limit знаков: по границе слова и с «…»."""
    text = str(text)
    if len(text) <= limit:
        return text
    cut = text[:max(1, limit - 1)].rsplit(" ", 1)[0].rstrip(",;:—- ")
    return (cut or text[:max(1, limit - 1)]) + "…"


def _join(items: list[dict]) -> str:
    return " ".join(it["text"] for it in items)


def _shortened(items: list[dict], limit: int) -> tuple[list[dict], list[str]] | None:
    """Сократить тексты сотрудника ровно настолько, чтобы влезть в limit (сначала самый длинный). None — не выйдет."""
    out = [dict(it) for it in items]
    changed = []
    for it in sorted((x for x in out if x.get("render")), key=lambda x: -x["body_len"]):
        over = len(_join(out)) - limit
        if over <= 0:
            break
        target = max(_MIN_STAFF, it["body_len"] - over - 1)
        if target < it["body_len"]:
            it["text"] = it["render"](target)
            changed.append("сокращено: " + it["key"])
    return (out, changed) if len(_join(out)) <= limit else None


def _fit(items: list[dict], limit: int) -> tuple[str, list[str]]:
    """Склеить предложения в черновик не длиннее limit. -> (текст, что убрано или сокращено).

    1) убираем второстепенное (_SOFT_DROP); 2) если тексты сотрудника можно сократить и влезть — сокращаем ровно
    настолько; 3) иначе убираем передачу, затем срок ответа (_HARD_DROP), каждый раз снова пробуя шаг 2;
    4) в крайнем случае режем по границе слова (при текстах сотрудника ≤ 200 знаков не бывает)."""
    items = [dict(it) for it in items]
    changed: list[str] = []
    for step in _SOFT_DROP:
        if len(_join(items)) <= limit:
            return _join(items), changed
        for it in [x for x in items if x["key"] == step]:
            items.remove(it)
            changed.append("убрано: " + step)
    for step in (None,) + _HARD_DROP:
        if step is not None:
            for it in [x for x in items if x["key"] == step]:
                items.remove(it)
                changed.append("убрано: " + step)
        if len(_join(items)) <= limit:
            return _join(items), changed
        trial = _shortened(items, limit)
        if trial is not None:
            return _join(trial[0]), changed + trial[1]
    text = _shorten(_join(items), limit)
    return text, changed + ["обрезано"]


def draft(record: dict | None = None, *, status: str | None = None, lang: str | None = None, category=None,
          subtopic=None, names: dict | None = None, now: datetime | None = None, working_days=None,
          original_code=None, facts: dict | None = None, max_len: int = MAX_LEN) -> dict:
    """Черновик по записи R09 (или по категории без записи). status — какой ответ готовим (по умолчанию — статус записи)."""
    now = now or datetime.now(ASTANA_TZ)
    names = names or {}
    if facts is None:
        if record is not None:
            facts = facts_from_record(record, names=names, now=now, working_days=working_days,
                                      original_code=original_code)
        else:
            facts = {"code": None, "category": category, "subtopic": subtopic, "status": status, "services": [],
                     "response_due": None, "response_days_left": None, "fix_eta": None, "next_step": None,
                     "delay_reason": None, "temp_measure": None, "next_update": None, "what_done": None,
                     "handoff_to": None, "duplicate_of": None, "original_code": None, "reporters": None}
    status = status or facts.get("status") or "new"
    if status not in STATUSES:
        raise ValueError("status: new, accepted, in_progress, fixed или rejected.")
    if isinstance(facts.get("topic"), (tuple, list)) and len(facts["topic"]) == 2:
        about_ru = (" " + facts["topic"][0]) if facts["topic"][0] else ""
        about_kk = (" (" + facts["topic"][1] + ")") if facts["topic"][1] else ""
    else:
        about_ru, about_kk = _topic(facts.get("category"), facts.get("subtopic"))
    code = facts.get("code") or ""
    code_ru, code_kk = (code, code) if code else ("", "")
    parts = facts.get("services") or []
    service_ru = ", ".join(p["name_ru"] for p in parts) or "служба по таблице акимата"
    service_kk = ", ".join(p["name_kk"] for p in parts) or "әкімдік кестесі бойынша қызмет"
    due = date_words(facts.get("response_due"))
    due_state = facts.get("response_state") or (_due_state(facts["response_due"], now) if due else None)
    # Срок ответа прошёл, а ответа ещё нет: прошедшую дату как срок не пишем (житель прочёл бы её как обещание).
    overdue = bool(due) and due_state == "overdue"
    used, warnings, needs_input = [], [], []
    # Предложения по порядку вывода: {"key", "text", "render"?, "body_len"?} — render(n) пересобирает предложение
    # с текстом сотрудника не длиннее n знаков (бюджет длины, _fit).
    ru, kk = [{"key": "hello", "text": T.HELLO[0]}], [{"key": "hello", "text": T.HELLO[1]}]
    keep = {w for item in names.values() for w in (item.get("ru", "").split()[:1] + item.get("kk", "").split()[:1])}
    staff_texts = {}
    for key in ("next_step", "delay_reason", "temp_measure", "what_done"):
        if facts.get(key):
            staff_texts[key] = _after_colon(facts[key], keep)
            if text_lang(facts[key]) == "ru":
                warnings.append(f"Поле «{key}» написано по-русски — для ответа на казахском переведите его.")
            elif text_lang(facts[key]) == "kk":
                warnings.append(f"Поле «{key}» написано по-казахски — для ответа на русском переведите его.")

    def say(key: str, staff: str | None = None, **values) -> None:
        """Предложение на двух языках. Пустой номер (черновик без записи) не оставляет двойных пробелов, а
        предложение всегда начинается с заглавной: «{code} өтінішіңіз» без номера -> «Өтінішіңіз».
        staff — имя значения с текстом сотрудника: его можно сократить, если черновик не влезает в поле R09."""
        r, k = T.SENT[key]
        for out, template, i in ((ru, r, 0), (kk, k, 1)):
            vals = {n: v[i] if isinstance(v, tuple) else v for n, v in values.items()}

            def render(limit=None, template=template, vals=vals):
                local = dict(vals)
                if staff and limit is not None:
                    local[staff] = _shorten(local[staff], limit)
                line = " ".join(template.format(**local).split()).replace("….", "…")
                return line[:1].upper() + line[1:]

            item = {"key": key, "text": render()}
            if staff:
                item["render"], item["body_len"] = render, len(vals[staff])
            out.append(item)

    def plain(key: str, text_ru: str, text_kk: str) -> None:
        ru.append({"key": key, "text": text_ru})
        kk.append({"key": key, "text": text_kk})

    if code:
        used.append("code")
    if facts.get("duplicate_of"):
        say("duplicate")
        if facts.get("original_code"):
            say("duplicate_follow", original=facts["original_code"])
            used.append("original_code")
        template = "duplicate"
    elif status == "fixed":
        what = facts.get("what_done")
        say("fixed")
        if what:
            # «Что сделали: …» — как в карточке жителя; текст сотрудника — как он написал (с заглавной).
            say("what_done", staff="what_done", what_done=what)
            used.append("what_done")
        say("verify")
        plain("thanks", T.THANKS[0], T.THANKS[1])
        template = "fixed"
    elif status == "rejected":
        reason = staff_texts.get("delay_reason") or staff_texts.get("next_step")
        if reason:
            used.append("reason")
        else:
            needs_input.append("reason")
            warnings.append("Нет причины отказа в записи — допишите её в черновик.")
        say("rejected", staff="reason" if reason else None, code=(code_ru, code_kk), about=(about_ru, about_kk),
            reason=(reason or T.FILL_REASON[0], reason or T.FILL_REASON[1]))
        say("rejected_again")
        template = "rejected"
    else:
        if len(parts) >= 2 and status == "new":
            say("received_joint", code=(code_ru, code_kk), about=(about_ru, about_kk),
                n_dat={2: "двум", 3: "трём"}.get(len(parts), str(len(parts))),
                n_kk=_KK_NUMBERS.get(len(parts), str(len(parts))),
                names=(" и ".join([", ".join(p["name_ru"] for p in parts[:-1]), parts[-1]["name_ru"]]),
                       " және ".join([", ".join(p["name_kk"] for p in parts[:-1]), parts[-1]["name_kk"]])))
            used.append("services")
            template = "new_joint"
        elif len(parts) >= 2 and all(pt.get("status") in ("new", "todo", None) for pt in parts):
            say("joint_queued", code=(code_ru, code_kk), about=(about_ru, about_kk),
                n_dat={2: "двум", 3: "трём"}.get(len(parts), str(len(parts))),
                n_kk=_KK_NUMBERS.get(len(parts), str(len(parts))),
                names=(" и ".join([", ".join(p["name_ru"] for p in parts[:-1]), parts[-1]["name_ru"]]),
                       " және ".join([", ".join(p["name_kk"] for p in parts[:-1]), parts[-1]["name_kk"]])))
            used.append("services")
            template = "joint_queued"
        elif len(parts) >= 2:
            words_ru = ", ".join(f"{p['name_ru']} — {T.PART_STATUS.get(p['status'], T.PART_STATUS['new'])[0]}"
                                 for p in parts)
            words_kk = ", ".join(f"{p['name_kk']} — {T.PART_STATUS.get(p['status'], T.PART_STATUS['new'])[1]}"
                                 for p in parts)
            say("joint", code=(code_ru, code_kk), about=(about_ru, about_kk), n=str(len(parts)),
                n_kk=_KK_NUMBERS.get(len(parts), str(len(parts))), parts=(words_ru, words_kk))
            used.append("services")
            template = "joint"
        elif status == "new":
            say("received", code=(code_ru, code_kk), about=(about_ru, about_kk), service=(service_ru, service_kk))
            used.append("services")
            template = "new"
        elif status == "accepted":
            say("accepted", code=(code_ru, code_kk), about=(about_ru, about_kk), service=(service_ru, service_kk))
            used.append("services")
            template = "accepted"
        else:
            say("in_progress", code=(code_ru, code_kk), about=(about_ru, about_kk), service=(service_ru, service_kk))
            used.append("services")
            template = "in_progress"
        if facts.get("handoff_to"):
            to = names.get(facts["handoff_to"]) or {}
            to_pair = (to.get("ru") or facts["handoff_to"], to.get("kk") or facts["handoff_to"])
            # Служба, куда передали, уже названа выше («…передали в службу: Водоканал») — не повторяем её.
            named = facts["handoff_to"] in {p["service"] for p in parts}
            if due and not overdue and named:
                say("handoff_due", due=due)
            elif due and not overdue:
                say("handoff", to=to_pair, due=due)
            elif not named:
                say("handoff_only", to=to_pair)
            used.append("handoff")
        if facts.get("next_step"):
            say("next_step", staff="next_step", next_step=staff_texts["next_step"])
            used.append("next_step")
        if facts.get("delay_reason") or facts.get("next_update"):
            if facts.get("delay_reason"):
                say("delay", staff="reason", reason=staff_texts["delay_reason"])
            else:
                say("delay_no_reason")
            if facts.get("temp_measure"):
                say("temp_measure", staff="temp_measure", temp_measure=staff_texts["temp_measure"])
            nxt = date_words(facts.get("next_update"))
            if nxt:
                say("next_update", next_update=nxt)
            used.append("delay")
        if status == "new" and overdue:
            say("overdue", due=due)
            used.append("response_due")
            warnings.append(f"Срок ответа прошёл ({due[0]}): в черновике — извинение за задержку, новых дат нет.")
        elif status == "new" and due and not facts.get("handoff_to"):
            left = facts.get("response_days_left")
            if isinstance(left, int) and left > 0:
                say("due", days=working_days_words(left), due=due)
            else:
                plain("due", f"Срок ответа — {due[0]}.", f"Жауап мерзімі — {due[1]}.")
            used.append("response_due")
        if status == "in_progress" and template != "joint":
            eta = date_words(facts.get("fix_eta"))
            if eta:
                say("fix_eta", fix_eta=eta)
                used.append("fix_eta")
            elif not facts.get("delay_reason"):
                say("no_eta")
                warnings.append("Срока устранения нет в паспорте — дату не обещаем.")
        if status == "new":
            plain("thanks", T.THANKS[0], T.THANKS[1])
    text_ru, cut_ru = _fit(ru, max_len)
    text_kk, cut_kk = _fit(kk, max_len)
    if cut_ru or cut_kk:
        warnings.append(f"Черновик сокращён до {max_len} знаков (поле «Обновление для всех»): "
                        + ", ".join(sorted(set(cut_ru) | set(cut_kk))) + ".")
    want = lang if lang in ("ru", "kk") else "ru"
    return {
        "draft_ru": text_ru, "draft_kk": text_kk, "lang": want, "text": text_kk if want == "kk" else text_ru,
        "status": status, "template": template, "facts": facts, "facts_used": used,
        "needs_input": needs_input, "warnings": warnings, "source": "template", "version": VERSION,
        "max_len": max_len, "shortened": sorted(set(cut_ru) | set(cut_kk)),
    }


__all__ = ["VERSION", "date_words", "draft", "facts_from_record", "working_days_words"]
