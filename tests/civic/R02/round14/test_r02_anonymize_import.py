"""R02 · раунд 14 · обезличивание и импорт Google-формы. Все данные — выдуманные (синтетика)."""

import json
from pathlib import Path

import pytest

from ml.labeling import import_form, text_utils
from ml.labeling.anonymize import anonymize, anonymize_records, needs_review

FIX = Path(__file__).resolve().parent / "fixtures"


@pytest.mark.parametrize("raw, expected, marker", [
    ("Мой номер +7 701 123 45 67, звоните", "Мой номер [телефон], звоните", "[телефон]"),
    ("Тел. 8 (777) 123-45-67", "Тел. [телефон]", "[телефон]"),
    ("звоните 87011234567 или 7011234567", "звоните [телефон] или [телефон]", "[телефон]"),
    ("городской 57-12-34", "городской [телефон]", "[телефон]"),
    ("ИИН 990101300123", "ИИН [ИИН]", "[ИИН]"),
    ("карта 4400 4301 2345 6789", "карта [номер]", "[номер]"),
    ("Пишите на resident@mail.kz", "Пишите на [email]", "[email]"),
    ("смотрите https://t.me/nura_chat и www.example.kz/page", "смотрите [ссылка] и [ссылка]", "[ссылка]"),
    ("ул. Кенесары 40, кв. 15 нет воды", "ул. Кенесары [адрес] нет воды", "[адрес]"),
    ("пр. Кабанбай батыра, 53/1 не горят фонари", "пр. Кабанбай батыра [адрес] не горят фонари", "[адрес]"),
    ("во дворе дома 12 темно", "во дворе [адрес] темно", "[адрес]"),
    ("Кенесары 40 яма", "Кенесары [адрес] яма", "[адрес]"),
    ("Сыганак 18а мусор", "Сыганак [адрес] мусор", "[адрес]"),
    ("на Туран 24/1 яма", "на Туран [адрес] яма", "[адрес]"),
    ("12-үйдің жанында шам жоқ", "[адрес] жанында шам жоқ", "[адрес]"),
    ("№40 үй, 15-пәтер, суық", "[адрес], суық", "[адрес]"),
    ("пәтер 15 жылу жоқ", "[адрес] жылу жоқ", "[адрес]"),
    ("Кенесары көшесі, 40 шұңқыр", "Кенесары көшесі [адрес] шұңқыр", "[адрес]"),
    ("в 3 подъезде грязно", "в [адрес] грязно", "[адрес]"),
    ("машина 777 ABZ 01 стоит на газоне", "машина [госномер] стоит на газоне", "[госномер]"),
    ("Меня зовут Айгерим Сапарова, яма у школы №12", "Меня зовут [имя], яма у школы №12", "[имя]"),
    ("Менің атым Асқар, аулада қоқыс", "Менің атым [имя], аулада қоқыс", "[имя]"),
    ("С уважением, Иванов И.И.", "С уважением, [имя]", "[имя]"),
])
def test_replaces_personal_data(raw, expected, marker):
    clean, counts = anonymize(raw)
    assert clean == expected
    assert counts.get(marker, 0) >= 1


@pytest.mark.parametrize("text", [
    "школа №12, автобус 40, уже 3 дня, с 2024 года, 10.10.2026, 15 минут",
    "на улице Туран 5 минут ждём автобус",
    "маршрут 10 не ходит",
    "Абая 3 года не ремонтируют",
    "в доме 5 этажей",
    "Сарыарка районы, 5-й микрорайон",
    "Позвоните в 109",
    "Аулада шам жанбайды",
])
def test_keeps_public_places_numbers_and_durations(text):
    clean, counts = anonymize(text)
    assert clean == text
    assert counts == {}


def test_report_has_counts_but_never_original_values():
    rows = [{"id": "1", "text": "Звоните +7 701 123 45 67"}, {"id": "2", "text": "яма"}, {"id": "3", "text": "код AB12345"}]
    out, report = anonymize_records(rows)
    dumped = json.dumps(report, ensure_ascii=False)
    assert "701" not in dumped and "AB12345" not in dumped
    assert report["rows_changed"] == 1 and report["replaced"] == {"[телефон]": 1}
    assert report["rows_for_manual_review"] == [2]
    assert out[0]["text"] == "Звоните [телефон]"


def test_needs_review_flags_leftovers():
    assert needs_review("номер 12345 в конце")
    assert not needs_review("яма у [адрес], звоните [телефон]")


def test_import_form_consent_dedup_language_date_and_stable_ids():
    rows = import_form.read_csv(FIX / "form_sample.csv")
    records, report, _ = import_form.convert(rows, shuffle_seed=0)
    assert report["rows"] == 8 and report["kept"] == 6
    assert report["no_consent"] == 1 and report["empty_or_short"] == 1
    texts = " ".join(r["text"] for r in records)
    assert "701" not in texts and "@" not in texts and "990101300123" not in texts
    assert {r["lang"] for r in records} == {"ru", "kk", "mixed"}
    assert all(r["date"] == "2026-10-11" for r in records)
    assert all(r["schema"] == "birge-form-v1" and r["consent"] is True for r in records)
    # тот же текст → тот же id при повторном импорте; перемешивание id не меняет
    again, _, _ = import_form.convert(rows, shuffle_seed=7)
    assert sorted(r["id"] for r in again) == sorted(r["id"] for r in records)
    dumped = json.dumps(report, ensure_ascii=False)
    assert not any(r["text"] in dumped for r in records), "в отчёте не должно быть текстов жителей"


def test_import_form_dates_and_districts():
    assert import_form.parse_date("11.10.2026 10:01:12") == "2026-10-11"
    assert import_form.parse_date("10/11/2026 10:01:12") == "2026-10-11"
    assert import_form.parse_date("2026-10-11T10:00:00") == "2026-10-11"
    assert import_form.parse_date("вчера") == ""
    assert import_form.norm_district("Нура") == "nura"
    assert import_form.norm_district("Есіл") == "yesil"
    assert import_form.norm_district("другой город") == "other"


def test_import_form_duplicates_after_anonymization():
    rows = [["Текст жалобы", "Согласие"], ["Яма! Звоните +7 701 111 22 33", "Да"], ["яма, звоните 8 777 999 88 77", "Да"]]
    records, report, _ = import_form.convert(rows, shuffle_seed=0)
    assert report["duplicates"] == 1 and len(records) == 1


def test_output_outside_private_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        text_utils.check_output_path(tmp_path / "x.jsonl", allow_outside_private=False)
    text_utils.check_output_path(tmp_path / "x.jsonl", allow_outside_private=True)


def test_private_dir_gets_its_own_gitignore(tmp_path):
    p = text_utils.ensure_private_dir(tmp_path / "private")
    assert (p / ".gitignore").read_text(encoding="utf-8").strip().endswith("*")


def test_import_form_cli_writes_jsonl_report_and_review(tmp_path):
    out = tmp_path / "form.jsonl"
    assert import_form.main([str(FIX / "form_sample.csv"), "--out", str(out), "--allow-outside-private"]) == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 6
    assert json.loads(out.with_suffix(".report.json").read_text(encoding="utf-8"))["kept"] == 6
    assert out.with_suffix(".review.txt").exists()


def test_python_and_js_language_guess_agree():
    for text, lang in [("Аулада шам жанбайды", "kk"), ("Бағдаршам не работает уже неделю", "mixed"),
                       ("Не болды? Аулада қараңғы", "kk"), ("Яма на дороге", "ru"), ("yama na doroge", "")]:
        assert text_utils.guess_lang(text) == lang, text
