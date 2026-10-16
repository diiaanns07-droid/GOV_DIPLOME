"""R04 П3: место обращения по названию из индекса карты R12 (web/civic/map/search_index.json, OSM).

Нашли название рядом со словом-подсказкой — цель; не нашли — None («адрес уточнить»). Место не угадываем.
"""

from __future__ import annotations

import pytest

from ui.civic_ml_api.intake import INDEX_PATH, places, tokens, urgency
from ml.civic_dedup.normalize import normalize

pytestmark = pytest.mark.skipif(not INDEX_PATH.exists(), reason="нет индекса карты R12")


def found(text, category=None):
    hit = places().find(text, category)
    return hit and (hit["kind"], hit["label_ru"])


@pytest.mark.parametrize("text, expected", [
    ("На улице Сыганак открытый люк", ("street", "улица Сыганак")),
    ("Сығанақ көшесінде люктің қақпағы жоқ", ("street", "улица Сыганак")),
    ("Хан Шатырдағы аялдамада шатыр сынған", ("bus_stop", "Остановка «Хан Шатыр»")),
    ("ostanovka Khan Shatyr naves sloman", ("bus_stop", "Остановка «Хан Шатыр»")),
    ("Во дворе ЖК Инжу Арена баки", ("yard", "Двор: ЖК Инжу Арена")),
    ("Инжу Арена ауласында қоқыс", ("yard", "Двор: ЖК Инжу Арена")),
    ("1-й мкр, во дворе мусор", ("yard", "Двор: 1-й микрорайон")),
    ("Жерұйық саябағында шамдар жанбайды", ("park", "Парк Жеруйык")),
    ("На проспекте Абая яма", ("street", "проспект Абая")),               # тип улицы из текста
    ("на улице Абая яма", ("street", "улица Абая")),
    ("Кенесары 40 — снег не чистят", ("street", "улица Кенесары")),
    ("На Айнаколь ямы, подвеску убил", ("street", "улица Айнаколь")),     # предлог + имя с большой буквы
    ("Дорогу на Жанкожа батыра не чистят", ("street", "улица Жанкожа батыра")),   # редкое имя из двух слов
    ("фонари не горят на улице Шарбаккл", ("street", "улица Шарбаккол")),        # одна опечатка рядом с «улице»
    ("На остановке «улица Сарытогай» наледь", ("bus_stop", "Остановка «улица Сарытогай»")),  # длинное имя важнее
    ("дом 206 на улице Абая", ("street", "улица Абая")),                 # номер дома — не «улица 206»
    # П3, разбор ошибок на половине набора R02 (обобщаемые случаи):
    ("Не работает освещение на улице Айнаколь от остановки до перекрёстка", ("street", "улица Айнаколь")),  # «улице» вплотную
    ("Қорғалжын тас жолында огромная яма", ("street", "Коргалжинское шоссе")),       # казахское «тас жолы»
    ("v zhk buhar zhyrau de luxe v podezde net sveta", ("yard", "Двор: Бұқар Жырау De Luxe")),   # қ -> х
    ("spasibo, v zhk alau teplo", ("yard", "Двор: Alau")),              # ЖК вплотную — и маленькими буквами
    ("«Жилой комплекс Зелёный Квартал» аялдмаасында автобус жоқ",        # опечатка в слове «аялдама»
     ("bus_stop", "Остановка «Жилой комплекс Зелёный Квартал»")),
])
def test_place_found(text, expected):
    assert found(text) == expected


def test_street_twins_are_one_street():
    """OSM делит улицу на линии с разными подписями: «Жумекена Нажимеденова» и «Жұмекен Нәжімеденов» — одна цель."""
    a = places().find("Жұмекен Нәжімеденов көшесінде шұңқыр")
    b = places().find("Улица Жумекена Нажимеденова: провал асфальта")
    assert a["id"] == b["id"]


@pytest.mark.parametrize("text", ["Не горит светофор на перекрёстке Коргалжинское ш. и пр. Туран",
                                  "Қорғалжын тас жолы мен Тұран даңғылының қиылысында бағдаршам сөніп тұр",
                                  "Qorgaljyn tas joly men Turan dangylynyn qiylysynda bagdarsham jumys istemeidi",
                                  "Не работает сетофор на перекрёскте Коргалжинское ш. и пр. Туран"])
def test_junction_of_two_streets(text):
    """«Перекрёсток A и B» — светофор R12 с этими двумя улицами (data/civic/astana/geo/objects.json)."""
    hit = places().find(text)
    assert hit["kind"] == "traffic_signal" and hit["id"].startswith("osm-node-")
    assert "Коргалжинское шоссе" in hit["label_ru"] and "Туран" in hit["label_ru"]


def test_stop_name_without_stop_word_for_transport():
    assert places().find("«Барыс арена» — стоим час, ни одного автобуса") is None      # без категории — не угадываем
    assert found("«Барыс арена» — стоим час, ни одного автобуса", "transport") == ("bus_stop", "Остановка «Барыс арена»")


@pytest.mark.parametrize("text", [
    "Кіреберісте жарық жоқ, телефонның шамымен жүреміз",   # «жарық» — свет, а не двор «Жарык»
    "В сквере сломаны скамейки",                          # «Сквер» без имени — не место
    "на айнаколь ямы",                                    # без большой буквы и слова «улица» — не место
    "фонари на Шарбаккл",                                 # опечатка без слова «улица» — не угадываем
    "Темно на улице, фонари не горят",
    "Соседи шумят по ночам",
    "Хан Шатыр",                                          # остановка без слова «остановка» — неизвестно что
])
def test_no_place_without_a_clear_name(text):
    assert places().find(text) is None


def test_name_continuation_is_another_name():
    assert found("уборка снега на улице Арнасай") == ("street", "улица Арнасай")   # не «улица Арна»


def test_category_prefers_matching_kind():
    text = "Во дворе ЖК Инжу Арена на улице Кабанбай батыра переполнены баки"
    assert found(text, "waste")[0] == "yard"
    assert found(text, "roads")[0] == "street"


def test_tokens_fold_kazakh_latin_and_ordinals():
    assert tokens("Мәңгілік Ел даңғылында") == ["мангилик", "ел", "дангылында"]
    assert tokens("1-й мкр") == ["1", "микрораион"]
    assert tokens("Нурсая-2") == ["нурсая", "2"]
    assert tokens("prospekt Mangilik El") == ["проспект", "мангилик", "ел"]


@pytest.mark.parametrize("text, rule", [
    ("Открытый люк без крышки на тротуаре", "manhole"),
    ("Люктің қақпағы жоқ, адам құлап кетуі мүмкін", "manhole"),
    ("Оборван провод, висит над тротуаром", "wires"),
    ("Сым үзілген, жерде жатыр", "wires"),
    ("В подъезде сильно пахнет газом", "gas"),
    ("Горит мусорный бак во дворе", "fire"),
    ("Нет отопления вторые сутки", "no_heat"),
    ("Үйде жылу жоқ", "no_heat"),
    ("Третий день нет воды", "no_water"),
    ("Ыстық су жоқ", "no_water"),
    ("На площадке торчат гвозди, дети могут пораниться", "children"),
    ("Аварийное дерево может упасть", "danger"),
])
def test_urgency_rules(text, rule):
    assert urgency(normalize(text))[0] == rule


@pytest.mark.parametrize("text", ["На остановке не горит фонарь", "Фонари горят днём", "Яма на дороге",
                                  "Дети просят новую горку", "Переполнены баки"])
def test_not_urgent(text):
    assert urgency(normalize(text)) is None
