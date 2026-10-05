"""K02: пробы пределов прототипа. Не тест «пройдено/не пройдено», а фиксация известных слабых мест.

Запуск из корня репозитория: python research/next-round/K02/limits_probe.py > research/next-round/K02/limits_probe_result.json
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kk_numeral_guard import is_numeric  # noqa: E402
from agent.evidence import NUMBER_WORDS  # noqa: E402

PROBES = [  # (text, what a human would expect, why it is interesting)
    ("Есіл ауданы үшінші орынға түседі.", "numeric", "порядковые числительные вне словаря (как и в ru-фильтре)"),
    ("Есиль опустится на третье место.", "numeric", "ru порядковые тоже не фильтруются"),
    ("Бұл бір маңызды қадам.", "qualitative", "«бір» как неопределённый артикль"),
    ("Екіншіден, экология баяу жақсарады.", "qualitative", "«екіншіден» = во-вторых"),
    ("Жоспар бюджеттің жүзден бірін алады.", "numeric", "дробь «жүзден бірі»"),
    ("Bul josparda bes mektep bar.", "numeric", "латиница 2021 года вне словаря"),
    ("Шығын жартылай өтеледі.", "qualitative", "«жартылай» = частично, исключено"),
    ("Бюджеттің жүзі экологияға кетеді.", "numeric", "«жүзі» исключено из-за омонима «лицо»"),
]
rows = [{"text": t, "human_expectation": e, "note": n, "prototype_numeric": bool(is_numeric(t))}
        for t, e, n in PROBES]
# Проверка «остался ли текст» в agent/evidence.py: [А-Яа-яA-Za-z]{3}
anchor = re.compile(r"[А-Яа-яA-Za-z]{3}")
anchor_rows = [{"text": t, "current_anchor_matches": bool(anchor.search(t))}
               for t in ("Әсері күшті.", "Бұл іс өңір үшін.", "Іс әлі ұзақ.")]
print(json.dumps({"probes": rows, "current_text_anchor": anchor_rows}, ensure_ascii=False, indent=1))
