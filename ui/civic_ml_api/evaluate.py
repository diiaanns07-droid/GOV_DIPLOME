"""Оценка цепочки classify на синтетике R02 (val — для решений, test — один раз для отчёта).

    python -m ui.civic_ml_api.evaluate            # -> research/round-14-results/R04/classify_eval.json

Сравниваются: v1 одна (6 меток -> v2), словарь R03 один, цепочка R04 без перевода латиницы и полная
цепочка R04 (то, что отвечает API без модели v2). Модель v2 R03 сюда не входит — её отчёт делает R03.
Данные синтетические (evidence: synthetic): на текстах людей качество будет ниже — см. RESULTS.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ui.civic_ml_api import categories as C
from ui.civic_ml_api import classify_chain as K

CORPUS = C.REPO_ROOT / "ml" / "datasets" / "synth_v3" / "data" / "corpus_v3.jsonl"
OUT = C.REPO_ROOT / "research" / "round-14-results" / "R04" / "classify_eval.json"


def systems() -> dict:
    chain = K._Chain()
    v1, kw = chain.v1(), chain.kw()
    out = {}
    if v1 is not None:
        out["v1_only"] = lambda t: max(K._v1_probs(v1, t).items(), key=lambda kv: kv[1])[0]
    if kw is not None:
        out["kw12_only"] = lambda t: K._kw_result(kw.keyword_hits(t), tuple(kw.PRIORITY))[0]

    def chain_raw(t):
        cat, _s, _t3, best = K._kw_result(kw.keyword_hits(t), tuple(kw.PRIORITY))
        return cat if best or v1 is None else max(K._v1_probs(v1, t).items(), key=lambda kv: kv[1])[0]

    if kw is not None:
        out["r04_chain_no_translit"] = chain_raw
    out["r04_chain"] = lambda t: K.classify(t)["category"]  # то, что отвечает API (без v2)
    return out


def evaluate(path: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if r.get("split") in ("val", "test") and not r.get("excluded_near_dup")]
    report = {"generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "corpus": str(path.relative_to(C.REPO_ROOT)), "evidence": "synthetic (R02 synth_v3)",
              "model_version": K.CHAIN.version(), "splits": {}}
    sysmap = systems()
    for split in ("val", "test"):
        part = [r for r in rows if r["split"] == split]
        res = {"n": len(part), "accuracy": {}, "by_lang_variant": defaultdict(dict)}
        preds = {name: [fn(r["text"]) for r in part] for name, fn in sysmap.items()}
        for name, ps in preds.items():
            res["accuracy"][name] = round(sum(p == r["label"] for p, r in zip(ps, part)) / len(part), 4)
            groups = defaultdict(list)
            for p, r in zip(ps, part):
                groups[f"{r['lang']}/{r['variant'].split('+')[0]}"].append(p == r["label"])
            for g, v in sorted(groups.items()):
                res["by_lang_variant"][g][name] = {"n": len(v), "acc": round(sum(v) / len(v), 3)}
        # «suggest» (чип «Похоже на») — точность и покрытие
        sug = [(K.classify(r["text"]), r["label"]) for r in part]
        chosen = [(o["category"] == y) for o, y in sug if o["suggest"]]
        res["suggest"] = {"coverage": round(len(chosen) / len(part), 4),
                          "precision": round(sum(chosen) / len(chosen), 4) if chosen else None}
        res["by_lang_variant"] = dict(res["by_lang_variant"])
        report["splits"][split] = res
    report["note"] = ("v1 знает 6 меток; новые категории v2 ей недоступны. Транслит переводится в кириллицу "
                      "(ml/civic_dedup/normalize.to_cyrillic) только в цепочке r04_chain.")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ui.civic_ml_api.evaluate")
    ap.add_argument("--corpus", type=Path, default=CORPUS)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    if not args.corpus.exists():
        print(f"нет корпуса R02: {args.corpus}", file=sys.stderr)
        return 2
    report = evaluate(args.corpus)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for split, res in report["splits"].items():
        print(split, res["n"], res["accuracy"], "suggest", res["suggest"])
    print(f"отчёт: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
