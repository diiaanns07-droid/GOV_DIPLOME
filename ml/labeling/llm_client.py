"""Клиент OpenAI-совместимого чата для LLM-синтетики и LLM-разметчика (R02, раунд 14). Только stdlib.

Работает с OpenAI (https://api.openai.com/v1) и NVIDIA API (https://integrate.api.nvidia.com/v1) — у обоих
POST {base_url}/chat/completions с одинаковым форматом.

Безопасность и деньги:
  - ключ берётся ТОЛЬКО из переменной окружения (OPENAI_API_KEY / NVIDIA_API_KEY), никогда из файлов и аргументов;
    ключ не пишется ни в кэш, ни в журнал, ни в сообщения об ошибках;
  - бюджет: перед каждым запросом оценивается его наибольшая цена; если потрачено + оценка > --max-usd —
    запрос не отправляется (BudgetExceeded), уже полученные результаты сохраняются;
  - кэш ответов на диске: повторный запуск с теми же параметрами не платит второй раз;
  - повторы: 429/5xx/обрыв сети — до max_retries раз с паузой 2, 4, 8, 16… с (учитывается Retry-After);
    400/401/403/404 — сразу ошибка с понятным текстом (повтор не поможет).
Для проверки без сети передайте transport= (функция вместо HTTP) — так работают тесты и режим --mock.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

PROVIDERS = {
    "openai": {"base_url": "https://api.openai.com/v1", "key_env": "OPENAI_API_KEY"},
    "nvidia": {"base_url": "https://integrate.api.nvidia.com/v1", "key_env": "NVIDIA_API_KEY"},
}
# USD за 1 млн токенов (вход, выход). Цены меняются — ПРОВЕРЬТЕ на сайте провайдера перед запуском
# и при расхождении передайте --price-in/--price-out. Для моделей не из таблицы цены обязательны.
PRICES = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4o": (2.50, 10.00),
}
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
CHARS_PER_TOKEN = 2.5  # осторожная оценка для кириллицы: лучше переоценить цену, чем превысить бюджет

# transport(url, headers, body_bytes, timeout) -> (status, headers_dict, body_bytes)
Transport = Callable[[str, dict, bytes, float], tuple]


class BudgetExceeded(RuntimeError):
    pass


class LLMError(RuntimeError):
    pass


def http_transport(url: str, headers: dict, body: bytes, timeout: float) -> tuple:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() if e.fp else b""


@dataclass
class Budget:
    max_usd: float
    price_in: float   # USD за 1M входных токенов
    price_out: float  # USD за 1M выходных токенов
    spent: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    calls: int = 0

    def estimate(self, prompt_chars: int, max_tokens: int) -> float:
        return (prompt_chars / CHARS_PER_TOKEN * self.price_in + max_tokens * self.price_out) / 1e6

    def check(self, prompt_chars: int, max_tokens: int) -> None:
        est = self.estimate(prompt_chars, max_tokens)
        if self.spent + est > self.max_usd:
            raise BudgetExceeded(f"бюджет {self.max_usd:.2f} $: потрачено {self.spent:.4f} $, следующий запрос ≤ {est:.4f} $")

    def add(self, usage: dict) -> float:
        pin, pout = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        cost = (pin * self.price_in + pout * self.price_out) / 1e6
        self.spent += cost
        self.tokens_in += pin
        self.tokens_out += pout
        self.calls += 1
        return cost

    def summary(self) -> dict:
        return {"max_usd": self.max_usd, "spent_usd": round(self.spent, 6), "calls_paid": self.calls,
                "tokens_in": self.tokens_in, "tokens_out": self.tokens_out,
                "price_in_per_1m": self.price_in, "price_out_per_1m": self.price_out}


def resolve_prices(model: str, price_in: float | None, price_out: float | None) -> tuple[float, float]:
    if price_in is not None and price_out is not None:
        return price_in, price_out
    if model in PRICES:
        return PRICES[model]
    raise SystemExit(f"Нет цены для модели «{model}». Укажите --price-in и --price-out (USD за 1 млн токенов) "
                     "по прайсу провайдера — без цены бюджет --max-usd не может работать.")


@dataclass
class ChatClient:
    model: str
    base_url: str
    key_env: str
    budget: Budget
    cache_dir: Path | None = None
    timeout: float = 90.0
    max_retries: int = 5
    transport: Transport | None = None
    sleep: Callable[[float], None] = time.sleep
    log_path: Path | None = None
    stats: dict = field(default_factory=lambda: {"cache_hits": 0, "retries": 0, "errors": 0})

    def _key(self) -> str:
        key = os.environ.get(self.key_env, "").strip()
        if not key and self.transport is None:
            raise SystemExit(f"Нет ключа: задайте переменную окружения {self.key_env} в этом окне терминала "
                             f"(PowerShell: $env:{self.key_env}=\"…\"). В файлы репозитория ключ не кладите.")
        return key

    def _cache_file(self, payload: dict) -> Path | None:
        if not self.cache_dir:
            return None
        h = hashlib.sha256(json.dumps({"base_url": self.base_url, **payload}, ensure_ascii=False, sort_keys=True)
                           .encode("utf-8")).hexdigest()
        return self.cache_dir / h[:2] / f"{h}.json"

    def _log(self, rec: dict) -> None:
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def chat(self, messages: list[dict], *, temperature: float = 0.0, max_tokens: int = 512,
             seed: int | None = None, json_mode: bool = False) -> dict:
        """→ {"text", "usage", "cost", "cached"}. Бросает BudgetExceeded / LLMError."""
        payload = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if seed is not None:
            payload["seed"] = seed
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        cf = self._cache_file(payload)
        if cf and cf.exists():
            data = json.loads(cf.read_text(encoding="utf-8"))
            self.stats["cache_hits"] += 1
            return {"text": data["text"], "usage": data.get("usage", {}), "cost": 0.0, "cached": True}
        prompt_chars = sum(len(m.get("content", "")) for m in messages)
        self.budget.check(prompt_chars, max_tokens)
        transport = self.transport or http_transport
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self._key()}"}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = self.base_url.rstrip("/") + "/chat/completions"
        last = ""
        for attempt in range(self.max_retries + 1):
            try:
                status, rheaders, rbody = transport(url, headers, body, self.timeout)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                status, rheaders, rbody, last = None, {}, b"", f"сеть: {type(e).__name__}"
            if status == 200:
                try:
                    data = json.loads(rbody.decode("utf-8"))
                    text = data["choices"][0]["message"]["content"] or ""
                except (ValueError, KeyError, IndexError, TypeError):
                    last = "ответ не в формате chat/completions"
                    status = None
                else:
                    usage = data.get("usage") or {}
                    cost = self.budget.add(usage)
                    if cf:
                        cf.parent.mkdir(parents=True, exist_ok=True)
                        cf.write_text(json.dumps({"text": text, "usage": usage, "model": self.model},
                                                 ensure_ascii=False), encoding="utf-8")
                    self._log({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": self.model, "status": 200,
                               "usage": usage, "cost": round(cost, 6), "attempt": attempt})
                    return {"text": text, "usage": usage, "cost": cost, "cached": False}
            elif status is not None and status not in RETRY_STATUS:
                self.stats["errors"] += 1
                hint = {401: "ключ не принят — проверьте переменную окружения", 403: "нет доступа к модели",
                        404: "нет такой модели или неверный base_url", 400: "запрос отклонён (модель/параметры)"}
                raise LLMError(f"HTTP {status}: {hint.get(status, 'ошибка')}; {_short(rbody)}")
            elif status is not None:
                last = f"HTTP {status}"
            if attempt == self.max_retries:
                break
            self.stats["retries"] += 1
            wait = _retry_after(rheaders) or min(60.0, 2.0 * (2 ** attempt)) * (0.8 + 0.4 * random.random())
            self.sleep(wait)
        self.stats["errors"] += 1
        raise LLMError(f"не удалось после {self.max_retries + 1} попыток: {last}")


def _retry_after(headers: dict) -> float | None:
    for k, v in (headers or {}).items():
        if k.lower() == "retry-after":
            try:
                return min(120.0, float(v))
            except ValueError:
                return None
    return None


def _short(body: bytes) -> str:
    """Текст ошибки провайдера без лишнего (ключ в ответах не возвращается, но длину всё равно ограничим)."""
    try:
        msg = json.loads(body.decode("utf-8")).get("error", {})
        msg = msg.get("message", "") if isinstance(msg, dict) else str(msg)
    except (ValueError, AttributeError):
        msg = body.decode("utf-8", "replace")
    return msg[:200]


def make_client(provider: str, model: str, base_url: str | None, max_usd: float, price_in: float | None,
                price_out: float | None, cache_dir: Path | None, log_path: Path | None,
                transport: Transport | None = None) -> ChatClient:
    if provider not in PROVIDERS:
        raise SystemExit(f"Провайдер: {', '.join(PROVIDERS)}")
    pin, pout = resolve_prices(model, price_in, price_out)
    return ChatClient(model=model, base_url=base_url or PROVIDERS[provider]["base_url"],
                      key_env=PROVIDERS[provider]["key_env"], budget=Budget(max_usd, pin, pout),
                      cache_dir=cache_dir, transport=transport, log_path=log_path)


def extract_json(text: str):
    """Достаёт JSON из ответа модели: целиком, из ```json …```, или первый {…}/[…]."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[4:] if t.lower().startswith("json") else t
    try:
        return json.loads(t)
    except ValueError:
        pass
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        i, j = t.find(open_ch), t.rfind(close_ch)
        if 0 <= i < j:
            try:
                return json.loads(t[i:j + 1])
            except ValueError:
                continue
    raise ValueError("в ответе нет JSON")
