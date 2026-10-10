"""R02 · раунд 14 · шаблонная синтетика v3 и перевод v1 → v2."""

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from ml.datasets.synth_v3 import build
from ml.datasets.synth_v3.templates import T
from ml.datasets.v1_in_v2 import convert
from ml.labeling.text_utils import normalize

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "ml" / "datasets" / "synth_v3" / "data"
LABELS = [c["id"] for c in json.loads((ROOT / "research/round-14/categories_v2.json").read_text(encoding="utf-8"))["categories"]]


@pytest.fixture(scope="module")
def corpus():
    return [json.loads(line) for line in (DATA / "corpus_v3.jsonl").read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def manifest():
    return json.loads((DATA / "manifest_v3.json").read_text(encoding="utf-8"))


def test_size_and_all_categories_in_every_split(corpus, manifest):
    assert 4000 <= len(corpus) <= 6000
    assert manifest["rows"] == len(corpus)
    for split in ("train", "val", "test"):
        labels = {r["label"] for r in corpus if r["split"] == split}
        assert labels == set(LABELS), (split, set(LABELS) - labels)


def test_templates_do_not_leak_between_splits(corpus):
    split_by_tpl = {}
    for r in corpus:
        if r["split"] == "excluded_near_dup":
            continue
        split_by_tpl.setdefault(r["template_id"], set()).add(r["split"])
    assert all(len(s) == 1 for s in split_by_tpl.values())


def test_no_exact_duplicates_and_synthetic_marked(corpus):
    norms = Counter(normalize(r["text"]) for r in corpus)
    assert max(norms.values()) == 1
    assert all(r["evidence"] == "synthetic" and r["corpus"] == "synth_v3" for r in corpus)
    assert all(r["label"] in LABELS for r in corpus)


def test_no_personal_data_left(corpus):
    rx = re.compile(r"\+7|\b8 ?7\d{2}|\d{5,}|@\w|zhitel\d|turgyn\d")
    leaks = [r["text"] for r in corpus if rx.search(r["text"])]
    assert leaks == []
    assert sum(1 for r in corpus if "[телефон]" in r["text"]) > 50  # контакты были и заменены


def test_styles_languages_and_hard_cases_present(corpus):
    styles = Counter(r["style"] for r in corpus)
    for s in ("colloquial", "official", "short", "long", "typos", "slang", "translit", "question", "thanks"):
        assert styles[s] >= 40, (s, styles[s])
    langs = Counter(r["lang"] for r in corpus)
    assert langs["kk"] >= 1000 and langs["mixed"] >= 300 and langs["ru"] >= 1500
    assert sum(r["hard"] for r in corpus) >= 500


def test_templates_follow_guide_on_snow_and_ids_unique():
    assert len({t[0] for t in T}) == len(T)
    snow = re.compile(r"снег|гололёд|наледь|сосульк|сугроб|\bқар\b|қарды|көктайғақ|сүңгі|\bмұз")
    for tid, label, *_rest in T:
        text = _rest[3]
        if snow.search(text.lower()):
            assert label == "snow_ice", tid


def test_build_is_deterministic(tmp_path, manifest):
    m = build.build(tmp_path)
    assert m["corpus_sha256"] == manifest["corpus_sha256"]
    assert m["pairs_sha256"] == manifest["pairs_sha256"]


def test_paraphrase_pairs_for_dedup(manifest):
    pairs = [json.loads(line) for line in (DATA / "paraphrase_pairs_v3.jsonl").read_text(encoding="utf-8").splitlines()]
    kinds = Counter(p["kind"] for p in pairs)
    assert kinds["same_place_other_problem"] >= 150 and kinds["same_problem_other_place"] >= 150
    assert kinds["paraphrase"] + kinds["paraphrase_same_template"] >= 150
    assert kinds["paraphrase_crosslingual"] >= 100
    for p in pairs:
        assert p["same_incident"] == p["kind"].startswith("paraphrase")
        assert p["a"] != p["b"]
    assert {p["split"] for p in pairs} == {"dev", "test"}


def test_generator_text_fixes():
    import random
    rng = random.Random(1)
    v = build.sample_values(rng)
    v.update(place="во дворе дома 5", place_kk="5-үйдің ауласында", Place_kk="5-үйдің ауласында")
    assert build.render("Во дворе {place} темно", v, rng) == "Во дворе дома 5 темно"
    assert build.render("{Place_kk} аулада орын жоқ", v, rng) == "5-үйдің ауласында орын жоқ"
    assert build.join_prefix("Короче,", "Автобусы не ходят") == "автобусы не ходят"
    assert build.join_prefix("Короче,", "Кенесары разбита") == "Кенесары разбита"
    assert build.translit("Шұңқыр", random.Random(0), "ru").startswith("Sh")


def test_v1_relabel_rules():
    table = convert.load_table()
    assert convert.refine("roads", "Проезжую часть не чистят от снега", table)[0] == "snow_ice"
    assert convert.refine("sidewalks", "Тротуарда көктайғақ", table)[0] == "snow_ice"
    assert convert.refine("other", "Нет горячей воды", table)[0] == "utilities"
    assert convert.refine("other", "Мусор во дворе не вывозят", table)[0] == "waste"
    assert convert.refine("other", "Стройка шумит по ночам", table)[0] == "noise_safety"
    assert convert.refine("other", "Где можно оплатить штраф за парковку?", table, "irrelevant")[0] == "other"
    assert convert.refine("landscaping", "Саябақта қоқыс жәшіктері жоқ", table)[0] == "yards"
    assert convert.refine("transport_stops", "Сломан павильон", table) == ("transport", "table")
    assert convert.new_markers("Тел. <phone> .") == "Тел. [телефон]."


def test_v1_in_v2_file():
    path = ROOT / "ml/datasets/v1_in_v2/corpus_v1_in_v2.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2725
    assert all(r["label"] in LABELS and r["label_table"] in LABELS for r in rows)
    assert not any("<phone>" in r["text"] for r in rows)
    man = json.loads((path.parent / "manifest_v1_in_v2.json").read_text(encoding="utf-8"))
    assert man["label_disagrees_with_table"] == sum(r["label"] != r["label_table"] for r in rows)
