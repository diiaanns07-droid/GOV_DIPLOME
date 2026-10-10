"""Сборка шаблонной синтетики v3 (R02, раунд 14). Детерминированно: SEED фиксирован.

    python -m ml.datasets.synth_v3.build           # пересобрать data/
    python -m ml.datasets.synth_v3.build --check   # пересобрать во временную папку и сверить sha256 (код 1, если отличается)

Выход (ml/datasets/synth_v3/data/):
  corpus_v3.jsonl          — сообщения: id, text, label, lang, template_id, family, register, variant, style,
                             hard, split, evidence="synthetic", corpus="synth_v3", anonymized
  manifest_v3.json         — seed, sha256, счётчики по split/категории/языку/стилю, разбиение шаблонов, что удалено
  paraphrase_pairs_v3.jsonl — пары для проверки поиска дублей (R04): тот же случай другими словами / другой случай

Защита от утечки между train/val/test (как в v1):
  1) обезличивание (ml/labeling/anonymize.py) до всего остального — корпус содержит маркеры [телефон], [адрес];
  2) точные повторы после нормализации удаляются ДО split; повтор с разными метками — удаляются все копии;
  3) split по шаблонам: val/test построены из шаблонов, которых нет в train (внутри пары категория × язык);
  4) val/test, слишком похожие на train (Jaccard символьных 3-грамм ≥ NEAR_DUP), помечаются excluded_near_dup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import tempfile
from pathlib import Path

from ml.datasets.synth_v3 import slots as S
from ml.datasets.synth_v3.templates import T
from ml.labeling.anonymize import anonymize
from ml.labeling.text_utils import normalize

CORPUS_VERSION = "synth_v3"
SEED = 20261011
EXPANSIONS = 22          # вариантов на обычный шаблон
SHORT_EXPANSIONS = 7     # на короткий (у них мало вариантов — иначе одни повторы)
NEAR_DUP = 0.8
SPLIT_PATTERN = ("train", "val", "train", "test", "train", "train", "val", "train", "test", "train")
# Вероятности вариантов (на одно сообщение)
P_LONG, P_TYPOS, P_TRANSLIT, P_SLANG, P_CODESWITCH, P_CONTACT = 0.18, 0.14, 0.06, 0.10, 0.08, 0.07
P_LOWER, P_NO_PUNCT = 0.22, 0.08
PAIRS_POSITIVE, PAIRS_SAME_PLACE, PAIRS_OTHER_PLACE = 400, 200, 200

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
CATEGORIES_JSON = HERE.parents[2] / "research" / "round-14" / "categories_v2.json"

_ALT = re.compile(r"\[([^\[\]]*)\]")
_SLOT = re.compile(r"\{(\w+)\}")
LOC_KINDS = {"street": "street", "street_kk": "street", "street_kk_loc": "street",
             "place": "place", "Place": "place", "place_kk": "place", "Place_kk": "place",
             "stop": "stop", "stop_kk": "stop"}


def labels_v2() -> list[str]:
    return [c["id"] for c in json.loads(CATEGORIES_JSON.read_text(encoding="utf-8"))["categories"]]


# ── заполнение шаблона ───────────────────────────────────────────────────────

def alternatives(text: str, rng: random.Random) -> str:
    """[а|б|в] → один вариант (изнутри наружу)."""
    while True:
        m = _ALT.search(text)
        if not m:
            return text
        text = text[:m.start()] + rng.choice(m.group(1).split("|")) + text[m.end():]


def sample_values(rng: random.Random) -> dict:
    """Один «случай»: место, улица, остановка, время — сразу на ru и kk (выровнено по индексу)."""
    i, j = rng.sample(range(len(S.STREETS)), 2)
    n = rng.randint(2, 98)
    p_ru, p_kk = rng.choice(S.PLACES)
    t_ru, t_kk = rng.choice(S.TIMES)
    st_ru, st_kk = rng.choice(S.STOPS)
    d_ru, d_kk = rng.choice(S.DISTRICTS)
    place = p_ru.format(n=n, s2=S.STREETS[j])
    place_kk = p_kk.format(n=n, s2kk=S.STREETS_KK[j])
    return {
        "street": S.STREETS[i], "street2": S.STREETS[j], "street2_kk": S.STREETS_KK[j],
        "street_kk": S.STREETS_KK[i] + " көшесі", "street_kk_loc": S.STREETS_KK[i] + " көшесінде",
        "place": place, "Place": place[:1].upper() + place[1:],
        "place_kk": place_kk, "Place_kk": place_kk[:1].upper() + place_kk[1:],
        "stop": st_ru, "stop_kk": st_kk, "time": t_ru, "time_kk": t_kk,
        "district": d_ru, "district_kk": d_kk, "bus": rng.choice(S.BUSES),
        "_loc": {"street": i, "place": (p_ru, n, j), "stop": st_ru},
    }


def tidy(text: str) -> str:
    text = " ".join(text.split())
    text = re.sub(r"\s+([.,!?:;])", r"\1", text)
    text = re.sub(r"([.,!?])\1+", r"\1", text)
    return text[:1].upper() + text[1:] if text else text


# Слот места иногда повторяет слово шаблона («Во дворе {place}» + «во дворе дома 12»). Чиним по-человечески.
PLACE_FIXES = (
    (re.compile(r"(?i)\b(во дворе) во дворе\b"), r"\1"),
    (re.compile(r"ауласында аулада\b"), "ауласында"),
    (re.compile(r"ауласында аулаға\b"), "ауласына"),
    (re.compile(r"ауласында аула\b"), "ауласы"),
    (re.compile(r"(?i)\bаулада (\S+ ауласында)"), r"\1"),
)
PROPER_START = tuple(S.STREETS) + tuple(S.STREETS_KK) + ("№", "«", "ТЭЦ", "ЖЭО", "ЦОН")


def render(template: str, values: dict, rng: random.Random) -> str:
    text = alternatives(template, rng).format(**values)
    for rx, repl in PLACE_FIXES:
        text = rx.sub(repl, text)
    return tidy(text)


def join_prefix(prefix: str, msg: str) -> str:
    """«Короче,» + «Автобусы …» → «Короче, автобусы …» (имена собственные не трогаем)."""
    if prefix.endswith(",") and msg and not msg.startswith(PROPER_START) and msg[1:2].islower():
        msg = msg[:1].lower() + msg[1:]
    return msg


def slots_of(template: str) -> set[str]:
    return set(_SLOT.findall(template))


def loc_kinds(template: str) -> set[str]:
    return {LOC_KINDS[s] for s in slots_of(template) if s in LOC_KINDS}


# ── варианты стиля ───────────────────────────────────────────────────────────

RU_LAT = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i",
          "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
          "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
          "э": "e", "ю": "yu", "я": "ya"}
# Казахские буквы пишут латиницей по-разному — выбираем схему на сообщение.
KK_LAT = ({"ә": "a", "ғ": "g", "қ": "k", "ң": "n", "ө": "o", "ұ": "u", "ү": "u", "һ": "h", "і": "i"},
          {"ә": "ae", "ғ": "gh", "қ": "q", "ң": "ng", "ө": "oe", "ұ": "u", "ү": "ue", "һ": "h", "і": "i"},
          # латиница 2021 года: ы → ı, і → i, ш → ş, ж → j, ұ → ū
          {"ә": "ä", "ғ": "ğ", "қ": "q", "ң": "ñ", "ө": "ö", "ұ": "ū", "ү": "ü", "һ": "h", "і": "i", "ы": "ı",
           "ш": "ş", "ж": "j", "ч": "ç"})


def translit(text: str, rng: random.Random, lang: str = "ru") -> str:
    """Латиница «как пишут в чатах». Русский текст — привычной схемой (sh, zh, ch); казахский — одной из трёх."""
    table = dict(RU_LAT)
    table.update(KK_LAT[0] if lang == "ru" else rng.choice(KK_LAT))
    out = []
    for ch in text:
        low = ch.lower()
        if low in table:
            lat = table[low]
            out.append(lat.capitalize() if ch != low and lat else lat)
        else:
            out.append(ch)
    return "".join(out)


# соседние клавиши ЙЦУКЕН — самые частые опечатки при наборе на телефоне
NEIGHBORS = {"а": "вп", "о": "рл", "е": "кн", "и": "мт", "н": "ег", "т": "иь", "с": "чм", "р": "по", "л": "до",
             "к": "уе", "м": "си", "п": "ар", "д": "лж", "у": "цк", "в": "ыа", "ы": "фв", "я": "чф", "ш": "щг"}


def typos(text: str, rng: random.Random) -> str:
    words = text.split(" ")
    idx = [i for i, w in enumerate(words) if len(w) >= 4 and not w.startswith("[")]
    for i in rng.sample(idx, min(len(idx), rng.randint(1, 3))):
        w = words[i]
        j = rng.randrange(1, len(w) - 1)
        op = rng.choice(("drop", "swap", "dup", "near"))
        if op == "drop":
            w = w[:j] + w[j + 1:]
        elif op == "swap":
            w = w[:j - 1] + w[j] + w[j - 1] + w[j + 1:]
        elif op == "dup":
            w = w[:j] + w[j] + w[j:]
        elif w[j].lower() in NEIGHBORS:
            w = w[:j] + rng.choice(NEIGHBORS[w[j].lower()]) + w[j + 1:]
        words[i] = w
    text = " ".join(words).replace("ё", "е")
    if rng.random() < 0.6:
        text = text.replace(",", "")
    return text


def other_lang(lang: str) -> str:
    return "kk" if lang == "ru" else "ru"


def expand(tpl: tuple, rng: random.Random) -> list[dict]:
    tid, label, lang, family, register, text, hard = tpl
    short = register == "short"
    rows = []
    for k in range(SHORT_EXPANSIONS if short else EXPANSIONS):
        values = sample_values(rng)
        msg = render(text, values, rng)
        out_lang, variant, reg = lang, "plain", register
        if not short:
            frame_lang = "ru" if lang == "mixed" and rng.random() < 0.5 else lang
            frame_reg = register if register in ("official", "slang") else "colloquial"
            if register == "colloquial" and rng.random() < P_SLANG:
                frame_reg, reg = "slang", "slang"
            if lang in ("ru", "kk") and rng.random() < P_CODESWITCH:
                frame_lang, out_lang, variant = other_lang(lang), "mixed", "codeswitch"
            if register in ("thanks", "question"):
                pre, suf = ("", "Здравствуйте!", "Добрый день.") if lang != "kk" else ("", "Сәлеметсіз бе!"), ("",)
            else:
                pre, suf = S.FRAME[(frame_lang if frame_lang != "mixed" else "ru", frame_reg)]
            prefix = rng.choice(pre)
            msg = join_prefix(prefix, msg)
            parts = [prefix, msg, rng.choice(suf)]
            if register not in ("thanks", "question") and rng.random() < P_LONG:
                pool = S.LONG_BY_CAT[label] + S.LONG_COMMON
                det = rng.sample(pool, rng.randint(1, 2))
                li = 1 if lang == "kk" else 0
                # детали — после основного текста, до просьбы
                parts = [parts[0], msg] + [d[li] for d in det] + [parts[2]]
                variant = "long" if variant == "plain" else variant + "+long"
            if rng.random() < P_CONTACT:
                c = rng.choice(S.CONTACTS_KK if lang == "kk" else S.CONTACTS_RU)
                parts.append(c.format(d=rng.randint(0, 8), a=rng.randint(100, 999), b=rng.randint(10, 99),
                                      c=rng.randint(10, 99), n=rng.randint(1, 99), street=values["street"],
                                      h=rng.randint(1, 120), k=rng.randint(1, 300)))
            msg = tidy(" ".join(p for p in parts if p))
        r = rng.random()
        if r < P_TRANSLIT and not short:
            msg = translit(msg, rng, out_lang)
            variant = "translit"
        elif r < P_TRANSLIT + P_TYPOS:
            msg = typos(msg, rng)
            variant = "typos" if variant == "plain" else variant + "+typos"
        r = rng.random()
        if r < P_LOWER:
            msg = msg.lower()
        elif r < P_LOWER + P_NO_PUNCT:
            msg = msg.rstrip(".!?")
        rows.append({"id": f"{tid}-{k:02d}", "raw": msg, "label": label, "lang": out_lang, "template_id": tid,
                     "family": family, "register": reg, "variant": variant, "hard": hard})
    return rows


def style_of(row: dict) -> str:
    """Один основной стиль для отчётов: транслит > опечатки > длинный > регистр шаблона."""
    v = row["variant"]
    if "translit" in v:
        return "translit"
    if "typos" in v:
        return "typos"
    if "long" in v:
        return "long"
    return row["register"]


# ── защита от утечки ─────────────────────────────────────────────────────────

def grams(text: str) -> frozenset:
    t = f" {normalize(text)} "
    return frozenset(t[i:i + 3] for i in range(len(t) - 2))


def max_similarity(items: list[frozenset], pool: list[frozenset]) -> list[float]:
    """Максимальная Jaccard-близость каждого элемента к пулу (инвертированный индекс по 3-граммам)."""
    index: dict[str, list[int]] = {}
    for j, g in enumerate(pool):
        for gram in g:
            index.setdefault(gram, []).append(j)
    out = []
    for g in items:
        overlap: dict[int, int] = {}
        for gram in g:
            for j in index.get(gram, ()):
                overlap[j] = overlap.get(j, 0) + 1
        best = 0.0
        for j, inter in overlap.items():
            union = len(g) + len(pool[j]) - inter
            best = max(best, inter / union if union else 1.0)
        out.append(best)
    return out


def template_split(seed: int) -> dict[str, str]:
    """Внутри (категория, язык) шаблоны упорядочиваются по sha256(seed:id) и раскладываются по SPLIT_PATTERN.
    Короткие шаблоны всегда в train: они слишком похожи друг на друга, чтобы честно проверять на них."""
    split, groups = {}, {}
    for t in T:
        if t[4] == "short":
            split[t[0]] = "train"
            continue
        groups.setdefault((t[1], t[2]), []).append(t[0])
    for key in sorted(groups):
        ordered = sorted(groups[key], key=lambda i: hashlib.sha256(f"{seed}:{i}".encode()).hexdigest())
        for k, tid in enumerate(ordered):
            split[tid] = SPLIT_PATTERN[k % len(SPLIT_PATTERN)]
    return split


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# ── пары перефразов для R04 ──────────────────────────────────────────────────

def frame_light(msg: str, lang: str, rng: random.Random) -> str:
    pre, suf = S.FRAME[("kk" if lang == "kk" else "ru", "colloquial")]
    return tidy(" ".join(x for x in (rng.choice(pre), msg, rng.choice(suf)) if x))


def build_pairs(rng: random.Random) -> list[dict]:
    pool = [t for t in T if t[4] not in ("short", "thanks", "question") and loc_kinds(t[5])]
    by_family: dict[tuple, list[tuple]] = {}
    for t in pool:
        by_family.setdefault((t[1], t[3]), []).append(t)
    multi = [fam for fam, ts in sorted(by_family.items()) if len(ts) >= 2]
    pairs = []

    def emit(kind, same, ta, tb, va, vb):
        # одинаковые строки — не пара перефразов: перерисовываем (другие варианты слов и рамка)
        for _try in range(10):
            a = anonymize(frame_light(render(ta[5], va, rng), ta[2], rng))[0]
            b = anonymize(frame_light(render(tb[5], vb, rng), tb[2], rng))[0]
            if normalize(a) != normalize(b):
                break
        else:
            return
        fam_hash = hashlib.sha256(f"{SEED}:{ta[1]}:{ta[3]}".encode()).hexdigest()
        pairs.append({"pair_id": f"pp-{len(pairs):04d}", "a": a, "b": b, "same_incident": same, "kind": kind,
                      "category_a": ta[1], "category_b": tb[1], "family_a": ta[3], "family_b": tb[3],
                      "lang_a": ta[2], "lang_b": tb[2], "template_a": ta[0], "template_b": tb[0],
                      "split": "dev" if int(fam_hash, 16) % 2 == 0 else "test", "evidence": "synthetic"})

    def differs(va, vb, kinds):
        return all(va["_loc"][k] != vb["_loc"][k] for k in kinds)

    for n in range(PAIRS_POSITIVE):
        v = sample_values(rng)
        if n % 2 == 0:
            # тот же язык: другой шаблон семейства на том же языке, иначе тот же шаблон с другими словами и рамкой
            ta = rng.choice(pool)
            same_lang = [t for t in by_family[(ta[1], ta[3])] if t is not ta and t[2] == ta[2]
                         and loc_kinds(t[5]) & loc_kinds(ta[5])]
            if same_lang:
                emit("paraphrase", True, ta, rng.choice(same_lang), v, v)
            else:
                emit("paraphrase_same_template", True, ta, ta, v, v)
            continue
        fam = rng.choice(multi)
        for _try in range(20):
            ta, tb = rng.sample(by_family[fam], 2)
            if loc_kinds(ta[5]) & loc_kinds(tb[5]):
                break
        else:
            continue
        emit("paraphrase" if ta[2] == tb[2] else "paraphrase_crosslingual", True, ta, tb, v, v)
    for _ in range(PAIRS_SAME_PLACE):
        ta = rng.choice(pool)
        cands = [t for t in pool if t[3] != ta[3] and loc_kinds(t[5]) & loc_kinds(ta[5])]
        same_cat = [t for t in cands if t[1] == ta[1]]
        tb = rng.choice(same_cat if same_cat and rng.random() < 0.5 else cands)
        v = sample_values(rng)
        emit("same_place_other_problem", False, ta, tb, v, v)
    for _ in range(PAIRS_OTHER_PLACE):
        fam = rng.choice(multi)
        ta, tb = rng.choice(by_family[fam]), rng.choice(by_family[fam])
        kinds = loc_kinds(ta[5]) & loc_kinds(tb[5])
        if not kinds:
            continue
        va = sample_values(rng)
        vb = sample_values(rng)
        for _try in range(50):
            if differs(va, vb, kinds):
                break
            vb = sample_values(rng)
        emit("same_problem_other_place", False, ta, tb, va, vb)
    return pairs


# ── сборка ───────────────────────────────────────────────────────────────────

def build(out_dir: Path = DATA) -> dict:
    labels = labels_v2()
    ids = [t[0] for t in T]
    assert len(ids) == len(set(ids)), "повтор id шаблона"
    assert all(t[1] in labels for t in T), "метка вне categories_v2.json"
    assert set(labels) == {t[1] for t in T}, "есть категория без шаблонов"
    rng = random.Random(SEED)
    split_of = template_split(SEED)
    rows, pii = [], {}
    for tpl in T:
        for r in expand(tpl, rng):
            text, counts = anonymize(r.pop("raw"))
            for c, n in counts.items():
                pii[c] = pii.get(c, 0) + n
            r.update(text=" ".join(text.split()), anonymized=counts, split=split_of[r["template_id"]],
                     style=style_of(r))
            rows.append(r)
    generated = len(rows)
    by_norm: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        by_norm.setdefault(normalize(r["text"]), []).append(i)
    drop, conflicts = set(), 0
    for idxs in by_norm.values():
        if len({rows[i]["label"] for i in idxs}) > 1:
            conflicts += 1
            drop.update(idxs)
        else:
            drop.update(idxs[1:])
    rows = [r for i, r in enumerate(rows) if i not in drop]
    train_g = [grams(r["text"]) for r in rows if r["split"] == "train"]
    held = [r for r in rows if r["split"] != "train"]
    near = 0
    for r, s in zip(held, max_similarity([grams(r["text"]) for r in held], train_g)):
        r["max_train_jaccard"] = round(s, 3)
        if s >= NEAR_DUP:
            r["split"] = "excluded_near_dup"
            near += 1
    out_dir.mkdir(parents=True, exist_ok=True)
    corpus = out_dir / "corpus_v3.jsonl"
    keys = ("id", "text", "label", "lang", "split", "template_id", "family", "register", "variant", "style", "hard",
            "anonymized")
    with open(corpus, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            rec = {k: r[k] for k in keys}
            if "max_train_jaccard" in r:
                rec["max_train_jaccard"] = r["max_train_jaccard"]
            rec.update(evidence="synthetic", corpus=CORPUS_VERSION)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    pairs = build_pairs(random.Random(SEED + 1))
    pairs_path = out_dir / "paraphrase_pairs_v3.jsonl"
    with open(pairs_path, "w", encoding="utf-8", newline="\n") as fh:
        for p in pairs:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")

    def count(field):
        c: dict[str, int] = {}
        for r in rows:
            c[r[field]] = c.get(r[field], 0) + 1
        return dict(sorted(c.items()))

    by_split_label: dict[str, dict[str, int]] = {}
    for r in rows:
        by_split_label.setdefault(r["split"], {}).setdefault(r["label"], 0)
        by_split_label[r["split"]][r["label"]] += 1
    pair_kinds: dict[str, int] = {}
    for p in pairs:
        pair_kinds[p["kind"]] = pair_kinds.get(p["kind"], 0) + 1
    manifest = {
        "corpus": corpus.name, "corpus_version": CORPUS_VERSION, "corpus_sha256": sha256_file(corpus),
        "pairs": pairs_path.name, "pairs_sha256": sha256_file(pairs_path), "pairs_count": len(pairs),
        "pair_kinds": dict(sorted(pair_kinds.items())),
        "evidence_type": "synthetic", "labels_by": "agent (Claude, R02) by ml/datasets/LABELING_GUIDE_v2.md — not human",
        "categories": labels, "categories_source": "research/round-14/categories_v2.json",
        "seed": SEED, "expansions": EXPANSIONS, "short_expansions": SHORT_EXPANSIONS, "templates": len(T),
        "probabilities": {"long": P_LONG, "typos": P_TYPOS, "translit": P_TRANSLIT, "slang": P_SLANG,
                          "codeswitch": P_CODESWITCH, "contact": P_CONTACT, "lower": P_LOWER, "no_punct": P_NO_PUNCT},
        "split_unit": "template_id (group split внутри категория × язык; короткие шаблоны — только train)",
        "split_pattern": list(SPLIT_PATTERN), "near_dup_threshold": NEAR_DUP,
        "generated": generated, "rows": len(rows),
        "removed": {"exact_duplicates": len(drop), "label_conflicts": conflicts, "near_dup_val_test": near},
        "anonymized_markers": dict(sorted(pii.items())),
        "by_split": count("split"), "by_label": count("label"), "by_lang": count("lang"), "by_style": count("style"),
        "by_split_label": {k: dict(sorted(v.items())) for k, v in sorted(by_split_label.items())},
        "hard_cases": sum(1 for r in rows if r["hard"]),
        "template_split": dict(sorted(split_of.items())),
    }
    (out_dir / "manifest_v3.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Шаблонная синтетика v3: 12 категорий, ru/kk/mixed")
    ap.add_argument("--check", action="store_true", help="пересобрать во временную папку и сверить с data/")
    args = ap.parse_args(argv)
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            m = build(Path(tmp))
        cur = json.loads((DATA / "manifest_v3.json").read_text(encoding="utf-8"))
        ok = m["corpus_sha256"] == cur["corpus_sha256"] and m["pairs_sha256"] == cur["pairs_sha256"]
        print(("ok: data/ воспроизводится" if ok else "ОТЛИЧАЕТСЯ: пересоберите") +
              f" (corpus {m['corpus_sha256'][:12]}, pairs {m['pairs_sha256'][:12]})")
        return 0 if ok else 1
    m = build()
    print(f"corpus_v3: {m['rows']} сообщений из {m['generated']} (повторы −{m['removed']['exact_duplicates']}, "
          f"близкие к train в val/test: {m['removed']['near_dup_val_test']})")
    print("split:", m["by_split"])
    print("язык:", m["by_lang"])
    print("стиль:", m["by_style"])
    print("категории:", m["by_label"])
    print(f"пары: {m['pairs_count']} {m['pair_kinds']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
