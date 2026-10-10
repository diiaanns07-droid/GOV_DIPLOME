"""ui.civic_ml_api.classify: контракт ответа, запасные пути при отсутствии моделей, сбой v2, крайние тексты."""

import time

import pytest

import ui.civic_ml_api as api
from ui.civic_ml_api import categories as C
from ui.civic_ml_api import classify_chain as K

from r04_helpers import clean_api  # noqa: F401 — autouse-фикстура (чистое состояние ML-API)

CONTRACT_KEYS = {"category", "score", "needs_review", "model_version", "top3"}


def check_contract(res):
    assert CONTRACT_KEYS <= set(res)
    assert res["category"] in C.ids()
    assert isinstance(res["score"], float) and 0.0 <= res["score"] <= 1.0
    assert isinstance(res["needs_review"], bool) and isinstance(res["model_version"], str) and res["model_version"]
    assert len(res["top3"]) <= 3
    for item in res["top3"]:
        assert item["category"] in C.ids() and 0.0 <= item["score"] <= 1.0
    assert isinstance(res["suggest"], bool)


def has_v1():
    return K._Chain().v1() is not None


def has_kw():
    return K._Chain().kw() is not None


@pytest.mark.parametrize("text", ["Во дворе не горят фонари", "Аялдамада қар тазаланбаған", "Спасибо за ремонт",
                                  "Лифт не работает", "Мусор не вывозят, баки полные"])
def test_contract_on_ordinary_texts(text):
    check_contract(api.classify(text))


@pytest.mark.parametrize("text", ["", "   ", "...", "123 456", "?!"])
def test_empty_or_meaningless_text(text):
    res = api.classify(text)
    check_contract(res)
    assert res["category"] == "other" and res["needs_review"] is True and res["top3"] == [] and not res["suggest"]


def test_non_string_is_bad_request():
    with pytest.raises(ValueError):
        api.classify(None)
    with pytest.raises(ValueError):
        api.classify(["яма"])


def test_very_long_text_is_truncated_and_fast():
    text = "Во дворе не горят фонари, очень темно. " * 5000  # ~200 000 символов
    t0 = time.perf_counter()
    res = api.classify(text)
    assert time.perf_counter() - t0 < 1.0
    check_contract(res)


@pytest.mark.skipif(not has_kw(), reason="нет ml/civic_classifier_v2 (словарь R03) в сборке")
@pytest.mark.parametrize("text,expected", [
    ("Аялдамада кар тазаланбаган, тайгак", "snow_ice"),           # казахский без специфических букв
    ("Кокыс жашиктери толып кетти, шыгарылмаиды", "waste"),
    ("Yama na doroge, mashiny lomayut kolesa", "roads"),          # русский транслит
    ("Ystyq su joq, ush kunnen beri", "utilities"),              # казахская латиница
    ("aialdamada qar tazalanbaidy", "snow_ice"),
    ("Во дворе не горят фонари", "lighting"),
])
def test_kazakh_unmarked_and_translit(text, expected):
    assert api.classify(text)["category"] == expected


@pytest.mark.skipif(not has_kw(), reason="нет словаря R03")
def test_russian_card_word_is_not_snow():
    # сведённое «қар» = «кар» не должно ловиться в русском тексте («карта»)
    assert api.classify("Карта Onay не работает в автобусе")["category"] != "snow_ice"


def test_suggest_only_when_confident():
    res = api.classify("Не убран снег, наледь и сугробы на тротуаре")
    if res["source"] == "kw":
        assert res["suggest"] is True
    assert api.classify("Лифт не работает")["suggest"] is False


def _break(monkeypatch, *names):
    """Сделать модели недоступными, как будто файлов нет."""
    def boom():
        raise FileNotFoundError("нет файла модели (тест)")
    for name in names:
        monkeypatch.setattr(K._Chain, f"_load_{name}", staticmethod(boom))
    api.reset()


def test_no_v2_files_falls_back_without_error(monkeypatch):
    _break(monkeypatch, "v2")
    res = api.classify("Во дворе не горят фонари")
    check_contract(res)
    assert res["source"] in ("kw", "v1", "v1-heuristic", "none")
    assert "v2" in api.status()["classify"]["models"]


def test_no_v1_model_uses_keywords(monkeypatch):
    if not has_kw():
        pytest.skip("нет словаря R03")
    _break(monkeypatch, "v2", "v1")
    res = api.classify("Лифт не работает")              # слов словаря нет, v1 нет
    check_contract(res)
    assert res["category"] == "other" and res["model_version"] == K.KW_VERSION
    assert api.classify("Не горят фонари")["category"] == "lighting"


def test_only_v1_heuristic_left(monkeypatch):
    _break(monkeypatch, "v2", "v1", "kw")
    res = api.classify("Не горят фонари во дворе")
    check_contract(res)
    if K.CHAIN.v1_heuristic() is not None:
        assert res["source"] == "v1-heuristic" and res["category"] == "lighting"


def test_nothing_available_still_answers(monkeypatch):
    _break(monkeypatch, "v2", "v1", "kw", "v1_heuristic")
    res = api.classify("Не горят фонари во дворе")
    check_contract(res)
    assert res == {**res, "category": "other", "model_version": "none", "source": "none", "needs_review": True}


class FakeV2:
    model_version = "civic-clf-v2-test"
    threshold = 0.5

    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    def classify(self, text):
        self.calls += 1
        if self.fail:
            raise RuntimeError("onnxruntime: тестовый сбой")
        return {"category": "snow_ice", "score": 0.91, "needs_review": False, "model_version": self.model_version,
                "top3": [{"category": "snow_ice", "score": 0.91}, {"category": "roads", "score": 0.05}]}


def test_v2_is_used_first(monkeypatch):
    fake = FakeV2()
    monkeypatch.setattr(K._Chain, "_load_v2", staticmethod(lambda: fake))
    api.reset()
    res = api.classify("Гололёд")
    check_contract(res)
    assert res["source"] == "v2" and res["model_version"] == "civic-clf-v2-test" and res["suggest"] is True
    assert api.status()["classify"]["model_version"] == "civic-clf-v2-test"


def test_v2_failure_falls_back_and_disables_after_three(monkeypatch):
    fake = FakeV2(fail=True)
    monkeypatch.setattr(K._Chain, "_load_v2", staticmethod(lambda: fake))
    api.reset()
    for _ in range(5):
        res = api.classify("Во дворе не горят фонари")
        check_contract(res)
        assert res["source"] != "v2" and res["model_version"] != "civic-clf-v2-test"
    assert fake.calls == K.V2_MAX_FAILURES  # после трёх сбоев v2 больше не вызывается
    assert api.status()["classify"]["models"]["v2"].startswith("unavailable")


def test_v2_unknown_category_is_rejected(monkeypatch):
    class Odd(FakeV2):
        def classify(self, text):
            return {"category": "aliens", "score": 0.9, "needs_review": False, "top3": []}
    monkeypatch.setattr(K._Chain, "_load_v2", staticmethod(lambda: Odd()))
    api.reset()
    assert api.classify("Во дворе не горят фонари")["category"] in C.ids()


def test_lazy_load_happens_once(monkeypatch):
    calls = {"n": 0}
    real = K._Chain._load_kw

    def counting():
        calls["n"] += 1
        return real()
    monkeypatch.setattr(K._Chain, "_load_kw", staticmethod(counting))
    api.reset()
    for _ in range(20):
        api.classify("Не горят фонари")
    assert calls["n"] == 1


def test_status_has_no_absolute_paths():
    # настоящая ошибка R03 содержит путь к artifacts/ — наружу он уходит относительным
    text = str(api.status())
    assert str(C.REPO_ROOT) not in text
