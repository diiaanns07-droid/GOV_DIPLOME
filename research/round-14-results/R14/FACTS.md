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

## 10. Сборка и сервер (R01)

| Факт | Значение | Источник |
|---|---|---|
| Сервер | `ui/web_server.py`, только стандартная библиотека, `ThreadingHTTPServer`; порт 8501 (`run.bat`) / 8611 (`run-city.bat`) | R01 @ bc7c961; `run-city.bat`, pkg |
| Маршрутов API | civic v1 — 30; civic v2 — 14 + `/modules` | `ui/web_server.py`, R01 @ bc7c961 |
| Перенесено в сборку на 10.10 | модули раунда 13 (I0), ui-kit/i18n R11, поставки R02, R07, R08, R09 (99 файлов в B1 шаг 1) | `research/round-14-results/R01/BUILD_LOG.md`, R01 |
| Весь pytest сборки | 1 458 passed / 11 skipped (на 2eaeacb) | `research/round-14-results/R01/DELIVERY.json` |
| Запуск сборки (повтор R14) | civic-v1 4/4 ready; civic-v2 ready R08; `/akim/summary` 200 за 21.8 мс; `/civic/akim/akim.js` 404 (не в белом списке) | запуск R14 на bc7c961, Linux, Python 3.13.16 |
| Словари в сборке | 257 ключей ru = 257 kk | `web/civic/i18n/*.json`, R01 @ bc7c961 |

## 11. Модули интерфейса и сервиса

| Факт | Значение | Источник |
|---|---|---|
| R09: маршрутов жалобы v2 | 11 | `ui/civic_feedback/v2/api.py`, R09 @ e012f73 (код a4ab5a4) |
| R09: шагов мастера жителя | 5 | `web/civic/feedback/complaint.js`, R09 |
| R09: лимит | 20 жалоб в час с устройства | `ui/civic_feedback/v2/store.py`, R09 |
| R09: тесты | pytest v2 83 PASS; папка 205 PASS; браузер 105/105 | `research/round-14-results/R09/DELIVERY.json` |
| R07: вес цели | Σ (1 + metoo)·0.5^(возраст/14); уровни 1/3/6/10; районы — пороги × 5; «исправлено» 7 дней | `ui/civic_heat/engine.py`, `config.py`, R07 @ 3eb3f9d (код 5a97636) |
| R07: смысловой зум | z < 12 — районы; значки с числом при z ≥ 15 | `ui/civic_heat/service.py`, `web/civic/heat/heat.js`, R07 |
| R07: скорость | 6 500 жалоб за 90 дней < 300 мс (тест); кэш 60 с | `tests/civic/R07/test_r07_heat.py`, `service.py`, R07 |
| R07: демо | 136 синтетических жалоб, 241 человек, 45 реальных целей OSM | `ui/civic_heat/demo_seed.py`, `research/round-14-results/R07/RUN.txt`, R07 |
| R07: тесты | pytest 97 PASS; браузер 16 PASS | `research/round-14-results/R07/DELIVERY.json` |
| R08: картина дня | 4 KPI, топ-10 горячих мест из тепловой карты за 7 дней, 12 сроков исправления (демо-норматив), сводка ru/kk шаблоном без LLM, кэш 30 с | `ui/civic_akim/summary.py`, `deadlines.py`, `text.py`, R08 @ a4189ba (код 9f1d9c0) |
| R08: тесты | pytest 112 PASS (с R07), UI 77/77 | `research/round-14-results/R08/DELIVERY.json`, `screens/ui_check.json` |
| R06: этапы | 6: planned → design → procurement → construction → acceptance → operating; stale > 14 дней | `ui/civic_store/stages.py`, R06 @ 3d10f7d (код 7031afa) |
| R06: база | миграция 6 — 6 новых таблиц; история только дополняется (триггеры) | `ui/civic_store/db.py`, R06 |
| R06: голос | один с устройства (sha256 соль + id); 30 голосов в минуту с адреса | `ui/civic_store/proposals.py`, R06 |
| R06: тесты | 445 passed / 5 skipped (папка), round14 66 / 4, браузер 48/48 | `research/round-14-results/R06/DELIVERY.json` |
| R05: объекты 3D | 5 видов (сквер 40×30 м, детская площадка, спортплощадка, остановка, освещение — опоры через ~30 м), лимит 20, анимация 1.2 с | `web/civic/build3d/build3d-core.js`, `build3d.js`, R05 @ e533e67 (код b0353ee) |
| R05: точность 3D | смещение якоря 0.000 px при наклоне 0–60° и повороте; освещение ≤ 0.5 м от рёбер | `research/round-14-results/R05/runs/browser_check.json`, DELIVERY R05 |
| R05: тесты | node 25/25, python 9/9, браузер 25 PASS / 1 NOT_RUN (плавность на GPU) | `research/round-14-results/R05/DELIVERY.json` |
| R11: дизайн-система | ~48 компонентов `bk-*`, 49 иконок, шрифт Inter 4.0 (OFL) «Birge Sans» | `web/civic/ui-kit/`, R11 @ cc77761 |
| R11: словари | 509 ключей ru = 509 kk; 29 мест ⚑ для проверки владельцем | `web/civic/i18n/*.json`, `research/round-14-results/R11/KK_REVIEW.md`, R11 |
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

NOT_RUN в этой сессии: браузерные проверки ролей (Playwright), R04 (тесты в работе), R13 (тестов нет), Windows `run-city.bat`.
