"""R02 · раунд 14 · ml/labeling/agreement.py: kappa на известных примерах и чтение файлов."""

import json

import pytest

from ml.labeling import agreement


def _pairs(*groups):
    out = []
    for a, b, n in groups:
        out += [(a, b)] * n
    return out


def test_kappa_textbook_example():
    # Классический пример (Wikipedia «Cohen's kappa»): 20 да/да, 5 да/нет, 10 нет/да, 15 нет/нет → 0.4
    k, p_o, p_e = agreement.kappa_from_pairs(_pairs(("y", "y", 20), ("y", "n", 5), ("n", "y", 10), ("n", "n", 15)))
    assert p_o == pytest.approx(0.7)
    assert p_e == pytest.approx(0.5)
    assert k == pytest.approx(0.4)


def test_kappa_perfect_and_undefined():
    assert agreement.kappa_from_pairs(_pairs(("a", "a", 3), ("b", "b", 4)))[0] == pytest.approx(1.0)
    # оба всегда ставят одну и ту же метку — kappa не определена (p_e = 1), а не деление на ноль
    assert agreement.kappa_from_pairs(_pairs(("a", "a", 5)))[0] is None
    assert agreement.interpret(None) == "не определена"


def test_compare_matrix_per_label_and_exclusions():
    a = {"1": "roads", "2": "roads", "3": "lighting", "4": "waste", "5": "not_complaint", "6": "roads"}
    b = {"1": "roads", "2": "sidewalks", "3": "lighting", "4": "waste", "5": "other", "7": "roads"}
    res = agreement.compare(a, b, exclude={"not_complaint"}, bootstrap=200, seed=1)
    assert res["common"] == 5 and res["n"] == 4 and res["dropped"]["excluded_label"] == 1
    assert res["only_a"] == 1 and res["only_b"] == 1
    assert res["matrix"]["roads"]["sidewalks"] == 1
    assert res["per_label"]["roads"]["specific_agreement"] == pytest.approx(2 * 1 / (2 + 1))
    assert res["disagreements"] == [{"id": "2", "a": "roads", "b": "sidewalks"}]
    assert res["top_confusions"] == [("roads ↔ sidewalks", 1)]
    lo, hi = res["kappa_ci95"]
    assert lo <= res["kappa"] <= hi


def test_bootstrap_is_reproducible():
    pairs = _pairs(("a", "a", 30), ("a", "b", 7), ("b", "b", 25), ("b", "a", 5), ("c", "c", 10))
    assert agreement.bootstrap_ci(pairs, 300, 5) == agreement.bootstrap_ci(pairs, 300, 5)


def test_reads_tool_export_llm_output_and_csv(tmp_path):
    tool = tmp_path / "A.jsonl"
    tool.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        {"schema": "birge-labels-v1", "id": "x1", "text": "яма", "label": "roads", "unsure": True},
        {"schema": "birge-labels-v1", "id": "x2", "text": "снег", "label": "snow_ice", "unsure": False},
        {"schema": "birge-labels-v1", "id": "x3", "text": "?", "label": ""},
    ]) + "\nне json\n", encoding="utf-8")
    llm = tmp_path / "llm.jsonl"
    llm.write_text(json.dumps({"id": "x1", "label": "roads"}) + "\n" + json.dumps({"id": "x2", "label": "invalid"}) + "\n",
                   encoding="utf-8")
    csvf = tmp_path / "B.csv"
    csvf.write_text("id;label\nx1;roads\nx2;snow_ice\n", encoding="utf-8")
    a, texts, unsure = agreement.read_labels(tool)
    assert a == {"x1": "roads", "x2": "snow_ice"} and unsure["x1"] is True and texts["x1"] == "яма"
    assert agreement.read_labels(llm)[0] == {"x1": "roads"}
    assert agreement.read_labels(csvf)[0] == {"x1": "roads", "x2": "snow_ice"}
    # --drop-unsure убирает x1
    res = agreement.compare(a, agreement.read_labels(csvf)[0], drop_unsure=True, unsure_a=unsure, bootstrap=0)
    assert res["n"] == 1 and res["dropped"]["unsure"] == 1


def test_cli_writes_markdown_and_json(tmp_path, capsys):
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    rows_a = [{"id": str(i), "label": lab} for i, lab in enumerate(["roads"] * 5 + ["waste"] * 5)]
    rows_b = [{"id": str(i), "label": lab} for i, lab in enumerate(["roads"] * 4 + ["waste"] * 6)]
    a.write_text("\n".join(json.dumps(r) for r in rows_a), encoding="utf-8")
    b.write_text("\n".join(json.dumps(r) for r in rows_b), encoding="utf-8")
    md, js = tmp_path / "r.md", tmp_path / "r.json"
    assert agreement.main([str(a), str(b), "--md", str(md), "--json", str(js), "--bootstrap", "100"]) == 0
    out = capsys.readouterr().out
    assert "Cohen's kappa = 0.800" in out
    assert "| **roads** |" in md.read_text(encoding="utf-8")
    assert json.loads(js.read_text(encoding="utf-8"))["kappa"] == pytest.approx(0.8)


def test_texts_in_report_only_inside_private(tmp_path):
    a = tmp_path / "a.jsonl"
    a.write_text(json.dumps({"id": "1", "label": "roads", "text": "реальный текст"}), encoding="utf-8")
    b = tmp_path / "b.jsonl"
    b.write_text(json.dumps({"id": "1", "label": "waste"}), encoding="utf-8")
    with pytest.raises(SystemExit):
        agreement.main([str(a), str(b), "--md", str(tmp_path / "r.md"), "--with-texts", "--bootstrap", "0"])
