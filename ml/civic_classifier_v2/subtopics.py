"""Уточнения (subtopics) ↔ категории: найдёт ли житель нужный чип после подсказки модели.

POLISH_WAVE п. 2 (R09): после категории — чипы уточнений этой категории из categories_v2.json; модель предсказывает
только категорию. Значит, чип «Опасный перекрёсток» (он в roads) житель увидит, только если текст про перекрёсток
модель отнесёт к roads. Модель учится по разметке R02 (LABELING_GUIDE_v2.md), а уточнения разложены по категориям
отдельно, координатором. Где эти две раскладки расходятся, чип «теряется» не из-за ошибки модели.

Две проверки:
  1. labels — сами подписи чипов (39 × ru/kk) через словарь (v1 и продуктовый), логрегрессию (--logreg, обучается
     здесь же на v3 + LLM, ≈ 20 с) и модель v2 (--model DIR, на ноутбуке: ONNX/torch).
  2. corpus — тексты корпусов R02 со словами уточнения (SUBTOPIC_STEMS ниже): какую категорию им ставит разметка R02.
     Это то, чему учится модель. Если метка другая и подходящего чипа в той категории нет — чип «потерян».
Слова SUBTOPIC_STEMS написал R03 11.10 по подписям чипов и LABELING_GUIDE_v2 (не по текстам людей).

    python -m ml.civic_classifier_v2.subtopics --synth-v3 DIR --llm-v1 DIR --probe-v2 DIR --v1-in-v2 DIR --logreg
    python -m ml.civic_classifier_v2.subtopics ... --model ml/civic_classifier_v2/artifacts/onnx   # ноутбук
Результат: results/subtopic_check.json и results/SUBTOPIC_CHECK.md (тексты людей — только числа).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from ml.civic_classifier_v2 import heuristic as H
from ml.civic_classifier_v2 import labels as L
from ml.civic_classifier_v2.config import LLM_V1_DIR, PROBE_V2_DIR, RESULTS_DIR, SYNTH_V3_DIR, V1_IN_V2_DIR

# Совпадение — подстрока в " " + normalize(text) + " " (как в heuristic.py): ведущий пробел = начало слова;
# "a&b" — в тексте есть и a, и b. Для каждого уточнения — слова, по которым житель его опишет; ru и kk.
# Общие слова (газон, переход) допустимы: смысл проверки — куда разметка относит тексты с этими словами.
SUBTOPIC_STEMS: dict[str, tuple[str, ...]] = {
    "pothole": (" ям", "выбоин", "колдобин", "шұңқыр"),
    "traffic_light_broken": ("светофор", "бағдаршам"),
    "traffic_light_timing": ("светофор", "бағдаршам"),
    "intersection": ("перекрест", "қиылыс"),
    "marking": ("разметк", "жол таңба", "жол белгі"),
    "speed_bump": ("лежач", "кедір"),
    "snow_not_cleared": ("снег", "сугроб", " қар ", " қарды", " қардан", " қары "),
    "ice": ("гололед", "налед", "көктайғақ", "тайғақ"),
    "icicles": ("сосульк", "сүңгі"),
    "crossing": ("переход", "зебр", "өткел"),
    "broken_sidewalk": ("тротуар", "плитк"),
    "accessibility": ("пандус", "бордюр", "коляск", "жиектас", "мүгедек"),
    "stop_shelter": ("павильон", "навес", "остановк", "аялдам"),
    "schedule": ("расписан", "интервал", "долго жд", "кесте", "ұзақ күт"),
    "route": ("маршрут", " бағыт"),
    "lamp_off": ("фонар", "светильник", "не горит", "не горят", "жанбайды"),
    "dark_yard": ("темно", "темнот", "қараңғы"),
    "blinking": ("мигает", "мигают", "жыпылық"),
    "wire_down": (" провод", " сым ", " сымдар", " сымы "),
    "playground": ("детск", "площадк", "качел", "әткеншек", "балалар алаң"),
    "trees_lawn": ("дерев", "газон", "ағаш", "көгал"),
    "benches": ("скамейк", "лавочк", "орындық"),
    "bins_full": ("переполн", "контейнер", " бак", "толып"),
    "dump": ("свалк", "үйінді"),
    "not_collected": ("не вывоз", "вывоз", "шығарылмай"),
    "no_heating": ("отоплен", "батаре", "жылу", "жылыт"),
    "no_water": ("нет воды", "без воды", "воды нет", "су жоқ", "су жоқ"),
    "sewage": ("канализ", "кәріз"),
    "power_building": ("свет в подъезд", "света в подъезд", "в подъезде не горит", "в подъезде не горят",
                       "свет в доме", "света в доме", "в квартире нет света", "нет электричеств",
                       "үйде жарық", "кіреберісте жарық", "электр жоқ"),
    "gas": (" газ ", " газа ", " газом ", " газу ", "газов", "газопровод", " газ иіс", " газдың"),
    "smoke_fire": (" дым", "задымл", "гарь", " гари", "түтін", " өрт"),
    "dust": ("пыль", "пыли", " шаң"),
    "bad_smell": ("запах", "вонь", "воня", "иіс"),
    "noise_night": ("шум", "громк", "музык", " шу ", "шуыл"),
    "dangerous_place": ("опасное место", "опасном месте", "опасный участок", " люк", "қауіпті орын", "қауіпті жер"),
    "stray_dogs": ("собак", " ит ", " иттер", "қаңғыбас"),
    "yard_cars": ("машин&газон", "автомобил&газон", "паркуют&газон", "во дворе машин", "машины во двор",
                  "көлік&көгал", "көлік&газон", "аулада көлік"),
    "sidewalk_parking": ("машин&тротуар", "автомобил&тротуар", "паркуют&тротуар", "паркуются&тротуар", "көлік&тротуар"),
    "no_spaces": ("нет мест", "мест нет", "нет парковочн", "орын жоқ", "тұрақ жоқ"),
}
LOST_SHARE_FLAG = 0.25
MIN_TEXTS = 10
PRIVATE_SETS = {"human"}


def subtopics(path: Path = L.CATEGORIES_PATH) -> list[dict]:
    """[{id, category, ru, kk}] в порядке categories_v2.json."""
    return [{"id": s["id"], "category": c["id"], "ru": s.get("ru", ""), "kk": s.get("kk", "")}
            for c in L.categories(path) for s in c.get("subtopics") or []]


def _check_stems() -> None:
    ids = {s["id"] for s in subtopics()}
    if ids and set(SUBTOPIC_STEMS) != ids:
        raise ValueError(f"SUBTOPIC_STEMS не совпадают с уточнениями categories_v2.json: "
                         f"лишние {sorted(set(SUBTOPIC_STEMS) - ids)}, нет {sorted(ids - set(SUBTOPIC_STEMS))}")


def _norm(text: str) -> str:
    return " " + H.normalize(text) + " "


def matches(text: str, sid: str, normed: str | None = None) -> bool:
    t = normed if normed is not None else _norm(text)
    return any(all(part in t for part in stem.split("&")) for stem in SUBTOPIC_STEMS[sid])


# --- 1. подписи чипов --------------------------------------------------------------------------------------

def label_check(predictors: dict) -> dict:
    """predictors: {имя: f(list[str]) -> list[str]}. Для каждой подписи — категории по каждой модели."""
    items = [(s, lang) for s in subtopics() for lang in ("ru", "kk") if s[lang]]
    texts = [s[lang] for s, lang in items]
    preds = {name: fn(texts) for name, fn in predictors.items()}
    rows, wrong = [], Counter()
    for i, (s, lang) in enumerate(items):
        row = {"subtopic": s["id"], "category": s["category"], "lang": lang, "text": texts[i],
               "pred": {name: preds[name][i] for name in predictors}}
        for name in predictors:
            wrong[name] += preds[name][i] != s["category"]
        rows.append(row)
    return {"n": len(items), "wrong": {n: wrong[n] for n in predictors}, "rows": rows}


# --- 2. корпуса --------------------------------------------------------------------------------------------

def corpus_check(sets: dict[str, list[dict]]) -> dict:
    """Для каждого уточнения s (чип в категории X) — тексты наборов со словами s и их метка разметки R02 Y:
      home    — Y == X: модель, выученная на этой разметке, покажет чипы X, нужный чип есть;
      covered — Y != X, но в Y есть другой чип, слова которого тоже есть в тексте (скамейка на остановке ->
                чип «Остановка: павильон, скамья»): житель найдёт подходящий чип;
      lost    — Y != X и подходящего чипа в Y нет: нужное уточнение житель не увидит.
    Флаг — lost ≥ 25 % при ≥ 10 текстах. Тексты людей (human) — в by_set, в итоговые доли не входят."""
    subs = subtopics()
    by_cat: dict[str, list[str]] = {}
    for t in subs:
        by_cat.setdefault(t["category"], []).append(t["id"])
    normed = {name: [(r, _norm(r["text"])) for r in rows] for name, rows in sets.items()}
    res = {}
    for s in subs:
        by_set, labels, kinds, lost_to = {}, Counter(), Counter(), Counter()
        for name, rows in normed.items():
            c = Counter()
            for r, t in rows:
                if not matches(r["text"], s["id"], t):
                    continue
                y = r["label"]
                c[y] += 1
                if name in PRIVATE_SETS:
                    continue
                labels[y] += 1
                if y == s["category"]:
                    kinds["home"] += 1
                elif any(matches(r["text"], o, t) for o in by_cat.get(y, [])):
                    kinds["covered"] += 1
                else:
                    kinds["lost"] += 1
                    lost_to[y] += 1
            by_set[name] = dict(c.most_common())
        n = sum(labels.values())
        share = {k: round(kinds[k] / n, 3) if n else None for k in ("home", "covered", "lost")}
        res[s["id"]] = {"category": s["category"], "n": n, **{k: kinds[k] for k in ("home", "covered", "lost")},
                        "share": share, "labels": dict(labels.most_common(5)), "lost_to": dict(lost_to.most_common(3)),
                        "by_set": by_set, "flag": bool(n >= MIN_TEXTS and kinds["lost"] / n >= LOST_SHARE_FLAG)}
    return res


def report_md(lab: dict | None, corp: dict | None, meta: dict) -> str:
    names = L.names("ru")
    lines = ["# Уточнения ↔ категории: найдёт ли житель нужный чип (R03)", "",
             "Чипы уточнений показываются после категории (POLISH_WAVE п. 2), модель предсказывает только категорию. "
             "Если текст про уточнение модель отнесёт к другой категории, нужного чипа житель не увидит. "
             f"Состав: {meta.get('what', '')}.", ""]
    if lab:
        models = list(lab["wrong"])
        lines += ["## 1. Подписи чипов (39 × ru/kk) — какую категорию дают модели", "",
                  "Ошибок (категория не та, в которой лежит чип): " +
                  ", ".join(f"{m} {lab['wrong'][m]} из {lab['n']}" for m in models), "",
                  "| Уточнение | Чип в категории | Язык | Подпись | " + " | ".join(models) + " |",
                  "|---|---|---|---|" + "---|" * len(models)]
        for r in lab["rows"]:
            if all(r["pred"][m] == r["category"] for m in models):
                continue
            cells = [("**" + r["pred"][m] + "**") if r["pred"][m] != r["category"] else r["pred"][m] for m in models]
            lines.append(f"| {r['subtopic']} | {r['category']} | {r['lang']} | {r['text']} | " + " | ".join(cells) + " |")
        lines += ["", "Показаны только подписи, где хотя бы одна модель ошиблась.", ""]
    if corp:
        lines += ["## 2. Корпуса R02: куда разметка относит тексты со словами уточнения", "",
                  "Чему учится модель. «Свой» — метка = категория чипа; «рядом» — метка другая, но там есть подходящий "
                  "чип; «потерян» — подходящего чипа в той категории нет. "
                  f"Флаг — потерян ≥ {LOST_SHARE_FLAG:.0%} при ≥ {MIN_TEXTS} текстах. Слова — SUBTOPIC_STEMS (R03).", "",
                  "| Уточнение | Чип в категории | Текстов | Свой | Рядом | Потерян | Куда уходят потерянные | Флаг |",
                  "|---|---|---:|---:|---:|---:|---|---|"]
        for sid, r in sorted(corp.items(), key=lambda kv: -(kv[1]["share"]["lost"] or 0)):
            if not r["n"]:
                lines.append(f"| {sid} | {names.get(r['category'], r['category'])} | 0 | — | — | — | | |")
                continue
            sh = r["share"]
            lost_to = ", ".join(f"{names.get(k, k)} {v}" for k, v in r["lost_to"].items())
            lines.append(f"| {sid} | {names.get(r['category'], r['category'])} | {r['n']} | {sh['home']:.0%} | "
                         f"{sh['covered']:.0%} | {sh['lost']:.0%} | {lost_to} | {'⚠' if r['flag'] else ''} |")
        lines.append("")
    return "\n".join(lines) + "\n"


# --- CLI ---------------------------------------------------------------------------------------------------

def _load_sets(args) -> dict[str, list[dict]]:
    from ml.civic_classifier_v2 import data as D
    sets = {}
    for name, path, ev in (("synth_v3", args.synth_v3, "synthetic_template"), ("llm_v1", args.llm_v1, "synthetic_llm"),
                           ("probe_v2", args.probe_v2, "synthetic_agent_written"),
                           ("v1_in_v2", args.v1_in_v2, "synthetic_template_v1")):
        try:
            sets[name], _ = D.load_corpus(Path(path), source=name, evidence=ev)
        except FileNotFoundError:
            print(f"нет {name}: {path} — пропуск", file=sys.stderr)
    if args.human:
        sets["human"], _ = D.load_human([Path(p) for p in args.human])
    return sets


def _logreg_predictor(sets: dict, seed: int):
    """Логрегрессия synth_all (v3 + LLM, train-часть; C=64 без весов — выбор LOCAL-4), без probe_v2."""
    from ml.civic_classifier_v2 import data as D
    from ml.civic_classifier_v2 import logreg
    pool = [dict(r) for name in ("synth_v3", "llm_v1") for r in sets.get(name, [])]
    D.ensure_splits(pool, seed)
    tr = [r for r in pool if r["split"] == "train"]
    va = [r for r in pool if r["split"] == "val"]
    model, _ = logreg.fit(tr, va, seed, grid=[{"C": 64.0, "class_weight": None, "keyword_scale": 1.0}])
    labs = L.labels()
    return lambda texts: [labs[i] for i in model.predict(texts)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_classifier_v2.subtopics", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--synth-v3", default=str(SYNTH_V3_DIR))
    ap.add_argument("--llm-v1", default=str(LLM_V1_DIR))
    ap.add_argument("--probe-v2", default=str(PROBE_V2_DIR))
    ap.add_argument("--v1-in-v2", default=str(V1_IN_V2_DIR))
    ap.add_argument("--human", nargs="*", help="JSONL разметки людей: только числа")
    ap.add_argument("--logreg", action="store_true", help="обучить логрегрессию synth_all здесь же (≈ 20 с)")
    ap.add_argument("--model", help="папка модели v2 (artifacts/onnx) — подписи чипов через модель")
    ap.add_argument("--seed", type=int, default=20261011)
    ap.add_argument("--out", default=str(RESULTS_DIR / "subtopic_check.json"))
    ap.add_argument("--md", default=str(RESULTS_DIR / "SUBTOPIC_CHECK.md"))
    args = ap.parse_args(argv)
    _check_stems()
    sets = _load_sets(args)
    predictors = {"словарь v1": lambda t: H.predict(t, "v1"), "словарь продукт": lambda t: H.predict(t, "product")}
    if args.logreg:
        predictors["логрегрессия"] = _logreg_predictor(sets, args.seed)
    model_version = None
    if args.model:
        from ml.civic_classifier_v2.predict import Classifier
        clf = Classifier.load(Path(args.model))
        model_version = clf.model_version
        predictors["модель v2"] = lambda t: [clf.labels[int(i)] for i in clf.predict_proba(t).argmax(axis=1)]
    lab = label_check(predictors)
    corp = corpus_check(sets)
    meta = {"what": "подписи чипов: " + ", ".join(predictors) + "; корпуса: " + ", ".join(
        f"{k} {len(v)}" for k, v in sets.items()), "model_version": model_version}
    out = {"meta": meta, "labels": lab, "corpus": corp}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    Path(args.md).write_text(report_md(lab, corp, meta), encoding="utf-8")
    print("ошибок на подписях чипов:", lab["wrong"])
    print("флаги корпусов:", {k: v["share"]["lost"] for k, v in corp.items() if v["flag"]})
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
