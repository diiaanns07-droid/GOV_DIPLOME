"""Базовая модель без обучения: LLM zero-shot через OpenAI-совместимый API. Запуск ТОЛЬКО локально.

Ключ — только из переменной окружения в окне терминала (никогда из файлов репозитория):
    $env:OPENAI_API_KEY="..."      (PowerShell)    или   $env:NVIDIA_API_KEY="..."
    python -m ml.civic_classifier_v2.zeroshot --human private/labels_owner.jsonl --model gpt-4o-mini --max-usd 1
    python -m ml.civic_classifier_v2.zeroshot --human private/labels_owner.jsonl \
        --base-url https://integrate.api.nvidia.com/v1 --api-key-env NVIDIA_API_KEY \
        --model meta/llama-3.1-70b-instruct --max-usd 1
--human принимает любые размеченные JSONL: тексты людей и/или probe_v2 (ml/datasets/probe_v2/probe_v2.jsonl,
текст агента — его можно отправлять и без людей). Метки в API не отправляются.
Выход: artifacts/zeroshot/<model>.jsonl — только {id, label, raw_ok} (без текстов), затем
    python -m ml.civic_classifier_v2.experiments ... --zeroshot-preds artifacts/zeroshot/<model>.jsonl

Кэш ответов (artifacts/zeroshot/cache.jsonl) — ключ sha256(модель, версия промпта, текст), значение — метка;
повторный запуск не тратит деньги. Ошибка сети/429/5xx -> повтор с паузой; бюджет --max-usd считается
по usage из ответа и ценам --price-in/--price-out ($ за 1 млн токенов) и останавливает запуск ДО превышения.
Модель видит только список категорий (из categories_v2.json), без примеров из набора людей.
Похожий инструмент R02 — ml/labeling/llm_label.py (LLM как второй разметчик); его выход в формате
{id, label} тоже подходит для --zeroshot-preds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from ml.civic_classifier_v2 import data as D
from ml.civic_classifier_v2 import labels as L
from ml.civic_classifier_v2.config import ARTIFACTS_DIR

PROMPT_VERSION = "zs-v1"


def system_prompt() -> str:
    lines = ["Ты классифицируешь обращения жителей Астаны в акимат (тексты на русском, казахском или смешанные).",
             "Выбери ровно одну категорию из списка. Ответь только её id латиницей, без пояснений.", "",
             "Категории (id — название — примеры):"]
    for c in L.categories():
        lines.append(f"{c['id']} — {c['ru']} / {c['kk']} — {c.get('examples_ru', '')}")
    lines += ["", "Правила: категорию определяет объект проблемы, а не место. Снег или лёд на тротуаре -> snow_ice. "
              "Яма во дворе -> roads. Не горит свет на остановке -> lighting. Благодарность, вопрос, "
              "не жалоба или ничего не подошло -> other."]
    return "\n".join(lines)


def parse_label(answer: str) -> str | None:
    """Первая категория v2, встретившаяся в ответе как отдельное слово."""
    labs = L.labels()
    for tok in re.findall(r"[a-z_]+", (answer or "").lower()):
        if tok in labs:
            return tok
    return None


class Budget:
    def __init__(self, max_usd: float, price_in: float, price_out: float):
        self.max_usd, self.price_in, self.price_out = max_usd, price_in, price_out
        self.spent = 0.0
        self.tokens_in = self.tokens_out = 0

    def add(self, usage: dict) -> None:
        ti, to = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        self.tokens_in += ti
        self.tokens_out += to
        self.spent += ti / 1e6 * self.price_in + to / 1e6 * self.price_out

    def would_exceed(self, est_in: int, est_out: int = 8) -> bool:
        return self.spent + est_in / 1e6 * self.price_in + est_out / 1e6 * self.price_out > self.max_usd


def http_client(base_url: str, api_key: str, timeout: float = 60.0):
    """Минимальный клиент /chat/completions на urllib (без пакета openai)."""
    url = base_url.rstrip("/") + "/chat/completions"

    def call(payload: dict) -> dict:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST", headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    return call


def classify_all(records: list[dict], call, model: str, cache_path: Path, budget: Budget,
                 max_requests: int, retries: int = 4, sleep: float = 0.0) -> tuple[list[dict], dict]:
    cache: dict[str, str] = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                cache[row["key"]] = row["answer"]
            except (json.JSONDecodeError, KeyError):
                continue
    sysmsg = system_prompt()
    est_in = len(sysmsg) // 2 + 60
    out, stats = [], {"cached": 0, "requested": 0, "unparsed": 0, "failed": 0, "stopped_by_budget": False}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "a", encoding="utf-8") as cfh:
        for r in records:
            key = hashlib.sha256(f"{model}\n{PROMPT_VERSION}\n{r['text']}".encode("utf-8")).hexdigest()
            answer = cache.get(key)
            if answer is None:
                if stats["requested"] >= max_requests or budget.would_exceed(est_in + len(r["text"]) // 2):
                    stats["stopped_by_budget"] = True
                    break
                payload = {"model": model, "temperature": 0, "max_tokens": 8,
                           "messages": [{"role": "system", "content": sysmsg},
                                        {"role": "user", "content": r["text"]}]}
                for attempt in range(retries + 1):
                    try:
                        resp = call(payload)
                        answer = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
                        budget.add(resp.get("usage") or {})
                        break
                    except urllib.error.HTTPError as exc:
                        if exc.code in (429, 500, 502, 503, 504) and attempt < retries:
                            time.sleep(2 ** (attempt + 1))
                            continue
                        raise
                    except (urllib.error.URLError, TimeoutError):
                        if attempt < retries:
                            time.sleep(2 ** (attempt + 1))
                            continue
                        answer = None
                stats["requested"] += 1
                if answer is None:
                    stats["failed"] += 1
                    continue
                cache[key] = answer
                cfh.write(json.dumps({"key": key, "answer": answer}, ensure_ascii=False) + "\n")
                cfh.flush()
                if sleep:
                    time.sleep(sleep)
            else:
                stats["cached"] += 1
            lab = parse_label(answer)
            if lab is None:
                stats["unparsed"] += 1
            out.append({"id": r["id"], "label": lab or L.OTHER, "raw_ok": lab is not None})
    stats.update({"usd_spent_estimate": round(budget.spent, 4), "tokens_in": budget.tokens_in,
                  "tokens_out": budget.tokens_out, "n_out": len(out), "n_in": len(records)})
    return out, stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_classifier_v2.zeroshot", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--human", nargs="+", required=True, help="JSONL разметки людей (метки не отправляются)")
    ap.add_argument("--model", required=True)
    ap.add_argument("--base-url", default="https://api.openai.com/v1")
    ap.add_argument("--api-key-env", default="OPENAI_API_KEY")
    ap.add_argument("--max-usd", type=float, default=1.0)
    ap.add_argument("--price-in", type=float, default=0.15, help="$ за 1 млн входных токенов (gpt-4o-mini: 0.15)")
    ap.add_argument("--price-out", type=float, default=0.60, help="$ за 1 млн выходных токенов (gpt-4o-mini: 0.60)")
    ap.add_argument("--max-requests", type=int, default=2000)
    ap.add_argument("--sleep", type=float, default=0.0, help="пауза между запросами, с")
    ap.add_argument("--out-dir", default=str(ARTIFACTS_DIR / "zeroshot"))
    args = ap.parse_args(argv)

    key = os.environ.get(args.api_key_env, "").strip()
    if not key:
        print(f"нет ключа в переменной окружения {args.api_key_env} — задайте её в окне терминала", file=sys.stderr)
        return 2
    recs, _ = D.load_human([Path(p) for p in args.human])
    out_dir = Path(args.out_dir)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", args.model)
    preds, stats = classify_all(recs, http_client(args.base_url, key), args.model, out_dir / "cache.jsonl",
                                Budget(args.max_usd, args.price_in, args.price_out), args.max_requests,
                                sleep=args.sleep)
    out_path = out_dir / f"{safe}.jsonl"
    out_path.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in preds), encoding="utf-8")
    stats.update({"model": args.model, "base_url": args.base_url, "prompt_version": PROMPT_VERSION,
                  "out": str(out_path)})
    (out_dir / f"{safe}.report.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1) + "\n",
                                                 encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    return 0 if not stats["stopped_by_budget"] else 3


if __name__ == "__main__":
    sys.exit(main())
