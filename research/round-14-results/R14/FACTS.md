# Birge · ключевые цифры проекта с источниками (FACTS)

> Роль R14, раунд 14. Для диплома, презентации и заявки Gton.
> **Правило:** в текст диплома и на слайды попадают только числа из этой таблицы (или из файлов, на которые она ссылается).
> Каждое число — с источником: файл, ветка, SHA. Если число меняется в новой поставке — обновить строку и SHA.
> Срез: 10 октября 2026, обновлено ночью 10→11.10 (результаты LOCAL-4 R03 c19b889, сборка B2 R01 f54361d, приёмка R10 B2,
> ревью R15, приёмка LOCAL B2 на Windows). Ветки ролей — на момент чтения (git show, без запуска кода, если не сказано иное).
> Пометки: **real** — реальные данные (OSM, Open-Meteo); **synthetic** — синтетика; **derived** — вычислено из real;
> **demo** — учебные данные ТЗ хакатона; **NOT_RUN / NOT_EVALUATED** — измерения ещё нет.

Сокращения веток: `pkg` = `claude/round-14-package`; `R01` = `claude/sharp-dijkstra-0t87gl`; `R02` = `claude/r14-R02`;
`R03` = `claude/r14-R03`; `R04` = `claude/r14-R04`; `R05` = `claude/r14-R05`; `R06` = `claude/round-14-r06`;
`R07` = `claude/upbeat-knuth-i0rqaa`; `R08` = `claude/r14-R08`; `R09` = `claude/modest-shannon-0ki93p`;
`R10` = `claude/r14-R10`; `R11` = `claude/r14-R11`; `R12` = `claude/tender-brahmagupta-ef5ztl`; `R13` = `claude/r14-R13`;
`R15` = `claude/r14-R15`;
`v1` = `claude/wizardly-ptolemy-qy8ltw`.

## 1. Продукт и сценарий

| Факт | Значение | Источник |
|---|---|---|
| Продукт | Birge — платформа обратной связи жители ↔ акимат Астаны | `research/round-14/CONTRACT.md` §0, pkg @ 4bbf456 |
| Сценарий демо | 6 шагов: жалоба → категория и «Я тоже» → тепловая карта → картина дня → предложение с 3D и голосом → «исправлено»; 3 минуты | там же |
| Фокус-район | Нура | там же |
| Категорий обращений (v2) | 12: roads, snow_ice, sidewalks, transport, lighting, yards, waste, utilities, smell_air, noise_safety, parking, other | `research/round-14/categories_v2.json`, pkg @ 4bbf456 |
| Категорий v1 | 6: roads, sidewalks, transport_stops, lighting, landscaping, other | `ml/civic_classifier/labels.py`, v1 @ 14c3384 |
| Уровни тепловой карты | 5 (0; 1–2; 3–5; 6–9; 10+) + «исправлено» 7 дней | `categories_v2.json` → `heat_levels`, `fixed_state` |
| Период полураспада веса жалобы | 14 дней: вес = 0.5^(возраст/14) | `CONTRACT.md` §6; `categories_v2.json` |
| Кейсы Gton, которые закрывает сценарий | «ЕКЦ 109+», «Единая карта инфраструктурных объектов», «Предиктивная аналитика проблем региона» (60–70 % прогнозов подтверждаются, 10–30 территорий) | `research/round-14/prompts/R06.txt`, `R08.txt`, `R13.txt`, pkg — формулировки из заданий, **сверить с официальным текстом Gton** |

## 2. Открытые данные Астаны (real / derived)

| Факт | Значение | Источник |
|---|---|---|
| Наборов OSM-объектов (LOCAL-1) | 12 | `data/civic/astana/osm-objects/SOURCE.json`, `README.md`, pkg @ 4bbf456 |
| Уникальных OSM-объектов | 3 513 (записей по наборам 4 192), архивы 317 868 Б | там же |
| Дата снимка OSM (osm_base) | 2026-10-10 13:01–13:09 UTC | там же |
| Лицензия | ODbL 1.0, «© OpenStreetMap contributors» | там же |
| Остановок в наборе геоданных | 940 (real, derived) | `data/civic/astana/geo/SOURCE.json`, R12 @ 8bb7bf8 (код 8810221) |
| Детских площадок | 334 | там же |
| Спортплощадок | 696 | там же |
| Парков и скверов | 177 (из них garden 51) | там же |
| Мест сбора мусора | 136 (из них recycling 40) | там же |
| Дворов (landuse=residential) | 538 (у 290 есть название) | там же |
| Всего объектов в geo-наборе | 2 283 | `data/civic/astana/geo/objects.json`, R12 — подсчёт R14 |
| Отброшено при сборке | вне города 108, без геометрии 13, дубли 697 | `data/civic/astana/geo/SOURCE.json`, R12 |
| Остановок без названия | 403 | там же, `known_limits` DELIVERY R12 |
| Пешеходный граф улиц | 66 027 узлов, 94 089 рёбер, снимок OSM 2026-05-06, 28.8 МБ | `engine/civic_scenarios/graphs/MANIFEST.json`, pkg |
| Рёбер с названием улицы | 20 289; суммарная длина ≈ 7 394 км | там же — подсчёт агента R14 по файлу графа |
| Линий OSM с тегами улиц | 34 380 (23 класса highway) | `data/civic/astana/geo/way_tags.json`, R12 |
| Районов на карте | 6 (Алматы, Байконур, Есиль, Нура, Сарайшык, Сарыарка), отношения OSM, osm_base 2026-09-22 | `data/civic/astana/geofence.json`, `data/astana_districts.geojson`, pkg |
| Погода (Open-Meteo, LOCAL-9) — real (реанализ, не наблюдения станций) | 1 378 дней 2023-01-01…2026-10-09, точка 51.13 N 71.43 E, 7 суточных показателей (t max/min, осадки, снег, дождь, ветер, глубина снега), пропусков 0; CSV 58 557 Б; лицензия CC BY 4.0 «Weather data by Open-Meteo.com» | `data/civic/astana/weather/SOURCE.json`, pkg @ a2ff96e |
| Реальные работы в Нуре (LOCAL-5) | **нет файла**: `data/civic/astana/nura-real/` отсутствует | поиск по origin/* |
| Подтверждённых реальных записей работ (раунд 13) | 0; кандидатов к проверке 44 | `data/civic/astana/round13-verified/`, ветка `claude/fervent-dijkstra-1cqrg5` @ a995f9f |

## 3. Точность карты (R12)

| Факт | Значение | Источник |
|---|---|---|
| Проверок точности | 954 PASS / 0 FAIL | `research/round-14-results/R12/accuracy_report.json`, R12 tested d13f49a |
| Допуски | линия участка ≤ 5 м от формы ребра (шаг проверки 2 м); остановка ≤ 60 м от улицы; координаты внутри геозабора | `engine/civic_geo/accuracy.py`; `CONTRACT.md` §8 |
| Расстояние «остановка → улица» | медиана 9.8 м, p95 18.0 м, максимум 34.7 м (940 остановок) | `accuracy_report.json`, R12 — подсчёт агента R14 |
| Перекрытие ул. Сакена Сейфуллина | было 3 точки «от руки» (конец ~32 м от оси); стало 528.2 м по 13 рёбрам графа, отклонение 0.00 м, отношение длин 0.999 | `research/round-14-results/R12/DELIVERY.json`; `data/civic/astana/geo/demo_snapped.json`, R12 |
| Скорость `/targets` | p50 0.23 мс, p95 0.61 мс, max 3.64 мс на 3 000 точек; загрузка 1.92 с | `research/round-14-results/R12/targets_bench.json`, R12 |
| Радиусы поиска цели | объект 150 м, участок улицы 80 м, двор 40 м; ячейка 150 м | `engine/civic_geo/targets.py`, `objects.py`, R12 код 8810221 |
| Тесты R12 | pytest 29/29; ядро карты 29/29; браузер карты 69/69; приёмка в приложении 12 PASS / 0 FAIL / 1 NOT_RUN (подложка OpenFreeMap — 403 в облаке) | `research/round-14-results/R12/DELIVERY.json`, `runs/app_acceptance_map_d13f49a.json` |
| Независимая проверка R10 (CONTRACT §8, по веткам) | R07, R12-объекты, R13, R06, сборка R01 — PASS; **FAIL**: R12 `yards.json` — двор `yard-619707707` частично за границей (19 из 26 вершин; проверяется только центр); R05 `astana-existing.json` — 41 ж/д платформа как «остановка», 55 точек и 22 двора за границей | `research/round-14-results/R10/accuracy/README.md`, `BUGS.md` B-007…B-009, R10 @ e73f1e8 |
| Проверка R10 на сборке B2 (f54361d) | `accuracy.py`: **24 PASS / 4 FAIL**; pytest 31 passed / 4 failed. FAIL — те же B-007 (41 ж/д платформа, 2 дальше 60 м от улицы), B-008 (337 координат R05 за границей), B-009 (19 вершин двора R12) | `research/round-14-results/R10/ACCEPTANCE_B2.md`, `accuracy/B2-f54361d.json`, R10 @ ac8508e |
| Геометрия на Windows (LOCAL B2, независимый расчёт) | участки R07: 26, худшее отклонение от оси улицы **0.066 м**; линия предложения R05 — 0.06 м; линия демо-проекта R06 — 0 м (допуск 5 м) | `research/round-14-results/LOCAL/LOCAL_B2.md`, pkg @ a38da11 |
| Привязка 3D к карте (LOCAL B2) | расхождение основания модели Three.js и точки MapLibre в 12 положениях камеры (наклон 0–60°, азимут −16…40°): максимум **1.51·10⁻⁸ px** | там же, `screens/B2/extra/EXTRA.json` |

## 4. Корпуса обращений (R02) — всё synthetic, кроме формы

| Факт | Значение | Источник |
|---|---|---|
| synth_v3 (шаблонная синтетика) | 4 260 текстов из 221 шаблона; train/val/test 2 659 / 945 / 656; ru 2 060, kk 1 542, mixed 658; seed 20261011 | `ml/datasets/synth_v3/data/manifest_v3.json`, R02 @ 73b97d2 (код f62cc93) |
| synth_v3: удалено точных повторов | 212 (из 4 472); почти-повторов по Jaccard 3-грамм ≥ 0.8 — 0 | там же |
| synth_v3: обезличено | [телефон] 128, [email] 70, [адрес] 489 | там же |
| Пары перефразов для дублей | 781 (dev 363 / test 418; совпадение 391 / несовпадение 390), в т. ч. межъязыковые ru↔kk 184 | `ml/datasets/synth_v3/data/paraphrase_pairs_v3.jsonl`, R02 |
| v1_in_v2 (корпус раунда 12 в категориях v2) | 2 725 текстов; ru 1 461, kk 1 041, mixed 223; меток, изменённых правилами v2, 393; smell_air 0, parking 5 | `ml/datasets/v1_in_v2/manifest_v1_in_v2.json`, R02 |
| probe_v2 (написан вручную агентом, synthetic_agent_written) | 300 = 25 × 12; ru 155, kk 97, mixed 48; трудных 94 | `ml/datasets/probe_v2/manifest_probe_v2.json`, R02 |
| llm_v1 (LLM-синтетика, synthetic_llm) | 3 979 текстов (запрошено 4 000; 199 из 200 запросов разобраны); OpenAI gpt-4.1-mini, температура 0.9, 20 текстов на запрос; train/val/test 2 781 / 719 / 479; ru 1 940, kk 1 360, mixed 679; метка = запрошенная категория, людьми не проверена; дубликатов и совпадений с v3 — 0 | `ml/datasets/llm_v1/manifest_llm_v1.json`, R02 @ 2a95286 |
| llm_v1: стоимость | **$0.278** (200 платных вызовов; 67 606 токенов на вход, 156 679 на выход; бюджет $3) | там же (`budget`) |
| human_form (тексты людей) | **собирается** (цель 200–400 к 13.10); в Git не попадает | `DATASHEET.md` §6, R02 |
| Тесты R02 | pytest 89 PASS; node 12 + 7 PASS | `research/round-14-results/R02/DELIVERY.json` |

## 5. Классификатор (v1, v2)

Прогон LOCAL-4: ноутбук владельца (RTX 4060), код R03 477f97b, корпуса R02 @ 2a95286, результаты — коммит **c19b889**
(ветка R03); разбор и model card — d472baf; поставка — c2b4dda. Сокращение «R03-res» = `ml/civic_classifier_v2/results/`
на ветке R03 @ c2b4dda. **Всё ниже — synthetic или synthetic_agent_written; на текстах людей — NOT_EVALUATED.**

| Факт | Значение | Источник |
|---|---|---|
| v1: macro-F1 на синтетическом test (невиданные шаблоны, n = 631) | 0.871 [0.780–0.928] (логрегрессия + словарь) против 0.848 [0.745–0.912] у словаря; разница +0.022 [−0.048; +0.096] — **не доказана** | `ml/civic_classifier/MODEL_CARD.md`, v1 @ 14c3384 |
| v1: macro-F1 на пробном наборе (n = 112) | 0.837 [0.767–0.896] | там же |
| v2: модель | `FacebookAI/xlm-roberta-base`, 278.1 млн параметров (192.0 млн — словарь эмбеддингов), все обучаются | `final_model_meta.json` (`env.params_total`), R03-res |
| v2: гиперпараметры | lr 2e-5, batch 16 × grad_accum 2, до 8 эпох, patience 2, max_length 128, fp16, веса классов sqrt_inv, seed 20261011, 1 seed | `final_model_meta.json` (`train_config`), R03-res |
| LOCAL-4: среда и время | RTX 4060 Laptop 8 ГБ, Windows, Python 3.12.10, torch 2.14.1+cu126; пик GPU 5.23 ГБ; эпоха 40–60 с; все этапы 1 621 с (≈ 27 мин) + 220 с диагностика ONNX | `RESULTS.md` («Замечания прогона»), `train_log_*.jsonl`, R03-res |
| LOCAL-4: что выполнено | 4 синтетических режима × 3 модели = 12 конфигураций; режимы human/mix и LLM zero-shot — **NOT_RUN по решению владельца** | `RESULTS.md`, `experiments.json`, R03-res |
| **Итоговая модель на probe_v2 (300 текстов вне шаблонов)** | **macro-F1 0.828 [0.778–0.865]**, accuracy 0.827 [0.780–0.867]; рецепт synth_all (v3 + LLM), выбран правилом RUN.txt, не по probe | `final_model_meta.json` (`probe_v2_eval`), R03-res; `MODEL_CARD.md` R03 @ d472baf |
| Итоговая модель: версия, обучение | `civic-clf-v2-xlm-roberta-base-synth_all-daaa6dae4-s20261011`; train 5 440 (v3 2 659 + LLM 2 781), val 1 664; лучшая эпоха 7, val macro-F1 0.909 | там же |
| Итоговая модель: по языкам (probe_v2) | kk 0.806 (n = 97), ru 0.834 (n = 155), mixed 0.853 (n = 48) | там же (`slices.lang`) |
| Итоговая модель: по стилю / трудные | короткие 0.971, длинные 0.943, официальные 0.895, разговорные 0.793, опечатки 0.762, сленг 0.761, **транслит 0.606** (n = 24); трудные 0.702 (n = 94) против 0.858 | там же (`slices.style`, `slices.hard`) |
| Эксперимент на probe_v2: трансформер | v1→v2 0.450 · v3 0.685 · LLM 0.748 · **v3 + LLM 0.812 [0.763–0.850]** | `RESULTS.md` раздел 1б, R03-res |
| Эксперимент на probe_v2: логрегрессия | 0.534 · 0.751 · 0.746 · 0.797 [0.746–0.838] | там же |
| Эксперимент на probe_v2: словарь | 0.684 [0.628–0.726] (не обучается) | там же |
| Парные Δ на probe_v2 | v3 + LLM: трансформер − логрегрессия **+0.015 [−0.034; +0.068] — не доказано**; трансформер − словарь +0.128 [+0.070; +0.189]; только v3: трансформер − логрегрессия −0.065 [−0.126; −0.009]; трансформер: LLM − шаблоны +0.063 [+0.011; +0.117]; v3 − v1→v2: трансформер +0.235, логрегрессия +0.217 | `RESULTS.md` раздел 3, R03-res |
| По языкам на probe_v2 (v3 + LLM) | трансформер kk 0.803 / ru 0.816 / mixed 0.813; логрегрессия 0.767 / 0.816 / 0.789; словарь 0.684 / 0.684 / 0.650 | `experiments.json` (`slices.lang`), R03-res — выборка R14 |
| Транслит на probe_v2 (n = 24) | трансформер v3 + LLM 0.528; логрегрессия 0.458; словарь 0.013 | там же (`slices.style`) |
| Слабые категории (трансформер v3 + LLM, probe_v2) | noise_safety F1 0.714, roads 0.724, sidewalks 0.750; лучшие — waste и other 0.889, snow_ice 0.870 | `RESULTS.md` раздел 4б |
| Калибровка | ECE 0.144 на probe_v2 — score завышен | там же |
| Переобучение на шаблоны | трансформер только на v3: loss 0.03, val 0.756, test v3 **0.482** [0.333–0.612]; sidewalks и parking F1 0.00 на test v3 | `MODEL_CARD.md` R03 @ d472baf, `RESULTS.md` раздел 2 |
| Синтетический test завышает | модель на LLM-синтетике: test LLM 0.899 → probe 0.748 («потеря вне шаблонов» +0.151); v3 + LLM: test LLM 0.913 → probe 0.812 | `RESULTS.md` раздел 2 |
| Независимость probe_v2 | Jaccard 3-грамм к ближайшему обучающему: llm_v1 медиана 0.17 / max 0.37; synth_v3 медиана 0.17 / max 0.56; ≥ 0.6 нет | `MODEL_CARD.md` R03 @ d472baf, вывод 8 |
| Воспроизводимость | словарь и логрегрессия: облако (Linux) и ноутбук (Windows) — одинаковые числа (логрегрессия на v3: 0.632 [0.494–0.771] в обоих) | `RESULTS.md` облачный (git 762c6a0) и LOCAL-4 (c19b889) — сравнение R14 |
| Порог «нужна проверка» | 0.30: на синтетической val 92.2 % автоподсказок при точности 0.902; пока нет оценки на людях — `needs_review = true` всегда | `final_model_meta.json` (`threshold_detail`), `predict.py`, R03 |
| ONNX fp32 | совпадение top-1 с PyTorch 100 %, max \|Δp\| 9·10⁻⁶; 1 060.9 МБ | `onnx_export.json`, R03-res |
| ONNX int8 (штатный экспорт 477f97b) | 265.8 МБ; совпадение 96.5 % — FAIL (< 97 %); 102.9 мс на текст при 24 потоках — FAIL (< 50 мс) | там же (`verdict`) |
| ONNX int8 per-channel, 4 потока (диагностика) | совпадение 98 %; 22.7 мс в среднем, p95 32.9 мс — PASS; с d472baf это умолчание | `onnx_export.json`, `MODEL_CARD.md` R03 @ d472baf |
| Модель в сборке на Windows (LOCAL B2) | `source=v2`, per-channel int8: текст «Аялдамада жарық жоқ, вечером на остановке темно» → lighting, score 0.9939; один HTTP-замер 155 мс | `research/round-14-results/LOCAL/LOCAL_B2.md`, pkg @ a38da11 |
| Повторный экспорт с d472baf на ноутбуке; int8 на probe_v2 | **NOT_RUN** (RUN.txt R03 шаги 8 и 8б) | `research/round-14-results/R03/DELIVERY.json` @ c2b4dda |
| Качество на текстах людей | **NOT_EVALUATED** — шаги с текстами людей не запускались | там же |
| Тесты R03 | 66/66 (полная среда, torch CPU); 59 PASS + 7 NOT_RUN без torch/sklearn/onnx; на ноутбуке перед LOCAL-4 — 65 PASS | там же |

## 6. Поиск дублей и ML-API (R04) — сдан (code deeb1de), числа на синтетике

| Факт | Значение | Источник |
|---|---|---|
| Метод (запасной, работает всегда) | символьные n-граммы 3–5 + двуязычный словарь понятий (48 тем), α = 0.3; порог 0.18 (с местом) / 0.40 (только текст) | `ml/civic_dedup/dedup_config.json`, R04 @ 94bd9ac (код deeb1de) |
| Метод (основной, ждёт весов) | эмбеддинги `intfloat/multilingual-e5-base` в ONNX; порог не подобран (null) | там же |
| Правило «похоже» | сходство ≥ порога И (та же цель ИЛИ ≤ 200 м) И не старше 14 дней И статус new/accepted/in_progress | `ml/civic_dedup/search.py`, R04 |
| Качество на test-парах (с геофильтром, n = 320) | P 0.880 [0.833; 0.922], R 0.906 [0.863; 0.945], F1 0.893 | `research/round-14-results/R04/DELIVERY.json` (`metrics`), `ml/civic_dedup/results/dedup_eval_ngram.json` |
| Качество на test-парах (только текст, n = 418) | P 0.616 [0.559; 0.676], R 0.906, F1 0.734 | `ml/civic_dedup/results/dedup_eval_ngram.json`, R04 |
| По видам пар (test) | ru↔kk перефраз — полнота 0.875; «та же проблема, другое место» верно отклонено 0.092 | там же (`test_by_kind`) |
| Цепочка classify (без v2): точность на synth_v3 test | 0.784 (v1 одна 0.518; словарь 0.745) — метрика accuracy, не macro-F1 | `research/round-14-results/R04/classify_eval.json`, R04 @ 243526f |
| Скорость (облако, 4 vCPU) | classify p95 0.36 мс; similar p95 8.2 мс по городу, 39.3 мс в «горячей точке» на 5 000 синтетических жалоб; первый запрос без прогрева ~155 мс | `research/round-14-results/R04/DELIVERY.json` (`speed_cloud_cpu_ms`) |
| Тесты R04 | вместе с R03 — 137 passed / 6 skipped; весь `tests` с копиями соседей — 967 passed / 4 skipped | `research/round-14-results/R04/DELIVERY.json` |

## 7. Прогноз (R13) — прототип, сдан (code 8705829), всё на синтетической истории

| Факт | Значение | Источник |
|---|---|---|
| Территорий для прогноза | 2 334 (остановки 940, площадки 334, парки 177, мусор 136, дворы 538, участки улиц 209) — real (OSM через R12) | `ml/civic_forecast/data/targets.json`, R13 @ 8746927 |
| Синтетическая история | 34 месяца (2024-01…2026-10) × 12 категорий, Пуассон с сезонностью; seed 2026 (+2027, 2028 в backtest) | `ml/civic_forecast/history.py`, R13 |
| Погода в backtest | **синтетическая фикстура** 1 378 дней (seed 14), не Open-Meteo; реальный архив скачан позже (§2, pkg @ a2ff96e) — повтор backtest с ним **NOT_RUN** (голова R13 8746927 не менялась) | `ml/civic_forecast/data/weather_fixture.SOURCE.json`, R13 |
| Цель прогноза | ≥ 4 жалоб на территории в следующем месяце; доля таких территорий 3.3 % (≈ 77 в месяц) | `ml/civic_forecast/RESULTS.md`, R13 |
| Backtest | 48 прогнозов (16 месяцев 2025-07…2026-10 × 3 seed), обучение только на прошлом | там же |
| precision@10 / @20 / @30 — градиентный бустинг | 0.58 / 0.49 / 0.44 | там же; `research/round-14-results/R13/DELIVERY.json` |
| — бустинг без погоды | 0.58 / 0.50 / 0.44 | там же |
| — запасная (сезонная наивная + частота) | 0.55 / 0.49 / 0.44 | там же |
| — «как в прошлом месяце» | 0.47 / 0.40 / 0.35 | там же |
| — «тот же месяц год назад» | 0.38 / 0.33 / 0.31 | там же |
| — случайный выбор | 0.03 | там же |
| Выигрыш бустинга над лучшим базовым (по месяцам) | +0.062 / +0.068 / +0.061; лучше в 26/30/34 из 48 месяцев | там же |
| Ориентир Gton 60–70 % | **не достигнут** на синтетике | там же |
| Вклад погодных признаков | −0.004 (≈ 0): известна только норма месяца, она дублирует сезон | там же |
| `forecast()` | из кэша < 1 мс; холодная загрузка ~30 мс; месяц вне кэша ~3.5 с один раз | `research/round-14-results/R13/DELIVERY.json` |
| Тесты R13 | 30 passed / 7 skipped (без шлюза); 37/37 со шлюзом R01 @ d3c33d9 + patch | там же |

## 8. Хакатонный предшественник «Аким на 5 часов» (demo, данные ТЗ)

| Факт | Значение | Источник |
|---|---|---|
| Модель | 5 районов, 10 показателей, 14 мер, бюджет 100 у.е., горизонт 8 кварталов | `data/city_data.json`, `README.md`, pkg |
| Эталоны | базовый Score 52.56, пример ТЗ 56.54 | `README.md`, `check.py` |
| Полный перебор | 1 407 050 сценариев | `README.md` |
| События | 8 кризисных событий | `data/events.json` |
| Тесты (сентябрь 2026) | 112 автотестов движка | `README.md` |

## 9. Среда

| Факт | Значение | Источник |
|---|---|---|
| Ноутбук для обучения | NVIDIA GeForce RTX 4060 Laptop 8 ГБ, CUDA 12.6, Python 3.12.10, torch 2.14.1+cu126, transformers 5.19.0 | `research/round-14-results/LOCAL/ENV.md`, pkg |
| three.js | 0.169.0, MIT | `web/vendor/three/SOURCE.txt`, pkg |
| MapLibre GL JS | 5.6.2, BSD-3 | `web/vendor/maplibre-gl.js`, pkg |

## 10. Сборка и сервер (R01)

Сборки R01: B1-кандидат d3c33d9 (документы e9b34a6); **B2-кандидат f54361d (код b5c153d)**; после B2 — шаги B3
a8fabce → be82fa8 → 7227fce → d9a8895 (голова `claude/sharp-dijkstra-0t87gl` = `claude/r14-R01` на ночь 10→11.10;
DELIVERY R01 описывает B2, для B3 — только сообщения коммитов).

| Факт | Значение | Источник |
|---|---|---|
| Сервер | `ui/web_server.py`, только стандартная библиотека, `ThreadingHTTPServer`; порт 8501 (`run.bat`) / 8611 (`run-city.bat`, `CIVIC_DEMO=1`) | R01; `run-city.bat`, pkg |
| Маршрутов API | civic v1 — 30; civic v2 — 14 по CONTRACT §7 на B1; **на B2 — 37 маршрутов v2, все `ready`** | `ui/web_server.py`; `GET /api/civic/v2/modules` — запуск R14 на f54361d |
| Состав B2 | R11 6102dfb, R02 229f1aa, R07 5a97636, R08 4ce8f08, R09 fa49fc9, R12 d13f49a, R06 7031afa, R05 b0353ee, R13 8705829, R04 deeb1de, R03 252913e (без весов) | `research/round-14-results/R01/DELIVERY.json` (`restored_from`), R01 @ f54361d |
| B2: весь pytest | **2 377 passed / 20 skipped / 1 xfailed** (skip — нет torch/sklearn/onnx в облаке и одна устаревшая копия теста; xfail — ждёт демо-набор R07) | `research/round-14-results/R01/BUILD_LOG.md` «B2 — проверки», DELIVERY R01 |
| B2: весь pytest, повтор R14 | **2 377 passed / 20 skipped / 1 xfailed за 256 с** — совпадает с отчётом R01 | `python3 -m pytest -q tests` в рабочей копии f54361d, Linux, Python 3.13.16, pytest 9.1.1 |
| B2: браузер | путь демо B1 15/0; путь демо B2 17/0 на b5c153d и **20/0** с путём жителя через R12/R04; шапка 38/0, город 81/0, сценарии 16/0, пустой реестр 15/0; P0 62/1/2 (1 FAIL — давняя гонка `demo-ring` модуля карты, есть и на I0) | там же |
| B2: запуск R14 | `civic-v2: ready R04, R06, R07, R08, R09, R12, R13`; 37/37 маршрутов ready; `/targets` 2.6 мс, `/heat` 25 мс, `/akim/summary` 27 мс, `/forecast` 23 мс, `/proposals` 2 мс (первые вызовы); `/classify` без весов — `source: kw` (словарь), `needs_review: true` | запуск R14 на f54361d, Linux, Python 3.13.16, `CIVIC_DEMO=1` |
| Голова R01 d9a8895 (B3 шаг 4): запуск R14 | 37/37 маршрутов ready; при `CIVIC_DEMO=1` сервер сам создаёт 5 синтетических демо-проектов R06 (ручной шаг `seed-r14-demo` больше не нужен) | запуск R14 на d9a8895 |
| B3 шаги (после B2, без DELIVERY) | a8fabce — R06 b42e790, R07 306074b; be82fa8 — R11 52d7c59, R02 f62cc93, R10 9c364c7, R14 8e106a9; 7227fce — офлайн-подложка из осей улиц OSM, демо-проекты при старте, UX-правки по R10/R11; d9a8895 — R03 d472baf (model card LOCAL-4, ONNX-умолчания, без весов) | сообщения коммитов R01 |
| B3 be82fa8: весь pytest (R15) | 2 429 passed, 7 failed, 23 skipped, 1 error — падения старые (стыки R07 ↔ R09/R12/R08 после повторной поставки R07, I-01…I-03 в `BUGS.md` R01), не от патчей R15 | `research/round-14-results/R15/DELIVERY.json` |
| Словари в сборке | B2: 557 ключей ru = kk; d9a8895: 563; ветка R11 (ночь): 665 | `web/civic/i18n/*.json` — подсчёт R14 |
| Кандидат B1 (d3c33d9), для истории | весь pytest 1 793 passed / 11 skipped; путь демо B1 15/0 | DELIVERY R01, `BUILD_LOG.md` |

## 11. Модули интерфейса и сервиса

| Факт | Значение | Источник |
|---|---|---|
| R09: маршрутов жалобы v2 | 11 | `ui/civic_feedback/v2/api.py`, R09 @ e012f73 (код a4ab5a4) |
| R09: шагов мастера жителя | 5 | `web/civic/feedback/complaint.js`, R09 |
| R09: лимит | 20 жалоб в час с устройства | `ui/civic_feedback/v2/store.py`, R09 |
| R09: тесты (поставка fa49fc9, в B2) | pytest v2 89 passed / 2 skipped; папка вместе с тестами помощника 211 passed; браузер 106/106 (заглушки) и **107/107 с настоящими R12 `/targets` и R04 `/classify`, `/similar`** | `research/round-14-results/R09/DELIVERY.json`, R09 @ 5dd6465 |
| R07: вес цели | Σ (1 + metoo)·0.5^(возраст/14); уровни 1/3/6/10; районы — пороги × 5; «исправлено» 7 дней | `ui/civic_heat/engine.py`, `config.py`, R07 @ 3eb3f9d (код 5a97636) |
| R07: смысловой зум | z < 12 — районы; значки с числом при z ≥ 15 | `ui/civic_heat/service.py`, `web/civic/heat/heat.js`, R07 |
| R07: скорость | 6 500 жалоб за 90 дней < 300 мс (тест); кэш 60 с | `tests/civic/R07/test_r07_heat.py`, `service.py`, R07 |
| R07: демо | 136 синтетических жалоб, 241 человек, 45 реальных целей OSM | `ui/civic_heat/demo_seed.py`, `research/round-14-results/R07/RUN.txt`, R07 |
| R07: тесты | в B2 (5a97636): pytest 97 PASS, браузер 16 PASS; повторная поставка 306074b (в B3): pytest 108 passed / 3 skipped, браузер 29/29 | `research/round-14-results/R07/DELIVERY.json`, R07 @ 35e6feb |
| R08: картина дня | 4 KPI, топ-10 горячих мест из тепловой карты за 7 дней, 12 сроков исправления (демо-норматив), сводка ru/kk шаблоном без LLM, кэш 30 с | `ui/civic_akim/summary.py`, `deadlines.py`, `text.py`, R08 @ a4189ba (код 9f1d9c0) |
| R08: тесты (поставка 2, 4ce8f08, в B2) | pytest 126 PASS + 1 XFAIL (ждёт правдоподобный демо-набор R07); UI 95/95 | `research/round-14-results/R08/DELIVERY.json`, R08 @ 7101f46 |
| R06: этапы | 6: planned → design → procurement → construction → acceptance → operating; stale > 14 дней | `ui/civic_store/stages.py`, R06 @ 3d10f7d (код 7031afa) |
| R06: база | миграция 6 — 6 новых таблиц; история только дополняется (триггеры) | `ui/civic_store/db.py`, R06 |
| R06: голос | один с устройства (sha256 соль + id); 30 голосов в минуту с адреса | `ui/civic_store/proposals.py`, R06 |
| R06: тесты | в B2 (7031afa): 445 passed / 5 skipped, round14 66 / 4, браузер 48/48; поставка 2 b42e790 (в B3): 467 passed / 7 skipped, через шлюз R01 B2 5/5, клиент R05 17/17, браузер 83/83 | `research/round-14-results/R06/DELIVERY.json`, R06 @ 6b9da27 |
| R05: объекты 3D | 5 видов (сквер 40×30 м, детская площадка, спортплощадка, остановка, освещение — опоры через ~30 м), лимит 20, анимация 1.2 с | `web/civic/build3d/build3d-core.js`, `build3d.js`, R05 @ e533e67 (код b0353ee) |
| R05: точность 3D | смещение якоря 0.000 px при наклоне 0–60° и повороте; освещение ≤ 0.5 м от рёбер | `research/round-14-results/R05/runs/browser_check.json`, DELIVERY R05 |
| R05: тесты | node 25/25, python 9/9, браузер 25 PASS / 1 NOT_RUN (плавность на GPU) | `research/round-14-results/R05/DELIVERY.json` |
| R11: дизайн-система | ~48 компонентов `bk-*`, 49 иконок, шрифт Inter 4.0 (OFL) «Birge Sans» | `web/civic/ui-kit/`, R11 @ cc77761 |
| R11: словари | 509 ключей (день 2) → 563 (день 4, в сборке d9a8895) → **665 ключей ru = 665 kk** (ночь 10→11.10, +102 ключа из сборки); проверка `i18n_tools check` PASS; ⚑ места для проверки владельцем — `KK_REVIEW.md` | `web/civic/i18n/*.json`, R11 @ 8451468 — подсчёт R14 |
| R11: контраст | текст 14.8:1, вторичный 5.7:1, бренд 6.5:1; значки 9.5 / 6.8 / 5.0 / 7.1, «исправлено» 4.9 | `research/round-14-results/R11/UX_SPEC.md` §2 |

## 12. Повторный запуск тестов R14 (облако: Linux, Python 3.13.16, pytest 9.1.1, Node 22.22.0, без torch/sklearn)

| Роль @ SHA | Команда | Результат R14 | По DELIVERY |
|---|---|---|---|
| R02 @ f62cc93 | `python3 -m pytest -q tests/civic/R02/round14` | 89 passed | 89 PASS |
| R03 @ 847bf31 | `python3 -m pytest -q tests/civic/R03/round14` | 58 passed, 7 skipped | 58 + 7 NOT_RUN без torch/sklearn/onnx |
| R05 @ b0353ee | `node --test …/test_core.mjs …/test_models.mjs`; `python3 -m unittest discover -s tests/civic/R05/build3d -p "test_*.py"` | 25 pass; 9 OK | 25/25; 9/9 |
| R06 @ 7031afa | `python3 -m pytest -q tests/civic/R06/round14` | 66 passed, 4 skipped | 66 / 4 |
| R07 @ 5a97636 | `python3 -m pytest -q tests/civic/R07` | 98 passed | 97 PASS |
| R08 @ 9f1d9c0 | `python3 -m pytest -q tests/civic/R08` | 101 passed, 1 skipped (R07 нет в дереве) | 100 + 1 SKIP без R07 |
| R09 @ a4ab5a4 | `python3 -m pytest -q tests/civic/R09/test_r09v2_{store,migrate,api,frontend,stand_osm}.py` | 83 passed | 83 PASS |
| R11 @ cc77761 | `python3 tests/civic/R11/i18n_tools.py check`; `pytest tests/civic/R11/test_r11_ui_kit.py` | PASS; 14 passed | PASS |
| R12 @ d13f49a | `python3 -m pytest -q tests/civic/R12/test_civic_geo.py`; `python3 -m engine.civic_geo report` | 29 passed; 954/954 PASS | 29/29; 954/954 |
| R01 @ bc7c961 | `python3 -B app.py --port 8711 --civic-db <tmp>` | старт OK, см. §10 | — |
| **R01 B2 @ f54361d** | `python3 -m pytest -q tests` | **2 377 passed, 20 skipped, 1 xfailed** (256 с) | 2 377 / 20 / 1 xfailed |
| R01 B2 @ f54361d и d9a8895 | `CIVIC_DEMO=1 python3 -B app.py --port 872x --civic-db <tmp>` | старт OK; v2 37/37 ready (R04, R06, R07, R08, R09, R12, R13) | — |

NOT_RUN в сессиях R14: браузерные проверки ролей (Playwright) — числа из DELIVERY и протоколов R10; Windows `run-city.bat` — выполнен Codex (LOCAL B2, §13). R04 и R13 входят в полный прогон B2 (0 FAIL).

## 13. Приёмка, безопасность, проверка на Windows

| Факт | Значение | Источник |
|---|---|---|
| Приёмка R10 сборки B2 (f54361d), облако | **сценарий демо проходит целиком, блокеров нет**; API 19/19 PASS; шаги 1–6 в интерфейсе: 1366 ru/kk — PASS (шаг 1 — с обходом B-019), 375 — PASS кроме постановки проекта (B-022); консоль без ошибок | `research/round-14-results/R10/ACCEPTANCE_B2.md`, R10 @ ac8508e |
| R10 B2: числа прогона | сценарий: 107 проверок — 81 PASS / 24 FAIL / 2 NOT_RUN; UX-чек-лист: 50 PASS / 42 FAIL / 8 NOT_RUN; точность карты 24 / 4 | там же, `e2e/b2/RESULT.md`, `UX_RESULT.md` |
| R10: дефекты | 26 записей B-001…B-026: исправлены B-001 (блокер), B-002, B-003, B-011; не подтвердился B-024; открыты важные B-007, B-012…B-014, B-016, B-019…B-021 и мелочи | `research/round-14-results/R10/BUGS.md`, R10 @ ac8508e |
| Приёмка LOCAL B2 на Windows (Codex) | `run-city.bat` на 127.0.0.1:8611, Windows build 26200, Python 3.12.10, Playwright 1.63 Chromium; 1366×768 и 375×812 × РУС/ҚАЗ; все API-проверки сценария PASS; **полная приёмка — FAIL** по UX (перекрытия на телефоне, клик по значку остановки, неполный ҚАЗ); P0 (потеря данных, падение) — нет | `research/round-14-results/LOCAL/LOCAL_B2.md`, pkg @ a38da11 |
| LOCAL B2: числа прогона R10 | сценарий 77 PASS / 28 FAIL / 2 NOT_RUN; UX 38 / 54 / 8; точность 24 / 4; pytest точности 31 / 4 | там же |
| LOCAL B2: загрузка (прогретый сервер) | DOMContentLoaded 72–163 мс; оболочка + обзорные тайлы 1.8–2.9 с; тайлы после приближения 0.22–0.27 с; 60 кадров/с (headless, SwiftShader) | там же, «Отдельные замеры» |
| LOCAL B2: тепловая карта реагирует | синтетический стимул: 1 жалоба + 12 «Я тоже» → у цели 5 → 17 человек, уровень 2 → 4, цвет #EF9F27 → #A32D2D | там же |
| LOCAL B2: снимков | 163 кадра, 12.8 МБ, SHA-256 каждого — `SCREENSHOTS.json` | там же |
| Ревью безопасности R15 (сборка be82fa8) | **критичных находок нет**; важных 11 (S09 уже исправлена), мелочей 3; на каждую — тест `tests/civic/R15/` и patch | `research/round-14-results/R15/SECURITY_REVIEW.md`, R15 @ 77bd744 |
| R15: тесты | на be82fa8: 80 passed, 19 xfailed (каждая открытая находка воспроизводится); со всеми patch — 19 XPASS (закрыты); путь демо B1 15/15 и B2 20/20 и со строгой CSP | `research/round-14-results/R15/DELIVERY.json` |
| R15: что защищено | статика по белому списку (15 попыток выйти за `web/` → 404); CSRF, Origin, `Sec-Fetch-Site`, Host; cookie HttpOnly + SameSite=Strict; пароль scrypt; SQL с параметрами; `device_id` хранится только как хэш с солью; three.js и MapLibre сверены по sha256 с официальными пакетами; в 187 коммитах раунда ключей API нет | там же, «Что проверено и защищено» |
| R15: главные открытые находки | S04+S11 — подпись цели из запроса жителя видна всем; S03+S13 — точка жителя восстанавливается до метра; S02+S08+S12 — накрутки без лимита по адресу; S07+S14 — ФИО с отчеством проходят обезличивание, тексты уходят в LLM | там же, «Итог за 1 минуту» |
