"""K02 round 3: сравнение трёх подходов на одних фразах.

A. текущий фильтр продукта agent.evidence.qualitative_comment (не меняется);
B. словарь K02 round 2 (research/next-round/K02/kk_numeral_guard.py, только чтение);
C. объяснение по ID: фраза модели — либо кандидат в ID (отклоняется), либо комментарий
   (по умолчанию отбрасывается, в режиме separate печатается как непроверяемый).
Плюс проверка: все числа проверяемой части C совпадают со значениями каталога.

Запуск из корня: python research/round-3-results/K02/compare_current_filter.py
Пишет compare_result.json рядом со скриптом.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parents[1] / "next-round" / "K02"))
from verified_explainer import PlanError, build_catalog, explain, validate_plan  # noqa: E402
from kk_numeral_guard import qualitative_comment_v2  # noqa: E402
from agent.evidence import EvidenceError, format_value, qualitative_comment  # noqa: E402
from engine.optimizer import optimize  # noqa: E402
from engine.simulation import simulate  # noqa: E402

ANCHOR = "Решение требует обсуждения с жителями."
PHRASES = [  # (id, text, has_numeric_claim, note)
    ("bir_article", "Бұл бір маңызды қадам.", False, "«бір» как артикль"),
    ("kk_letters_only", "Іс әлі ұзақ.", False, "нет трёх подряд русских/латинских букв"),
    ("kk_cardinal", "Үш аудан ғана жақсарады.", True, "казахское числительное"),
    ("kk_ordinal", "Есіл ауданы үшінші орынға түседі.", True, "порядковое, вне словаря"),
    ("kk_latin", "Bul josparda bes mektep bar.", True, "латиница"),
    ("ru_digit", "Score вырос на 99 баллов.", True, "неверное число цифрами"),
]


def kept_in_comment(fn, text):
    """Сохранилась ли фраза в комментарии. Одиночная фраза проверяется отдельно,
    чтобы увидеть EvidenceError проверки «остался текст»."""
    try:
        alone, _ = fn(text)
        alone_result = "kept" if text in alone.split("\n") else "removed"
    except EvidenceError:
        alone_result = "EvidenceError"
    try:
        mixed, _ = fn(text + " " + ANCHOR)
        mixed_result = "kept" if text in mixed.split("\n") else "removed"
    except EvidenceError:
        mixed_result = "EvidenceError"
    return {"alone": alone_result, "with_ru_sentence": mixed_result}


def main():
    result = simulate(optimize(top_n=1)["results"][0]["decisions"])
    catalog = build_catalog(result)
    rows = []
    for pid, text, numeric, note in PHRASES:
        try:
            validate_plan({"sections": [{"type": "summary", "fact_ids": [text]}]}, catalog,
                          city="astana_hackathon", scenario_id="base")
            as_id = "accepted"
        except PlanError as exc:
            as_id = exc.code
        rows.append({"id": pid, "text": text, "has_numeric_claim": numeric, "note": note,
                     "A_current_filter": kept_in_comment(qualitative_comment, text),
                     "B_k02_r2_dictionary": kept_in_comment(qualitative_comment_v2, text),
                     "C_as_fact_id": as_id,
                     "C_as_comment": "dropped (default) / shown as unverified (separate)"})

    # Проверяемая часть C: каждое число в тексте — запись значения из каталога.
    checks = {}
    for lang in ("ru", "kk"):
        out = explain(result, lang=lang)
        allowed = {format_value(f.value) for f in catalog.values()
                   if isinstance(f.value, (int, float)) and not isinstance(f.value, bool)}
        numbers = re.findall(r"\d+(?:,\d+)?", out["verified_text"])
        checks[lang] = {"numbers_in_text": numbers,
                        "all_from_catalog": all(n in allowed for n in numbers),
                        "current_filter_on_verified_text": kept_in_comment(qualitative_comment,
                                                                           out["verified_text"])["alone"]}
    out = {"rows": rows, "verified_part_number_check": checks}
    (HERE / "compare_result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                                              encoding="utf-8")
    for r in rows:
        print(f"{r['id']:16} A={r['A_current_filter']['alone']:13}/{r['A_current_filter']['with_ru_sentence']:7} "
              f"B={r['B_k02_r2_dictionary']['alone']:13}/{r['B_k02_r2_dictionary']['with_ru_sentence']:7} "
              f"C_id={r['C_as_fact_id']}")
    print(json.dumps(checks, ensure_ascii=False))


if __name__ == "__main__":
    main()
