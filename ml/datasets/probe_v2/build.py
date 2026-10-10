"""Сборка проверочного набора probe_v2 из source.py (R02, раунд 14).

    python -m ml.datasets.probe_v2.build           # записать probe_v2.jsonl и manifest_probe_v2.json
    python -m ml.datasets.probe_v2.build --check   # пересобрать во временную папку и сверить sha256

Что проверяется при сборке (иначе ошибка):
  - ровно 25 сообщений на каждую из 12 категорий categories_v2.json, всего 300;
  - нет точных повторов (после нормализации);
  - после обезличивания не осталось телефонов, e-mail, длинных номеров;
  - НЕЗАВИСИМОСТЬ от обучающих корпусов: максимальная близость к любому сообщению synth_v3 и v1_in_v2
    (Jaccard символьных 3-грамм) ниже NEAR_DUP = 0.8 — тот же порог, что отсекает утечку в synth_v3.
Близость каждой строки к v3 и v1 записывается в поля max_jaccard_synth_v3 / max_jaccard_v1 — по ним R03 может
отдельно посмотреть «далёкие» сообщения.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

from ml.datasets.probe_v2.source import P
from ml.datasets.synth_v3.build import grams, max_similarity
from ml.labeling import guide
from ml.labeling.anonymize import anonymize
from ml.labeling.text_utils import normalize

HERE = Path(__file__).resolve().parent
DATASETS = HERE.parent
OUT = HERE / "probe_v2.jsonl"
MANIFEST = HERE / "manifest_probe_v2.json"
SYNTH_V3 = DATASETS / "synth_v3" / "data" / "corpus_v3.jsonl"
V1 = DATASETS / "v1_in_v2" / "corpus_v1_in_v2.jsonl"
PER_CATEGORY = 25
NEAR_DUP = 0.8
LANGS = {"ru", "kk", "mixed"}
STYLES = {"long", "short", "slang", "translit", "typos", "official", "colloquial", "question", "thanks"}
_LEAK = re.compile(r"\+7|\b8 ?7\d{2}|\d{5,}|@\w")


def _texts(path: Path) -> list[str]:
    return [json.loads(line)["text"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build(out: Path = OUT, manifest_path: Path = MANIFEST) -> dict:
    labels = [c["id"] for c in guide.categories()]
    rows, seen, counters, pii = [], set(), {}, {}
    for cat, lang, style, hard, text in P:
        assert cat in labels, cat
        assert lang in LANGS and style in STYLES, (lang, style, text)
        n = counters.get(cat, 0) + 1
        counters[cat] = n
        clean, counts = anonymize(text)
        key = normalize(clean)
        assert key not in seen, f"повтор: {clean}"
        seen.add(key)
        assert not _LEAK.search(clean), f"персональные данные остались: {clean}"
        for k, v in counts.items():
            pii[k] = pii.get(k, 0) + v
        rows.append({"id": f"probe2-{cat}-{n:02d}", "text": clean, "label": cat, "lang": lang, "style": style,
                     "hard": bool(hard), "hard_rule": hard, "anonymized": counts, "source": "agent_probe_v2",
                     "evidence": "synthetic_agent_written", "split": "test",
                     "labels_by": "agent (Claude, R02) by ml/datasets/LABELING_GUIDE_v2.md"})
    bad = {c: counters.get(c, 0) for c in labels if counters.get(c, 0) != PER_CATEGORY}
    assert not bad, f"нужно по {PER_CATEGORY} на категорию: {bad}"

    g = [grams(r["text"]) for r in rows]
    sim_v3 = max_similarity(g, [grams(t) for t in _texts(SYNTH_V3)])
    sim_v1 = max_similarity(g, [grams(t) for t in _texts(V1)])
    for r, s3, s1 in zip(rows, sim_v3, sim_v1):
        r["max_jaccard_synth_v3"] = round(s3, 3)
        r["max_jaccard_v1"] = round(s1, 3)
    close = [(r["id"], r["max_jaccard_synth_v3"], r["max_jaccard_v1"]) for r in rows
             if max(r["max_jaccard_synth_v3"], r["max_jaccard_v1"]) >= NEAR_DUP]
    assert not close, f"слишком похоже на обучающие корпуса: {close}"

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    def count(field):
        c: dict[str, int] = {}
        for r in rows:
            c[str(r[field])] = c.get(str(r[field]), 0) + 1
        return dict(sorted(c.items()))

    def quantiles(vals):
        s = sorted(vals)
        return {"median": s[len(s) // 2], "p90": s[int(0.9 * (len(s) - 1))], "max": s[-1]}

    by_cat_lang: dict[str, dict[str, int]] = {}
    for r in rows:
        by_cat_lang.setdefault(r["label"], {}).setdefault(r["lang"], 0)
        by_cat_lang[r["label"]][r["lang"]] += 1
    manifest = {
        "corpus": out.name, "corpus_sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "rows": len(rows),
        "source": "agent_probe_v2", "evidence_type": "synthetic_agent_written",
        "written_by": "агент (Claude, R02, раунд 14) вручную, вне шаблонов synth_v3; не тексты жителей",
        "labels_by": "агент по ml/datasets/LABELING_GUIDE_v2.md (guide_sha256 ниже); не экспертная разметка",
        "guide_sha256": guide.guide_sha256(), "purpose": "только проверка (split=test); не использовать для обучения и подбора порогов",
        "per_category": PER_CATEGORY, "by_label": count("label"), "by_lang": count("lang"), "by_style": count("style"),
        "hard_cases": sum(r["hard"] for r in rows), "by_label_lang": {k: dict(sorted(v.items())) for k, v in sorted(by_cat_lang.items())},
        "anonymized_markers": dict(sorted(pii.items())),
        "independence": {"near_dup_threshold": NEAR_DUP, "max_jaccard_synth_v3": quantiles(sim_v3),
                         "max_jaccard_v1": quantiles(sim_v1),
                         "synth_v3_sha256": hashlib.sha256(SYNTH_V3.read_bytes()).hexdigest(),
                         "v1_in_v2_sha256": hashlib.sha256(V1.read_bytes()).hexdigest()},
        "length_chars": quantiles([len(r["text"]) for r in rows]),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="probe_v2: 300 проверочных сообщений, написанных вручную")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            m = build(Path(tmp) / OUT.name, Path(tmp) / MANIFEST.name)
        cur = json.loads(MANIFEST.read_text(encoding="utf-8"))
        ok = m["corpus_sha256"] == cur["corpus_sha256"]
        print("ok: probe_v2 воспроизводится" if ok else "ОТЛИЧАЕТСЯ: пересоберите probe_v2")
        return 0 if ok else 1
    m = build()
    print(f"probe_v2: {m['rows']} сообщений; язык {m['by_lang']}; стиль {m['by_style']}; спорных {m['hard_cases']}")
    print(f"близость к synth_v3: {m['independence']['max_jaccard_synth_v3']}, к v1: {m['independence']['max_jaccard_v1']}")
    print(f"обезличено: {m['anonymized_markers']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
