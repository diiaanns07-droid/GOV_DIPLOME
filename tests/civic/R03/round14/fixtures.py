"""Фикстуры R03 (раунд 14): СИНТЕТИЧЕСКИЕ данные и крошечная случайная модель для проверки конвейера.

Ничего здесь не является текстами реальных людей: «человеческий» набор — тоже синтетика R03,
просто записанная в формате экспорта web/labeling (birge-labels-v1), чтобы проверить загрузчик.
Крошечная модель (2 слоя, hidden 32, случайные веса, токенизатор обучен на этих фразах) — только
для проверки кода без интернета; её метрики ничего не значат.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

# (категория, язык, шаблон). {p} — место, {t} — время.
TEMPLATES = [
    ("roads", "ru", "На дороге {p} огромная яма, машины бьют колёса {t}"),
    ("roads", "ru", "Разбит асфальт на проезжей части {p}"),
    ("roads", "kk", "Жолда {p} үлкен шұңқыр бар {t}"),
    ("snow_ice", "ru", "Не убран снег {p}, сплошная наледь {t}"),
    ("snow_ice", "ru", "Гололёд {p}, люди падают"),
    ("snow_ice", "kk", "Қар тазаланбаған {p}, көктайғақ {t}"),
    ("sidewalks", "ru", "Тротуар {p} разбит, плитка вздулась"),
    ("sidewalks", "ru", "Нет пандуса {p}, с коляской не пройти"),
    ("sidewalks", "kk", "Жаяу жүргіншілер жолы {p} бұзылған"),
    ("transport", "ru", "Автобус {p} не ходит по расписанию {t}"),
    ("transport", "ru", "На остановке {p} сломан павильон"),
    ("transport", "kk", "Аялдамада {p} автобус келмейді {t}"),
    ("lighting", "ru", "Не горят фонари {p} {t}"),
    ("lighting", "ru", "Темно {p}, освещения нет"),
    ("lighting", "kk", "Шам жанбайды {p}, қараңғы {t}"),
    ("yards", "ru", "Сломаны качели на детской площадке {p}"),
    ("yards", "ru", "Во дворе {p} спилили деревья, нет скамеек"),
    ("yards", "kk", "Аулада {p} балалар алаңы сынған"),
    ("waste", "ru", "Не вывозят мусор {p}, баки переполнены {t}"),
    ("waste", "ru", "Свалка строительного мусора {p}"),
    ("waste", "kk", "Қоқыс шығарылмайды {p} {t}"),
    ("utilities", "ru", "Нет горячей воды {p} {t}"),
    ("utilities", "ru", "В квартире холодно, батареи еле тёплые {p}"),
    ("utilities", "kk", "Су жоқ {p}, жылу берілмейді {t}"),
    ("smell_air", "ru", "Сильный запах гари {p} {t}"),
    ("smell_air", "ru", "Пыль и вонь от свалки {p}"),
    ("smell_air", "kk", "Сасық иіс шығады {p} {t}"),
    ("noise_safety", "ru", "Громкая музыка ночью {p} {t}"),
    ("noise_safety", "ru", "Опасный перекрёсток {p}, нет перехода"),
    ("noise_safety", "kk", "Түнде шу {p}, қауіпті {t}"),
    ("parking", "ru", "Машины паркуются на газоне {p}"),
    ("parking", "ru", "Двор заставлен машинами {p}, не проехать скорой"),
    ("parking", "kk", "Көлік тұрағы жоқ {p} {t}"),
    ("other", "ru", "Спасибо за быстрый ремонт {p}"),
    ("other", "ru", "Подскажите, когда будет приём у акима {t}"),
    ("other", "kk", "Рақмет, бәрі жақсы {p}"),
]
PLACES_RU = ["у дома 5", "возле школы", "на улице Туран", "в микрорайоне", "у рынка", "во дворе дома 12"]
PLACES_KK = ["үйдің жанында", "мектептің қасында", "Тұран көшесінде", "базардың жанында", "аулада"]
TIMES_RU = ["уже неделю", "второй месяц", "с весны", ""]
TIMES_KK = ["бір аптадан бері", "екі айдан бері", ""]


def synth_corpus(n_per_template: int = 6, seed: int = 7) -> list[dict]:
    """Корпус в формате, который ожидается от R02: id, text, label, lang, template_id, split, style."""
    rng = random.Random(seed)
    rows = []
    for ti, (lab, lang, tpl) in enumerate(TEMPLATES):
        split = ("train", "train", "val", "test")[ti % 4] if ti % 3 else "train"
        places, times = (PLACES_RU, TIMES_RU) if lang == "ru" else (PLACES_KK, TIMES_KK)
        seen = set()
        for j in range(n_per_template):
            text = tpl.format(p=rng.choice(places), t=rng.choice(times)).strip()
            if j % 3 == 1:
                text = text.lower()
            if text in seen:
                text = f"{text} {j}"
            seen.add(text)
            rows.append({"id": f"syn-{ti:02d}-{j}", "text": text, "label": lab, "language": lang,
                         "template_id": f"tpl-{ti:02d}", "split": split, "style": "fixture",
                         "evidence": "synthetic_test_fixture"})
    return rows


def human_like(n: int = 60, seed: int = 11) -> list[dict]:
    """«Человеческий» набор — СИНТЕТИКА в формате экспорта web/labeling (birge-labels-v1)."""
    rng = random.Random(seed)
    tails = ["пожалуйста разберитесь", "сколько можно", "очень прошу", "", "срочно", "жители"]
    rows = []
    for i in range(n):
        lab, lang, tpl = TEMPLATES[i % len(TEMPLATES)]
        places = PLACES_RU if lang == "ru" else PLACES_KK
        text = tpl.format(p=rng.choice(places), t="") + " " + rng.choice(tails) + f" №{i}"
        rows.append({"schema": "birge-labels-v1", "id": f"f-fixture{i:04d}", "text": " ".join(text.split()),
                     "lang": lang, "label": lab, "unsure": i % 17 == 0, "annotator": "fixture", "role": "first",
                     "labeled_at": None, "ms": None, "source": "fixture.jsonl"})
    return rows


PROBE_TEXTS = [  # фразы вне TEMPLATES — как probe_v2 у R02 (синтетика, написано вручную)
    ("roads", "ru", "После дождя на перекрёстке асфальт провалился, колесо попало в дыру"),
    ("roads", "kk", "Көпірдің алдында жол ойылып кетті"),
    ("snow_ice", "ru", "Дворники не посыпают дорожки, я вчера упала у подъезда"),
    ("snow_ice", "kk", "Аулада қар үйіліп жатыр, өту мүмкін емес"),
    ("sidewalks", "ru", "Бордюр слишком высокий, коляска не заезжает"),
    ("sidewalks", "kk", "Тротуардағы плиталар сынып қалған"),
    ("transport", "ru", "Сорок минут ждали автобус, табло показывает неправду"),
    ("transport", "kk", "Аялдамада орындық жоқ, қарттар тұрып күтеді"),
    ("lighting", "ru", "Вечером у школы ни одного работающего фонаря"),
    ("lighting", "kk", "Көшеде шамдар жанбайды, түнде қорқынышты"),
    ("yards", "ru", "Горку во дворе разобрали и бросили, детям негде играть"),
    ("yards", "kk", "Аулада ағаштар кесілді, көгал жоқ"),
    ("waste", "ru", "Контейнеры стоят открытые, мусор разносит ветер"),
    ("waste", "kk", "Қоқыс жәшіктері толып кетті"),
    ("utilities", "ru", "Третий день из крана течёт только холодная"),
    ("utilities", "kk", "Үйде жылу жоқ, балалар ауырып жатыр"),
    ("smell_air", "ru", "От канала по вечерам стоит тяжёлый запах"),
    ("smell_air", "kk", "Түнде түтін иісі шығады, терезені ашу мүмкін емес"),
    ("noise_safety", "ru", "Компания под окнами шумит до трёх ночи"),
    ("noise_safety", "kk", "Бұл қиылыста балаларға қауіпті"),
    ("parking", "ru", "Машины встали на газон, весь двор в колеях"),
    ("parking", "kk", "Көліктер жаяу жолға тұрып алды"),
    ("other", "ru", "Благодарю коммунальщиков за оперативную работу"),
    ("other", "kk", "Рақмет, мәселе шешілді"),
]


def probe_like() -> list[dict]:
    """Независимый тест вне шаблонов в формате probe_v2 R02 (split=test, style, hard)."""
    return [{"id": f"probe-fx-{i:02d}", "text": t, "label": lab, "lang": lang, "style": "colloquial",
             "hard": i % 5 == 0, "split": "test", "source": "agent_probe_fixture", "evidence": "synthetic_test_fixture"}
            for i, (lab, lang, t) in enumerate(PROBE_TEXTS)]


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


def build_tiny_model(out_dir: Path) -> Path:
    """Крошечная XLM-R-подобная модель со случайными весами и токенизатором, обученным на фикстурах.

    Спецтокены в порядке XLM-R: <s>=0, <pad>=1, </s>=2, <unk>=3, <mask>=4 — как у xlm-roberta-base,
    чтобы проверить ту же логику паддинга и позиций, что и в настоящей модели.
    """
    from tokenizers import Tokenizer, models, normalizers, pre_tokenizers, processors, trainers
    from transformers import PreTrainedTokenizerFast, XLMRobertaConfig, XLMRobertaForSequenceClassification

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    texts = [r["text"] for r in synth_corpus()] + [r["text"] for r in human_like()]
    tok = Tokenizer(models.Unigram())
    tok.normalizer = normalizers.NFKC()
    tok.pre_tokenizer = pre_tokenizers.Metaspace()
    specials = ["<s>", "<pad>", "</s>", "<unk>", "<mask>"]
    trainer = trainers.UnigramTrainer(vocab_size=600, special_tokens=specials, unk_token="<unk>")
    tok.train_from_iterator(texts, trainer)
    tok.post_processor = processors.TemplateProcessing(
        single="<s> $A </s>", pair="<s> $A </s> </s> $B </s>",
        special_tokens=[("<s>", tok.token_to_id("<s>")), ("</s>", tok.token_to_id("</s>"))])
    assert [tok.token_to_id(s) for s in specials] == [0, 1, 2, 3, 4]
    fast = PreTrainedTokenizerFast(tokenizer_object=tok, bos_token="<s>", eos_token="</s>", unk_token="<unk>",
                                   pad_token="<pad>", mask_token="<mask>", cls_token="<s>", sep_token="</s>",
                                   model_max_length=64)
    fast.save_pretrained(out_dir)
    cfg = XLMRobertaConfig(vocab_size=tok.get_vocab_size(), hidden_size=32, num_hidden_layers=2,
                           num_attention_heads=2, intermediate_size=64, max_position_embeddings=80,
                           pad_token_id=1, bos_token_id=0, eos_token_id=2, num_labels=12)
    import torch
    torch.manual_seed(0)
    XLMRobertaForSequenceClassification(cfg).save_pretrained(out_dir)
    return out_dir
