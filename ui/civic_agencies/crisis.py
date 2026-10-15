"""Кризисный штаб: шаблоны, зона, проверка текстов, виды записи для жителя и сотрудника (CONTRACT §5.5, §10).

Шаблон — это только подсказка: вид, название и чек-лист задач служб. Сотрудник правит всё перед созданием.
Тексты шаблонов — наши слова интерфейса (казахский — на вычитку R11, ключи в INTEGRATION.txt), без реальных
названий организаций, без телефонов и без чисел, которых нет в данных.
"""

from __future__ import annotations

import re

from . import geo, profiles

TEXT_MIN, TEXT_MAX = 3, 600
TITLE_MAX = 80
MAX_TARGETS = 50

TEMPLATES = {
    "blizzard": {
        "title_ru": "Буран", "title_kk": "Боран",
        "tasks": [
            ("street_cleaning", "Расчистить главные улицы, остановки и подходы к школам",
             "Негізгі көшелерді, аялдамаларды және мектепке баратын жолдарды тазарту"),
            ("transport", "Пустить автобусы по зимней схеме и сообщить об изменениях",
             "Автобустарды қысқы сызба бойынша жіберу және өзгерістер туралы хабарлау"),
            ("housing", "Сбить снег и сосульки с крыш у входов в подъезды",
             "Кіреберістердің үстіндегі шатырлардан қар мен мұзды түсіру"),
            ("emergency", "Дежурство: помощь застрявшим машинам и людям",
             "Кезекшілік: тұрып қалған көліктер мен адамдарға көмек"),
        ],
        "update_ru": "Службы работают в районе: расчищаем улицы и остановки. Без необходимости не выезжайте.",
        "update_kk": "Қызметтер ауданда жұмыс істеп жатыр: көшелер мен аялдамаларды тазартып жатырмыз. "
                     "Қажет болмаса, көлікпен шықпаңыз.",
    },
    "heat_outage": {
        "title_ru": "Авария теплосети", "title_kk": "Жылу желісіндегі апат",
        "tasks": [
            ("heating", "Найти место порыва и восстановить подачу тепла",
             "Жарылған жерді тауып, жылу беруді қалпына келтіру"),
            ("housing", "Проверить подвалы и стояки в домах зоны",
             "Аймақтағы үйлердің жертөлелері мен құбырларын тексеру"),
            ("emergency", "Обойти квартиры, где живут пожилые люди и семьи с детьми",
             "Қарт адамдар мен балалы отбасылар тұратын пәтерлерді аралау"),
            ("akimat", "Открыть пункты обогрева и сообщить жителям адреса",
             "Жылыну пункттерін ашып, мекенжайларын тұрғындарға хабарлау"),
        ],
        "update_ru": "Теплосеть ищет место аварии. Тепло вернут как можно скорее, следующее обновление — в течение двух часов.",
        "update_kk": "Жылу желісі апат болған жерді іздеп жатыр. Жылу мүмкіндігінше тез беріледі, келесі хабар — екі сағат ішінде.",
    },
    "water_outage": {
        "title_ru": "Прорыв водопровода", "title_kk": "Су құбырының жарылуы",
        "tasks": [
            ("water", "Перекрыть участок и заменить трубу", "Учаскені жауып, құбырды ауыстыру"),
            ("road", "Восстановить покрытие после раскопки — один раз, после сетей",
             "Қазудан кейін жол жабынын қалпына келтіру — бір рет, желілерден кейін"),
            ("traffic", "Поставить знаки объезда и временную разметку",
             "Айналма жол белгілері мен уақытша таңбаларды қою"),
            ("akimat", "Организовать подвоз питьевой воды во дворы зоны",
             "Аймақтағы аулаларға ауыз су жеткізуді ұйымдастыру"),
        ],
        "update_ru": "В зоне нет воды: службы меняют трубу. Подвоз питьевой воды — во дворы зоны.",
        "update_kk": "Аймақта су жоқ: қызметтер құбырды ауыстырып жатыр. Ауыз су аймақтағы аулаларға жеткізіледі.",
    },
    "flood": {
        "title_ru": "Подтопление", "title_kk": "Су басу",
        "tasks": [
            ("emergency", "Откачать воду из подвалов и с дорог", "Жертөлелер мен жолдардан суды сорып шығару"),
            ("water", "Прочистить ливневую канализацию", "Нөсер кәрізін тазарту"),
            ("street_cleaning", "Убрать наледь и грязь после откачки", "Су сорғаннан кейін мұз бен балшықты тазалау"),
            ("akimat", "Сообщать жителям, какие улицы закрыты", "Қай көшелер жабық екенін тұрғындарға хабарлау"),
        ],
        "update_ru": "Службы откачивают воду. Объезжайте закрытые улицы.",
        "update_kk": "Қызметтер суды сорып жатыр. Жабық көшелерді айналып өтіңіз.",
    },
    "other": {
        "title_ru": "Чрезвычайная ситуация", "title_kk": "Төтенше жағдай",
        "tasks": [],
        "update_ru": "", "update_kk": "",
    },
}

# Подсказка модератору «похоже на личные данные» (как R13 ui.civic_qa): в публичных обновлениях их быть не должно.
PII_PATTERNS = (
    ("phone", re.compile(r"(?<![\d+])(?:(?:\+\s*)?[78][\s(-]*)?7(?:[\s().-]{0,2}\d){9}(?!\d)")),
    ("iin", re.compile(r"(?<!\d)(?:\d[\s-]?){11}\d(?!\d)")),
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
)


class InputError(ValueError):
    """Неверные данные от сотрудника: field — поле, message — что исправить (по-русски), status — 400 или 422."""

    def __init__(self, field: str, message: str, status: int = 422, code: str = "invalid"):
        super().__init__(message)
        self.field, self.message, self.status, self.code = field, message, status, code


def templates_view() -> list[dict]:
    """Шаблоны для формы «Новый кризис»: вид, название, задачи по службам, первое обновление (ru/kk)."""
    out = []
    for kind, tpl in TEMPLATES.items():
        out.append({"kind": kind, "title_ru": tpl["title_ru"], "title_kk": tpl["title_kk"],
                    "tasks": [{"service": s, "text_ru": ru, "text_kk": kk} for s, ru, kk in tpl["tasks"]],
                    "update_ru": tpl["update_ru"], "update_kk": tpl["update_kk"]})
    return out


def clean_text(value, *, field: str, low: int = TEXT_MIN, high: int = TEXT_MAX, required: bool = True) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise InputError(field, "Заполните поле.")
        return None
    if not isinstance(value, str):
        raise InputError(field, "Нужен текст.")
    text = re.sub(r"[ \t ]+", " ", value.replace("\r\n", "\n")).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "".join(ch for ch in text if ch == "\n" or ch.isprintable())
    if len(text) < low:
        raise InputError(field, f"Слишком коротко: нужно хотя бы {low} символа.")
    if len(text) > high:
        raise InputError(field, f"Слишком длинно: не больше {high} символов.")
    return text


def pii_kinds(text: str | None) -> list[str]:
    return [kind for kind, rx in PII_PATTERNS if rx.search(text or "")]


def moderate(text: str | None, lang: str) -> dict:
    """Проверка текста до публикации (CONTRACT §10): R04 moderate(text, lang) → {text_public, clean, action, pii, rude,
    flags: [{kind, group, …}]} (раунд 15; раньше — flags списком строк или {имя: bool}); без R04 — свои правила личных
    данных + фильтр грубых слов R04 (profanity), если он есть. -> {"flags": [...], "by": ...}.
    Флаг — и вид находки (phone, iin, email, contact, rude…), и её группа (pii, rude): «contact» группы pii — тоже
    личные данные."""
    if not text:
        return {"flags": [], "by": "none"}
    flags: list[str] = []
    by = "rules"
    try:
        from ui.civic_ml_api import moderate as r04_moderate  # type: ignore — поставка R04 раунда 15
    except Exception:  # noqa: BLE001
        r04_moderate = None
    if callable(r04_moderate):
        try:
            result = r04_moderate(text, lang)
            raw = result.get("flags") if isinstance(result, dict) else None
            if isinstance(raw, dict):
                flags = [str(k) for k, v in raw.items() if v]
            elif isinstance(raw, (list, tuple)):
                for f in raw:
                    if isinstance(f, dict):
                        flags.extend(str(f[k]) for k in ("kind", "group") if f.get(k))
                    elif f:
                        flags.append(str(f))
            if isinstance(result, dict):
                flags.extend(name for name in ("pii", "rude") if result.get(name) is True)
            by = "r04"
        except Exception:  # noqa: BLE001 — модель R04 упала: свои правила ниже
            flags, by = [], "rules"
    if by == "rules":
        try:
            from ui.civic_ml_api.profanity import moderation as rude_check  # type: ignore
            if (rude_check(text) or {}).get("rude"):
                flags.append("rude")
        except Exception:  # noqa: BLE001
            pass
    for kind in pii_kinds(text):
        if kind not in flags:
            flags.append(kind)
    return {"flags": sorted(set(flags)), "by": by}


def check_public_texts(texts: dict) -> dict:
    """Публичный текст с личными данными или грубостью не публикуем: 422 и подсказка, что убрать."""
    report = {}
    for lang, text in texts.items():
        result = moderate(text, lang)
        report[lang] = result
        flags = set(result["flags"])
        if flags & {"phone", "iin", "email", "pii", "personal_data"}:
            raise InputError("text_" + lang, "Уберите из текста телефон, ИИН или e-mail: обновление видят все жители зоны.",
                             code="personal_data")
        if flags & {"rude", "profanity", "obscene"}:
            raise InputError("text_" + lang, "Уберите грубые слова: обновление видят все жители зоны.", code="rude")
    return report


def parse_zone(raw) -> tuple[dict, str | None]:
    """Зона кризиса: район или цели (дворы R12, объекты и участки улиц). -> (zone по §5.5, район для фильтра).

    Полигон «от руки» не принимается (CONTRACT §8, prompt R17). Подписи целей — только с карты (R12), не из запроса.
    """
    if not isinstance(raw, dict):
        raise InputError("zone", "Выберите зону: район или дворы.")
    kind = raw.get("kind")
    if kind == "polygon" or raw.get("geometry"):
        raise InputError("zone", "Зона — район, дворы или объекты карты. Контур от руки не принимается.")
    if kind == "district":
        district = raw.get("district")
        if district not in geo.DISTRICTS:
            raise InputError("zone.district", "Неизвестный район.")
        return {"kind": "district", "district": district, "targets": [], "geometry": None}, district
    if kind == "targets":
        targets = raw.get("targets")
        if not isinstance(targets, list) or not targets:
            raise InputError("zone.targets", "Выберите хотя бы один двор или объект.")
        if len(targets) > MAX_TARGETS:
            raise InputError("zone.targets", f"Не больше {MAX_TARGETS} целей в зоне.")
        clean, labels, districts = [], [], []
        for tid in targets:
            info = geo.target_info(tid) if isinstance(tid, str) else None
            if info is None:
                raise InputError("zone.targets", "Такой цели нет на карте: " + str(tid)[:60])
            if tid in clean:
                continue
            clean.append(tid)
            labels.append({"id": tid, "label_ru": info["label_ru"], "label_kk": info["label_kk"]})
            if info.get("district"):
                districts.append(info["district"])
        district = raw.get("district") if raw.get("district") in geo.DISTRICTS else None
        if district is None and districts:
            district = max(set(districts), key=districts.count)  # район, где больше целей зоны
        return {"kind": "targets", "district": district, "targets": clean, "labels": labels, "geometry": None}, district
    raise InputError("zone.kind", "Зона — district (район) или targets (дворы и объекты).")


def parse_tasks(raw) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise InputError("tasks", "Задачи — список.")
    out = []
    for i, item in enumerate(raw):
        # R15-S43: список/словарь вместо строки — 422, а не TypeError (unhashable) → 500.
        if not isinstance(item, dict) or not isinstance(item.get("service"), str) or item["service"] not in profiles.PROFILES:
            raise InputError(f"tasks[{i}].service", "Выберите службу из справочника.")
        ru = clean_text(item.get("text_ru"), field=f"tasks[{i}].text_ru", high=200, required=False)
        kk = clean_text(item.get("text_kk"), field=f"tasks[{i}].text_kk", high=200, required=False)
        if not ru and not kk:
            raise InputError(f"tasks[{i}].text_ru", "Опишите задачу хотя бы на одном языке.")
        out.append({"service": item["service"], "text_ru": ru or kk, "text_kk": kk or ru, "status": "todo"})
    return out


def services_of(incident: dict) -> list[str]:
    seen = []
    for task in incident.get("tasks") or []:
        if task["service"] not in seen:
            seen.append(task["service"])
    return seen


def progress(incident: dict) -> list[dict]:
    """Прогресс по службам для чипов штаба: сколько задач службы сделано из скольких."""
    rows: dict[str, dict] = {}
    for task in incident.get("tasks") or []:
        row = rows.setdefault(task["service"], {"service": task["service"], "done": 0, "doing": 0, "total": 0})
        row["total"] += 1
        if task["status"] == "done":
            row["done"] += 1
        elif task["status"] == "doing":
            row["doing"] += 1
    return list(rows.values())


def zone_label(zone: dict) -> dict:
    if zone.get("kind") == "district":
        names = geo.DISTRICT_NAMES.get(zone.get("district"), {"ru": "", "kk": ""})
        return {"ru": f"район {names['ru']}", "kk": f"{names['kk']} ауданы"}
    labels = zone.get("labels") or []
    if len(labels) == 1:
        return {"ru": labels[0]["label_ru"], "kk": labels[0]["label_kk"]}
    district = geo.DISTRICT_NAMES.get(zone.get("district"))
    tail_ru = f" · район {district['ru']}" if district else ""
    tail_kk = f" · {district['kk']} ауданы" if district else ""
    return {"ru": f"{len(labels)} мест{_plural_ru(len(labels))}{tail_ru}", "kk": f"{len(labels)} орын{tail_kk}"}


def _plural_ru(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "о"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "а"
    return ""


def public_view(incident: dict, *, with_geometry: bool = False) -> dict:
    """Жителю: без внутренних задач, без журнала, без заметок штаба и без пометок модерации (CONTRACT §10)."""
    zone = {k: v for k, v in incident["zone"].items() if k in ("kind", "district", "targets", "labels")}
    view = {
        "id": incident["id"], "kind": incident["kind"], "title_ru": incident["title_ru"], "title_kk": incident["title_kk"],
        "zone": zone, "zone_label": zone_label(incident["zone"]), "district": zone.get("district"),
        "status": incident["status"],
        "started_at": incident["started_at"], "closed_at": incident.get("closed_at"), "result": incident.get("result"),
        "services": services_of(incident),
        "updates": [{"id": u["id"], "at": u["at"], "kind": u["kind"], "text_ru": u["text_ru"], "text_kk": u["text_kk"]}
                    for u in incident.get("updates") or [] if u["public"]],
        "demo": incident["demo"], "updated_at": incident["updated_at"],
    }
    if with_geometry:
        shape = geo.zone_geometry(incident["zone"])
        view["geometry"] = shape
        view["bbox"] = geo.zone_bbox(shape)
    return view


def staff_view(incident: dict, *, journal: list | None = None, with_geometry: bool = False) -> dict:
    """Сотруднику: всё, кроме имён сотрудников (в журнале только роль)."""
    view = public_view(incident, with_geometry=with_geometry)
    view["tasks"] = [dict(t) for t in incident.get("tasks") or []]
    view["progress"] = progress(incident)
    view["updates"] = [{k: u[k] for k in ("id", "at", "kind", "text_ru", "text_kk", "public", "moderation")}
                       for u in incident.get("updates") or []]
    view["revision"] = incident.get("revision")
    if journal is not None:
        view["journal"] = journal
    return view


def in_zone(incident: dict, districts: set, yards: set) -> bool:
    """Касается ли кризис жителя: его район в зоне или его двор — цель зоны / лежит в районе зоны."""
    zone = incident.get("zone") or {}
    if zone.get("kind") == "district":
        if zone.get("district") in districts:
            return True
        return any((geo.yards().get(y) or {}).get("district") == zone.get("district") for y in yards)
    targets = set(zone.get("targets") or [])
    return bool(targets & yards)
