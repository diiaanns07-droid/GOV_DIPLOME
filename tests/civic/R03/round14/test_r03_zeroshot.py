"""R03 v2: LLM zero-shot на подставном клиенте (без сети и без ключа)."""

from __future__ import annotations

import json
import urllib.error

import pytest

import fixtures as F
from ml.civic_classifier_v2 import data as D
from ml.civic_classifier_v2 import labels as L
from ml.civic_classifier_v2 import zeroshot as Z


def _records(tmp_path, n=12):
    recs, _ = D.load_human([F.write_jsonl(tmp_path / "h.jsonl", F.human_like(n))])
    return recs


class FakeLLM:
    """Отвечает истинной меткой (по тексту из фикстуры) с разным «мусором» вокруг; считает вызовы."""

    def __init__(self, recs, fail_first=0):
        self.by_text = {r["text"]: r["label"] for r in recs}
        self.calls = 0
        self.fail_first = fail_first

    def __call__(self, payload):
        self.calls += 1
        if self.calls <= self.fail_first:
            raise urllib.error.URLError("сеть недоступна")
        assert payload["temperature"] == 0 and payload["messages"][0]["role"] == "system"
        text = payload["messages"][1]["content"]
        lab = self.by_text[text]
        answer = {0: lab, 1: f"Категория: {lab}.", 2: f"`{lab}`"}[self.calls % 3]
        return {"choices": [{"message": {"content": answer}}], "usage": {"prompt_tokens": 400, "completion_tokens": 3}}


def test_prompt_lists_all_categories_from_file():
    sp = Z.system_prompt()
    for lab in L.labels():
        assert f"\n{lab} — " in sp
    assert "snow_ice" in sp and "Яма во дворе -> roads" in sp


@pytest.mark.parametrize("answer,label", [("lighting", "lighting"), ("Ответ: snow_ice.", "snow_ice"),
                                          ("ROADS", "roads"), ("не знаю", None), ("", None), (None, None),
                                          ("road", None)])
def test_parse_label(answer, label):
    assert Z.parse_label(answer) == label


def test_classify_all_with_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(Z.time, "sleep", lambda s: None)
    recs = _records(tmp_path)
    fake = FakeLLM(recs, fail_first=1)                     # первый вызов — сетевая ошибка, затем повтор
    cache = tmp_path / "zs" / "cache.jsonl"
    preds, stats = Z.classify_all(recs, fake, "fake-model", cache, Z.Budget(1.0, 0.15, 0.6), 100)
    assert [p["label"] for p in preds] == [r["label"] for r in recs]
    assert stats["requested"] == len(recs) and stats["unparsed"] == 0 and stats["failed"] == 0
    assert stats["usd_spent_estimate"] > 0
    # в кэше нет текстов людей — только хэш и ответ
    raw = cache.read_text(encoding="utf-8")
    assert all(r["text"] not in raw for r in recs)
    # повторный запуск не вызывает API
    fake2 = FakeLLM(recs)
    preds2, stats2 = Z.classify_all(recs, fake2, "fake-model", cache, Z.Budget(1.0, 0.15, 0.6), 100)
    assert fake2.calls == 0 and stats2["cached"] == len(recs) and preds2 == preds


def test_budget_stops_before_exceeding(tmp_path):
    recs = _records(tmp_path)
    fake = FakeLLM(recs)
    # Цена так высока, что после 3 запросов следующий превысил бы бюджет.
    budget = Z.Budget(max_usd=0.0013, price_in=1.0, price_out=1.0)
    preds, stats = Z.classify_all(recs, fake, "m", tmp_path / "c.jsonl", budget, 100)
    assert stats["stopped_by_budget"] and 0 < len(preds) < len(recs)
    assert budget.spent <= 0.0013 + 1e-9


def test_auth_error_is_not_retried(tmp_path):
    recs = _records(tmp_path, 2)

    def unauthorized(payload):
        raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)

    with pytest.raises(urllib.error.HTTPError):
        Z.classify_all(recs, unauthorized, "m", tmp_path / "c.jsonl", Z.Budget(1, 1, 1), 10)


def test_main_requires_env_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("R03_FAKE_KEY", raising=False)
    rc = Z.main(["--human", str(F.write_jsonl(tmp_path / "h.jsonl", F.human_like(3))), "--model", "m",
                 "--api-key-env", "R03_FAKE_KEY", "--out-dir", str(tmp_path / "zs")])
    assert rc == 2 and "R03_FAKE_KEY" in capsys.readouterr().err


def test_zeroshot_preds_feed_experiments(tmp_path):
    """Файл {id,label} от zeroshot.py читается экспериментом; неполное покрытие помечается."""
    from ml.civic_classifier_v2 import experiments as E
    recs = _records(tmp_path, 24)
    preds = [{"id": r["id"], "label": r["label"]} for r in recs[:20]]
    path = tmp_path / "zs.jsonl"
    path.write_text("".join(json.dumps(p) + "\n" for p in preds), encoding="utf-8")
    probe, _ = D.load_corpus(F.write_jsonl(tmp_path / "p.jsonl", F.probe_like()), source="probe_v2", evidence="x")
    path.write_text(path.read_text(encoding="utf-8") + "".join(
        json.dumps({"id": r["id"], "label": r["label"]}) + "\n" for r in probe), encoding="utf-8")
    store = {}
    entry = E._external_preds(path, {"human": recs, "probe_v2": probe}, L.labels(), store, "none/zeroshot_llm")
    assert entry["status"] == "OK" and entry["coverage"] == {"human": "20/24", "probe_v2": f"{len(probe)}/{len(probe)}"}
    assert entry["eval"]["human"]["accuracy"] == 1.0 and entry["eval"]["probe_v2"]["accuracy"] == 1.0
    # полное покрытие -> в парных сравнениях участвует только probe_v2
    assert set(store["none/zeroshot_llm"]) == {"probe_v2"} and "покрытие 20/24" in entry["note"]
