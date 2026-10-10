"""Подписи улиц для двух языков без выдуманных переводов (только стандартная библиотека).

В OSM у половины улиц Астаны нет name:kk (10 390 из 20 289 рёбер с названием). Тогда по-казахски переводим
только слово-тип улицы и ставим его после имени, имя собственное не трогаем: «улица Сыганак» → «Сыганак көшесі».
Таблица та же, что у R07 (ui/civic_heat/targets.py, kk_street_from_ru) — один и тот же объект подписан одинаково
на шаге «Это здесь?» (R12) и в карточке тепловой карты (R07). Решение R11 (UX_REVIEW B3 п. 4): участок — «бөлік».
"""
from __future__ import annotations

# Русский тип улицы → казахский (после названия). Регистр первой буквы типа не важен («Улица …» встречается 211 раз).
KK_TYPES = (("улица", "көшесі"), ("проспект", "даңғылы"), ("переулок", "тұйық көшесі"),
            ("шоссе", "тас жолы"), ("бульвар", "бульвары"), ("площадь", "алаңы"))

# Родительный падеж казахского слова-типа: окончание известно заранее («көшесі» → «көшесінің»).
KK_GENITIVE = (("көшесі", "нің"), ("даңғылы", "ның"), ("жолы", "ның"), ("бульвары", "ның"), ("алаңы", "ның"))

# Русский родительный падеж слова-типа для «у улицы Сауран»: имя после типа остаётся в именительном.
RU_GENITIVE = (("улица", "улицы"), ("проспект", "проспекта"), ("переулок", "переулка"), ("шоссе", "шоссе"),
               ("бульвар", "бульвара"), ("площадь", "площади"), ("набережная", "набережной"))


def _split_type(name: str, table) -> tuple[str, str] | None:
    """('улица', 'Сыганак') для «улица Сыганак» и «Сыганак улица»; None — тип не распознан."""
    low = name.lower()
    for ru_type, _ in table:
        if low.startswith(ru_type + " ") and len(name) > len(ru_type) + 1:
            return ru_type, name[len(ru_type) + 1:].strip()
        if low.endswith(" " + ru_type) and len(name) > len(ru_type) + 1:
            return ru_type, name[: -len(ru_type) - 1].strip()
    return None


def kk_street(name_ru: str | None, name_kk: str | None = None) -> str | None:
    """Казахская подпись улицы: name:kk из OSM; иначе тип по-казахски после имени; иначе имя как есть."""
    if name_kk:
        return name_kk
    if not name_ru:
        return None
    split = _split_type(name_ru, KK_TYPES)
    if not split:
        return name_ru
    kk_type = dict(KK_TYPES)[split[0]]
    return f"{split[1]} {kk_type}"


def kk_genitive(name_kk: str | None) -> str | None:
    """«Сығанақ көшесі» → «Сығанақ көшесінің»; неизвестное окончание → None (тогда подпись через двоеточие)."""
    if not name_kk:
        return None
    for ending, suffix in KK_GENITIVE:
        if name_kk.endswith(ending):
            return name_kk + suffix
    return None


def ru_near(name_ru: str | None) -> str | None:
    """«улица Сауран» → «у улицы Сауран»; тип не распознан → None (тогда подпись через тире)."""
    if not name_ru:
        return None
    split = _split_type(name_ru, RU_GENITIVE)
    if not split or not name_ru.lower().startswith(split[0]):
        return None
    return "у " + dict(RU_GENITIVE)[split[0]] + " " + split[1]


def segment_labels(name_ru: str | None, name_kk: str | None = None) -> tuple[str, str]:
    """Подпись участка улицы с названием: «Участок: проспект Туран» / «Тұран даңғылының бөлігі»."""
    kk = kk_street(name_ru, name_kk)
    gen = kk_genitive(kk)
    return f"Участок: {name_ru}", (f"{gen} бөлігі" if gen else f"{kk}: көше бөлігі")


# Безымянный участок: что это и как сказать «рядом с улицей …».
UNNAMED = {
    # группа: (ru без улицы, kk без улицы, ru-слово, kk-слово)
    "foot": ("Тротуар или дорожка без названия", "Атауы жоқ жаяу жол", "Тротуар или дорожка", "жаяу жол"),
    "service": ("Проезд без названия", "Атауы жоқ өтпе жол", "Проезд", "өтпе жол"),
    "other": ("Участок улицы без названия", "Атауы жоқ көше бөлігі", "Улица без названия", "атауы жоқ көше"),
}


def unnamed_labels(group: str, near_ru: str | None = None, near_kk: str | None = None) -> tuple[str, str]:
    """Безымянный участок с привязкой к ближайшей улице с названием (UX_REVIEW R11 B2 п. 2):
    «Проезд у улицы Сауран» / «Сауран көшесі маңындағы өтпе жол»; без улицы рядом — «Проезд без названия»."""
    ru0, kk0, ru_word, kk_word = UNNAMED.get(group if group in ("foot", "service") else "other")
    if not near_ru:
        return ru0, kk0
    near = ru_near(near_ru)
    ru = f"{ru_word} {near}" if near else f"{ru_word} — {near_ru}"
    return ru, f"{kk_street(near_ru, near_kk)} маңындағы {kk_word}"
