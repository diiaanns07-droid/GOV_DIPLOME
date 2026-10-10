# Birge · ключевые цифры проекта с источниками (FACTS)

> Роль R14, раунд 14. Для диплома, презентации и заявки Gton.
> **Правило:** в текст диплома и на слайды попадают только числа из этой таблицы (или из файлов, на которые она ссылается).
> Каждое число — с источником: файл, ветка, SHA. Если число меняется в новой поставке — обновить строку и SHA.
> Срез: 10 октября 2026, ветки ролей на момент чтения (git show, без запуска кода, если не сказано иное).
> Пометки: **real** — реальные данные (OSM, Open-Meteo); **synthetic** — синтетика; **derived** — вычислено из real;
> **demo** — учебные данные ТЗ хакатона; **NOT_RUN / NOT_EVALUATED** — измерения ещё нет.

Сокращения веток: `pkg` = `claude/round-14-package`; `R01` = `claude/sharp-dijkstra-0t87gl`; `R02` = `claude/r14-R02`;
`R03` = `claude/r14-R03`; `R04` = `claude/r14-R04`; `R05` = `claude/r14-R05`; `R06` = `claude/round-14-r06`;
`R07` = `claude/upbeat-knuth-i0rqaa`; `R08` = `claude/r14-R08`; `R09` = `claude/modest-shannon-0ki93p`;
`R11` = `claude/r14-R11`; `R12` = `claude/tender-brahmagupta-ef5ztl`; `R13` = `claude/r14-R13`;
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
| Погода (Open-Meteo, LOCAL-9) | **нет файла**: `data/civic/astana/weather/openmeteo_daily.csv` отсутствует во всех ветках на 10.10 | поиск по origin/* |
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

## 4. Корпуса обращений (R02) — всё synthetic, кроме формы

| Факт | Значение | Источник |
|---|---|---|
| synth_v3 (шаблонная синтетика) | 4 260 текстов из 221 шаблона; train/val/test 2 659 / 945 / 656; ru 2 060, kk 1 542, mixed 658; seed 20261011 | `ml/datasets/synth_v3/data/manifest_v3.json`, R02 @ 73b97d2 (код f62cc93) |
| synth_v3: удалено точных повторов | 212 (из 4 472); почти-повторов по Jaccard 3-грамм ≥ 0.8 — 0 | там же |
| synth_v3: обезличено | [телефон] 128, [email] 70, [адрес] 489 | там же |
| Пары перефразов для дублей | 781 (dev 363 / test 418; совпадение 391 / несовпадение 390), в т. ч. межъязыковые ru↔kk 184 | `ml/datasets/synth_v3/data/paraphrase_pairs_v3.jsonl`, R02 |
| v1_in_v2 (корпус раунда 12 в категориях v2) | 2 725 текстов; ru 1 461, kk 1 041, mixed 223; меток, изменённых правилами v2, 393; smell_air 0, parking 5 | `ml/datasets/v1_in_v2/manifest_v1_in_v2.json`, R02 |
| probe_v2 (написан вручную агентом, synthetic_agent_written) | 300 = 25 × 12; ru 155, kk 97, mixed 48; трудных 94 | `ml/datasets/probe_v2/manifest_probe_v2.json`, R02 |
| llm_v1 (LLM-синтетика) | **не создан** (LOCAL-8); план 4 000 текстов, оценка стоимости ≤ 0.84 $ (gpt-4.1-mini) | `ml/datasets/DATASHEET.md`, `research/round-14-results/R02/RUN.txt`, R02 |
| human_form (тексты людей) | **собирается** (цель 200–400 к 13.10); в Git не попадает | `DATASHEET.md` §6, R02 |
| Тесты R02 | pytest 89 PASS; node 12 + 7 PASS | `research/round-14-results/R02/DELIVERY.json` |

## 5. Классификатор (v1, v2)

| Факт | Значение | Источник |
|---|---|---|
| v1: macro-F1 на синтетическом test (невиданные шаблоны, n = 631) | 0.871 [0.780–0.928] (логрегрессия + словарь) против 0.848 [0.745–0.912] у словаря; разница +0.022 [−0.048; +0.096] — **не доказана** | `ml/civic_classifier/MODEL_CARD.md`, v1 @ 14c3384 |
| v1: macro-F1 на пробном наборе (n = 112) | 0.837 [0.767–0.896] | там же |
| v2: модель | `FacebookAI/xlm-roberta-base`, 278.1 млн параметров (192.0 млн — словарь эмбеддингов) | `ml/civic_classifier_v2/config.py`; `results/cloud_check_2026-10-10.json`, R03 @ 1d0edd7 (код 847bf31) |
| v2: гиперпараметры | lr 2e-5, batch 16 × grad_accum 2, до 8 эпох, patience 2, max_length 128, fp16, веса классов sqrt_inv, seed 20261011 | `ml/civic_classifier_v2/config.py`, R03 |
| v2: ONNX int8 (случайные веса, только скорость) | 265.8 МБ; 11.6 мс в среднем на текст (4 vCPU); 58 мс в 1 поток при 128 токенах | `results/cloud_check_2026-10-10.json`, R03 |
| v2: качество трансформера | **NOT_RUN** — обучение на GPU (LOCAL-4) по `research/round-14-results/R03/RUN.txt` | `research/round-14-results/R03/DELIVERY.json`, R03 |
| v2: качество на текстах людей | **NOT_EVALUATED** — нужно ≥ 200 размеченных текстов | там же; `experiments.py` `MIN_HUMAN = 200` |
| Базовые модели на синтетическом test v3 (n = 656, бутстрэп по шаблонам) | словарь 0.731 [0.570–0.857]; логрегрессия на v3 0.632 [0.494–0.771]; логрегрессия на v1→v2 0.548 [0.424–0.675] | `ml/civic_classifier_v2/results/RESULTS.md`, R03 (прогон на git 762c6a0, корпуса R02 @ 05b789e) |
| Парная разница на test v3 | логрегрессия(v1→v2) − словарь = −0.183 [−0.322; −0.017]; логрегрессия(v3) − словарь = −0.099 [−0.196; +0.014] | там же |
| Порог «нужна проверка» | минимальный t из 0.30…0.95, при котором точность автоподсказок на val ≥ 0.90; пока модель не проверена на людях — needs_review = true всегда | `metrics.py`, `predict.py`, R03 |
| Тесты R03 | pytest 65/65 (полная среда); 58 PASS + 7 NOT_RUN без torch/sklearn/onnx | `research/round-14-results/R03/DELIVERY.json` |

## 6. Поиск дублей и ML-API (R04) — в работе, числа на синтетике

| Факт | Значение | Источник |
|---|---|---|
| Метод (запасной, работает всегда) | символьные n-граммы 3–5 + двуязычный словарь понятий, α = 0.3; порог 0.18 (с местом) / 0.40 (только текст) | `ml/civic_dedup/dedup_config.json`, R04 @ 243526f |
| Метод (основной, ждёт весов) | эмбеддинги `intfloat/multilingual-e5-base` в ONNX; порог не подобран (null) | там же |
| Правило «похоже» | сходство ≥ порога И (та же цель ИЛИ ≤ 200 м) И не старше 14 дней И статус new/accepted/in_progress | `ml/civic_dedup/search.py`, R04 |
| Качество на test-парах (с геофильтром) | P 0.880, R 0.906, F1 0.893 | `dedup_config.json` (`test_geo`), R04 @ 243526f — **предварительно, R04 ещё не сдал** |
| Цепочка classify (без v2): точность на synth_v3 test | 0.784 (v1 одна 0.518; словарь 0.745) — метрика accuracy, не macro-F1 | `research/round-14-results/R04/classify_eval.json`, R04 @ 243526f |
| Скорость similar | p95 10.0–12.7 мс по городу, 39.5–45.1 мс в «горячей точке» на 5 000 синтетических жалоб (R04 @ 243526f) | `ml/civic_dedup/results/bench.json`, R04 |

## 7. Прогноз (R13) — прототип

| Факт | Значение | Источник |
|---|---|---|
| Территорий для прогноза | 2 334 (остановки 940, площадки 334, парки 177, мусор 136, дворы 538, участки улиц 209) | `ml/civic_forecast/data/targets.json`, R13 @ 754de0c |
| Синтетическая история | 34 месяца (2024-01…2026-10) × 12 категорий, seed 2026, Пуассон с сезонностью | `ml/civic_forecast/history.py`, R13 |
| Погода | пока **синтетическая фикстура** 1 378 дней (seed 14), не Open-Meteo | `ml/civic_forecast/data/weather_fixture.SOURCE.json`, R13 |
| precision@K backtest | **нет** — модель и backtest ещё не написаны | R13 @ 754de0c, `research/handoffs/astana/R13/round14/STATUS.md` |

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

_Разделы 10+ (сборка R01, жалобы R09, тепловая карта R07, картина дня R08, предложения R06, 3D R05, UX R11) — добавляются по мере чтения поставок._
