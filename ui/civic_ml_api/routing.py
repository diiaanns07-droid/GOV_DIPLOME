"""route() — каким службам нужно обращение (CONTRACT §7: POST /api/civic/v2/route; §5.1 route_hint). Без сети.

    from ui.civic_ml_api import route
    route(text="Яма после раскопок водоканала")
    # -> {"services": [{"service": "water", "role": "lead", …}, {"service": "road", "role": "partner", …}],
    #     "joint": True, "summary_ru": "Нужны 2 службы: Водоканал и Дорожная служба", "why_ru": "…", …}

Как решаем (по порядку):
  1. Категория и уточнение. Выбрал житель или сотрудник (category, subtopic) — берём их; уточнения нет — ищем его
     по словам текста внутри той же категории. Категории нет — сначала «сигналы» текста (ниже, SIGNALS: «лифт»,
     «канализация», «светофор» …), затем категория модели (classify, как /classify).
  2. Основная служба — таблица R08 «категория/уточнение -> служба» (ui.civic_akim.routing.service_for, с правками
     акимата). Нет R08 — копия умолчаний у R09 (ui.civic_feedback.v2.lifecycle), нет и её — своя копия (_DEFAULT_RULES).
     Сигнал может назвать свою службу (Signal.service) только там, где в таблице нет строки; сейчас таких нет:
     лифт, подъезд и крыша идут по таблице («ЖКХ» -> utilities), как в демо-мире R02.
  3. Правила совместных случаев (JOINT, по порядку, срабатывает первое): дерево на проводах; упал столб с проводами;
     течь из сети + наледь; раскопки или прорыв сети + яма/провал (служба сетей + служба покрытия); снег и сосульки с крыши
     на неубранном тротуаре; светофор без электричества; два отключения разных сетей; две разные проблемы в одном тексте.
  4. Ответ: services — только НУЖНЫЕ службы (ведущая первой, role lead/partner), joint = служб больше одной; объяснение
     одной строкой ru/kk (summary_* + why_*); source rules|model (как route_hint R09); model_version.

Числа score — уверенность правила (0..1), не вероятность: «правило по таблице» 0.9–0.95, «сигнал текста» 0.85,
«служба сетей не названа, чаще всего водопровод» 0.6. Названия служб — из таблицы R08 (общие, акимат может уточнить);
своих служб и реальных названий организаций здесь нет — только id CONTRACT §3.

Текст сравнивается в «сведённом» виде (ml.civic_dedup.normalize): нижний регистр, латиница из чатов -> кириллица,
казахские буквы -> русские двойники (қ -> к, ү -> у, і -> и), й -> и, без пунктуации и цифр. Поэтому шаблоны ниже
пишутся сведёнными: «шункыр» = «шұңқыр», «кубыр» = «құбыр», «жок» = «жоқ», «аулада», «казып» = «қазып».
Набор проверки — tests/civic/R04/round15/route_cases.json (dev/test, протокол — в самом файле).
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass

from ml.civic_dedup.normalize import letters, normalize
from ui.civic_ml_api import categories as C

VERSION = "r04-route-1"
MAX_TEXT = 5000
# Город с запасом (как ASTANA_BOUNDS шлюза R01): точка вне — ошибка ввода.
ASTANA_BOUNDS = (70.9, 50.8, 72.0, 51.5)

# ---------------------------------------------------------------- службы: таблица R08 и запасные копии
# Копия умолчаний R08 (ui/civic_akim/routing.py DEFAULT_RULES, = R09 lifecycle.SERVICE_RULES) — только если обоих нет.
_DEFAULT_RULES = {
    "roads": "road", "roads/traffic_light_broken": "traffic", "roads/traffic_light_timing": "traffic",
    "roads/intersection": "traffic", "roads/marking": "traffic",
    "snow_ice": "street_cleaning", "snow_ice/icicles": "housing",
    "sidewalks": "road", "sidewalks/crossing": "traffic",
    "transport": "transport",
    "lighting": "lighting", "lighting/wire_down": "power",
    "yards": "landscaping", "yards/trees_lawn": "greenery",
    "waste": "waste",
    "utilities": "utilities", "utilities/no_heating": "heating", "utilities/no_water": "water",
    "utilities/sewage": "water", "utilities/power_building": "power",
    "smell_air": "ecology", "smell_air/gas": "gas", "smell_air/smoke_fire": "emergency",
    "noise_safety": "police", "noise_safety/stray_dogs": "animals",
    "parking": "parking", "parking/sidewalk_parking": "police",
    "other": "akimat",
}
SERVICE_IDS = ("road", "traffic", "street_cleaning", "transport", "lighting", "landscaping", "greenery", "waste",
               "utilities", "heating", "water", "power", "gas", "housing", "ecology", "emergency", "police", "animals",
               "parking", "akimat")
_NAMES_TTL_S = 10.0          # правку названий акиматом видим не позже чем через 10 с
_names_cache: dict = {"at": 0.0, "names": None}
_names_lock = threading.Lock()


def _r08():
    try:
        from ui.civic_akim import routing as r08
        return r08
    except Exception:  # noqa: BLE001 — модуль соседа не обязателен
        return None


def _fallback_names() -> dict:
    try:
        from ui.civic_feedback.v2.lifecycle import SERVICES
        return {sid: dict(SERVICES[sid]) for sid in SERVICE_IDS if sid in SERVICES}
    except Exception:  # noqa: BLE001
        return {sid: {"ru": sid, "kk": sid} for sid in SERVICE_IDS}


def service_names() -> dict:
    """id -> {"ru", "kk"}: таблица R08 с правками акимата (кэш 10 с); нет R08 — копия R09."""
    now = time.monotonic()
    cached = _names_cache["names"]
    if cached is not None and now - _names_cache["at"] < _NAMES_TTL_S:
        return cached
    with _names_lock:
        names = None
        r08 = _r08()
        if r08 is not None:
            try:
                names = {sid: {"ru": v["ru"], "kk": v["kk"]} for sid, v in r08.table()["services"].items()}
            except Exception:  # noqa: BLE001 — файл правок повреждён и т. п.: запасные названия
                names = None
        if not names:
            names = _fallback_names()
        _names_cache.update(at=now, names=names)
        return names


def table_service(category: str, subtopic: str | None) -> tuple[str, str]:
    """(id службы, правило subtopic|category|fallback) по таблице R08 (с правками акимата) или запасной копии."""
    r08 = _r08()
    if r08 is not None:
        try:
            found = r08.service_for(category, subtopic)
            if found.get("id") in SERVICE_IDS:
                return found["id"], found.get("rule") or "category"
        except Exception:  # noqa: BLE001
            pass
    if subtopic and f"{category}/{subtopic}" in _DEFAULT_RULES:
        return _DEFAULT_RULES[f"{category}/{subtopic}"], "subtopic"
    if category in _DEFAULT_RULES:
        return _DEFAULT_RULES[category], "category"
    return _DEFAULT_RULES["other"], "fallback"


# ---------------------------------------------------------------- категории (подписи для объяснений)
def _cat_index() -> dict:
    data = C._data()  # noqa: SLF001 — тот же файл categories_v2.json, что у classify
    out = {}
    for cat in data["categories"]:
        out[cat["id"]] = {"ru": cat["ru"], "kk": cat["kk"],
                          "subtopics": {s["id"]: {"ru": s["ru"], "kk": s["kk"]} for s in cat.get("subtopics") or []}}
    return out


_CATS: dict | None = None


def categories() -> dict:
    global _CATS
    if _CATS is None:
        _CATS = _cat_index()
    return _CATS


# ---------------------------------------------------------------- сигналы текста (одна служба)
@dataclass(frozen=True)
class Signal:
    name: str
    rx: re.Pattern
    category: str
    subtopic: str | None = None
    service: str | None = None      # служба без строки в таблице R08 (лифт -> housing)
    strong: bool = True             # сильный сигнал важнее категории модели; слабый — только если модель молчит
    label_ru: str | None = None     # подпись для объяснения, если нет подписи уточнения
    label_kk: str | None = None
    unless: re.Pattern | None = None  # сигнал не считается, если в тексте есть это («не горит фонарь» — не пожар)


def _rx(*parts: str) -> re.Pattern:
    return re.compile("|".join(parts))


# Порядок важен: срабатывает ПЕРВЫЙ подходящий (узкое — раньше общего). Порядок проверен на наборе R04 и на корпусах
# R02 (synth_v3, probe_v2): снег раньше двора («снег свалили на детскую площадку»), мусор раньше остановки («урны у
# остановки»), фонарь раньше автобуса («не горит фонарь, ждём автобус»), газон — слабый сигнал («яма, ездят по газону»).
SIGNALS = (
    Signal("gas", _rx(r"\bзапах\w* газ", r"\bпахнет газ", r"\bгазом\b", r"\bгаз иис", r"\bутечк\w* газ",
                      r"\bнет газа\b", r"\bгаз жок"), "smell_air", "gas"),
    Signal("burning", _rx(r"\bжгут\b", r"\bсжига\w*", r"\bгар(ь|и)\b", r"\bжжет\b", r"\bорте(иди|п|ди|у)\b",
                          r"\bкуиик ии"), "smell_air"),
    Signal("fire", _rx(r"\bпожар\w*", r"\bдым\b", r"\bдым из", r"\bдымит\w*", r"\bзадымлен\w*", r"\bтутин\w*",
                       r"\bжанып жатыр", r"что то горит"), "smell_air", "smoke_fire"),
    Signal("fire_burns", _rx(r"\bгор(ит|ят)\b", r"\bзагорел\w*", r"\bподожгл\w*"), "smell_air", "smoke_fire",
           unless=_rx(r"\bне гор(ит|ят)\b", r"\bфонар", r"\bсвет", r"\bламп", r"\bосвещ", r"\bшам", r"\bжарык",
                      r"\bсветофор", r"\bгорит (красн|зелен|желт)", r"\bсроки? гор", r"\bтабло")),
    Signal("wire_down", _rx(r"\bоборва\w* провод", r"\bпровод\w* оборва", r"\bобрыв\w* провод",
                            r"\bпровод\w* (лежит|лежат|висит|висят|на земле)", r"\bсым\w* (узил|жерде|узип)",
                            r"\bузилген сым"), "lighting", "wire_down"),
    # Лифт, подъезд, крыша, лампочки в подъезде — категория «ЖКХ» без уточнения: служба по таблице R08 (сейчас
    # «Служба ЖКХ»). Своя служба здесь не подставляется, чтобы подсказка не спорила с таблицей акимата (демо-мир R02
    # считает так же); акимат может поменять службу категории в таблице R08.
    Signal("housing_lamps", _rx(r"\bлампоч\w*", r"\bв подъезд\w*\b.{0,20}\b(темно|не гор)",
                                r"\bкиреберис\w*\b.{0,20}\b(шам|жарык|караны)", r"\b(шам|жарык)\w*\b.{0,20}\bкиреберис"),
           "utilities"),
    Signal("power_building", _rx(
        r"\b(в доме|в квартир\w*|во всем доме|в подъезд\w*|в нашем район\w*|по всему район\w*|во всем район\w*)\b"
        r".{0,30}\b(свет|электричеств)",
        r"\b(свет|электричеств)\w*\b.{0,25}\b(в доме|в квартир|во всем доме|в район)",
        r"\bотключа\w* свет", r"\bотключил\w* свет", r"\bсвет\w* отключ", r"\bнет электричеств", r"\bбез электричеств",
        r"\bэлектр\w* жок", r"\bуиде (де )?жарык", r"\bпатерде (де )?жарык"), "utilities", "power_building"),
    Signal("no_heating", _rx(r"\bотоплени\w*", r"\bбатаре\w*", r"\bтеплотрасс\w*", r"\bтеплосет\w*", r"\bгоряч\w* вод",
                             r"\bжылу\b", r"\bыстык су", r"\bнет тепла\b", r"\bхолодно в (квартир|доме)",
                             r"\bжылу жели\w*"), "utilities", "no_heating"),
    Signal("sewage", _rx(r"\bканализ\w*", r"\bкариз\w*", r"\bколлектор\w*", r"\bлюк\w*", r"\bколод(ец|ца|цы|це)\b",
                         r"\bфекал\w*"), "utilities", "sewage"),
    Signal("no_water", _rx(r"\bнет (холодн\w* )?вод", r"\bбез вод", r"\bотключ\w* (холодн\w* )?вод", r"\bсу жок",
                           r"\bсуык су", r"\bводокана\w*", r"\bводопровод\w*", r"\bржав\w* вод", r"\bиз крана",
                           r"\bкубыр\w*", r"\bтруб(а|у|ы|ои|е)\b", r"\bсумен жабдыкта\w*", r"\bнапор\w* вод",
                           r"\bдавлени\w* вод", r"\bсудын кысым\w*", r"\bсу кысым\w*"), "utilities", "no_water"),
    Signal("underpass", _rx(r"\b(подземн|надземн)\w* переход\w*", r"\bжер асты\w*"), "sidewalks", "broken_sidewalk"),
    Signal("storm_drain", _rx(r"\bливнев\w*", r"\bливнест\w*", r"\bносер кариз\w*"), "roads", "pothole"),
    Signal("housing", _rx(r"\bлифт\w*", r"\bподъезд\w*\b.{0,25}\b(мыть|моют|грязн\w*|не убира\w*|уборк\w*|не убран\w*)",
                          r"\b(грязн\w*|не убира\w*|не моют)\b.{0,20}\bподъезд",
                          r"\bтечет крыш", r"\bкрыш\w* теч", r"\bпротека\w* крыш", r"\bкрыш\w* протека", r"\bдомофон\w*"),
           "utilities"),
    Signal("icicles", _rx(r"\bсосул\w*", r"\bсунги\w*", r"\bснег\w* с крыш", r"\bшатырдан кар", r"\bс крыши"),
           "snow_ice", "icicles"),
    Signal("traffic_light_timing", _rx(r"\bсветофор\w*\b.{0,30}\b(долго|красн|зелен|секунд)",
                                       r"\bбагдаршам\w*\b.{0,30}\b(узак|кызыл|жасыл)"), "roads", "traffic_light_timing"),
    Signal("traffic_light", _rx(r"\bсветофор\w*", r"\bбагдаршам\w*"), "roads", "traffic_light_broken"),
    Signal("marking", _rx(r"\bразметк\w*", r"\bжол танба\w*"), "roads", "marking"),
    Signal("crossing", _rx(r"\bпешеходн\w* переход\w*", r"\bзебр\w*", r"\bжаяу (жургиншилер )?откел\w*"),
           "sidewalks", "crossing"),
    Signal("speed_bump", _rx(r"\bлежач\w* полицеиск\w*", r"\bкедир буды\w*", r"\bискусственн\w* неровност\w*",
                             r"\bжылдамдыкты азаит\w*", r"\bкедерги\w*"), "roads", "speed_bump"),
    Signal("pothole", _rx(r"\bям(а|ы|у)\b.{0,20}\b(на дорог|на проезд|на улиц|на перекрест|асфальт)",
                          r"\b(на дороге|на проезде|на улице|проезд\w*|дорог\w*)\b.{0,20}\bям(а|ы)\b",
                          r"\bжолда\b.{0,20}\bшункыр"), "roads", "pothole"),
    # Собаки — служба отлова, только если они бродячие или опасные: «собаки растаскивают мусор» — это про мусор.
    Signal("stray_dogs", _rx(r"\b(бродяч|бездомн)\w* (собак|пс)\w*", r"\bста(я|и|ю) (бродяч\w* )?собак", r"\bсвор\w*",
                             r"\bсобак\w* (кусают|кидаются|бросаются|напада|бегают стаями)", r"\bкангыбас\w*",
                             r"\bиттер\w*", r"\bпсы\b", r"\bпсов\b"), "noise_safety", "stray_dogs"),
    Signal("noise", _rx(r"\bшум\w*", r"\bшу\b", r"\bгромк\w*", r"\bработа(ет|ют) ночью", r"\bночью работа\w*",
                        r"\bне спят\b", r"\bневозможно спать", r"\bспать невозможно", r"\bне да(ет|ют) спать",
                        r"\bтишин\w*", r"\bуиыктаи алмаи\w*", r"\bшула\w*", r"\bтунде\b.{0,25}\bжумыс\w*"),
           "noise_safety", "noise_night"),
    Signal("sidewalk_parking", _rx(r"\b(парку\w*|парков\w*|машин\w* стоят|ставят машин\w*|колик\w* кои\w*|колик\w* кою\w*)"
                                   r"\b.{0,15}\bтротуар", r"\bтротуар\w*\b.{0,10}\b(парку\w*|колик)",
                                   r"\bтротуарга колик", r"\bзаставлен\w* машин", r"\bмашин\w* на тротуар",
                                   r"\bпарку\w*\b.{0,20}\b(на остановк|у остановк)"), "parking", "sidewalk_parking"),
    Signal("yard_cars", _rx(r"\bмашин\w*\b.{0,30}\b(на газон|во двор)", r"\bна газон\w*\b.{0,20}\b(машин|парку)",
                            r"\bпарку\w*\b.{0,20}\bна газ", r"\bаулада колик\w* кой"), "parking", "yard_cars"),
    Signal("no_spaces", _rx(r"\bнегде (при)?парков\w*", r"\bнет (парковочн\w* )?мест\b", r"\bпарковк\w*",
                            r"\bколик коятын орын", r"\bтурак\w*"), "parking", "no_spaces"),
    Signal("parking", _rx(r"\bпарку\w*", r"\bпаркующ\w*", r"\bприпарков\w*", r"\bброшен\w* (авто|машин)",
                          r"\bбесхоз\w* (авто|машин)", r"\bтасталган колик", r"\bколик\w*\b.{0,20}\bкогал",
                          r"\b(аулада|двор\w*)\b.{0,10}\bорын жок", r"\bжолды жабады", r"\bвыезд\w*\b.{0,15}\b(перекры|загород|заблок)"),
           "parking", "yard_cars"),
    Signal("snow", _rx(r"\bснег\w*", r"\bсугроб\w*", r"\bкар\b", r"\bкар тазаланба", r"\bкарды\b", r"\bуборк\w* сне\w*",
                       r"\bне очищен\w*", r"\bочист\w* от сне\w*"), "snow_ice", "snow_not_cleared"),
    Signal("ice", _rx(r"\bгололед\w*", r"\bналед\w*", r"\bне посыпа\w*", r"\bкоктаигак\w*", r"\bтаигак\w*",
                      r"\bмуз(га|ы|бен|дан|ды)?\b", r"\bкат(ок|ке|ку|ком)\b", r"\bво льду\b", r"\bлед\b"),
           "snow_ice", "ice"),
    Signal("bins", _rx(r"\bбак\w* переполн", r"\bпереполн\w*\b.{0,15}\bбак", r"\bконтеинер\w*", r"\bбаки\b",
                       r"\bурн\w*\b.{0,20}\b(переполн|забит|полн)", r"\b(переполн\w*|забит\w*)\b.{0,20}\bурн"),
           "waste", "bins_full"),
    Signal("dump", _rx(r"\bсвалк\w*", r"\bуииндиси\w*"), "waste", "dump"),
    Signal("waste", _rx(r"\bмусор\w*", r"\bкокыс\w*", r"\bотход\w*", r"\bмебел\w*", r"\bкрупногабарит\w*"),
           "waste", "not_collected"),
    Signal("stop_shelter", _rx(r"\b(скамеи\w*|скамеек|павильон\w*|навес\w*|орындык\w*)\b.{0,20}\b(остановк|аялдама)",
                               r"\b(остановк\w*|аялдама\w*)\b.{0,20}\b(скамеи|скамеек|павильон|навес|орындык)",
                               r"\bпавильон\w*", r"\bтабло\b"), "transport", "stop_shelter"),
    Signal("dark_yard", _rx(r"\b(во дворе|аулада)\b.{0,20}\b(темно|караны\w*|нет освещени|нет света|жарык жок)",
                            r"\b(темно|караны\w*)\b.{0,20}\b(во дворе|аулада)"), "lighting", "dark_yard"),
    Signal("blinking", _rx(r"\b(фонар|светильник)\w*\b.{0,15}\b(мига|гасн)\w*", r"\bмига\w*\b.{0,15}\bфонар",
                           r"\bшам\w* жыпылыкта\w*"),
           "lighting", "blinking"),
    Signal("lamp", _rx(r"\bфонар\w*", r"\bсветильник\w*", r"\bосвещени\w*", r"\bшам(дар\w*|ы)?\b", r"\bжарыктандыр\w*", r"\bтемно\b",
                       r"\bкараны\w*"), "lighting", "lamp_off"),
    Signal("schedule", _rx(r"\bавтобус\w*", r"\bрасписани\w*", r"\bинтервал\w*", r"\bкесте\w*"), "transport", "schedule"),
    Signal("route", _rx(r"\bмаршрут\w*"), "transport", "route"),
    Signal("trees", _rx(r"\bдерев\w*", r"\bтрав(а|у|ы)\b", r"\bбурьян\w*", r"\bагаш\w*", r"\bкуст\w*", r"\bспил\w*",
                        r"\bне кос(ят|ит)\b"), "yards", "trees_lawn"),
    Signal("playground", _rx(r"\bдетск\w* площадк\w*", r"\bкачел\w*", r"\bпесочниц\w*", r"\bбалалар алан\w*"),
           "yards", "playground"),
    Signal("benches", _rx(r"\bскамеек\b", r"\bскамеи\w*", r"\bлавочк\w*", r"\bорындык\w*", r"\bурн\w*"),
           "yards", "benches"),
    Signal("dogs", _rx(r"\bсобак\w*"), "noise_safety", "stray_dogs", strong=False),
    Signal("dust", _rx(r"\bпыл\w*", r"\bшан\b", r"\bвыброс\w*", r"\bнечем дышать", r"\bтыныс алу"), "smell_air", "dust"),
    Signal("sewage_smell", _rx(r"\bвоня\w*", r"\bвонь\w*", r"\bсмрад\w*", r"\bжагымсыз иис"), "smell_air", "bad_smell"),
    Signal("dangerous", _rx(r"\bзаброшен\w*", r"\bопасн\w* мест", r"\bлазят\b", r"\bкауипти\w*",
                            r"\bкараусыз калган\w*", r"\bкоршалмаган\w*"),
           "noise_safety", "dangerous_place"),
    Signal("sidewalk_broken", _rx(r"\bнет тротуар\w*", r"\bтротуар\w* нет\b", r"\bтротуар жок", r"\bразбит\w* тротуар",
                                  r"\bтротуар\w* разбит", r"\bтротуар\w* бузыл"), "sidewalks", "broken_sidewalk"),
    Signal("lawn", _rx(r"\bгазон\w*", r"\bкогал\w*"), "yards", "trees_lawn", strong=False),
    Signal("sidewalk", _rx(r"\bтротуар\w*", r"\bпандус\w*", r"\bбордюр\w*"), "sidewalks", "broken_sidewalk",
           strong=False),
    Signal("road", _rx(r"\bям(а|ы|у|ои|е|ам|ами|ах|очн\w*)?\b", r"\bшункыр\w*", r"\bасфальт\w*", r"\bдорог\w*",
                       r"\bжол(да|га|ды|дагы|дын|ы|дар\w*)?\b", r"\bливнев\w*", r"\bвыбоин\w*"), "roads", "pothole",
           strong=False),
    # Предложение без проблемы — аппарат акима (сигнал последний: любая проблема в тексте важнее).
    Signal("other", _rx(r"\bспасибо\b", r"\bблагодар\w*", r"\bпредлага\w*", r"\bпредлож\w*", r"\bрахмет\b",
                        r"\bракмет\b", r"\bусыныс\w*", r"\bусына(мын|мыз)\b"), "other"),
)
# Благодарность без жалобы («Спасибо за ремонт двора», «Жаңа алаң үшін рақмет») — аппарат акима, даже если в ней
# названа тема: служба ничего не должна делать. Слова жалобы («не», «нет», «опять», «просим») отменяют правило.
# «Рақмет.» / «Спасибо.» в конце жалобы — вежливость, а не благодарность: нужно «спасибо за …», «… үшін рақмет».
_THANKS = _rx(r"\bспасибо за (?!внимани|понимани|ответ|помощ|скор)", r"\bблагодар\w* за (?!внимани|понимани|ответ)",
              r"\bушин (рахмет|ракмет)\b", r"\bалгыс\w*")
_COMPLAINT_WORDS = _rx(r"\bне\b", r"\bнет\b", r"\bжок\b", r"\bемес\b", r"\bопять\b", r"\bснова\b", r"\bкогда\b",
                       r"\bсколько можно", r"\bпрошу\b", r"\bпросим\b", r"\bпримите\b", r"\bсураим\w*", r"\bкашан\b",
                       r"\bсломан\w*", r"\bразбит\w*", r"\bям(а|ы)\b", r"\bбузыл\w*", r"\bпомогите\b")
_SIGNAL_BY_NAME = {s.name: s for s in SIGNALS}


def first_signal(norm: str, category: str | None = None, strong_only: bool = False) -> Signal | None:
    """Первый сигнал текста (в категории category, если она задана; strong_only — без слабых: «газон», «яма»)."""
    for signal in SIGNALS:
        if category is not None and signal.category != category:
            continue
        if strong_only and not signal.strong:
            continue
        if signal.rx.search(norm) and not (signal.unless is not None and signal.unless.search(norm)):
            return signal
    return None


# ---------------------------------------------------------------- признаки для совместных случаев
_TREE = _rx(r"\bдерев\w*", r"\bветк\w*", r"\bагаш\w*", r"\bсук\b")
_WIRE = _rx(r"\bпровод\w*", r"\bлэп\b", r"\bэлектропередач\w*", r"\bсым\w*", r"\bлини\w* электр")
_FELL = _rx(r"\bупал\w*", r"\bуп(ало|ала)\b", r"\bупавш\w*", r"\bповали\w*", r"\bснес\w*", r"\bсбил\w*", r"\bрухну\w*", r"\bсвали\w*",
            r"\bкулап\w*", r"\bкулады\b", r"\bкулаган\w*", r"\bлежит\b", r"\bнавали\w*", r"\bузип\b", r"\bоборва\w*")
_POLE = _rx(r"\bстолб\w*", r"\bопор(а|у|ы)\b", r"\bбагана\w*")
_POLE_DOWN = _rx(r"\bупал\w*", r"\bуп(ало|ала)\b", r"\bупавш\w*", r"\bповали\w*", r"\bснес\w*", r"\bсбил\w*", r"\bрухну\w*",
                 r"\bсвали\w*", r"\bкулап\w*", r"\bкулады\b", r"\bкулаган\w*", r"\bлежит\b")
_ELEC = _rx(r"\bпровод\w*", r"\bсвет\w*", r"\bэлектр\w*", r"\bсым\w*", r"\bжарык\w*", r"\bтемно\b", r"\bкараны\w*")

_ROOF = _rx(r"\bсосул\w*", r"\bкрыш\w*", r"\bшатыр\w*", r"\bсунги\w*")
_WALK = _rx(r"\bтротуар\w*", r"\bдорожк\w*", r"\bпроход\w*")
_NOT_CLEANED = _rx(r"\bне почищ\w*", r"\bне убра\w*", r"\bне убир\w*", r"\bне чищ\w*", r"\bне чист\w*",
                   r"\bтазаланба\w*", r"\bсбросил\w*", r"\bнавалил\w*", r"\bтастап кетти", r"\bтусирип", r"\bзавалил\w*")

# Сети и кто «копал»: (служба, шаблон). Порядок — от явного к общему; вода — запасной вариант.
_NETWORKS = (
    ("heating", _rx(r"\bтеплотрасс\w*", r"\bтеплосет\w*", r"\bотоплени\w*", r"\bтеплов\w*", r"\bкипят\w*",
                    r"\bпар(ом)?\b", r"\bгоряч\w* вод", r"\bжылу\b", r"\bыстык су", r"\bбу\b")),
    ("power", _rx(r"\bкабел\w*", r"\bэлектросет\w*", r"\bэлектрик\w*", r"\bэлектр жели\w*")),
    ("gas", _rx(r"\bгазопровод\w*", r"\bгазовик\w*", r"\bгазов\w* служб\w*", r"\bгаз(а|ом|у)?\b")),
    ("water", _rx(r"\bводокана\w*", r"\bводопровод\w*", r"\bводовод\w*", r"\bканализ\w*", r"\bколлектор\w*",
                  r"\bкубыр\w*", r"\bкариз\w*", r"\bсумен жабдыкта\w*", r"\bтруб(а|у|ы|ои|е|ами|ах)?\b",
                  r"\bколод(ец|ца|це)\b", r"\bлюк\w*", r"\bвод(а|у|ы|ои)\b", r"\bсу\b")),
)
# Служба, названная прямо (её работы): «водоканал раскопал».
_NAMED_NETWORK = (
    ("water", _rx(r"\bводокана\w*", r"\bсумен жабдыкта\w*")),
    ("heating", _rx(r"\bтеплосет\w*", r"\bжылу жели\w*")),
    ("power", _rx(r"\bэлектросет\w*", r"\bэлектр желил\w*")),
    ("gas", _rx(r"\bгазовик\w*", r"\bгазов\w* служб\w*")),
)
_DIG = _rx(r"\bраскоп\w*", r"\bперекоп\w*", r"\bземлян\w* работ\w*", r"\bразры(л|т)\w*", r"\bвыры(л|т)\w*", r"\bраскуроч\w*",
           r"\bразворот\w*", r"\bказыл\w*", r"\bвскры\w*", r"\bкопа(ли|ют|л|ла|ть)\b", r"\bвыкопа\w*",
           r"\bказ(ып|ды|ган|ылган|ба\w*)\b", r"\bказу\w*", r"\bкабель тарт\w*")
# «Не восстановили / не положили асфальт», «жол қалпына келтірілмеді», «асфальт төселмеді» — покрытие после чьих-то
# работ: тоже раскоп (служба сетей не названа — по умолчанию водопровод). Объект нужен: «не восстановили разметку» — нет.
_RESTORE_FAIL = _rx(
    r"\bне (восстановил|положил|заасфальтировал|засыпал|закопал)\w*\b.{0,15}\b(асфальт|покрыти|газон|тротуар|дорог|проезд|"
    r"двор|площадк|бордюр|плитк|яму|траншею)",
    r"\b(асфальт|покрыти|газон|тротуар|дорог|проезд|плитк)\w*\b.{0,15}\bне (восстановил|положил|заасфальтировал)\w*",
    r"\b(жол|асфальт|когал|тротуар|аула)\w*\b.{0,20}\b(калпына келтир(и)?лме|тосел?ме)\w*")
# «Траншея», «котлован» — раскоп, только если рядом сети или «засыпали / не закопали»: «асфальт провалился,
# получилась настоящая траншея» — это яма (R02 probe2-roads-01), а котлован стройки — не работы служб.
_PIT_NOUN = _rx(r"\bтранше\w*", r"\bкотлован\w*")
_FILL = _rx(r"\bзасыпа\w*", r"\bзасып(ал|ет)\w*", r"\bзакопа\w*", r"\bкомбе\w*", r"\bкомме\w*", r"\bне восстанов\w*",
            r"\bкалпына келтирме\w*", r"\bбросил\w*", r"\bкопа\w*")
_BUILDING_SITE = _rx(r"\bстроиплощадк\w*", r"\bстроик\w*", r"\bзастроищик\w*", r"\bстроительн\w*", r"\bкурылыс\w*")
_WORKS = _rx(r"\bменя(ли|л|ют)\b", r"\bзамен\w*", r"\bремонт\w*", r"\bавари\w*", r"\bпрокладыва\w*", r"\bжонде\w*",
             r"\bтарт(ып|кан\w*)\b", r"\bповреди\w*", r"\bработ\w*", r"\bжумыс\w*")
_LEAK = _rx(r"\bпрорва\w*", r"\bпрорыв\w*", r"\bпорыв\w*", r"\bлопну\w*", r"\bтечет\b", r"\bтечь\b", r"\bхлещ\w*",
            r"\bбьет\b", r"\bиз под (земли|асфальта)", r"\bагып\b", r"\bжарыл\w*", r"\bпарит\b")
_COLLAPSE = _rx(r"\bям(а|ы|у|ои|е)?\b", r"\bпровал\w*", r"\bпросел\w*", r"\bпроседа\w*", r"\bпромоин\w*", r"\bразмы\w*",
                r"\bопырыл\w*", r"\bшункыр\w*", r"\bкотлован\w*", r"\bтранше\w*")
_DAMAGE = _rx(r"\bям(а|ы|у|ои|е)?\b", r"\bкотлован\w*", r"\bтранше\w*", r"\bпровал\w*", r"\bпросел\w*", r"\bпроседа\w*",
              r"\bпромоин\w*", r"\bразмы\w*", r"\bне закопа\w*", r"\bне засыпа\w*", r"\bкое как\b", r"\bне восстанов\w*",
              r"\bне заасфальт\w*", r"\bне полож\w*", r"\bразби(ли|т|та|ты)\b", r"\bсломали\b", r"\bгрязь\b",
              r"\bкучи земли\b", r"\bопырыл\w*", r"\bшункыр\w*", r"\bкомбе\w*", r"\bкомме\w*", r"\bкалпына келтир(и)?лме\w*",
              r"\bтосел?ме\w*", r"\bтастап кетти", r"\bбросил\w*", r"\bоставил\w*", r"\bразбит\w*", r"\bперекопа\w*")
_SINK = _rx(r"\bпровал\w*", r"\bпросел\w*", r"\bпроседа\w*", r"\bпромоин\w*", r"\bразмы\w*", r"\bопырыл\w*")
_PERSON_FELL = re.compile(r"\b(кто то|ребен\w*|человек|люди|прохож\w*|мужчин\w*|женщин\w*|пожил\w*|девочк\w*|мальчик\w*|"
                          r"собак\w*|машин\w*|колес\w*)( уже)? (чуть не )?(провалил\w*|упал\w*)")
_ICE = _rx(r"\bлед\b", r"\bльд\w*", r"\bво льду\b", r"\bналед\w*", r"\bкаток\b", r"\bгололед\w*",
           r"\bмуз(га|ы|бен|дан|ды)?\b", r"\bтаигак\w*", r"\bкоктаигак\w*")
_YARD = _rx(r"\bдвор\w*", r"\bаула\w*", r"\bдетск\w* площадк\w*", r"\bплощадк\w*", r"\bбалалар алан\w*")
_LAWN = _rx(r"\bгазон\w*", r"\bклумб\w*", r"\bкогал\w*")
_ROADWORDS = _rx(r"\bдорог\w*", r"\bпроезд\w*", r"\bпроезж\w*", r"\bулиц\w*", r"\bперекрест\w*", r"\bтротуар\w*",
                 r"\bжол(да|га|ды|дагы|дын|ы)?\b", r"\bкоше\w*", r"\bмагистрал\w*")
_TRAFFIC_LIGHT = _rx(r"\bсветофор\w*", r"\bбагдаршам\w*")
_POWER_OUT = _rx(r"\bотключ\w* свет", r"\bсвет\w* отключ", r"\bнет электричеств", r"\bбез электричеств", r"\bнет света",
                 r"\bэлектр\w* жок", r"\bжарык жок")

# Два отключения: что «нет» (рус. «нет/без/отключили/ни» + до 5 слов; каз. до 6 слов + «жок»).
_UTILITY_WORDS = (
    ("heating", re.compile(r"^(отоплени\w*|тепл(а|о)|жылу|батаре\w*)$")),
    ("water", re.compile(r"^(вод(а|ы|у)|су)$")),
    ("power", re.compile(r"^(свет(а|у)?|электричеств\w*|жарык\w*|электр\w*)$")),
    ("gas", re.compile(r"^газ(а|у)?$")),
)
_NEG_RU = re.compile(r"\b(нет|без|отключил\w*|отключи\w*|ни)\b((?: \w+){1,5})")
_NEG_KK = re.compile(r"((?:\w+ ){1,6})жок\b")
_HOT = re.compile(r"\b(горяч\w*|ыстык)$")

# Две разные проблемы в одном тексте: узкие шаблоны, иначе «двор» + «мусор» = две службы на пустом месте.
_PROBLEMS = (
    ("transport", _rx(r"\bпавильон\w*", r"\bскамеи\w* на остановк", r"\bаялдама\w* (павильон|орындык)")),
    ("lighting", _rx(r"\bне горит фонар", r"\bне горят фонар", r"\bфонар\w* (тоже |также |еще )?не гор",
                     r"\bшам\w* жанба\w*", r"\bнет освещени", r"\bосвещени\w* нет")),
    ("road", _rx(r"\bна дороге ям", r"\bям\w* на дороге", r"\bразбит\w* дорог", r"\bжолда\b.{0,15}\bшункыр")),
    ("waste", _rx(r"\bмусор\w*", r"\bбак\w* переполн", r"\bпереполн\w*\b.{0,15}\bбак", r"\bкокыс\w*", r"\bсвалк\w*")),
    # Площадка — только сломанная; собаки — только бродячие: «рядом с детской площадкой», «собаки растаскивают
    # мусор», «песочница — туалет для собак» — это место и подробность, а не вторая проблема (R02 probe_v2).
    ("landscaping", _rx(r"\b(сломан\w*|разбит\w*|оторван\w*|ржав\w*)\b.{0,25}\b(детск\w* площадк|качел|горк)",
                        r"\b(детск\w* площадк\w*|качел\w*|горк\w*)\b.{0,25}\b(сломан|разбит|оторван|ржав)",
                        r"\bбалалар алан\w* (бузыл|сын)\w*")),
    ("animals", _rx(r"\bбродяч\w* собак", r"\bбездомн\w* собак", r"\bста(я|и|ю) (бродяч\w* )?собак",
                    r"\bсобак\w* (кусают|кидаются|бросаются|напада)", r"\bкангыбас\w*", r"\bсвор\w*")),
    ("housing", _rx(r"\bлифт\w*")),
    ("heating", _rx(r"\bнет отоплени", r"\bбатаре\w* холодн")),
)


@dataclass(frozen=True)
class Joint:
    rule: str
    lead: str
    partner: str
    score: float
    default_network: bool = False   # служба сетей не названа — взяли самую частую (водопровод)
    any_order: bool = False
    extra: tuple = ()               # третья служба (только «нет сразу трёх сетей»)


def _network(norm: str) -> tuple[str, bool]:
    """(служба сетей, по умолчанию ли). Явно названная служба важнее косвенных слов."""
    for sid, rx in _NAMED_NETWORK:
        if rx.search(norm):
            return sid, False
    for sid, rx in _NETWORKS:
        if rx.search(norm):
            return sid, False
    return "water", True


def _surface(norm: str, base: str | None) -> str:
    """Кто восстанавливает покрытие: дорога -> road, газон -> greenery, двор -> landscaping.

    Слова дороги («проезд», «тротуар», «жол») важнее двора: «раскопали проезд во дворе» — Дорожная служба; газон важнее
    двора: «не восстановили газон, двор выглядит…» — Служба озеленения. «Асфальт» — не слово дороги: асфальт есть и во
    дворе. Слов нет — категория, которую выбрал ЖИТЕЛЬ (base; догадку модели сюда не передаём), иначе дорога."""
    if _ROADWORDS.search(norm):
        return "road"
    if _LAWN.search(norm):
        return "greenery"
    if _YARD.search(norm):
        return "landscaping"
    if base in ("landscaping", "greenery"):
        return base
    return "road"


def outages(norm: str) -> list[str]:
    """Какие сети «нет» (по порядку упоминания): «нет ни воды, ни света» -> [water, power]."""
    found: list[str] = []

    def add(word: str, prev: str) -> None:
        for sid, rx in _UTILITY_WORDS:
            if rx.match(word):
                if sid == "water" and _HOT.search(prev):
                    sid = "heating"  # горячая вода — теплосеть
                if sid not in found:
                    found.append(sid)
                return

    for m in _NEG_RU.finditer(norm):
        words = m.group(2).split()
        for i, word in enumerate(words):
            if word in ("во", "в", "на", "у", "с", "по", "уже", "дома", "доме"):
                break
            add(word, words[i - 1] if i else "")
    for m in _NEG_KK.finditer(norm):
        words = m.group(1).split()
        for i, word in enumerate(words):
            add(word, words[i - 1] if i else "")
    return found


def joint_rule(norm: str, base: str | None) -> Joint | None:
    """Первое сработавшее правило совместного случая или None. base — служба по таблице (если уже известна)."""
    # 1. Дерево на проводах: убрать дерево и восстановить линию.
    if _TREE.search(norm) and _WIRE.search(norm) and _FELL.search(norm):
        return Joint("tree_on_wires", "greenery", "power", 0.85)
    # 2. Упал столб с проводами или без света: линия — электросети, столб и фонари — служба освещения.
    if _POLE.search(norm) and _POLE_DOWN.search(norm) and _ELEC.search(norm):
        return Joint("pole_down", "power", "lighting", 0.85)
    network, by_default = _network(norm)
    leak = bool(_LEAK.search(norm))
    # «Люк без крышки, уже кто-то провалился» — провалился человек, а не асфальт (R02 synth_v3 open_manhole).
    norm_c = _PERSON_FELL.sub(" ", norm)
    # 3. Течь из сети + наледь: устранить течь и убрать лёд.
    if leak and _ICE.search(norm):
        return Joint("leak_ice", network, "street_cleaning", 0.8)
    # 4. Раскопки сетей / прорыв + яма или провал: служба сетей + служба покрытия.
    named = any(rx.search(norm) for _sid, rx in _NAMED_NETWORK)
    has_network = any(rx.search(norm) for _sid, rx in _NETWORKS)
    dig = (bool(_DIG.search(norm)) or bool(_PIT_NOUN.search(norm) and (has_network or _FILL.search(norm)))
           or bool(_RESTORE_FAIL.search(norm)))
    if dig and not has_network and _BUILDING_SITE.search(norm):
        dig = False  # котлован стройки — опасное место, а не раскоп служб
    works = has_network and bool(_WORKS.search(norm)) and bool(_DAMAGE.search(norm))
    burst = leak and bool(_COLLAPSE.search(norm_c))
    sunk = has_network and not _DIG.search(norm) and bool(_SINK.search(norm_c))
    named_pit = named and bool(_COLLAPSE.search(norm_c))
    if dig or works or burst or sunk or named_pit:
        rule = "dig_after_works" if (dig or works or named_pit) else "burst_pit"
        default = by_default and not leak
        return Joint(rule, network, _surface(norm, base), 0.6 if default else 0.8, default_network=default)
    # 5. Снег и сосульки с крыши на неубранном тротуаре: крыша — дом, тротуар — уборка.
    if _ROOF.search(norm) and _WALK.search(norm) and _NOT_CLEANED.search(norm):
        return Joint("roof_snow_walk", "housing", "street_cleaning", 0.8)
    # 6. Светофор без электричества.
    if _TRAFFIC_LIGHT.search(norm) and _POWER_OUT.search(norm):
        return Joint("signal_power", "traffic", "power", 0.8)
    # 7. Нет сразу двух разных сетей.
    out = outages(norm)
    if len(out) >= 2:
        return Joint("two_outages", out[0], out[1], 0.8, any_order=True, extra=tuple(out[2:3]))
    # 8. Две разные проблемы (узкие шаблоны).
    hits = []
    for sid, rx in _PROBLEMS:
        m = rx.search(norm)
        if m:
            hits.append((m.start(), sid))
    services = []
    for _pos, sid in sorted(hits):
        if sid not in services:
            services.append(sid)
    if len(services) >= 2:
        return Joint("two_problems", services[0], services[1], 0.7, any_order=True)
    return None


# ---------------------------------------------------------------- объяснения (одна строка ru / kk)
# {a} — ведущая служба, {b} — участвующая. Имена — в именительном падеже через тире: не зависят от правок названий.
_JOINT_WHY = {
    "dig_after_works": ("Раскопки сетей: {a} — работы на сетях и засыпка, {b} — восстановление покрытия.",
                        "Желідегі қазба жұмыстары: {a} — желідегі жұмыс пен көму, {b} — жабынды қалпына келтіру."),
    "dig_unknown": ("Раскопки без восстановления покрытия: {a} — работы на сетях (уточните, чьи), {b} — покрытие.",
                    "Жабыны қалпына келтірілмеген қазба: {a} — желідегі жұмыс (кімдікі екенін нақтылаңыз), {b} — жабын."),
    "burst_pit": ("Течь из сети размыла покрытие: {a} — ремонт трубы, {b} — восстановление покрытия.",
                  "Желідегі ағу жабынды бұзды: {a} — құбырды жөндеу, {b} — жабынды қалпына келтіру."),
    "leak_ice": ("Вода из сети замерзает: {a} — устранить течь, {b} — убрать наледь.",
                 "Желіден аққан су қатып жатыр: {a} — ағуды тоқтату, {b} — мұзды тазалау."),
    "pole_down": ("Упал столб с проводами: {a} — линия и отключение, {b} — столб и фонари.",
                  "Сымы бар бағана құлады: {a} — желі мен ажырату, {b} — бағана мен шамдар."),
    "tree_on_wires": ("Дерево на проводах: {a} — убрать дерево, {b} — обесточить и восстановить линию.",
                      "Ағаш сымға құлады: {a} — ағашты алу, {b} — желіні ажыратып, қалпына келтіру."),
    "roof_snow_walk": ("Снег и сосульки с крыши: {a} — крыша дома, {b} — уборка тротуара.",
                       "Шатырдағы қар мен сүңгілер: {a} — үйдің шатыры, {b} — тротуарды тазалау."),
    "signal_power": ("Светофор без электричества: {a} — светофор, {b} — питание.",
                     "Бағдаршам электрсіз қалды: {a} — бағдаршам, {b} — қуат беру."),
    "two_outages": ("Нет сразу двух услуг: {a} и {b} — каждая служба по своей сети.",
                    "Екі қызмет бірден жоқ: {a} және {b} — әрқайсысы өз желісі бойынша."),
    "two_problems": ("В обращении две разные проблемы: {a} и {b}.",
                     "Өтініште екі түрлі мәселе бар: {a} және {b}."),
}
# Строка для каждой службы совместного случая: (ru, kk) для ведущей и участвующей.
_ROLE_WHY = {
    "dig_after_works": (("Работы на сетях и засыпка раскопа", "Желідегі жұмыс пен қазбаны көму"),
                        ("Восстановление покрытия после раскопок", "Қазбадан кейін жабынды қалпына келтіру")),
    "burst_pit": (("Ремонт трубы", "Құбырды жөндеу"), ("Восстановление покрытия", "Жабынды қалпына келтіру")),
    "leak_ice": (("Устранить течь", "Ағуды тоқтату"), ("Убрать наледь", "Мұзды тазалау")),
    "pole_down": (("Линия и отключение", "Желі мен ажырату"), ("Столб и фонари", "Бағана мен шамдар")),
    "tree_on_wires": (("Убрать дерево", "Ағашты алу"), ("Обесточить и восстановить линию", "Желіні ажыратып, қалпына келтіру")),
    "roof_snow_walk": (("Крыша дома: снег и сосульки", "Үй шатыры: қар мен сүңгілер"),
                       ("Уборка тротуара", "Тротуарды тазалау")),
    "signal_power": (("Светофор", "Бағдаршам"), ("Питание светофора", "Бағдаршамның қуаты")),
    "two_outages": (("Своя сеть", "Өз желісі"), ("Своя сеть", "Өз желісі")),
    "two_problems": (("Своя часть обращения", "Өтініштің өз бөлігі"), ("Своя часть обращения", "Өтініштің өз бөлігі")),
}


def _label(category: str | None, subtopic: str | None) -> tuple[str, str] | None:
    cat = categories().get(category or "")
    if cat is None:
        return None
    sub = cat["subtopics"].get(subtopic or "")
    item = sub or cat
    return item["ru"], item["kk"]


# ---------------------------------------------------------------- проверка ввода
def _text(value) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("text: нужна строка с текстом обращения.")
    return value.strip()[:MAX_TEXT]


def _category(value) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or value not in categories():
        raise ValueError("category: неизвестная категория.")
    return value


def _subtopic(category: str | None, value) -> str | None:
    """Чужое или неизвестное уточнение пропускаем (как R12): подсказка не должна падать из-за старого клиента."""
    if value in (None, "") or category is None or not isinstance(value, str):
        return None
    return value if value in categories()[category]["subtopics"] else None


def _point(value) -> list[float] | None:
    if value is None:
        return None
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)):
        raise ValueError("point: нужна точка [lon, lat].")
    lon, lat = float(value[0]), float(value[1])
    if not (ASTANA_BOUNDS[0] <= lon <= ASTANA_BOUNDS[2] and ASTANA_BOUNDS[1] <= lat <= ASTANA_BOUNDS[3]):
        raise ValueError("point: точка вне Астаны.")
    return [lon, lat]


# ---------------------------------------------------------------- главное
def _classify(text: str) -> dict | None:
    try:
        from ui.civic_ml_api.classify_chain import classify
        return classify(text)
    except Exception:  # noqa: BLE001 — без модели остаются правила
        return None


def _model_version(used_model: dict | None) -> str:
    if used_model and used_model.get("model_version"):
        return f"{VERSION}+{used_model['model_version']}"
    return VERSION


def route(text=None, category=None, subtopic=None, point=None, body=None, **_ignored) -> dict:
    """Службы для обращения. Нужен text или category. body — тело POST целиком (шлюз R01: {"body": body}).

    Ответ: {services:[{service, score, role, why_ru, why_kk, name_ru, name_kk}], joint, summary_ru, summary_kk,
            why_ru, why_kk, rule, category, subtopic, category_source, source, model_version, ms}.
    """
    started = time.perf_counter()
    if isinstance(body, dict):
        text = body.get("text", text)
        category = body.get("category", category)
        subtopic = body.get("subtopic", subtopic)
        point = body.get("point", point)
    text = _text(text)
    category = _category(category)
    subtopic = _subtopic(category, subtopic)
    _point(point)  # точка пока только проверяется: календарь работ R12 (кто копал рядом) — следующий шаг
    if not category and letters(text) < 3:
        raise ValueError("Нужен текст обращения (от 3 букв) или категория.")

    norm = normalize(text) if text else ""
    model = None
    category_source = "given" if category else None
    signal: Signal | None = None
    # Благодарность — только если в тексте нет ни одного сигнала проблемы (даже слабого: «спасибо за ремонт дороги»
    # пусть получит Дорожная служба).
    thanks = (not category and bool(_THANKS.search(norm)) and not _COMPLAINT_WORDS.search(norm)
              and all(sig.name == "other" or not sig.rx.search(norm) for sig in SIGNALS))
    if thanks:
        category, category_source = C.OTHER, "rules"
    if category:
        if subtopic is None and norm:
            signal = first_signal(norm, category)
            if signal is not None and signal.subtopic:
                subtopic = signal.subtopic
            if signal is not None and signal.service is None:
                signal = None  # уточнение найдено — дальше обычная таблица
    else:
        signal = first_signal(norm)
        if signal is not None and not signal.strong:
            model = _classify(text)
            if model and model.get("category") not in (None, C.OTHER) and model.get("source") != "none":
                weak = signal
                signal = None
                category, category_source = model["category"], "model"
                inner = first_signal(norm, category, strong_only=True)
                subtopic = inner.subtopic if inner is not None else None
                if inner is not None and inner.service is not None:
                    signal = inner
                del weak
        if signal is not None and category is None:
            category, subtopic, category_source = signal.category, signal.subtopic, "rules"
        if category is None:
            model = model or _classify(text)
            category = (model or {}).get("category") or C.OTHER
            if category not in categories():
                category = C.OTHER
            category_source = "model"
            inner = first_signal(norm, category, strong_only=True)
            subtopic = inner.subtopic if inner is not None else None
            if inner is not None and inner.service is not None:
                signal = inner

    if signal is not None and signal.service is not None:
        base, base_rule = signal.service, "signal"
    else:
        base, base_rule = table_service(category, subtopic)

    # Покрытие для раскопа берём из категории только если её выбрал житель или сотрудник (не догадка модели).
    joint = joint_rule(norm, base if category_source == "given" else None) if norm and not thanks else None
    names = service_names()

    def nm(sid: str) -> tuple[str, str]:
        item = names.get(sid) or {"ru": sid, "kk": sid}
        return item["ru"], item["kk"]

    services: list[dict] = []
    if joint is not None and joint.lead != joint.partner:
        (a_ru, a_kk), (b_ru, b_kk) = nm(joint.lead), nm(joint.partner)
        key = "dig_unknown" if joint.default_network else joint.rule
        why_ru, why_kk = (s.format(a=x, b=y) for s, x, y in zip(_JOINT_WHY[key], (a_ru, a_kk), (b_ru, b_kk)))
        role_why = _ROLE_WHY.get(joint.rule) or _ROLE_WHY["two_problems"]
        lead_score = 0.6 if joint.default_network else joint.score
        services = [
            {"service": joint.lead, "role": "lead", "score": lead_score, "name_ru": a_ru, "name_kk": a_kk,
             "why_ru": role_why[0][0], "why_kk": role_why[0][1]},
            {"service": joint.partner, "role": "partner", "score": joint.score, "name_ru": b_ru, "name_kk": b_kk,
             "why_ru": role_why[1][0], "why_kk": role_why[1][1]},
        ]
        for sid in joint.extra:
            c_ru, c_kk = nm(sid)
            services.append({"service": sid, "role": "partner", "score": joint.score, "name_ru": c_ru, "name_kk": c_kk,
                             "why_ru": role_why[1][0], "why_kk": role_why[1][1]})
        names_ru = [x["name_ru"] for x in services]
        names_kk = [x["name_kk"] for x in services]
        count_ru = {2: "Нужны 2 службы", 3: "Нужны 3 службы"}[len(services)]
        count_kk = {2: "Екі қызмет керек", 3: "Үш қызмет керек"}[len(services)]
        summary_ru = f"{count_ru}: {', '.join(names_ru[:-1])} и {names_ru[-1]}"
        summary_kk = f"{count_kk}: {', '.join(names_kk[:-1])} және {names_kk[-1]}"
        rule = "joint." + joint.rule + (".default_network" if joint.default_network else "")
    else:
        s_ru, s_kk = nm(base)
        if base_rule == "signal" and signal is not None:
            label = (signal.label_ru, signal.label_kk)
        else:
            label = _label(category, subtopic if base_rule == "subtopic" else None) or (category, category)
        if category_source == "model":
            why_ru = f"По тексту похоже на «{label[0]}» — {s_ru}."
            why_kk = f"Мәтінге қарағанда «{label[1]}» — {s_kk}."
            score = round(min(0.9, max(0.3, float((model or {}).get("score") or 0.0))), 2)
        else:
            why_ru = f"По таблице служб: «{label[0]}» — {s_ru}."
            why_kk = f"Қызметтер кестесі бойынша: «{label[1]}» — {s_kk}."
            score = 0.95 if base_rule == "subtopic" else (0.85 if base_rule == "signal" else 0.9)
        services = [{"service": base, "role": "lead", "score": score, "name_ru": s_ru, "name_kk": s_kk,
                     "why_ru": why_ru, "why_kk": why_kk}]
        summary_ru, summary_kk = f"Служба: {s_ru}", f"Қызмет: {s_kk}"
        rule = "table." + base_rule if base_rule != "signal" else "signal." + (signal.name if signal else "")

    source = "model" if category_source == "model" else "rules"
    return {
        "services": services,
        "joint": len(services) > 1,
        "summary_ru": summary_ru, "summary_kk": summary_kk,
        "why_ru": why_ru, "why_kk": why_kk,
        "rule": rule,
        "category": category, "subtopic": subtopic, "category_source": category_source,
        "source": source,
        "model_version": _model_version(model if category_source == "model" else None),
        "ms": round((time.perf_counter() - started) * 1000, 2),
    }


def route_hint(result: dict) -> dict:
    """Поле route_hint записи жалобы R09 (CONTRACT §5.1) из ответа route()."""
    return {"services": [s["service"] for s in result.get("services") or []], "joint": bool(result.get("joint")),
            "source": result.get("source") or "rules", "model_version": result.get("model_version") or VERSION}
