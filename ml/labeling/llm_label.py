"""LLM-разметчик: размечает тот же набор, что и владелец, строго одной меткой из 12 (R02, раунд 14).

Результат — JSONL в формате экспорта web/labeling (birge-labels-v1, role="llm"), его сразу читает
    python -m ml.labeling.agreement private/labels_owner.jsonl private/labels_llm_gpt-4o-mini.jsonl
— это согласие «человек–LLM» для диплома.

Правила для модели берутся из ml/datasets/LABELING_GUIDE_v2.md (главные правила, определения категорий,
таблица спорных случаев) — те же, по которым размечает владелец. Метки владельца модели НЕ показываются.

Запуск ЛОКАЛЬНО у владельца (ключ — только переменная окружения):
    $env:OPENAI_API_KEY="…"
    python -m ml.labeling.llm_label private/labels_owner.jsonl --provider openai --model gpt-4o-mini --max-usd 1 --confirm-external
    python -m ml.labeling.llm_label private/form_2026-10-13.jsonl --provider nvidia --model meta/llama-3.3-70b-instruct \
        --price-in 0.5 --price-out 0.5 --max-usd 1 --confirm-external
    python -m ml.labeling.llm_label tests/civic/R02/round14/fixtures/texts_sample.jsonl --mock --out private/llm_mock_labels.jsonl

Тексты жителей уходят во внешний API. Поэтому: каждый текст ещё раз обезличивается перед отправкой; для
файлов, не помеченных как синтетика, нужен явный флаг --confirm-external; в выходной файл текст не пишется.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

from ml.labeling import guide
from ml.labeling.anonymize import anonymize
from ml.labeling.llm_client import BudgetExceeded, LLMError, make_client
from ml.labeling.text_utils import PRIVATE, check_output_path

PROMPT_VERSION = "llm_label_v1"
NOT_COMPLAINT = "not_complaint"
SYNTHETIC_EVIDENCE = {"synthetic", "synthetic_llm"}


def system_prompt(labels: list[str], allow_not_complaint: bool) -> str:
    defs = guide.category_definitions()
    names = {c["id"]: c["ru"] for c in guide.categories()}
    # Модели нужны правила 1–4 (что считается чем). Правила 5–7 — про кнопки инструмента для человека.
    rules = re.split(r"(?m)^5\.", guide.main_rules())[0]
    rules = re.sub(r"\s*Отметьте «Сомневаюсь»[^.]*\.", "", rules).strip()
    lines = ["Ты размечаешь обращения жителей Астаны в акимат по 12 категориям. Тексты на русском, казахском или "
             "вперемешку, иногда латиницей и с опечатками.", "", "Главные правила:", rules, "",
             "Категории (id — название: что относится и что нет):"]
    for lab in labels:
        if lab in defs:
            lines.append(f"- {lab} — {names.get(lab, lab)}: {defs[lab]}")
    if allow_not_complaint:
        lines.append(f"- {NOT_COMPLAINT} — не обращение: реклама, спам, «тест», бессмыслица, текст не о городе.")
    lines += ["", "Спорные случаи (текст → метка):"]
    lines += [f"- {t} → {lab}" for t, lab in guide.dispute_table() if lab in labels or allow_not_complaint]
    if not allow_not_complaint:
        lines.append("- Реклама, тест, бессмыслица, текст не о городе → other")
    allowed = labels + ([NOT_COMPLAINT] if allow_not_complaint else [])
    lines += ["", "Ответь ровно одним id из списка, без кавычек и пояснений: " + ", ".join(allowed) + "."]
    return "\n".join(lines)


def parse_label(raw: str, allowed: list[str]) -> str | None:
    """Строго одна метка. «roads» / «Ответ: roads.» / «`roads`» → roads; две разные метки или ни одной → None."""
    low = raw.strip().lower()
    token = re.sub(r"[^a-z_]", "", low)
    if token in allowed:
        return token
    found = {lab for lab in allowed if re.search(rf"(?<![a-z_]){re.escape(lab)}(?![a-z_])", low)}
    return found.pop() if len(found) == 1 else None


def read_items(path: Path) -> list[dict]:
    items, seen = [], set()
    for n, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            print(f"предупреждение: строка {n} — не JSON, пропущена", file=sys.stderr)
            continue
        rid, text = str(r.get("id") or "").strip(), str(r.get("text") or "").strip()
        if not rid or not text or rid in seen:
            continue
        seen.add(rid)
        items.append({"id": rid, "text": text, "evidence": r.get("evidence", "")})
    return items


def mock_transport(url: str, headers: dict, body: bytes, timeout: float) -> tuple:
    """Подставной «LLM»: ключевые слова → метка (грубо, только чтобы проверить конвейер без сети)."""
    payload = json.loads(body.decode("utf-8"))
    text = payload["messages"][-1]["content"].lower()
    rules = (("snow_ice", "снег|лёд|гололёд|көктайғақ|қар"), ("roads", "яма|дорог|асфальт|жол|светофор"),
             ("sidewalks", "тротуар|плитк|пандус"), ("transport", "остановк|автобус|аялдам|павильон"),
             ("lighting", "фонар|шам|свет|темно|қараңғы"), ("yards", "площадк|алаң|дерев|сквер"),
             ("waste", "мусор|бак|қоқыс"), ("utilities", "вод|отоплен|жылу|лифт"), ("smell_air", "вон|дым|запах|тэц"),
             ("noise_safety", "шум|гоня|собак|опасн"), ("parking", "машин|газон|парков"))
    label = next((lab for lab, rx in rules if re.search(rx, text)), "other")
    resp = {"choices": [{"message": {"content": label}}], "usage": {"prompt_tokens": len(json.dumps(payload)) // 3,
                                                                     "completion_tokens": 2}}
    return 200, {}, json.dumps(resp).encode("utf-8")


def run(args, transport=None) -> dict:
    labels = [c["id"] for c in guide.categories()]
    allowed = labels + ([NOT_COMPLAINT] if args.allow_not_complaint else [])
    items = read_items(args.input)
    if args.limit:
        items = items[:args.limit]
    client = make_client(args.provider, args.model, args.base_url, args.max_usd, args.price_in, args.price_out,
                         args.cache, args.cache / "requests.log.jsonl" if args.cache else None, transport)
    system = system_prompt(labels, args.allow_not_complaint)
    prompt_sha = hashlib.sha256(system.encode("utf-8")).hexdigest()[:12]
    if args.dry_run:
        est = sum(client.budget.estimate(len(system) + len(i["text"]) + 40, args.max_tokens) for i in items)
        info = {"texts": len(items), "upper_bound_usd": round(est, 4), "model": args.model,
                "system_prompt_chars": len(system), "prompt_sha": prompt_sha}
        print(json.dumps(info, ensure_ascii=False, indent=1))
        return info
    # Пробный расчёт выше ничего не отправляет; дальше тексты уходят во внешний API.
    real = [i for i in items if i["evidence"] not in SYNTHETIC_EVIDENCE]
    if real and not args.confirm_external and transport is None:
        raise SystemExit(f"В файле {len(real)} текстов, не помеченных как синтетика: они уйдут во внешний API "
                         "(после повторного обезличивания). Если это допустимо по согласию участников — добавьте "
                         "--confirm-external.")
    check_output_path(args.out, args.allow_outside_private)
    out_rows, stats = [], {"ok": 0, "invalid": 0, "errors": 0, "retried_strict": 0, "stopped_by_budget": False,
                           "labels": {}}
    for it in items:
        text, _ = anonymize(it["text"])  # повторно: в API не уходит ничего, что обезличивание может убрать
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": f"Текст обращения:\n<<<\n{text}\n>>>"}]
        try:
            resp = client.chat(msgs, temperature=0.0, max_tokens=args.max_tokens, seed=args.seed)
            label = parse_label(resp["text"], allowed)
            if label is None:
                stats["retried_strict"] += 1
                msgs.append({"role": "assistant", "content": resp["text"][:200]})
                msgs.append({"role": "user", "content": "Ответь ТОЛЬКО одним id из списка: " + ", ".join(allowed)})
                resp = client.chat(msgs, temperature=0.0, max_tokens=args.max_tokens, seed=args.seed)
                label = parse_label(resp["text"], allowed)
        except BudgetExceeded as e:
            print(f"остановка: {e}", file=sys.stderr)
            stats["stopped_by_budget"] = True
            break
        except LLMError as e:
            print(f"{it['id']}: {e}", file=sys.stderr)
            stats["errors"] += 1
            continue
        if label is None:
            stats["invalid"] += 1
            label = "invalid"  # agreement.py такие строки пропускает
        else:
            stats["ok"] += 1
        stats["labels"][label] = stats["labels"].get(label, 0) + 1
        out_rows.append({"schema": "birge-labels-v1", "id": it["id"], "label": label, "unsure": False,
                         "annotator": f"llm:{args.model}", "role": "llm", "labeled_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                         "raw": resp["text"].strip()[:40], "model": args.model, "provider": args.provider,
                         "prompt_version": PROMPT_VERSION, "prompt_sha": prompt_sha, "source": args.input.name})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        for r in out_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    report = {"input": args.input.name, "output": args.out.name, "texts": len(items), "stats": stats,
              "client": client.stats, "budget": client.budget.summary(), "model": args.model, "provider": args.provider,
              "prompt_version": PROMPT_VERSION, "prompt_sha": prompt_sha, "guide_sha256": guide.guide_sha256(),
              "allow_not_complaint": args.allow_not_complaint, "mock": transport is not None}
    args.out.with_suffix(".report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                                    encoding="utf-8")
    print(f"размечено {stats['ok']} из {len(items)}; не по формату {stats['invalid']}, ошибок {stats['errors']}")
    print(f"потрачено {client.budget.spent:.4f} $ из {args.max_usd} $; из кэша {client.stats['cache_hits']}")
    print(f"дальше: python -m ml.labeling.agreement <разметка владельца> {args.out}")
    return report


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="LLM-разметчик (одна метка из 12) для согласия «человек–LLM»")
    ap.add_argument("input", type=Path, help="JSONL с id и text (экспорт web/labeling или private/form_*.jsonl)")
    ap.add_argument("--out", type=Path, help="по умолчанию private/labels_llm_<модель>.jsonl")
    ap.add_argument("--provider", choices=("openai", "nvidia"), default="openai")
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--base-url")
    ap.add_argument("--max-usd", type=float, help="предел расходов, обязателен для реального запуска")
    ap.add_argument("--price-in", type=float)
    ap.add_argument("--price-out", type=float)
    ap.add_argument("--max-tokens", type=int, default=12)
    ap.add_argument("--seed", type=int, default=14)
    ap.add_argument("--limit", type=int, help="только первые N текстов (проба)")
    ap.add_argument("--allow-not-complaint", action="store_true", help="разрешить 13-й ответ not_complaint")
    ap.add_argument("--confirm-external", action="store_true", help="я понимаю, что тексты уходят во внешний API")
    ap.add_argument("--cache", type=Path, default=PRIVATE / "llm_cache" / "label")
    ap.add_argument("--allow-outside-private", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--mock", action="store_true", help="подставной клиент без сети")
    args = ap.parse_args(argv)
    safe_model = re.sub(r"[^\w.-]+", "_", args.model)
    if args.out is None:
        args.out = PRIVATE / (f"labels_llm_mock_{safe_model}.jsonl" if args.mock else f"labels_llm_{safe_model}.jsonl")
    if args.mock:
        args.max_usd = 1.0 if args.max_usd is None else args.max_usd
        args.price_in = 0.15 if args.price_in is None else args.price_in
        args.price_out = 0.60 if args.price_out is None else args.price_out
    elif args.max_usd is None and not args.dry_run:
        ap.error("укажите --max-usd, например --max-usd 1")
    if args.max_usd is None:
        args.max_usd = 1e9
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    run(args, transport=mock_transport if args.mock else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
