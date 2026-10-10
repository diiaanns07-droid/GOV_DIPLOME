"""Нормализация текста: транслит, казахский без специфических букв, маркеры, пустые строки."""

from ml.civic_dedup.concepts import concepts
from ml.civic_dedup.normalize import letters, normalize, to_cyrillic


def test_russian_translit_becomes_cyrillic():
    assert normalize("Yama na doroge u ostanovki!") == "яма на дороге у остановки"
    assert normalize("Avtobus ne prihodit uzhe chas") == "автобус не приходит уже час"


def test_kazakh_latin_variants_match_cyrillic():
    # латиница 2021 (q, ğ), 2017 (апострофы) и чат без спецбукв дают одну строку
    target = normalize("Аялдамада қар тазаланбайды")
    assert normalize("aialdamada qar tazalanbaidy") == target
    assert normalize("Ayaldamada kar tazalanbaydy") != ""  # не падает на «y» в разных ролях
    assert normalize("s'yg'ys") == normalize("шығыс")


def test_kazakh_without_special_letters_equals_with_letters():
    assert normalize("Аулада шамдар жанбайды, қараңғы") == normalize("Аулада шамдар жанбаиды, караңгы".replace("ң", "н"))
    assert normalize("Қоқыс жәшіктері толып кетті") == normalize("Кокыс жашиктери толып кетти")


def test_markers_digits_urls_removed():
    assert normalize("Звоните [телефон], дом 12, <phone> https://x.kz/a") == "звоните дом"


def test_to_cyrillic_keeps_cyrillic_text_with_brand_words():
    assert to_cyrillic("Карта Onay не работает") == "Карта Onay не работает"
    assert to_cyrillic("qar tazalanbaidy") == "қар тазаланбайды"
    assert to_cyrillic("Ağaştar kesildi") == "ағаштар кесилди"


def test_empty_and_symbols():
    assert normalize("") == ""
    assert normalize("!!! ... 123") == ""
    assert letters("...") == 0


def test_concepts_cross_language():
    assert concepts(normalize("На остановке нет навеса")) == concepts(normalize("Аялдамада шатыр жоқ"))
    assert "pothole" in concepts(normalize("yama na doroge"))
    assert "pothole" in concepts(normalize("Жолда үлкен шұңқыр"))
    # место — не понятие: «двор» не должен склеивать разные проблемы
    assert concepts(normalize("Во дворе")) == frozenset()
