"""AST-A13 E5: does STUPITS qualitative_comment() strip numeric claims written in Kazakh?
Sentences are SYNTHETIC test inputs written by AST-A13. Only checks sentence removal, not translation quality."""
import sys, json
sys.path.insert(0, "/home/claude/stupits")
from agent.evidence import qualitative_comment
CASES = [  # (lang, sentence, contains_numeric_claim)
 ("ru", "Этот план поднимает индекс на пять баллов.", True),
 ("ru", "Этот план поднимает индекс на 5 баллов.", True),
 ("ru", "План усиливает социальную сферу Нуры.", False),
 ("kk", "Бұл жоспар индексті бес балға көтереді.", True),
 ("kk", "Бұл жоспар индексті 5 балға көтереді.", True),
 ("kk", "Жоспар бюджеттің жартысын Нұраға жұмсайды.", True),     # 'half' — quantitative word
 ("kk", "Он екі мектеп салынады.", True),
 ("kk", "Жүз миллион теңге үнемделеді.", True),
 ("kk", "Үш аудан ғана жақсарады.", True),
 ("kk", "Жоспар Нұра ауданының әлеуметтік саласын күшейтеді.", False),
 ("ru", "Экономия составит десятки процентов.", True),
 ("ru", "Затраты вырастут вдвое.", True),
]
rows = []
for lang, s, numeric in CASES:
    try:
        out, _ = qualitative_comment(s)
        kept = s.strip().rstrip(".") in out
    except Exception as e:  # EvidenceError: nothing qualitative left -> sentence removed
        kept = False
    rows.append({"lang": lang, "sentence": s, "numeric_claim": numeric, "kept_by_filter": kept,
                 "leak": numeric and kept, "false_removal": (not numeric) and (not kept)})
summ = {lang: {"numeric_cases": sum(r["numeric_claim"] for r in rows if r["lang"] == lang),
               "leaked": sum(r["leak"] for r in rows if r["lang"] == lang),
               "false_removals": sum(r["false_removal"] for r in rows if r["lang"] == lang)} for lang in ("ru", "kk")}
print(json.dumps({"summary": summ, "rows": rows}, ensure_ascii=False, indent=1))
