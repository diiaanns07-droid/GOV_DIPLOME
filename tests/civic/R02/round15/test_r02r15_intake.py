"""R02 · раунд 15+ (поправка П3): набор «обращения за ночь» для «ИИ-разбора пачки» R04 и его эталон.

Проверяем: файл текстов — только то, что нужно экрану; состав — как в П3 (языки, латиница, опечатки, повторы,
«две службы», срочные, без адреса); эталон — по правилам Birge (categories_v2, таблица служб R08/R09, пары CONTRACT
§5.1, классы срочности); места названы в самом тексте и известны карте R12; сцены демо не задеты; личных данных нет;
тексты не из synth_v3 (на нём учится R04) и не из мира; воспроизводимость и оценщик метрик П3.
Проверки, которым нужна карта R12 той же версии, на других данных пропускаются с причиной (как у мира).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
DIR = ROOT / "data" / "civic" / "astana" / "demo-world"
TEXTS = DIR / "intake_night_v1.json"
GOLD = DIR / "intake_night_v1.gold.json"
JOINT_PAIRS = {("water", "road"), ("heating", "road"), ("heating", "greenery"), ("power", "lighting")}
SCENE_TARGETS = {"osm-node-4109037549", "yard-1454082640"}           # «Хан Шатыр» (шаг 2), двор сцены 7


@pytest.fixture(scope="module")
def texts() -> dict:
    return json.loads(TEXTS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def gold() -> dict:
    return json.loads(GOLD.read_text(encoding="utf-8"))


def _other_inputs(texts: dict) -> list[str]:
    from ml.datasets import demo_intake as di
    now = di.input_hashes()
    return sorted(k for k, v in (texts.get("inputs") or {}).items() if now.get(k) != v)


def test_texts_file_follows_r04_contract(texts, gold):
    """INTEGRATION R04 п. 9.4: {texts: [{id, text, lang}], gold: [{id, category, services: [id…], target_id, group,
    urgent}], demo: true}; краткий gold совпадает с полным эталоном."""
    assert texts["schema"] == "birge-intake-night-v1" and texts["demo"] is True and texts["synthetic"] is True
    ids = [i["id"] for i in texts["texts"]]
    assert ids == [f"night-{k:03d}" for k in range(1, len(ids) + 1)]
    for it in texts["texts"]:
        assert set(it) == {"id", "text", "lang", "received", "demo"} and it["demo"] is True
        assert it["text"].strip() == it["text"] and it["text"] and it["lang"] in ("ru", "kk", "mixed", "latin")
    full = {i["id"]: i for i in gold["items"]}
    assert [g["id"] for g in texts["gold"]] == ids
    for g in texts["gold"]:
        f = full[g["id"]]
        assert g["services"] == [s["id"] for s in f["services"]] and g["target_id"] == f["target_id"]
        assert (g["category"], g["subtopic"], g["group"], g["urgent"], g["urgent_why"], g["no_address"]) == \
            (f["category"], f["subtopic"], f["group"], f["urgent"], f["urgent_why"], f["no_address"])
    assert all(i["lang"] == full[i["id"]]["lang"] for i in texts["texts"])


def test_size_within_r04_batch_limits(texts):
    n = len(texts["texts"])
    assert 250 <= n <= 350                                          # П3: ~300
    assert n <= texts["limits"]["max_texts_per_batch"] == 500
    assert sum(len(i["text"].encode("utf-8")) for i in texts["texts"]) <= texts["limits"]["max_bytes_per_batch"]


def test_gold_belongs_to_this_texts_file(texts, gold):
    assert gold["schema"] == "birge-intake-night-gold-v1" and gold["demo"] is True
    assert gold["for"]["sha256"] == hashlib.sha256(TEXTS.read_bytes()).hexdigest()
    assert [i["id"] for i in gold["items"]] == [i["id"] for i in texts["texts"]]
    in_groups = [tid for g in gold["groups"] for tid in g["text_ids"]]
    assert sorted(in_groups) == sorted(i["id"] for i in gold["items"])          # группы делят набор без остатка
    by = {g["id"]: g for g in gold["groups"]}
    for it in gold["items"]:
        assert it["id"] in by[it["group"]]["text_ids"]


def test_composition_matches_amendment_p3(gold):
    s, n = gold["summary"], len(gold["items"])
    langs = Counter(i["lang"] for i in gold["items"])
    assert set(langs) == {"ru", "kk", "mixed", "latin"} and all(v >= 0.08 * n for v in langs.values()), langs
    assert {i["base_lang"] for i in gold["items"] if i["lang"] == "latin"} == {"ru", "kk"}
    assert sum(i["typos"] for i in gold["items"]) >= 0.05 * n
    assert s["groups_with_repeats"] >= 30 and s["largest_group"] >= 20       # одно место — много людей
    assert 10 <= s["two_service_groups"] <= 20                                # П3: 10–20 случаев «двух служб»
    assert 5 <= s["urgent_groups"] <= 10                                      # П3: 5–10 срочных
    assert 0.03 * n <= s["no_address_texts"] <= 0.12 * n
    assert s["merged"] == n - s["groups"] and s["texts"] == n


def test_labels_follow_birge_rules(gold):
    from ml.datasets import demo_intake_texts as TX
    from ui.civic_feedback.v2 import lifecycle
    cats = json.loads((ROOT / "research" / "round-14" / "categories_v2.json").read_text(encoding="utf-8"))
    subs = {c["id"]: {s["id"] for s in c.get("subtopics", [])} for c in cats["categories"]}
    for g in gold["groups"]:
        assert g["category"] in subs and (g["subtopic"] is None or g["subtopic"] in subs[g["category"]]), g["id"]
        ids = [s["id"] for s in g["services"]]
        assert all(i in lifecycle.SERVICES for i in ids) and [s["role"] for s in g["services"]][0] == "lead"
        if len(ids) == 1:
            assert ids[0] == lifecycle.default_service(g["category"], g["subtopic"]), g["id"]
        else:
            assert tuple(ids) in JOINT_PAIRS and g["two_services"], g["id"]
        assert g["urgent"] == (g["urgent_why"] is not None)
        assert g["urgent_why"] is None or g["urgent_why"] in TX.URGENT
    for it in gold["items"]:
        assert it["urgent"] == next(g["urgent"] for g in gold["groups"] if g["id"] == it["group"])


def test_place_is_named_in_every_text(texts, gold):
    from ml.datasets.demo_intake import latin
    text = {i["id"]: i["text"] for i in texts["texts"]}
    lang = {i["id"]: i for i in gold["items"]}
    norm = lambda s: s.lower().replace("«", "").replace("»", "")          # noqa: E731
    for g in gold["groups"]:
        if g["no_address"]:
            assert g["place"]["target"] is None and g["place"]["type"] in ("none", "district")
            continue
        assert g["place"]["mentions"], g["id"]
        for tid in g["text_ids"]:
            t = norm(text[tid])
            if lang[tid]["lang"] == "latin":
                forms = [norm(latin(m, lang[tid]["base_lang"])) for m in g["place"]["mentions"]]
            else:
                forms = [norm(m) for m in g["place"]["mentions"]]
            assert any(f in t for f in forms), (tid, text[tid])


def test_scenes_are_not_touched(gold):
    for g in gold["groups"]:
        t = g["place"]["target"] or {}
        assert t.get("id") not in SCENE_TARGETS
        assert g["place"].get("street_ru") != "улица Баян Сулу"              # сцена 8
        assert not (g["category"] == "snow_ice" and g["place"]["district"] == "nura")   # сцена 9: «Буран в Нуре»


def test_received_last_night_in_order(texts):
    from datetime import datetime
    from ml.datasets import demo_world_io as wio
    seen = []
    for it in texts["texts"]:
        d = it["received"]["day_at"]
        minutes = (d["hour"] * 60 + d["minute"] - (21 * 60 + 30)) % (24 * 60)
        assert (d["day"], d["hour"] >= 21) in ((-1, True), (0, False)) and minutes <= 600, it["id"]
        seen.append(minutes)
    assert seen == sorted(seen)
    now = datetime(2026, 10, 16, 9, 0, tzinfo=wio.ASTANA_TZ)
    iso = wio.materialize(texts["texts"], now)
    assert "2026-10-15T21:30:00+05:00" <= iso[0]["received"] and iso[-1]["received"] <= "2026-10-16T07:30:00+05:00"


def test_no_personal_data(texts):
    phone = re.compile(r"(\+?\d[\d\s\-()]{8,}\d)")
    for it in texts["texts"]:
        t = it["text"]
        assert not phone.search(t) and "@" not in t and "http" not in t.lower(), it["id"]


def test_texts_are_new_not_from_synth_v3_or_world(texts):
    norm = lambda s: re.sub(r"\W+", " ", s.lower()).strip()                 # noqa: E731
    mine = {norm(i["text"]) for i in texts["texts"]}
    world = json.loads((DIR / "world_v1.json").read_text(encoding="utf-8"))
    assert not mine & {norm(c["text"]) for c in world["complaints"]}
    corpus = ROOT / "ml" / "datasets" / "synth_v3" / "data" / "corpus_v3.jsonl"
    if corpus.exists():
        synth = {norm(json.loads(line)["text"]) for line in corpus.read_text(encoding="utf-8").splitlines() if line.strip()}
        assert not mine & synth


def test_targets_are_known_to_the_r12_map(texts, gold):
    other = _other_inputs(texts)
    if other:
        pytest.skip("набор собран на других данных карты R12 / мира в этом дереве: " + ", ".join(other))
    import sys
    sys.path.insert(0, str(ROOT))
    from engine.civic_geo import target_geometry
    from engine.civic_geo.graph import get_graph
    names = {e.id: e.name for e in get_graph().edges}
    for g in gold["groups"]:
        t = g["place"]["target"]
        if t is None:
            continue
        found = target_geometry({"kind": t["kind"], "id": t["id"]})
        assert found and found["label_ru"] == t["label_ru"], g["id"]
        assert t["id"] in g["place"]["accept_ids"]
        if g["place"]["type"] == "street":
            assert names[t["id"]] == g["place"]["street_ru"]


def test_generator_is_reproducible(texts):
    other = _other_inputs(texts)
    if other:
        pytest.skip("сверка байт в байт — только на тех же входах (карта R12 247c24a8, мир dd0e7bba): " + ", ".join(other))
    from ml.datasets import demo_intake as di
    t, g = di.build()
    assert di.dump(t) == TEXTS.read_text(encoding="utf-8")
    assert di.dump(g) == GOLD.read_text(encoding="utf-8")


def test_scorer_perfect_on_gold_and_zero_when_nothing_is_merged(gold):
    from ml.datasets import demo_intake_eval as ev
    res = ev.evaluate(ev.gold_as_prediction(gold), gold)
    assert res["services"]["lead_accuracy"] == res["services"]["exact_set"] == 1.0
    assert res["services"]["two_services_recall"] == res["services"]["two_services_precision"] == 1.0
    assert res["duplicates"]["pairwise_f1"] == res["duplicates"]["groups_exact"] == 1.0
    assert res["places"]["found_share"] == res["places"]["no_address_abstained"] == 1.0
    assert res["urgent"]["recall_texts"] == res["urgent"]["recall_groups"] == res["urgent"]["precision_texts"] == 1.0
    solo = {"tasks": [{"text_ids": [k], "services": [], "target": None, "urgent": False}
                      for k in range(len(gold["items"]))]}                    # номера строк с нуля
    res = ev.evaluate(solo, gold)
    assert res["covered"] == len(gold["items"]) and res["duplicates"]["pairwise_f1"] == 0.0
    assert res["services"]["lead_accuracy"] == 0.0 and res["urgent"]["recall_groups"] == 0.0
    assert res["places"]["found_share"] == 0.0 and res["places"]["no_address_abstained"] == 1.0


def test_scorer_counts_a_street_by_name_and_a_stop_by_any_side(gold):
    from ml.datasets import demo_intake_eval as ev
    pred = ev.gold_as_prediction(gold)
    street = next(g for g in gold["groups"] if g["place"]["type"] == "street")
    stop = next((g for g in gold["groups"] if g["place"]["type"] == "stop" and len(g["place"]["accept_ids"]) > 1), None)
    for t in pred["tasks"]:
        if t["id"] == street["id"]:
            t["target"] = {"kind": "segment", "id": "another-segment"}
        if stop and t["id"] == stop["id"]:
            t["target"] = {"kind": "object", "id": stop["place"]["accept_ids"][-1]}
    res = ev.evaluate(pred, gold, streets={"another-segment": street["place"]["street_ru"]})
    assert res["places"]["found_share"] == 1.0
    res = ev.evaluate(pred, gold, streets={})
    assert res["places"]["found_share"] < 1.0
