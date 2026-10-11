"""«Кому передано»: таблица «категория / уточнение → служба» (раунд 14, волна мелочей п. 7).

    from ui.civic_akim import routing
    routing.service_for("roads", "traffic_light_broken")
    # → {"id": "traffic", "ru": "Служба светофоров и разметки", "kk": "…", "rule": "subtopic", "edited": False}

Правила:
- Названия служб — ОБЩИЕ («Дорожная служба», «Водоканал»). Реальные названия организаций не придумываем:
  если акимат захочет — впишет их сам (PUT ниже), и это будет его решение, а не наша догадка.
- Поиск: уточнение (subtopic) → категория → «Другое». Неизвестная категория — тоже «Другое».
- Таблица по умолчанию — DEFAULT_RULES здесь. Правки акимата хранятся отдельно, в файле
  .runtime/civic_akim/routing.json (в Git не попадает; путь можно задать BIRGE_AKIM_ROUTING) — так
  обновление кода не стирает их, а «сбросить» = удалить файл.
- Категории и уточнения — из categories_v2.json (единственный источник); validate() сверяет таблицу с ним.
- kk названий служб вычитан R11 (словарь service.<id>, разбор волны 2 №1); на экране — t("service." + id),
  а если акимат переименовал службу (edited) — его название как есть.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import deadlines

ROOT = deadlines.ROOT
OVERRIDE_PATH = Path(os.environ.get("BIRGE_AKIM_ROUTING") or ROOT / ".runtime" / "civic_akim" / "routing.json")
NAME_MAX = 80

SERVICES = {
    "road":            {"ru": "Дорожная служба", "kk": "Жол қызметі"},
    "traffic":         {"ru": "Служба светофоров и разметки", "kk": "Бағдаршам және жол таңбасы қызметі"},
    "street_cleaning": {"ru": "Служба уборки улиц", "kk": "Көшелерді тазалау қызметі"},
    "transport":       {"ru": "Служба общественного транспорта", "kk": "Қоғамдық көлік қызметі"},
    "lighting":        {"ru": "Служба освещения", "kk": "Жарықтандыру қызметі"},
    "landscaping":     {"ru": "Служба благоустройства", "kk": "Абаттандыру қызметі"},
    "greenery":        {"ru": "Служба озеленения", "kk": "Көгалдандыру қызметі"},
    "waste":           {"ru": "Оператор вывоза мусора", "kk": "Қоқыс шығару операторы"},
    "utilities":       {"ru": "Служба ЖКХ", "kk": "ТКШ қызметі"},
    "heating":         {"ru": "Теплосеть", "kk": "Жылу желісі"},
    "water":           {"ru": "Водоканал", "kk": "Сумен жабдықтау қызметі"},
    "power":           {"ru": "Электросети", "kk": "Электр желілері"},
    "gas":             {"ru": "Газовая служба", "kk": "Газ қызметі"},
    "housing":         {"ru": "Управляющая компания дома", "kk": "Үйді басқарушы компания"},
    "ecology":         {"ru": "Служба экологии", "kk": "Экология қызметі"},
    "emergency":       {"ru": "Служба спасения", "kk": "Құтқару қызметі"},
    "police":          {"ru": "Полиция", "kk": "Полиция"},
    "animals":         {"ru": "Служба отлова животных", "kk": "Жануарларды аулау қызметі"},
    "parking":         {"ru": "Служба парковок", "kk": "Тұрақ қызметі"},
    "akimat":          {"ru": "Аппарат акима района", "kk": "Аудан әкімінің аппараты"},
}

# Ключ — категория или «категория/уточнение». Уточнение, которого здесь нет, идёт в службу категории.
DEFAULT_RULES = {
    "roads": "road",
    "roads/traffic_light_broken": "traffic",
    "roads/traffic_light_timing": "traffic",
    "roads/intersection": "traffic",
    "roads/marking": "traffic",
    "snow_ice": "street_cleaning",
    "snow_ice/icicles": "housing",          # снег и сосульки с крыши убирает тот, кто обслуживает дом
    "sidewalks": "road",
    "sidewalks/crossing": "traffic",
    "transport": "transport",
    "lighting": "lighting",
    "lighting/wire_down": "power",          # оборванный провод — электросети (и баннер «звоните 112» у R09)
    "yards": "landscaping",
    "yards/trees_lawn": "greenery",
    "waste": "waste",
    "utilities": "utilities",
    "utilities/no_heating": "heating",
    "utilities/no_water": "water",
    "utilities/sewage": "water",
    "utilities/power_building": "power",
    "smell_air": "ecology",
    "smell_air/gas": "gas",
    "smell_air/smoke_fire": "emergency",
    "noise_safety": "police",
    "noise_safety/stray_dogs": "animals",
    "parking": "parking",
    "parking/sidewalk_parking": "police",
    "other": "akimat",
}

_lock = threading.Lock()


class RoutingError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field


# ---------------------------------------------------------------- справочник категорий

def _categories() -> dict:
    """id → {"ru","kk","subtopics": {id: {"ru","kk"}}} из categories_v2.json."""
    out = {}
    for c in deadlines.load_categories()["categories"]:
        out[c["id"]] = {"ru": c["ru"], "kk": c["kk"],
                        "subtopics": {s["id"]: {"ru": s["ru"], "kk": s["kk"]} for s in c.get("subtopics") or []}}
    return out


def _check_key(key: str, cats: dict) -> None:
    cat, _, sub = key.partition("/")
    if cat not in cats:
        raise RoutingError("category", f"неизвестная категория: {cat}")
    if sub and sub not in cats[cat]["subtopics"]:
        raise RoutingError("subtopic", f"у категории {cat} нет уточнения {sub}")


def validate() -> None:
    """Таблица по умолчанию согласована с categories_v2.json: у каждой категории есть служба, ключи настоящие."""
    cats = _categories()
    for key, service in DEFAULT_RULES.items():
        _check_key(key, cats)
        if service not in SERVICES:
            raise ValueError(f"нет службы {service} для {key}")
    missing = sorted(set(cats) - set(DEFAULT_RULES))
    if missing:
        raise ValueError(f"у категорий нет службы: {missing}")


# ---------------------------------------------------------------- правки акимата

def _load_override(path: Path | None = None) -> dict:
    p = Path(path or OVERRIDE_PATH)
    try:
        data = json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return {"rules": {}, "services": {}}
    return {"rules": dict(data.get("rules") or {}), "services": dict(data.get("services") or {}),
            "updated_at": data.get("updated_at"), "updated_by": data.get("updated_by")}


def table(path: Path | None = None) -> dict:
    """Действующая таблица: умолчания + правки акимата. Для экрана и для GET."""
    over = _load_override(path)
    services = {k: dict(v) for k, v in SERVICES.items()}
    for sid, names in over["services"].items():
        if sid in services and isinstance(names, dict):
            services[sid].update({lang: names[lang] for lang in ("ru", "kk") if isinstance(names.get(lang), str) and names[lang].strip()})
            services[sid]["edited"] = True
    rules = dict(DEFAULT_RULES)
    edited = set()
    for key, sid in over["rules"].items():
        if sid in services:
            rules[key] = sid
            edited.add(key)
    cats = _categories()
    rows = []
    for cat_id, cat in cats.items():
        cat_service = rules.get(cat_id, "akimat")
        rows.append({"key": cat_id, "category": cat_id, "subtopic": None, "ru": cat["ru"], "kk": cat["kk"],
                     "service": cat_service, "edited": cat_id in edited})
        for sub_id, sub in cat["subtopics"].items():
            key = f"{cat_id}/{sub_id}"
            rows.append({"key": key, "category": cat_id, "subtopic": sub_id, "ru": sub["ru"], "kk": sub["kk"],
                         "service": rules.get(key, cat_service), "own": key in rules, "edited": key in edited})
    # R15-S28: GET /akim/routing — публичный; логин сотрудника (updated_by) остаётся только в файле правок.
    return {"services": services, "rules": rows, "updated_at": over.get("updated_at"),
            "note": "Общие названия служб; акимат может уточнить."}


def service_for(category: str | None, subtopic: str | None = None, path: Path | None = None) -> dict:
    """Служба для обращения. rule: subtopic | category | fallback (категория неизвестна → «Другое»)."""
    over = _load_override(path)
    rules = {**DEFAULT_RULES, **{k: v for k, v in over["rules"].items() if v in SERVICES}}
    cat = category if category in rules else None
    sid, rule = None, "fallback"
    if cat and subtopic and f"{cat}/{subtopic}" in rules:
        sid, rule = rules[f"{cat}/{subtopic}"], "subtopic"
    elif cat:
        sid, rule = rules[cat], "category"
    else:
        sid = rules["other"]
    names = dict(SERVICES[sid])
    custom = over["services"].get(sid)
    if isinstance(custom, dict):
        names.update({lang: custom[lang] for lang in ("ru", "kk") if isinstance(custom.get(lang), str) and custom[lang].strip()})
    key = f"{cat}/{subtopic}" if rule == "subtopic" else (cat or "other")
    # name_edited — акимат переименовал службу: интерфейс показывает его название, а не service.<id> из словаря.
    return {"id": sid, "ru": names["ru"], "kk": names["kk"], "rule": rule,
            "edited": bool(custom) or key in over["rules"], "name_edited": bool(custom)}


def _clean_name(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoutingError(field, "название службы не может быть пустым")
    name = " ".join(value.split())
    if len(name) > NAME_MAX:
        raise RoutingError(field, f"название длиннее {NAME_MAX} знаков")
    if any(ch in name for ch in "<>{}"):
        raise RoutingError(field, "в названии недопустимы знаки < > { }")
    return name


def update(changes: dict, *, actor: str | None = None, path: Path | None = None, now: datetime | None = None) -> dict:
    """Правка акимата. changes = {"rules": {"roads/marking": "road", "yards": null}, "services": {"road": {"ru": "…"}}}.

    null у правила — вернуть умолчание. Пишем атомарно (временный файл + replace). Права проверяет вызывающий
    (api.handle_put принимает только staff=True; кто сотрудник — решает шлюз R01 с CSRF, как у R06/R09).
    """
    if not isinstance(changes, dict) or not (changes.get("rules") or changes.get("services")):
        raise RoutingError("body", "нужны rules или services")
    cats = _categories()
    p = Path(path or OVERRIDE_PATH)
    with _lock:
        over = _load_override(p)
        for key, sid in (changes.get("rules") or {}).items():
            if not isinstance(key, str):
                raise RoutingError("rules", "ключ — категория или категория/уточнение")
            _check_key(key, cats)
            if sid is None or sid == DEFAULT_RULES.get(key):
                over["rules"].pop(key, None)
            elif sid not in SERVICES:
                raise RoutingError("service", f"неизвестная служба: {sid}")
            else:
                over["rules"][key] = sid
        for sid, names in (changes.get("services") or {}).items():
            if sid not in SERVICES:
                raise RoutingError("service", f"неизвестная служба: {sid}")
            if names is None:
                over["services"].pop(sid, None)
                continue
            if not isinstance(names, dict):
                raise RoutingError("services", "названия — {ru, kk}")
            clean = {lang: _clean_name(names[lang], f"services.{sid}.{lang}") for lang in ("ru", "kk") if lang in names}
            merged = {**over["services"].get(sid, {}), **clean}
            if merged == SERVICES[sid]:
                over["services"].pop(sid, None)
            else:
                over["services"][sid] = merged
        stamp = (now or datetime.now(timezone.utc)).astimezone(timezone(timedelta(hours=5))).isoformat(timespec="seconds")
        data = {"rules": over["rules"], "services": over["services"], "updated_at": stamp,
                "updated_by": (str(actor)[:80] if actor else None)}
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, p)
    return table(p)


def assignee_lookup(category: str | None, subtopic: str | None = None) -> dict:
    """Для R09 (store.assignee_lookup, паспорт решения «Отвечает: …»): {"ru", "kk", "id"}.

    R09 lifecycle.passport_view принимает строку или словарь {ru, kk} (claude/modest-shannon-0ki93p @ 2bf9a92);
    id — чтобы интерфейс мог взять t("service." + id) из словаря R11, если акимат службу не переименовывал.
    """
    s = service_for(category, subtopic)
    return {"ru": s["ru"], "kk": s["kk"], "id": s["id"], "edited": s["name_edited"]}
