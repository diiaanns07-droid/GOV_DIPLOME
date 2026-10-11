"""Срочные случаи по тексту жалобы: «Это может быть опасно — звоните 104/112» (POLISH_WAVE п. 3, владелец R09).

Модель v2 здесь не участвует: она предсказывает только категорию. Это отдельное правило по словам, которое R09
показывает до отправки. Правила — в emergency_rules.json (один файл для Python и JS), эталон на JS —
emergency_ref.mjs (его можно скопировать в web/civic/feedback/). Телефон берётся из categories_v2.json
(emergency_phone уточнения), а не из правил.

Почему не просто «газ», «горит», «пожар» подстрокой: на корпусах R02 так ловится «газон» (парковка на газоне),
«не горит фонарь», «пожарная машина не проедет» — баннер «звоните 104» на обычной жалобе. Разбор —
results/EMERGENCY_KEYWORDS.md:

    python -m ml.civic_classifier_v2.emergency check --synth-v3 DIR --llm-v1 DIR --v1-in-v2 DIR --probe-v2 DIR
    python -m ml.civic_classifier_v2.emergency detect "В подъезде пахнет газом"
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

from ml.civic_classifier_v2 import data as D
from ml.civic_classifier_v2 import labels as L
from ml.civic_classifier_v2.config import LLM_V1_DIR, PKG_DIR, PROBE_V2_DIR, REPO_ROOT, RESULTS_DIR, SYNTH_V3_DIR, V1_IN_V2_DIR

RULES_PATH = PKG_DIR / "emergency_rules.json"
JS_REF_PATH = PKG_DIR / "emergency_ref.mjs"
CASES_PATH = REPO_ROOT / "tests" / "civic" / "R03" / "round14" / "emergency_cases.json"

# Буквальное прочтение задания («в тексте "газ", "горит", "пожар", "оборван провод"») — только для сравнения.
NAIVE_WORDS = ("газ", "горит", "пожар", "оборван провод")
_WS = re.compile(r"\s+")


def normalize(text) -> str:
    """Шаг 1 правил: нижний регистр, ё -> е, пробелы схлопнуты. Так же делает emergency_ref.mjs."""
    return _WS.sub(" ", str(text or "").lower().replace("ё", "е")).strip()


def _expand(src: str, defs: dict) -> str:
    for key, value in defs.items():
        src = src.replace("{" + key + "}", value)
    return src


@lru_cache(maxsize=4)
def load_rules(path: str = str(RULES_PATH)) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    defs = raw["defs"]
    kinds = raw["kinds"]
    rules = []
    for r in raw["rules"]:
        if r["kind"] not in kinds:
            raise ValueError(f"{path}: правило {r['id']} — неизвестный kind {r['kind']}")
        rules.append({"id": r["id"], "kind": r["kind"], "re": re.compile(_expand(r["re"], defs)),
                      "veto": re.compile(_expand(r["veto"], defs)) if r.get("veto") else None})
    return {"version": raw["version"], "kinds": kinds, "rules": rules,
            "except": [re.compile(_expand(e["re"], defs)) for e in raw["except"]]}


def phones(path: Path = L.CATEGORIES_PATH) -> dict[tuple[str, str], str]:
    """(категория, уточнение) -> телефон из categories_v2.json."""
    out = {}
    for c in L.categories(path):
        for s in c.get("subtopics") or []:
            if s.get("emergency_phone"):
                out[(c["id"], s["id"])] = str(s["emergency_phone"])
    return out


def detect(text, rules: dict | None = None) -> list[dict]:
    """Срочные виды в тексте, по порядку kinds (gas, fire, wire): [{kind, rule, category, subtopic, phone, match}].

    Пустой список — баннер не нужен. Уточнение с emergency_phone, выбранное жителем, R09 проверяет отдельно."""
    rules = rules or load_rules()
    t = normalize(text)
    for ex in rules["except"]:
        t = ex.sub(" ", t)
    found = {}
    for r in rules["rules"]:
        if r["kind"] in found:
            continue
        m = r["re"].search(t)
        if m and not (r["veto"] and r["veto"].search(t)):
            found[r["kind"]] = {"rule": r["id"], "match": m.group(0).strip()}
    tel = phones()
    out = []
    for kind, ks in rules["kinds"].items():
        if kind in found:
            out.append({"kind": kind, "category": ks["category"], "subtopic": ks["subtopic"],
                        "phone": tel.get((ks["category"], ks["subtopic"])), **found[kind]})
    return out


def naive(text) -> bool:
    t = normalize(text)
    return any(w in t for w in NAIVE_WORDS)


_WORD = re.compile(r"[a-zа-яеәғқңөұүһі]+")


def naive_words(text) -> list[str]:
    """Слова, в которых подстрока нашла «газ», «горит», «пожар» («газоне», «магазином»…); «оборван провод» — целиком."""
    t = normalize(text)
    out = [w for w in _WORD.findall(t) if any(n in w for n in NAIVE_WORDS[:3])]
    return out + (["оборван провод"] if "оборван провод" in t else [])


def detect_js(texts: list[str], rules_path: Path = RULES_PATH) -> list[list[str]] | None:
    """Те же тексты через emergency_ref.mjs (node): виды по каждому тексту. None — node нет."""
    node = shutil.which("node")
    if not node:
        return None
    runner = ("import {readFileSync} from 'node:fs';"
              "const {compileRules, detect} = await import(process.argv[1]);"
              "const rules = compileRules(JSON.parse(readFileSync(process.argv[2], 'utf8')));"
              "const texts = JSON.parse(readFileSync(0, 'utf8'));"
              "process.stdout.write(JSON.stringify(texts.map(t => detect(t, rules).map(h => h.kind))));")
    res = subprocess.run([node, "--input-type=module", "-e", runner, JS_REF_PATH.as_uri(), str(rules_path)],
                         input=json.dumps(texts, ensure_ascii=False).encode("utf-8"),
                         capture_output=True, check=True, timeout=600)
    return json.loads(res.stdout.decode("utf-8"))


# ---------- проверка на корпусах и на наборе фраз ----------

def load_cases(path: Path = CASES_PATH) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["cases"]


def score_cases(cases: list[dict]) -> dict:
    """Набор фраз (агент R03, не люди): ожидаемый вид или null. Сравнение «правила» и «подстрока»."""
    res = {"n": len(cases), "rules_ok": 0, "naive_ok": 0, "rules_miss": [], "naive_miss": []}
    for c in cases:
        kinds = [h["kind"] for h in detect(c["text"])]
        want = c["expect"]
        ok = (kinds == [] if want is None else want in kinds)
        res["rules_ok"] += ok
        if not ok:
            res["rules_miss"].append({**c, "got": kinds})
        n_ok = naive(c["text"]) == (want is not None)
        res["naive_ok"] += n_ok
        if not n_ok:
            res["naive_miss"].append(c)
    return res


def scan(corpora: dict[str, list[dict]]) -> dict:
    out = {}
    for name, recs in corpora.items():
        by_cat_rules, by_cat_naive, words, hits = Counter(), Counter(), Counter(), []
        for r in recs:
            found = detect(r["text"])
            if found:
                by_cat_rules[r["label"]] += 1
                hits.append({"id": r["id"], "label": r["label"], "lang": r["lang"], "text": r["text"],
                             "kinds": [h["kind"] for h in found], "rules": [h["rule"] for h in found],
                             "match": [h["match"] for h in found]})
            if naive(r["text"]):
                by_cat_naive[r["label"]] += 1
                if not found:
                    words.update(set(naive_words(r["text"])))
        out[name] = {"n": len(recs), "naive": sum(by_cat_naive.values()), "rules": len(hits),
                     "naive_by_label": dict(by_cat_naive.most_common()),
                     "rules_by_label": dict(by_cat_rules.most_common()),
                     "naive_only_words": dict(words.most_common()), "hits": hits}
    return out


def _cut(text: str, n: int = 150) -> str:
    text = " ".join(str(text).split()).replace("|", "/")
    return text if len(text) <= n else text[: n - 1] + "…"


def render(res: dict, cases: dict, js: dict | None, sources: dict) -> str:
    total_n = sum(v["n"] for v in res.values())
    total_naive = sum(v["naive"] for v in res.values())
    total_rules = sum(v["rules"] for v in res.values())
    out = ["# Срочные случаи по тексту: «газ», «горит», «пожар», «оборван провод» (R03 для R09)", "",
           f"Правила: `ml/civic_classifier_v2/emergency_rules.json` ({load_rules()['version']}); эталон на JS — "
           "`emergency_ref.mjs`. Файл собран командой `python -m ml.civic_classifier_v2.emergency check`.", "",
           "Зачем: POLISH_WAVE п. 3 — до отправки показать «Это может быть опасно. Звоните N». Если искать слова "
           "подстрокой, баннер появляется на обычных жалобах: «газ» находится в «газоне» и «магазине» (адрес «за "
           "магазином»), «горит» — в «не горит фонарь», «пожар» — в «пожарная машина не проедет». «Машины на газоне» — "
           "ещё и демо-фраза из бага R10 B-004.", "",
           "Корпуса — синтетика и тексты агента R02. Людей нет, поэтому настоящая доля срочных жалоб неизвестна. "
           "Сколько раз баннер сработал бы зря, видно по категориям: срочные виды — это smell_air (газ, дым) "
           "и lighting (провод). Срабатывание на parking или yards — почти всегда ошибка.", "",
           "## 1. Сколько текстов вызвали бы баннер", "",
           "| Корпус | Текстов | Подстрока | Правила R03 |", "|---|---:|---:|---:|"]
    for name, v in res.items():
        out.append(f"| {name} | {v['n']} | {v['naive']} ({v['naive'] / max(v['n'], 1):.1%}) | "
                   f"{v['rules']} ({v['rules'] / max(v['n'], 1):.1%}) |")
    out += [f"| **всего** | {total_n} | {total_naive} ({total_naive / max(total_n, 1):.1%}) | "
            f"{total_rules} ({total_rules / max(total_n, 1):.1%}) |", "",
            "По категориям (все корпуса вместе):", "",
            "| Категория | Подстрока | Правила R03 |", "|---|---:|---:|"]
    nv, rl = Counter(), Counter()
    for v in res.values():
        nv.update(v["naive_by_label"])
        rl.update(v["rules_by_label"])
    for lab in sorted(set(nv) | set(rl), key=lambda x: -(nv[x] + rl[x])):
        out.append(f"| {lab} | {nv[lab]} | {rl[lab]} |")
    ww = Counter()
    for v in res.values():
        ww.update(v["naive_only_words"])
    out += ["", "На каких словах срабатывает подстрока там, где правила баннер не показывают (текстов со словом, "
            "все корпуса):", "", "| Слово | Текстов |", "|---|---:|"]
    out += [f"| {w} | {n} |" for w, n in ww.most_common(15)]
    out += ["", "## 2. Набор фраз (tests/civic/R03/round14/emergency_cases.json)", "",
            f"Фраз: {cases['n']} (ru/kk/смешанные/транслит; срочные и похожие несрочные; написаны агентом R03, "
            "это не тексты людей).", "",
            f"- правила R03: верно {cases['rules_ok']} из {cases['n']};",
            f"- подстрока: верно {cases['naive_ok']} из {cases['n']}.", ""]
    if cases["rules_miss"]:
        out += ["Ошибки правил:", ""] + [f"- «{_cut(c['text'])}» — ждали {c['expect']}, получили {c['got']}"
                                         for c in cases["rules_miss"]] + [""]
    out += ["Ошибки подстроки (примеры):", ""]
    out += [f"- «{_cut(c['text'])}» — ждали {c['expect'] or 'без баннера'}" for c in cases["naive_miss"][:15]]
    out += ["", "## 3. Python и JS", ""]
    if js is None:
        out.append("node не найден — сверка не выполнялась (NOT_RUN).")
    else:
        out.append(f"Эталон `emergency_ref.mjs` (node) и `emergency.py` дали одинаковый ответ на {js['same']} из "
                   f"{js['n']} текстов (корпуса + набор фраз).")
        out += [f"- расхождение: «{_cut(d['text'])}» py={d['py']} js={d['js']}" for d in js["diff"][:10]]
    out += ["", "## 4. Все срабатывания правил в корпусах (для просмотра человеком)", "",
            "| Корпус | Метка | Язык | Вид | Правило | Что нашлось | Текст |", "|---|---|---|---|---|---|---|"]
    for name, v in res.items():
        for h in v["hits"]:
            out.append(f"| {name} | {h['label']} | {h['lang']} | {', '.join(h['kinds'])} | {', '.join(h['rules'])} | "
                       f"{_cut('; '.join(h['match']), 40)} | {_cut(h['text'])} |")
    out += ["", "## 5. Как подключить (R09)", "",
            "- Баннер по уточнению с `emergency_phone` (чип) остаётся главным; правило по тексту — подстраховка, "
            "если житель уточнение не выбрал.",
            "- Скопировать `emergency_rules.json` и `emergency_ref.mjs` к себе. `detect(text, compileRules(json))` "
            "возвращает виды: gas → уточнение smell_air/gas, fire → smell_air/smoke_fire, wire → lighting/wire_down. "
            "Телефон брать из categories_v2.json.",
            "- В JS не использовать `\\b` с кириллицей: он работает только для латиницы, и «газ» не найдётся. "
            "Не использовать просмотр назад (`(?<=`, `(?<!`): старый Safari на iOS < 16.4 падает на таком "
            "выражении, и ломается весь скрипт мастера. В правилах ни того, ни другого нет.",
            "- Жалобу можно отправить и после баннера (так в POLISH_WAVE).", "",
            "## 6. Что правила сознательно не ловят", "",
            "- «Торчат провода у фонарного столба», «провода оголены», kk «сымдары ашық», «висят», «салбырап» — частая "
            "обычная жалоба на опору (lighting), не «оборван провод» из задания. Баннер — только если провод оборван, "
            "упал или лежит на земле, искрит или бьёт током. Если житель сам выберет чип «Оборван провод», баннер "
            "покажет чип.",
            "- Уличный дым и гарь (ТЭЦ, жгут листья, свалка) — хроническая жалоба на воздух, а не пожар. Баннер — "
            "если дым или гарь в подъезде, квартире, подвале, лифте или идёт из окна.",
            "- «Огонь» без других слов: в probe_v2 есть сленг «новый сквер огонь».",
            "- «Нет газа» и «газовая плита сломалась» баннер вызывают: 104 — аварийная газовая служба, ей звонят "
            "и по таким поводам. Если владелец решит иначе, правило gas_ru нужно сузить до «запах/утечка газа».", "",
            "## Источники", ""]
    out += [f"- {name}: {_where(path)}" for name, path in sources.items()]
    return "\n".join(out) + "\n"


def _where(path: str) -> str:
    """Путь внутри своего git-репозитория + короткий SHA (корпуса обычно в отдельной копии ветки R02)."""
    p = Path(path)
    p = p if p.is_dir() else p.parent
    try:
        git = lambda *a: subprocess.run(["git", "-C", str(p), *a], capture_output=True, check=True,  # noqa: E731
                                        timeout=30).stdout.decode("utf-8").strip()
        return f"`{git('rev-parse', '--show-prefix').rstrip('/') or '.'}` @ {git('rev-parse', '--short', 'HEAD')}"
    except (OSError, subprocess.SubprocessError):
        return f"`{path}`"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_classifier_v2.emergency", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detect", help="проверить один текст")
    d.add_argument("text")
    c = sub.add_parser("check", help="корпуса R02 + набор фраз -> results/EMERGENCY_KEYWORDS.md")
    c.add_argument("--synth-v3", default=str(SYNTH_V3_DIR))
    c.add_argument("--llm-v1", default=str(LLM_V1_DIR))
    c.add_argument("--v1-in-v2", default=str(V1_IN_V2_DIR))
    c.add_argument("--probe-v2", default=str(PROBE_V2_DIR))
    c.add_argument("--cases", default=str(CASES_PATH))
    c.add_argument("--no-js", action="store_true", help="не сверять с emergency_ref.mjs")
    c.add_argument("--out", default=str(RESULTS_DIR / "EMERGENCY_KEYWORDS.md"))
    args = ap.parse_args(argv)

    if args.cmd == "detect":
        print(json.dumps(detect(args.text), ensure_ascii=False, indent=1))
        return 0

    sources = {"synth_v3": args.synth_v3, "llm_v1": args.llm_v1, "v1_in_v2": args.v1_in_v2, "probe_v2": args.probe_v2}
    corpora = {}
    for name, path in sources.items():
        try:
            corpora[name], _ = D.load_corpus(Path(path), source=name, evidence="synthetic")
        except FileNotFoundError as exc:
            D.warn(f"{name}: {exc} — пропускаю")
    res = scan(corpora)
    case_list = load_cases(Path(args.cases))
    cases = score_cases(case_list)
    js = None
    if not args.no_js:
        texts = [r["text"] for recs in corpora.values() for r in recs] + [x["text"] for x in case_list]
        js_kinds = detect_js(texts)
        if js_kinds is not None:
            diff = []
            for t, jk in zip(texts, js_kinds):
                pk = [h["kind"] for h in detect(t)]
                if pk != jk:
                    diff.append({"text": t, "py": pk, "js": jk})
            js = {"n": len(texts), "same": len(texts) - len(diff), "diff": diff}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(res, cases, js, {k: v for k, v in sources.items() if k in corpora}), encoding="utf-8")
    meta = {"rules_version": load_rules()["version"],
            "corpora": {k: {kk: vv for kk, vv in v.items() if kk != "hits"} | {"hit_ids": [h["id"] for h in v["hits"]]}
                        for k, v in res.items()},
            "cases": {k: v for k, v in cases.items() if not k.endswith("_miss")} |
                     {"rules_miss": [m["text"] for m in cases["rules_miss"]]},
            "js": None if js is None else {"n": js["n"], "same": js["same"]}}
    out.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tot = sum(v["n"] for v in res.values())
    js_note = "NOT_RUN" if js is None else f"{js['same']}/{js['n']}"
    print(f"{out}: текстов {tot}; подстрока {sum(v['naive'] for v in res.values())}, правила "
          f"{sum(v['rules'] for v in res.values())}; фразы {cases['rules_ok']}/{cases['n']} "
          f"(подстрока {cases['naive_ok']}/{cases['n']}); JS {js_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
