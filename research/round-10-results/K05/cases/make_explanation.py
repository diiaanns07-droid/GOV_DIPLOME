"""K05 r10: deterministic, code-built explanation (template, NOT an LLM) from out/<city>/compare.json + case.json.
Every number below is read from compare.json; nothing is hardcoded. Output: out/<city>/EXPLANATION.md
  python3 cases/make_explanation.py [out]"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "out")
m_ = lambda mm: "нет данных" if mm is None else f"{mm / 1000:.0f} м"
pct = lambda x: "нет данных" if x is None else f"{x * 100:.0f} %"
CITY = {"shymkent": "Шымкент", "astana": "Астана"}
METRIC_SOURCES = [
    ("Среднее расстояние", "sum_distance_mm / known_count, только по точкам с известным путём", "матрица (geodesic) × точки × школы/кандидат", "derived"),
    ("Худшая точка", "max(after_mm) по известным путям", "та же матрица", "derived"),
    ("В пределах порога", "число точек с after_mm ≤ threshold_mm; доля — от ВСЕХ точек", "матрица + порог пользователя", "derived"),
    ("Неизвестно", "точки без известного пути до школы/кандидата", "status матрицы ≠ ok", "derived"),
    ("Расстояние точки до ближайшей школы", "min по школам (кроме known_restricted), ничья: школа раньше кандидата, затем ID", "записи школ Overture (observed_secondary)", "derived"),
    ("Изменение для точки", "after_mm − before_mm (отрицательное — ближе)", "две строки выше", "derived"),
]

for city in ("shymkent", "astana"):
    c = json.load(open(os.path.join(out, city, "case.json"), encoding="utf-8"))
    r = json.load(open(os.path.join(out, city, "compare.json"), encoding="utf-8"))
    P = {p["plan_id"]: p for p in r["plans"]}
    cur = P["current"]
    L = [f"# Доступность школ — {CITY[city]} (шаблонное объяснение, не LLM)", "",
         f"case_digest `{r['case_digest']}` · код `{r['code_sha'][:10]}` · метод `{r['method']}` · порог {r['threshold_mm'] / 1000:.0f} м", "",
         "**Вопрос.** Какие точки участка дальше от известных школ и какой из двух предложенных вариантов лучше меняет расстояния?",
         "Это анализ расстояний по прямой, не расчёт дефицита мест, не решение о земле и не обещание строительства.", "",
         f"**Данные.** {len(c['schools'])} записей школ Overture внутри участка ({c['sources'][0]['data_period']}, вторичные данные, не реестр); "
         f"QA-флаги у {sum(1 for s in c['schools'] if s['qa'])} записей (не исключались). {len(c['origins'])} синтетических точек анализа "
         "(сетка 3×4, равновесные — не жители и не ученики). Варианты A и B — гипотетические места: A поставлен в точку, которая сейчас "
         "дальше всех от школ, B — в центр участка. Поэтому преимущество A заложено правилом выбора мест, это не самостоятельная находка.", "",
         "| План | Среднее | Худшая точка | В пределах порога | Неизвестно |", "|---|---|---|---|---|"]
    for pid, name in (("current", "Сейчас"), ("candidate:cand-A", "A"), ("candidate:cand-B", "B")):
        m = P[pid]["metrics"]
        L.append(f"| {name} | {m_(m['mean_distance_mm'])} | {m_(m['max_distance_mm'])} | {m['within_threshold_count']} из {m['total_origins']} ({pct(m['within_threshold_share_of_all_points'])}) | {m['unknown_count']} |")
    L.append("")
    for pid, name in (("candidate:cand-A", "A"), ("candidate:cand-B", "B")):
        rows = P[pid]["rows"]
        closer = [x for x in rows if x["delta_mm"] is not None and x["delta_mm"] < 0]
        same = [x for x in rows if x["delta_mm"] == 0]
        unk = [x for x in rows if x["delta_mm"] is None]
        big = min(closer, key=lambda x: (x["delta_mm"], x["origin_id"]), default=None)
        L.append(f"- **{name}**: точек ближе — {len(closer)}, без изменений — {len(same)}, неизвестно — {len(unk)}"
                 + (f"; сильнее всего — {big['origin_id']} ({m_(-big['delta_mm'])} ближе)." if big else "."))
    a, mm = P["auto:contract-lex"], P["auto:minimax"]
    pick = lambda p: ", ".join(p["selected_candidate_ids"]) or "без нового объекта"
    L += ["", f"**Предложение по правилу контракта:** {pick(a)} — сравниваются по очереди число неизвестных точек "
          f"({a['metrics']['unknown_count']}), сумма расстояний ({m_(a['metrics']['sum_distance_mm'])}), худшая точка, затем ID. "
          "Это лучшее только среди введённых мест и при этих допущениях.",
          f"**Другая цель (минимум худшей точки):** {pick(mm)}" + (" — совпадает." if mm["selected_candidate_ids"] == a["selected_candidate_ids"] else " — отличается: эта цель жертвует средним ради худшей точки."), ""]
    ma, mb = P["candidate:cand-A"]["metrics"], P["candidate:cand-B"]["metrics"]
    if ma["mean_distance_mm"] is not None and mb["mean_distance_mm"] is not None:
        better_mean = "A" if ma["sum_distance_mm"] < mb["sum_distance_mm"] else "B" if mb["sum_distance_mm"] < ma["sum_distance_mm"] else None
        better_max = "A" if ma["max_distance_mm"] < mb["max_distance_mm"] else "B" if mb["max_distance_mm"] < ma["max_distance_mm"] else None
        if better_mean and better_max and better_mean != better_max:
            L.append(f"**Компромисс.** {better_mean} лучше по среднему, {better_max} — по худшей точке; выбор зависит от того, что важнее.")
        else:
            L.append(f"**Компромисс.** В этом кейсе компромисса нет: {better_mean or better_max or 'варианты равны'} не хуже по среднему и по худшей точке. "
                     "Стоимость неизвестна, поэтому «дешевле» не сравнивается.")
    L += ["", "## Откуда каждое число", "| Показатель | Формула | Входы | Вид |", "|---|---|---|---|"]
    L += [f"| {a_} | {b_} | {c_} | {d_} |" for a_, b_, c_, d_ in METRIC_SOURCES]
    L += ["", "## Ограничения"] + [f"- {x['text']}" for x in r["limitations"]] + [f"- {x}" for x in c["model_assumptions"]]
    L += ["", f"Факты для AI/записки: `facts.json` ({len(r['facts'])} фактов, kind=derived, у каждого source_ids и assumptions)."]
    open(os.path.join(out, city, "EXPLANATION.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(city, "->", os.path.join(out, city, "EXPLANATION.md"))
