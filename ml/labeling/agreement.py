"""Согласие двух разметчиков: Cohen's kappa и матрица несогласий (R02, раунд 14). Только stdlib.

Подходит для пар «человек–человек» (экспорт web/labeling/) и «человек–LLM» (ml/labeling/llm_label.py).
Тексты сопоставляются по id; учитываются только id, размеченные в обоих файлах.

    python -m ml.labeling.agreement private/labels_A.jsonl private/labels_B.jsonl
    python -m ml.labeling.agreement A.jsonl B.jsonl --exclude not_complaint --md private/agreement.md --json private/agreement.json

Что считается:
  - наблюдаемое согласие p_o, ожидаемое случайное p_e, kappa = (p_o − p_e) / (1 − p_e);
  - 95% интервал kappa — бутстрэп по текстам (по умолчанию 2000 повторов, фиксированное зерно);
  - по категориям: сколько раз выбрал каждый, согласие на категории (2·совпало / (nA + nB));
  - если A — эталон (например, владелец), то точность/полнота/F1 разметчика B и macro-F1;
  - матрица A × B и самые частые пары несогласия; список несогласий (тексты — только с --with-texts).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys
from pathlib import Path

from ml.labeling.text_utils import check_output_path

SKIP_LABELS = {"", "skip", "skipped", "invalid", "none", "null"}


def read_labels(path: Path, label_field: str = "label", id_field: str = "id") -> tuple[dict, dict, dict]:
    """Файл разметки → ({id: метка}, {id: текст}, {id: сомневался}). Повтор id — берётся последняя метка."""
    raw = path.read_text(encoding="utf-8-sig")
    rows: list[dict] = []
    if path.suffix.lower() in (".csv", ".tsv"):
        try:
            dialect = csv.Sniffer().sniff(raw[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.DictReader(io.StringIO(raw), dialect=dialect))
    else:
        for n, line in enumerate(raw.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"предупреждение: {path.name}:{n} — не JSON, строка пропущена", file=sys.stderr)
    labels, texts, unsure = {}, {}, {}
    for r in rows:
        rid = str(r.get(id_field) or "").strip()
        lab = str(r.get(label_field) or "").strip()
        if not rid or lab.lower() in SKIP_LABELS:
            continue
        labels[rid] = lab
        if r.get("text"):
            texts[rid] = str(r["text"])
        unsure[rid] = str(r.get("unsure", "")).lower() in ("true", "1", "yes")
    return labels, texts, unsure


def kappa_from_pairs(pairs: list[tuple[str, str]]) -> tuple[float | None, float, float]:
    """(kappa, p_o, p_e). kappa = None, если p_e = 1 (оба всегда ставят одну метку — kappa не определена)."""
    n = len(pairs)
    if not n:
        return None, 0.0, 0.0
    p_o = sum(a == b for a, b in pairs) / n
    ca, cb = {}, {}
    for a, b in pairs:
        ca[a] = ca.get(a, 0) + 1
        cb[b] = cb.get(b, 0) + 1
    p_e = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    if p_e >= 1.0:
        return None, p_o, p_e
    return (p_o - p_e) / (1 - p_e), p_o, p_e


def bootstrap_ci(pairs: list[tuple[str, str]], reps: int, seed: int) -> tuple[float | None, float | None]:
    if len(pairs) < 2 or reps <= 0:
        return None, None
    rng = random.Random(seed)
    n = len(pairs)
    vals = []
    for _ in range(reps):
        k, _, _ = kappa_from_pairs([pairs[rng.randrange(n)] for _ in range(n)])
        if k is not None:
            vals.append(k)
    if not vals:
        return None, None
    vals.sort()
    return vals[int(0.025 * (len(vals) - 1))], vals[int(0.975 * (len(vals) - 1))]


def interpret(k: float | None) -> str:
    """Шкала Landis & Koch (1977) — общепринятая, но условная."""
    if k is None:
        return "не определена"
    for bound, word in ((0.0, "хуже случайного"), (0.20, "слабое"), (0.40, "удовлетворительное"),
                        (0.60, "умеренное"), (0.80, "существенное")):
        if k <= bound:
            return word
    return "почти полное"


def compare(a: dict, b: dict, *, exclude: set[str] = frozenset(), drop_unsure: bool = False,
            unsure_a: dict | None = None, unsure_b: dict | None = None,
            bootstrap: int = 2000, seed: int = 14) -> dict:
    common = sorted(set(a) & set(b))
    dropped = {"excluded_label": 0, "unsure": 0}
    ids = []
    for i in common:
        if a[i] in exclude or b[i] in exclude:
            dropped["excluded_label"] += 1
            continue
        if drop_unsure and ((unsure_a or {}).get(i) or (unsure_b or {}).get(i)):
            dropped["unsure"] += 1
            continue
        ids.append(i)
    pairs = [(a[i], b[i]) for i in ids]
    k, p_o, p_e = kappa_from_pairs(pairs)
    lo, hi = bootstrap_ci(pairs, bootstrap, seed)
    labels = sorted({x for p in pairs for x in p})
    matrix = {la: {lb: 0 for lb in labels} for la in labels}
    for x, y in pairs:
        matrix[x][y] += 1
    per = {}
    f1s = []
    for lab in labels:
        na = sum(1 for x, _ in pairs if x == lab)
        nb = sum(1 for _, y in pairs if y == lab)
        both = matrix[lab][lab]
        prec = both / nb if nb else None
        rec = both / na if na else None
        f1 = 2 * both / (na + nb) if na + nb else None  # совпадает с «согласием на категории»
        per[lab] = {"n_a": na, "n_b": nb, "agree": both, "specific_agreement": f1,
                    "b_precision_vs_a": prec, "b_recall_vs_a": rec}
        if na:
            f1s.append(f1 or 0.0)
    confusions: dict[str, int] = {}
    for x, y in pairs:
        if x != y:
            key = " ↔ ".join(sorted((x, y)))
            confusions[key] = confusions.get(key, 0) + 1
    return {
        "n_a": len(a), "n_b": len(b), "common": len(common), "only_a": len(set(a) - set(b)),
        "only_b": len(set(b) - set(a)), "dropped": dropped, "n": len(pairs),
        "p_o": p_o, "p_e": p_e, "kappa": k, "kappa_ci95": [lo, hi], "bootstrap": bootstrap, "seed": seed,
        "interpretation": interpret(k), "macro_f1_b_vs_a": sum(f1s) / len(f1s) if f1s else None,
        "labels": labels, "matrix": matrix, "per_label": per,
        "top_confusions": sorted(confusions.items(), key=lambda kv: (-kv[1], kv[0]))[:15],
        "disagreements": [{"id": i, "a": a[i], "b": b[i]} for i in ids if a[i] != b[i]],
    }


def fmt(x, digits=3):
    return "—" if x is None else f"{x:.{digits}f}"


def to_markdown(res: dict, name_a: str, name_b: str, texts: dict | None) -> str:
    lines = [f"# Согласие разметчиков: {name_a} × {name_b}", "",
             f"- Общих текстов: **{res['n']}** (в A {res['n_a']}, в B {res['n_b']}, только в A {res['only_a']}, "
             f"только в B {res['only_b']}; исключено по метке {res['dropped']['excluded_label']}, "
             f"по «сомневаюсь» {res['dropped']['unsure']})",
             f"- Наблюдаемое согласие p_o = **{fmt(res['p_o'])}**, ожидаемое случайное p_e = {fmt(res['p_e'])}",
             f"- **Cohen's kappa = {fmt(res['kappa'])}** (95% бутстрэп: {fmt(res['kappa_ci95'][0])}–"
             f"{fmt(res['kappa_ci95'][1])}, {res['bootstrap']} повторов, зерно {res['seed']}) — "
             f"{res['interpretation']} (Landis & Koch)",
             f"- Если A — эталон: macro-F1 разметчика B = {fmt(res['macro_f1_b_vs_a'])}", "",
             "## По категориям", "", "| метка | A | B | совпало | согласие | точность B | полнота B |", "|---|---|---|---|---|---|---|"]
    for lab, p in res["per_label"].items():
        lines.append(f"| {lab} | {p['n_a']} | {p['n_b']} | {p['agree']} | {fmt(p['specific_agreement'], 2)} | "
                     f"{fmt(p['b_precision_vs_a'], 2)} | {fmt(p['b_recall_vs_a'], 2)} |")
    labs = res["labels"]
    lines += ["", "## Матрица (строки — A, столбцы — B)", "", "| A \\ B | " + " | ".join(labs) + " |",
              "|---" * (len(labs) + 1) + "|"]
    for la in labs:
        lines.append(f"| **{la}** | " + " | ".join(
            (f"**{res['matrix'][la][lb]}**" if la == lb else (str(res['matrix'][la][lb]) if res['matrix'][la][lb] else "·"))
            for lb in labs) + " |")
    lines += ["", "## Частые несогласия", ""]
    lines += [f"- {k}: {v}" for k, v in res["top_confusions"]] or ["- нет"]
    lines += ["", f"## Все несогласия ({len(res['disagreements'])})", ""]
    for d in res["disagreements"]:
        t = f" — {texts.get(d['id'], '')}" if texts else ""
        lines.append(f"- `{d['id']}`: A={d['a']}, B={d['b']}{t}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Cohen's kappa и матрица несогласий для двух файлов разметки")
    ap.add_argument("a", type=Path, help="разметка A (JSONL экспорт web/labeling, вывод llm_label.py или CSV id,label)")
    ap.add_argument("b", type=Path, help="разметка B")
    ap.add_argument("--label-field", default="label")
    ap.add_argument("--exclude", action="append", default=[], help="метка, которую не учитывать (можно несколько раз)")
    ap.add_argument("--drop-unsure", action="store_true", help="не учитывать тексты с пометкой «сомневаюсь»")
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=14)
    ap.add_argument("--json", type=Path, help="записать полный результат JSON")
    ap.add_argument("--md", type=Path, help="записать отчёт Markdown")
    ap.add_argument("--with-texts", action="store_true", help="тексты в списке несогласий (только в private/)")
    ap.add_argument("--allow-outside-private", action="store_true")
    args = ap.parse_args(argv)

    a, ta, ua = read_labels(args.a, args.label_field)
    b, tb, ub = read_labels(args.b, args.label_field)
    if not a or not b:
        print("В одном из файлов нет ни одной метки.", file=sys.stderr)
        return 1
    res = compare(a, b, exclude=set(args.exclude), drop_unsure=args.drop_unsure, unsure_a=ua, unsure_b=ub,
                  bootstrap=args.bootstrap, seed=args.seed)
    res["files"] = [args.a.name, args.b.name]
    texts = {**tb, **ta} if args.with_texts else None
    if args.json:
        if texts:
            check_output_path(args.json, args.allow_outside_private)
            for d in res["disagreements"]:
                d["text"] = texts.get(d["id"], "")
        args.json.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if args.md:
        if texts:
            check_output_path(args.md, args.allow_outside_private)
        args.md.write_text(to_markdown(res, args.a.name, args.b.name, texts), encoding="utf-8")
    print(f"общих текстов: {res['n']} (A {res['n_a']}, B {res['n_b']}; только A {res['only_a']}, только B {res['only_b']})")
    print(f"p_o = {fmt(res['p_o'])}, p_e = {fmt(res['p_e'])}")
    print(f"Cohen's kappa = {fmt(res['kappa'])}  95% ДИ [{fmt(res['kappa_ci95'][0])}; {fmt(res['kappa_ci95'][1])}]"
          f"  — {res['interpretation']}")
    print(f"macro-F1 B относительно A = {fmt(res['macro_f1_b_vs_a'])}")
    if res["top_confusions"]:
        print("частые несогласия: " + "; ".join(f"{k} ×{v}" for k, v in res["top_confusions"][:5]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
