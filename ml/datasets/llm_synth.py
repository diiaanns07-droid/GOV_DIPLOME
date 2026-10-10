"""LLM-синтетика llm_v1: обращения жителей по 12 категориям через OpenAI-совместимый API (R02, раунд 14).

Отдельный корпус — НЕ смешивается с шаблонным synth_v3: для диплома нужно сравнение
«модель на шаблонной синтетике» против «модель на LLM-синтетике» на одних и тех же текстах людей.

Запускается ЛОКАЛЬНО у владельца (в облачной сессии нет доступа к API). Ключ — только переменная окружения:
    $env:OPENAI_API_KEY="…"      (PowerShell)        или    $env:NVIDIA_API_KEY="…"
    python -m ml.datasets.llm_synth --provider openai --model gpt-4o-mini --n-total 4000 --max-usd 3 --dry-run
    python -m ml.datasets.llm_synth --provider openai --model gpt-4o-mini --n-total 4000 --max-usd 3
    python -m ml.datasets.llm_synth --provider nvidia --model meta/llama-3.3-70b-instruct \
        --price-in 0.5 --price-out 0.5 --n-total 4000 --max-usd 5
    python -m ml.datasets.llm_synth --mock --n-total 120          # проверка без сети и без ключа

Сетка запросов: категория × стиль × язык (ru / kk / mixed); в одном запросе --per-request сообщений (JSON).
Определения категорий берутся из ml/datasets/LABELING_GUIDE_v2.md. После ответа: обезличивание
(ml/labeling/anonymize.py), фильтр длины, удаление точных и почти-повторов, удаление совпадений с synth_v3,
split по запросам (train/val/test ≈ 70/15/15). Повторный запуск с теми же параметрами берёт ответы из кэша.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
import time
from pathlib import Path

from ml.datasets.synth_v3.build import grams
from ml.labeling import guide
from ml.labeling.anonymize import anonymize
from ml.labeling.llm_client import BudgetExceeded, LLMError, extract_json, make_client
from ml.labeling.text_utils import PRIVATE, ensure_private_dir, normalize

PROMPT_VERSION = "llm_synth_v1"
ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent / "llm_v1"
SYNTH_V3 = Path(__file__).resolve().parent / "synth_v3" / "data" / "corpus_v3.jsonl"
NEAR_DUP = 0.85

STYLES = {
    "colloquial": "разговорный, как пишут в мессенджере или чате района",
    "official": "официальный: вежливое письменное обращение в акимат",
    "short": "очень коротко: 2–6 слов, как заголовок",
    "long": "длинно: 3–5 предложений с подробностями (как давно, кто страдает, куда уже обращались)",
    "typos": "с опечатками, без заглавных букв и с пропущенными запятыми, как быстро набирают на телефоне",
    "slang": "эмоционально, с разговорными и сленговыми словами (без мата и оскорблений)",
    "translit": "латиницей (транслитом), как пишут, когда нет кириллической раскладки",
    "question": "в форме вопроса к акимату, но с описанием проблемы («когда уберут…?», «почему до сих пор…?»)",
    "thanks": "благодарность за сделанную работу (без жалобы)",
}
STYLE_WEIGHTS = {"colloquial": 25, "official": 15, "short": 10, "long": 12, "typos": 12, "slang": 8, "translit": 6,
                 "question": 7}
# Для «Другое» — свои стили: вопросы без проблемы, благодарности, просьбы не о городской среде.
OTHER_STYLE_WEIGHTS = {"thanks": 30, "question": 30, "official": 20, "colloquial": 20}
OTHER_QUESTION = "вопрос о сроках, порядке или услугах БЕЗ описания городской проблемы"
LANGS = {"ru": "на русском языке",
         "kk": "на казахском языке: живой грамотный казахский, как пишут жители Астаны, без дословного перевода с русского",
         "mixed": "вперемешку на казахском и русском в одном сообщении, как часто пишут в Астане"}
LANG_WEIGHTS = {"ru": 45, "kk": 35, "mixed": 20}

SYSTEM = ("Ты помогаешь собрать СИНТЕТИЧЕСКИЙ набор обращений жителей Астаны (Казахстан) в акимат для обучения "
          "классификатора. Пиши так, как пишут реальные люди: разная длина, разные слова и начала фраз, без "
          "повторов одной схемы. Не используй имена людей, телефоны, e-mail, ИИН, номера квартир и госномера машин. "
          "Можно упоминать улицы и районы Астаны, остановки, школы по номеру, ЖК. Ответ — только JSON.")


def weighted(rng: random.Random, weights: dict) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys])[0]


def plan_requests(n_total: int, per_request: int, seed: int, categories: list[str] | None = None) -> list[dict]:
    """Детерминированный план: категории по кругу, стиль и язык — по весам."""
    cats = categories or [c["id"] for c in guide.categories()]
    rng = random.Random(seed)
    n_req = math.ceil(n_total / per_request)
    plan = []
    for i in range(n_req):
        cat = cats[i % len(cats)]
        style = weighted(rng, OTHER_STYLE_WEIGHTS if cat == "other" else STYLE_WEIGHTS)
        lang = weighted(rng, LANG_WEIGHTS)
        if style == "translit" and lang == "mixed":
            lang = rng.choice(("ru", "kk"))
        plan.append({"request_id": f"r{i:04d}-{cat}-{style}-{lang}", "category": cat, "style": style, "lang": lang,
                     "k": per_request, "seed": seed + i})
    return plan


def build_messages(req: dict, defs: dict[str, str], names: dict[str, str]) -> list[dict]:
    style = OTHER_QUESTION if req["category"] == "other" and req["style"] == "question" else STYLES[req["style"]]
    user = (f"Категория: «{names[req['category']]}» (id: {req['category']}).\n"
            f"Что относится и что НЕ относится: {defs[req['category']]}\n"
            f"Стиль: {style}.\nЯзык: {LANGS[req['lang']]}.\n"
            f"Напиши {req['k']} разных сообщений этой категории. Каждое — одно обращение одного жителя. "
            "Меняй конкретную проблему внутри категории, место, длину и начало фразы. "
            'Ответ строго JSON без пояснений: {"messages": ["…", "…"]}')
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def parse_messages(text: str) -> list[str]:
    data = extract_json(text)
    if isinstance(data, dict):
        data = data.get("messages") or next((v for v in data.values() if isinstance(v, list)), [])
    if not isinstance(data, list):
        raise ValueError("нет списка messages")
    return [str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in data]


def clean_message(text: str) -> tuple[str, dict] | None:
    t = re.sub(r"\s+", " ", text).strip().strip('"«»').strip()
    t = re.sub(r"^\d+[.)]\s*", "", t)  # «1. …» — нумерация из ответа модели
    if sum(ch.isalpha() for ch in t) < 3 or len(t) > 800:
        return None
    return anonymize(t)


def assign_splits(plan: list[dict], seed: int) -> dict[str, str]:
    """Split по запросам внутри категории: 70/15/15 по порядку sha256(seed:request_id)."""
    pattern = ("train", "train", "val", "train", "test", "train", "train", "train", "val", "train", "test", "train",
               "train", "train", "val", "train", "train", "test", "train", "train")
    out, by_cat = {}, {}
    for r in plan:
        by_cat.setdefault(r["category"], []).append(r["request_id"])
    for cat in sorted(by_cat):
        ordered = sorted(by_cat[cat], key=lambda i: hashlib.sha256(f"{seed}:{i}".encode()).hexdigest())
        for k, rid in enumerate(ordered):
            out[rid] = pattern[k % len(pattern)]
    return out


def drop_near_duplicates(rows: list[dict], stats: dict) -> list[dict]:
    """Инкрементальный инвертированный индекс по 3-граммам: O(n · соседи), а не O(n²) пересборок."""
    index: dict[str, list[int]] = {}
    kept, kept_g = [], []
    for r in rows:
        g = grams(r["text"])
        overlap: dict[int, int] = {}
        for gram in g:
            for j in index.get(gram, ()):
                overlap[j] = overlap.get(j, 0) + 1
        if any(inter / (len(g) + len(kept_g[j]) - inter) >= NEAR_DUP for j, inter in overlap.items()):
            stats["near_duplicates"] += 1
            continue
        for gram in g:
            index.setdefault(gram, []).append(len(kept))
        kept.append(r)
        kept_g.append(g)
    return kept


def mock_transport(url: str, headers: dict, body: bytes, timeout: float) -> tuple:
    """Подставной «LLM» для проверки без сети: детерминированные разные строки нужной категории."""
    payload = json.loads(body.decode("utf-8"))
    user = payload["messages"][-1]["content"]
    cat = re.search(r"\(id: (\w+)\)", user).group(1)
    k = int(re.search(r"Напиши (\d+)", user).group(1))
    seed = payload.get("seed", 0)
    rng = random.Random(f"{cat}:{seed}")
    words = ["двор", "улица", "остановка", "аула", "көше", "неделю", "давно", "срочно", "опять", "тағы", "жоқ", "плохо"]
    msgs = [f"[mock] {cat} {i}: " + " ".join(rng.sample(words, 4)) for i in range(k)]
    content = json.dumps({"messages": msgs}, ensure_ascii=False)
    resp = {"choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": len(json.dumps(payload)) // 3, "completion_tokens": len(content) // 3}}
    return 200, {}, json.dumps(resp).encode("utf-8")


def run(args, transport=None) -> dict:
    plan = plan_requests(args.n_total, args.per_request, args.seed, args.categories)
    defs = guide.category_definitions()
    names = {c["id"]: c["ru"] for c in guide.categories()}
    client = make_client(args.provider, args.model, args.base_url, args.max_usd, args.price_in, args.price_out,
                         args.cache, args.cache / "requests.log.jsonl" if args.cache else None, transport)
    if args.dry_run:
        est = sum(client.budget.estimate(sum(len(m["content"]) for m in build_messages(r, defs, names)), args.max_tokens)
                  for r in plan)
        info = {"requests": len(plan), "messages_requested": len(plan) * args.per_request,
                "upper_bound_usd": round(est, 4), "max_usd": args.max_usd if math.isfinite(args.max_usd) else None,
                "model": args.model,
                "price_in_per_1m": client.budget.price_in, "price_out_per_1m": client.budget.price_out}
        print(json.dumps(info, ensure_ascii=False, indent=1))
        return info
    splits = assign_splits(plan, args.seed)
    v3_norms = set()
    if SYNTH_V3.exists():
        v3_norms = {normalize(json.loads(line)["text"]) for line in SYNTH_V3.read_text(encoding="utf-8").splitlines()}
    rows, seen = [], set()
    stats = {"requests_ok": 0, "requests_failed": 0, "parse_failed": 0, "raw_messages": 0, "filtered_length": 0,
             "duplicates": 0, "same_as_synth_v3": 0, "near_duplicates": 0, "stopped_by_budget": False}
    pii: dict[str, int] = {}
    for req in plan:
        try:
            resp = client.chat(build_messages(req, defs, names), temperature=args.temperature,
                               max_tokens=args.max_tokens, seed=req["seed"], json_mode=args.json_mode)
        except BudgetExceeded as e:
            print(f"остановка: {e}", file=sys.stderr)
            stats["stopped_by_budget"] = True
            break
        except LLMError as e:
            print(f"{req['request_id']}: {e}", file=sys.stderr)
            stats["requests_failed"] += 1
            continue
        try:
            msgs = parse_messages(resp["text"])
        except ValueError:
            stats["parse_failed"] += 1
            continue
        stats["requests_ok"] += 1
        for j, m in enumerate(msgs):
            stats["raw_messages"] += 1
            cleaned = clean_message(m)
            if not cleaned:
                stats["filtered_length"] += 1
                continue
            text, counts = cleaned
            key = normalize(text)
            if key in seen:
                stats["duplicates"] += 1
                continue
            if key in v3_norms:
                stats["same_as_synth_v3"] += 1
                continue
            seen.add(key)
            for c, n in counts.items():
                pii[c] = pii.get(c, 0) + n
            rows.append({"id": f"llm-{hashlib.sha1(key.encode()).hexdigest()[:10]}", "text": text,
                         "label": req["category"], "lang": req["lang"], "style": req["style"],
                         "split": splits[req["request_id"]], "request_id": req["request_id"], "n_in_request": j,
                         "anonymized": counts, "label_source": "llm_prompted", "evidence": "synthetic_llm",
                         "corpus": "llm_v1", "model": args.model, "provider": args.provider,
                         "prompt_version": PROMPT_VERSION})
    # почти-повторы внутри корпуса: позднее сообщение удаляется, если похоже на любое раннее (Jaccard 3-грамм)
    kept = drop_near_duplicates(rows, stats)
    args.out.mkdir(parents=True, exist_ok=True)
    corpus = args.out / "corpus_llm_v1.jsonl"
    with open(corpus, "w", encoding="utf-8", newline="\n") as fh:
        for r in kept:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    def count(field):
        c: dict[str, int] = {}
        for r in kept:
            c[r[field]] = c.get(r[field], 0) + 1
        return dict(sorted(c.items()))

    manifest = {
        "corpus": corpus.name, "corpus_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest(), "rows": len(kept),
        "evidence_type": "synthetic_llm", "labels_by": "запрошенная категория (label_source=llm_prompted), не проверено человеком",
        "provider": args.provider, "model": args.model, "base_url": client.base_url, "prompt_version": PROMPT_VERSION,
        "guide_sha256": guide.guide_sha256(), "seed": args.seed, "temperature": args.temperature,
        "per_request": args.per_request, "n_total_requested": args.n_total, "requests_planned": len(plan),
        "near_dup_threshold": NEAR_DUP, "stats": stats, "client": client.stats, "budget": client.budget.summary(),
        "anonymized_markers": dict(sorted(pii.items())), "by_split": count("split"), "by_label": count("label"),
        "by_lang": count("lang"), "by_style": count("style"), "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mock": transport is not None,
    }
    (args.out / "manifest_llm_v1.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                                                   encoding="utf-8")
    print(f"llm_v1: {len(kept)} сообщений → {corpus}")
    print(f"запросов ок {stats['requests_ok']}, ошибок {stats['requests_failed']}, не JSON {stats['parse_failed']}; "
          f"повторы {stats['duplicates']}, почти-повторы {stats['near_duplicates']}, совпали с v3 {stats['same_as_synth_v3']}")
    print(f"потрачено {client.budget.spent:.4f} $ из {args.max_usd} $; из кэша {client.stats['cache_hits']}")
    return manifest


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="LLM-синтетика llm_v1 (OpenAI-совместимый API)")
    ap.add_argument("--provider", choices=("openai", "nvidia"), default="openai")
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--base-url", help="по умолчанию — адрес провайдера")
    ap.add_argument("--n-total", type=int, default=4000, help="сколько сообщений запросить (до чистки)")
    ap.add_argument("--per-request", type=int, default=20)
    ap.add_argument("--max-usd", type=float, required=False, default=None, help="предел расходов, обязателен для реального запуска")
    ap.add_argument("--price-in", type=float, help="USD за 1 млн входных токенов (если модели нет в таблице)")
    ap.add_argument("--price-out", type=float, help="USD за 1 млн выходных токенов")
    ap.add_argument("--temperature", type=float, default=0.9)
    ap.add_argument("--max-tokens", type=int, default=2500)
    ap.add_argument("--seed", type=int, default=14)
    ap.add_argument("--categories", nargs="*", help="только эти категории")
    ap.add_argument("--json-mode", action="store_true", help="response_format=json_object (OpenAI; не все модели NVIDIA)")
    ap.add_argument("--out", type=Path, help=f"по умолчанию ml/datasets/llm_v1/ (с --mock — private/llm_mock/)")
    ap.add_argument("--cache", type=Path, default=PRIVATE / "llm_cache" / "synth")
    ap.add_argument("--dry-run", action="store_true", help="только план и верхняя оценка стоимости, без запросов")
    ap.add_argument("--mock", action="store_true", help="подставной клиент без сети (проверка конвейера)")
    args = ap.parse_args(argv)
    if args.mock:
        args.max_usd = 1.0 if args.max_usd is None else args.max_usd
        args.price_in = args.price_in if args.price_in is not None else 0.15
        args.price_out = args.price_out if args.price_out is not None else 0.60
    elif args.max_usd is None and not args.dry_run:
        ap.error("укажите --max-usd (предел расходов в долларах), например --max-usd 3")
    if args.max_usd is None:
        args.max_usd = float("inf")
    if args.out is None:
        # подставные ответы никогда не попадают в настоящую папку корпуса
        args.out = PRIVATE / "llm_mock" if args.mock else OUT_DIR
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    if str(args.cache).startswith(str(PRIVATE)) or str(args.out).startswith(str(PRIVATE)):
        ensure_private_dir()
    run(args, transport=mock_transport if args.mock else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
