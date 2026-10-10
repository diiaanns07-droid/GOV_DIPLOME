"""R02 · раунд 14 · LLM-клиент, LLM-синтетика и LLM-разметчик на подставном транспорте (без сети, без ключа)."""

import json
from argparse import Namespace
from pathlib import Path

import pytest

from ml.datasets import llm_synth
from ml.labeling import llm_label
from ml.labeling.llm_client import Budget, BudgetExceeded, ChatClient, LLMError, extract_json, resolve_prices

FIX = Path(__file__).resolve().parent / "fixtures"


def ok(content, pin=100, pout=10):
    return 200, {}, json.dumps({"choices": [{"message": {"content": content}}],
                                "usage": {"prompt_tokens": pin, "completion_tokens": pout}}).encode()


class Script:
    """Транспорт, который отдаёт заранее заданные ответы и запоминает запросы."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": headers, "body": json.loads(body)})
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def client(transport, tmp_path=None, max_usd=1.0, **kw):
    sleeps = []
    c = ChatClient(model="m", base_url="https://example.invalid/v1", key_env="R02_TEST_KEY",
                   budget=Budget(max_usd, 1.0, 2.0), cache_dir=tmp_path / "cache" if tmp_path else None,
                   transport=transport, sleep=sleeps.append, log_path=tmp_path / "log.jsonl" if tmp_path else None, **kw)
    return c, sleeps


def test_retry_after_429_and_network_error_then_success(tmp_path):
    t = Script((429, {"Retry-After": "3"}, b""), ConnectionError("reset"), ok("roads"))
    c, sleeps = client(t, tmp_path)
    r = c.chat([{"role": "user", "content": "x"}])
    assert r["text"] == "roads" and not r["cached"]
    assert sleeps[0] == 3.0 and len(sleeps) == 2
    assert c.stats["retries"] == 2
    assert t.calls[0]["url"] == "https://example.invalid/v1/chat/completions"


def test_auth_error_is_not_retried():
    t = Script((401, {}, b'{"error": {"message": "invalid api key"}}'))
    c, sleeps = client(t)
    with pytest.raises(LLMError, match="401"):
        c.chat([{"role": "user", "content": "x"}])
    assert sleeps == [] and len(t.calls) == 1


def test_gives_up_after_max_retries():
    t = Script(*[(503, {}, b"")] * 3)
    c, _ = client(t, max_retries=2)
    with pytest.raises(LLMError, match="3 попыток"):
        c.chat([{"role": "user", "content": "x"}])


def test_budget_blocks_request_before_sending():
    t = Script(ok("a", pin=1000, pout=1000))
    c, _ = client(t, max_usd=0.0001)
    with pytest.raises(BudgetExceeded):
        c.chat([{"role": "user", "content": "x" * 1000}], max_tokens=1000)
    assert t.calls == []


def test_cost_from_usage_and_cache_hit_is_free(tmp_path, monkeypatch):
    monkeypatch.setenv("R02_TEST_KEY", "sk-secret-123")
    t = Script(ok("roads", pin=1_000_000, pout=500_000))
    c, _ = client(t, tmp_path, max_usd=10)
    msgs = [{"role": "user", "content": "яма"}]
    assert c.chat(msgs, max_tokens=5)["cost"] == pytest.approx(1.0 + 1.0)
    again = c.chat(msgs, max_tokens=5)
    assert again["cached"] and again["cost"] == 0 and len(t.calls) == 1
    assert t.calls[0]["headers"]["Authorization"] == "Bearer sk-secret-123"
    # ключ не пишется ни в кэш, ни в журнал
    for f in list((tmp_path / "cache").rglob("*.json")) + [tmp_path / "log.jsonl"]:
        assert "sk-secret" not in f.read_text(encoding="utf-8")


def test_missing_key_without_transport_exits(monkeypatch):
    monkeypatch.delenv("R02_TEST_KEY", raising=False)
    c = ChatClient(model="m", base_url="https://example.invalid/v1", key_env="R02_TEST_KEY", budget=Budget(1, 1, 1))
    with pytest.raises(SystemExit, match="R02_TEST_KEY"):
        c.chat([{"role": "user", "content": "x"}])


def test_unknown_model_requires_prices():
    assert resolve_prices("gpt-4o-mini", None, None) == (0.15, 0.60)
    assert resolve_prices("meta/llama-3.3-70b-instruct", 0.5, 0.7) == (0.5, 0.7)
    with pytest.raises(SystemExit, match="--price-in"):
        resolve_prices("meta/llama-3.3-70b-instruct", None, None)


@pytest.mark.parametrize("raw, expected", [
    ('{"messages": ["a", "b"]}', {"messages": ["a", "b"]}),
    ('```json\n{"messages": ["a"]}\n```', {"messages": ["a"]}),
    ('Вот ответ: {"messages": ["a"]} надеюсь, подходит', {"messages": ["a"]}),
    ('["a", "b"]', ["a", "b"]),
])
def test_extract_json(raw, expected):
    assert extract_json(raw) == expected


@pytest.mark.parametrize("raw, label", [
    ("roads", "roads"), (" Roads.\n", "roads"), ("`snow_ice`", "snow_ice"), ("Ответ: waste", "waste"),
    ("roads или sidewalks", None), ("дороги", None), ("not_complaint", None),
])
def test_parse_label_strict(raw, label):
    labels = [c for c in ("roads", "snow_ice", "sidewalks", "waste", "other")]
    assert llm_label.parse_label(raw, labels) == label


def test_system_prompt_comes_from_guide():
    labels = ["roads", "snow_ice", "other"]
    p = llm_label.system_prompt(labels, allow_not_complaint=False)
    assert "Снег на тротуаре → snow_ice" in p
    assert "not_complaint" not in p
    assert p.rstrip().endswith("без кавычек и пояснений: roads, snow_ice, other.")
    assert "клавиша" not in p and "Сомневаюсь" not in p


def _label_args(tmp_path, **kw):
    a = Namespace(input=FIX / "texts_sample.jsonl", out=tmp_path / "llm.jsonl", provider="openai", model="gpt-4o-mini",
                  base_url=None, max_usd=1.0, price_in=0.15, price_out=0.6, max_tokens=12, seed=14, limit=None,
                  allow_not_complaint=False, confirm_external=True, cache=tmp_path / "cache",
                  allow_outside_private=True, dry_run=False)
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def test_llm_label_strict_retry_invalid_and_no_texts_in_output(tmp_path):
    # первый текст: болтливый ответ → повтор → нормальная метка; второй: два раза мусор → invalid
    answers = [ok("Думаю, это roads или sidewalks"), ok("roads"), ok("не знаю"), ok("???")] + [ok("other")] * 20
    t = Script(*answers)
    rep = llm_label.run(_label_args(tmp_path), transport=t)
    rows = [json.loads(line) for line in (tmp_path / "llm.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["label"] == "roads" and rows[1]["label"] == "invalid"
    assert rep["stats"]["retried_strict"] == 2 and rep["stats"]["invalid"] == 1
    assert all("text" not in r and r["role"] == "llm" and r["schema"] == "birge-labels-v1" for r in rows)
    # метка «transport» из входного файла модели не показывается
    sent = [m["content"] for c in t.calls for m in c["body"]["messages"] if m["content"].startswith("Текст обращения")]
    assert sent and all("transport" not in x for x in sent)


def test_llm_label_reanonymizes_before_sending(tmp_path):
    src = tmp_path / "in.jsonl"
    src.write_text(json.dumps({"id": "a", "text": "Яма, звоните +7 701 123 45 67"}, ensure_ascii=False), encoding="utf-8")
    t = Script(ok("roads"))
    llm_label.run(_label_args(tmp_path, input=src), transport=t)
    sent = t.calls[0]["body"]["messages"][-1]["content"]
    assert "701" not in sent and "[телефон]" in sent


def test_llm_label_requires_confirmation_for_real_texts(tmp_path):
    with pytest.raises(SystemExit, match="--confirm-external"):
        llm_label.run(_label_args(tmp_path, confirm_external=False))


def test_llm_label_budget_stop_keeps_partial(tmp_path):
    t = Script(*[ok("roads", pin=5000, pout=5)] * 20)
    rep = llm_label.run(_label_args(tmp_path, max_usd=0.002), transport=t)
    assert rep["stats"]["stopped_by_budget"] and 0 < rep["stats"]["ok"] < 12
    assert len((tmp_path / "llm.jsonl").read_text(encoding="utf-8").splitlines()) == rep["stats"]["ok"]


def _synth_args(tmp_path, **kw):
    a = Namespace(provider="openai", model="gpt-4o-mini", base_url=None, n_total=48, per_request=4, max_usd=1.0,
                  price_in=0.15, price_out=0.6, temperature=0.9, max_tokens=500, seed=14, categories=None,
                  json_mode=False, out=tmp_path / "out", cache=tmp_path / "cache", dry_run=False, mock=True)
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def test_llm_synth_plan_covers_all_categories_and_is_deterministic():
    p1 = llm_synth.plan_requests(240, 20, 14)
    assert p1 == llm_synth.plan_requests(240, 20, 14)
    assert len({r["category"] for r in p1}) == 12
    assert all(not (r["style"] == "translit" and r["lang"] == "mixed") for r in llm_synth.plan_requests(4000, 20, 3))
    assert {r["style"] for r in p1 if r["category"] == "other"} <= set(llm_synth.OTHER_STYLE_WEIGHTS)


def test_llm_synth_mock_pipeline(tmp_path):
    m = llm_synth.run(_synth_args(tmp_path), transport=llm_synth.mock_transport)
    rows = [json.loads(line) for line in (tmp_path / "out/corpus_llm_v1.jsonl").read_text(encoding="utf-8").splitlines()]
    assert m["rows"] == len(rows) > 0
    assert all(r["corpus"] == "llm_v1" and r["evidence"] == "synthetic_llm" for r in rows)
    assert set(m["by_split"]) <= {"train", "val", "test"}
    # повторный запуск — только кэш, ноль долларов
    m2 = llm_synth.run(_synth_args(tmp_path), transport=llm_synth.mock_transport)
    assert m2["budget"]["spent_usd"] == 0 and m2["client"]["cache_hits"] == m["stats"]["requests_ok"]


def test_llm_synth_cleaning_dedup_and_bad_json(tmp_path):
    dup = json.dumps({"messages": ["1. Яма на дороге у школы, звоните 8 701 111 22 33", "Яма на дороге у школы!",
                                   "ок", "Яма на дороге у школы!!", "Совсем другой текст про фонари во дворе"]},
                     ensure_ascii=False)
    t = Script(ok(dup), ok("это не json"), *[ok('{"messages": []}')] * 20)
    m = llm_synth.run(_synth_args(tmp_path, n_total=12, per_request=4, mock=False), transport=t)
    rows = [json.loads(line) for line in (tmp_path / "out/corpus_llm_v1.jsonl").read_text(encoding="utf-8").splitlines()]
    texts = [r["text"] for r in rows]
    assert texts[0] == "Яма на дороге у школы, звоните [телефон]"   # нумерация убрана, телефон обезличен
    assert "Совсем другой текст про фонари во дворе" in texts
    assert m["stats"]["filtered_length"] == 1 and m["stats"]["parse_failed"] == 1
    assert m["stats"]["duplicates"] + m["stats"]["near_duplicates"] >= 1


def test_llm_synth_mock_never_writes_into_real_corpus_folder():
    args = llm_synth.parse_args(["--mock"])
    assert "private" in str(args.out) and "llm_v1" not in str(args.out)
    with pytest.raises(SystemExit):
        llm_synth.parse_args([])  # без --max-usd реальный запуск запрещён
