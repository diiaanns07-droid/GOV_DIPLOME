"""Профили служб (CONTRACT §5.4) поверх единого справочника id (CONTRACT §3).

Профиль — это то, чего нет в таблице R08: вид службы, цвет, значок ui-kit и сроки по умолчанию.
Названия ru/kk здесь НЕ хранятся: они живут в таблице R08 (ui.civic_akim.routing, с правками акимата);
запасной вариант — копия R09 (ui.civic_feedback.v2.lifecycle.SERVICES). Новых id не придумываем.

Сроки:
  sla_answer_days — срок ответа жителю в рабочих днях. Считается КОДОМ из двух чужих таблиц: правила
                    «категория → служба» R08 (DEFAULT_RULES) и сроки категорий R09 (RESPONSE_DAYS); берётся
                    самый короткий срок среди категорий, которые идут в эту службу. Сам срок каждой жалобы
                    (due_at) по-прежнему ставит R09 — профиль только подсказывает, чего ждать.
  sla_fix_days    — срок устранения по умолчанию. Это НАСТРОЙКА ПРОТОТИПА (не норматив и не закон):
                    акимат может поменять её; на экране — «срок по умолчанию». Отмечено полем sla_fix_source.

Цвет — по виду службы (7 видов, а не 20 оттенков: двадцать цветов на одном экране не различить).
Цвет никогда не единственный признак: рядом всегда значок и название (VISUAL_BRIEF §2 п. 4).
Палитра не пересекается с цветами тепловой карты (жёлтый, оранжевый, красный) и «исправлено» (зелёный):
все цвета — с контрастом не ниже 4.5:1 на белом (проверяет tests/civic/R17/test_r17_profiles.py).
"""

from __future__ import annotations

SERVICE_IDS = (
    "road", "traffic", "street_cleaning", "transport", "lighting", "landscaping", "greenery", "waste",
    "utilities", "heating", "water", "power", "gas", "housing", "ecology", "emergency", "police", "animals",
    "parking", "akimat",
)

KINDS = ("utility", "road", "cleaning", "transport", "safety", "social", "admin")

# Цвет вида службы (текст и точка на белом/стекле). Синий, сланцевый, фиолетовый, бирюзово-синий, сливовый,
# коричневый, тёплый серый — без красного/оранжевого/жёлтого (тепловая карта) и без зелёного («исправлено»).
KIND_COLORS = {
    "utility": "#1f5fa8",
    "road": "#4b5d7a",
    "cleaning": "#6a4c9c",
    "transport": "#0e6378",
    "safety": "#8a3a68",
    "social": "#7a5230",
    "admin": "#5b5f5c",
}

# Значки — из набора ui-kit (web/civic/ui-kit/icons.svg, id без префикса «i-»). Точные значки служб раунда 15 дал R11
# (INTEGRATION R11: R17-6, R17-10 — radiator, zap, flame, paw, traffic, siren, broom, wrench); в сборке со старым
# спрайтом (FINAL-4) экран берёт icon_fallback — ближайший значок старого набора.
# sla_fix_days — настройка прототипа (см. шапку файла).
PROFILES = {
    "road":            {"kind": "road",      "icon": "road",       "sla_fix_days": 20},
    "traffic":         {"kind": "road",      "icon": "traffic", "icon_fallback": "alert",      "sla_fix_days": 5},
    "street_cleaning": {"kind": "cleaning",  "icon": "broom", "icon_fallback": "snowflake",  "sla_fix_days": 2},
    "transport":       {"kind": "transport", "icon": "bus",        "sla_fix_days": 10},
    "lighting":        {"kind": "utility",   "icon": "bulb",       "sla_fix_days": 7},
    "landscaping":     {"kind": "cleaning",  "icon": "playground", "sla_fix_days": 20},
    "greenery":        {"kind": "cleaning",  "icon": "trees",      "sla_fix_days": 20},
    "waste":           {"kind": "cleaning",  "icon": "trash",      "sla_fix_days": 3},
    "utilities":       {"kind": "utility",   "icon": "wrench", "icon_fallback": "building",   "sla_fix_days": 5},
    "heating":         {"kind": "utility",   "icon": "radiator", "icon_fallback": "home",       "sla_fix_days": 2},
    "water":           {"kind": "utility",   "icon": "droplet",    "sla_fix_days": 3},
    "power":           {"kind": "utility",   "icon": "zap", "icon_fallback": "bulb",       "sla_fix_days": 2},
    "gas":             {"kind": "utility",   "icon": "flame", "icon_fallback": "wind",       "sla_fix_days": 1},
    "housing":         {"kind": "utility",   "icon": "home",       "sla_fix_days": 10},
    "ecology":         {"kind": "cleaning",  "icon": "wind",       "sla_fix_days": 10},
    "emergency":       {"kind": "safety",    "icon": "siren", "icon_fallback": "shield",     "sla_fix_days": 1},
    "police":          {"kind": "safety",    "icon": "shield",     "sla_fix_days": 3},
    "animals":         {"kind": "safety",    "icon": "paw", "icon_fallback": "alert",      "sla_fix_days": 5},
    "parking":         {"kind": "road",      "icon": "parking",    "sla_fix_days": 10},
    "akimat":          {"kind": "admin",     "icon": "building",   "sla_fix_days": 15},
}

# Подписи видов служб (для фильтра табло). Это наши слова интерфейса, не названия организаций.
KIND_LABELS = {
    "utility": {"ru": "Сети и ЖКХ", "kk": "Желілер және ТКШ"},
    "road": {"ru": "Дороги", "kk": "Жолдар"},
    "cleaning": {"ru": "Чистота и зелень", "kk": "Тазалық және көгал"},
    "transport": {"ru": "Транспорт", "kk": "Көлік"},
    "safety": {"ru": "Безопасность", "kk": "Қауіпсіздік"},
    "social": {"ru": "Социальные", "kk": "Әлеуметтік"},
    "admin": {"ru": "Акимат", "kk": "Әкімдік"},
}

# Запасной срок ответа, если таблиц R08/R09 нет в сборке (срок R09 по категории «Другое»).
FALLBACK_ANSWER_DAYS = 10


def _r08_routing():
    try:
        from ui.civic_akim import routing  # type: ignore
        return routing
    except Exception:  # noqa: BLE001 — модуля R08 нет в сборке: работаем на запасной таблице
        return None


def _r09_lifecycle():
    try:
        from ui.civic_feedback.v2 import lifecycle  # type: ignore
        return lifecycle
    except Exception:  # noqa: BLE001
        return None


def _response_days() -> dict:
    try:
        from ui.civic_feedback.v2 import categories  # type: ignore
        return dict(categories.RESPONSE_DAYS)
    except Exception:  # noqa: BLE001
        return {}


def service_names() -> dict:
    """{id: {"ru", "kk", "edited"}} — названия служб из таблицы R08 (с правками акимата).

    Нет R08 — копия R09; нет и её — пустые подписи (экран покажет ключ словаря R11 service.<id>).
    """
    routing = _r08_routing()
    if routing is not None:
        try:
            services = routing.table().get("services") or {}
            return {sid: {"ru": str(v.get("ru") or ""), "kk": str(v.get("kk") or ""), "edited": bool(v.get("edited"))}
                    for sid, v in services.items() if sid in PROFILES}
        except Exception:  # noqa: BLE001 — повреждён файл правок R08: берём умолчания R08
            services = getattr(routing, "SERVICES", {})
            return {sid: {"ru": v["ru"], "kk": v["kk"], "edited": False} for sid, v in services.items() if sid in PROFILES}
    lifecycle = _r09_lifecycle()
    services = getattr(lifecycle, "SERVICES", {}) if lifecycle is not None else {}
    return {sid: {"ru": services.get(sid, {}).get("ru", ""), "kk": services.get(sid, {}).get("kk", ""), "edited": False}
            for sid in SERVICE_IDS}


def answer_days() -> dict:
    """{id службы: самый короткий срок ответа (рабочих дней) среди категорий, которые идут в эту службу}."""
    days = _response_days()
    routing = _r08_routing()
    rules = dict(getattr(routing, "DEFAULT_RULES", {}) or {}) if routing is not None else {}
    if not rules:
        lifecycle = _r09_lifecycle()
        rules = dict(getattr(lifecycle, "SERVICE_RULES", {}) or {}) if lifecycle is not None else {}
    out: dict[str, int] = {}
    for key, sid in rules.items():
        category = key.split("/", 1)[0]
        if category in days and sid in PROFILES:
            out[sid] = min(out.get(sid, days[category]), days[category])
    return {sid: out.get(sid, FALLBACK_ANSWER_DAYS) for sid in SERVICE_IDS}


def profile(sid: str, names: dict | None = None, answers: dict | None = None) -> dict:
    """Профиль одной службы по CONTRACT §5.4 + названия R08 (ru/kk) для экрана."""
    if sid not in PROFILES:
        raise KeyError(sid)
    base = PROFILES[sid]
    names = names if names is not None else service_names()
    answers = answers if answers is not None else answer_days()
    name = names.get(sid) or {}
    return {
        "id": sid, "kind": base["kind"], "color": KIND_COLORS[base["kind"]], "icon": base["icon"],
        # Значок из спрайта ui-kit раунда 15 (R11); в сборке со старым спрайтом экран берёт icon_fallback.
        "icon_fallback": base.get("icon_fallback", base["icon"]),
        "sla_answer_days": answers.get(sid, FALLBACK_ANSWER_DAYS), "sla_fix_days": base["sla_fix_days"],
        "sla_fix_source": "default",  # настройка прототипа, не норматив
        "ru": name.get("ru") or "", "kk": name.get("kk") or "", "name_edited": bool(name.get("edited")),
    }


def all_profiles() -> list[dict]:
    """Все 20 служб в порядке справочника (CONTRACT §3) — для GET agencies, R12 (цвета полос), R08."""
    names, answers = service_names(), answer_days()
    return [profile(sid, names, answers) for sid in SERVICE_IDS]


def kinds() -> list[dict]:
    return [{"id": kind, "color": KIND_COLORS[kind], **KIND_LABELS[kind]} for kind in KINDS]
