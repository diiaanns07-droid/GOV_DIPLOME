"""R06 раунд 14 · LOCAL_B2: seed-r14-demo в консоли Windows (CP1251) падал UnicodeEncodeError при печати отчёта
с казахскими буквами — уже после записи в базу. Теперь JSON печатается с \\u-экранированием (валидный), код 0."""

import io
import json
import sys

import pytest

from ui.civic_store import cli


def run(monkeypatch, argv, encoding):
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding=encoding, errors="strict", write_through=True)
    monkeypatch.setattr(sys, "stdout", stream)
    code = cli.main(argv)
    stream.flush()
    return code, raw.getvalue().decode(encoding)


def test_cp1251_cannot_print_kazakh_report_without_escaping():
    # Сама причина: в CP1251 нет «ғ», «ә», «қ» — print(json.dumps(..., ensure_ascii=False)) падает.
    with pytest.raises(UnicodeEncodeError):
        "«Жағалау-3» аялдамасындағы павильон".encode("cp1251")


@pytest.mark.parametrize("encoding", ["cp1251", "cp866"])
def test_seed_r14_demo_in_windows_console(tmp_path, monkeypatch, encoding):
    db = str(tmp_path / "c.sqlite3")
    code, out = run(monkeypatch, ["--db", db, "init"], encoding)
    assert code == 0 and json.loads(out)["schema_version"] >= 7
    code, out = run(monkeypatch, ["--db", db, "seed-r14-demo"], encoding)
    assert code == 0
    report = json.loads(out)  # валидный JSON с \\u-экранированием
    assert len(report["proposals"]) == 5
    assert "Жағалау" in json.dumps(report, ensure_ascii=False)  # казахский текст на месте, просто экранирован
    code, out = run(monkeypatch, ["--db", db, "seed-r14-demo"], encoding)  # повтор: ничего не дублирует
    assert code == 0 and all(p["action"] == "kept" for p in json.loads(out)["proposals"])


def test_utf8_console_keeps_readable_letters(tmp_path, monkeypatch):
    db = str(tmp_path / "c.sqlite3")
    run(monkeypatch, ["--db", db, "init"], "utf-8")
    code, out = run(monkeypatch, ["--db", db, "seed-r14-demo"], "utf-8")
    assert code == 0 and "Жағалау" in out  # в UTF-8 буквы печатаются как есть
