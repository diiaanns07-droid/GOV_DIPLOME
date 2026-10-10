"""R08: текстовая сводка по шаблону — числа и склонения на ru и kk, без пустых мест и технических слов."""
import re

import pytest

from ui.civic_akim import text
from ui.civic_akim.summary import change

NB = " "


def fake(new=34, *, today=True, date="2026-10-12", district=None, main=None, overdue=5, objects=None):
    """Минимальный ответ summary() для шаблона."""
    return {
        "date": date, "is_today": today, "heat_days": 7,
        "district": district,
        "kpi": {"new_day": change(new, 0), "overdue": change(overdue, 0)},
        "main_problem": main,
        "objects": objects or {"available": False},
    }


def main_problem(value, prev, category=("Снег и гололёд", "Қар және көктайғақ"), district=("Нура", "Нұра")):
    return {"category": "snow_ice", "category_ru": category[0], "category_kk": category[1],
            "district": "nura", "district_ru": district[0], "district_kk": district[1], **change(value, prev)}


@pytest.mark.parametrize("n,form", [(0, "many"), (1, "one"), (2, "few"), (4, "few"), (5, "many"), (11, "many"),
                                    (12, "many"), (14, "many"), (21, "one"), (22, "few"), (25, "many"),
                                    (101, "one"), (111, "many"), (1004, "few")])
def test_plural_ru(n, form):
    assert text.plural_ru(n, "one", "few", "many") == form


def test_number_formats():
    assert text.fmt_num(1666) == f"1{NB}666" and text.fmt_num(1234567) == f"1{NB}234{NB}567"
    assert text.fmt_num(-12) == "−12" and text.fmt_pct(40) == f"40{NB}%"
    assert text.fmt_ratio(2.5) == "2,5" and text.fmt_ratio(3.0) == "3"


def test_prompt_example_ru_and_kk():
    s = fake(34, main=main_problem(14, 10), overdue=5,
             objects={"available": True, "total": 6, "late_count": 3, "stale_count": 0})
    assert text.render(s, "ru") == (
        f"Сегодня 34 новых обращения. Больше всего жалоб — «Снег и гололёд» в районе Нура: за 7 дней сообщили "
        f"14 человек, это на 40{NB}% больше, чем неделю назад. Просрочено 5 обращений. 3 объекта отстают от графика.")
    assert text.render(s, "kk") == (
        f"Бүгін 34 жаңа өтініш түсті. Ең көп шағым — «Қар және көктайғақ», Нұра ауданында: соңғы 7 күнде "
        f"14 адам хабарлады, бұл бір апта бұрынғыдан 40{NB}% көп. Мерзімі өткен өтініш: 5. "
        f"Кестеден қалып жатқан нысан: 3.")


@pytest.mark.parametrize("n,phrase", [
    (1, "Сегодня 1 новое обращение."), (2, "Сегодня 2 новых обращения."), (4, "Сегодня 4 новых обращения."),
    (5, "Сегодня 5 новых обращений."), (11, "Сегодня 11 новых обращений."), (21, "Сегодня 21 новое обращение."),
    (22, "Сегодня 22 новых обращения."), (1666, f"Сегодня 1{NB}666 новых обращений."),
])
def test_new_ru_agrees_with_number(n, phrase):
    assert text.render(fake(n), "ru").startswith(phrase)


@pytest.mark.parametrize("n", [1, 2, 5, 21, 1666])
def test_new_kk_noun_does_not_change(n):
    assert text.render(fake(n), "kk").startswith(f"Бүгін {text.fmt_num(n)} жаңа өтініш түсті.")


@pytest.mark.parametrize("n,phrase", [(1, "сообщил 1 человек"), (2, "сообщили 2 человека"), (5, "сообщили 5 человек"),
                                      (12, "сообщили 12 человек"), (21, "сообщил 21 человек"), (23, "сообщили 23 человека")])
def test_people_ru(n, phrase):
    assert phrase in text.render(fake(main=main_problem(n, n)), "ru")


@pytest.mark.parametrize("value,prev,ru,kk", [
    (14, 10, f"это на 40{NB}% больше, чем неделю назад", f"бұл бір апта бұрынғыдан 40{NB}% көп"),
    (6, 10, f"это на 40{NB}% меньше, чем неделю назад", f"бұл бір апта бұрынғыдан 40{NB}% аз"),
    (25, 10, "это в 2,5 раза больше, чем неделю назад", "бұл бір апта бұрынғыдан 2,5 есе көп"),
    (20, 10, "это в 2 раза больше, чем неделю назад", "бұл бір апта бұрынғыдан 2 есе көп"),
    (50, 10, "это в 5 раз больше, чем неделю назад", "бұл бір апта бұрынғыдан 5 есе көп"),
    (5, 2, "это на 3 больше, чем неделю назад", "(бір апта бұрын — 2)"),
    (2, 5, "это на 3 меньше, чем неделю назад", "(бір апта бұрын — 5)"),
    (7, 7, "столько же, сколько неделю назад", "бұл бір апта бұрынғымен бірдей"),
    (7, 0, "неделю назад таких жалоб не было", "бір апта бұрын мұндай шағым болмаған"),
])
def test_change_phrases(value, prev, ru, kk):
    s = fake(main=main_problem(value, prev))
    assert ru in text.render(s, "ru")
    assert kk in text.render(s, "kk")


@pytest.mark.parametrize("n,ru", [(0, "Просроченных обращений нет."), (1, "Просрочено 1 обращение."),
                                  (3, "Просрочено 3 обращения."), (12, "Просрочено 12 обращений.")])
def test_overdue(n, ru):
    assert ru in text.render(fake(overdue=n), "ru")
    assert ("Мерзімі өткен өтініш жоқ." if n == 0 else f"Мерзімі өткен өтініш: {n}.") in text.render(fake(overdue=n), "kk")


@pytest.mark.parametrize("late,stale,ru", [
    (1, 0, "1 объект отстаёт от графика."), (3, 0, "3 объекта отстают от графика."),
    (5, 0, "5 объектов отстают от графика."), (0, 0, "Объектов с отставанием нет."),
    (0, 2, "Объектов с отставанием нет. 2 объекта давно не обновлялись."),
    (21, 1, "21 объект отстаёт от графика. 1 объект давно не обновлялся."),
])
def test_objects_ru(late, stale, ru):
    s = fake(objects={"available": True, "total": 30, "late_count": late, "stale_count": stale})
    assert text.render(s, "ru").endswith(ru)


def test_objects_sentence_skipped_without_data():
    assert "объект" not in text.render(fake(objects={"available": False}), "ru")
    assert "объект" not in text.render(fake(objects={"available": True, "total": 0}), "ru")


def test_zero_and_past_date_and_district():
    assert text.render(fake(0), "ru").startswith("Сегодня новых обращений нет.")
    assert text.render(fake(0), "kk").startswith("Бүгін жаңа өтініш жоқ.")
    assert text.render(fake(3, today=False, date="2026-10-05"), "ru").startswith(f"5{NB}окт — 3 новых обращения.")
    assert text.render(fake(3, today=False, date="2026-10-05"), "kk").startswith(f"5{NB}қазан күні 3 жаңа өтініш түсті.")
    assert text.render(fake(0, today=False, date="2026-10-05"), "kk").startswith(f"5{NB}қазан күні жаңа өтініш болған жоқ.")
    d = {"id": "nura", "ru": "Нура", "kk": "Нұра"}
    s = fake(12, district=d, main=main_problem(9, 3))
    ru, kk = text.render(s, "ru"), text.render(s, "kk")
    assert ru.startswith("Сегодня в районе Нура 12 новых обращений.")
    assert kk.startswith("Бүгін Нұра ауданында 12 жаңа өтініш түсті.")
    assert ru.count("Нура") == 1 and kk.count("Нұра") == 1, "район не повторяется во второй фразе"


def test_no_technical_words_or_holes():
    cases = [fake(n, main=main_problem(v, p), overdue=o,
                  objects={"available": True, "total": 4, "late_count": l, "stale_count": l})
             for n, v, p, o, l in [(0, 1, 0, 0, 0), (1, 12, 10, 1, 1), (34, 30, 10, 5, 3), (1666, 5, 9, 21, 22)]]
    bad = re.compile(r"None|nan|undefined|null|\{|\}|target|segment|payload|  ", re.I)
    for s in cases:
        for lang in ("ru", "kk"):
            out = text.render(s, lang)
            assert not bad.search(out), out
            assert out.endswith(".") and ".." not in out


def test_names_come_from_i18n_dictionaries():
    assert text.district_name("nura", "kk") == "Нұра" and text.district_name("esil", "ru") == "Есиль"
    assert text.month_short(10, "ru") == "окт" and text.month_short(10, "kk") == "қазан"
    assert text.district_name(None, "ru") is None
