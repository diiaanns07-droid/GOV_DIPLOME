# Birge · модули

> Документ R14 (раунд 14) по **фактическому коду и отчётам веток ролей** на 10 октября 2026 (обновлено ночью 10→11.10:
> сборка B2 R01, обучение классификатора LOCAL-4, приёмка R10, ревью R15; FINAL-кандидаты R01 до 0a7a346).
> Читалось через `git show` по веткам (код не запускался, если не сказано иное). Числа тестов — из `DELIVERY.json` ролей.
> Каждая роль сдаёт `research/round-14-results/<роль>/DELIVERY.json`, `RUN.txt`, `INTEGRATION.txt` и handoff
> `research/handoffs/astana/<роль>/round14/STATUS.md` — **это первоисточник**; здесь — сводка, чтобы быстро найти, где что менять.
> После каждой сборки R01 таблицу §0 нужно обновить. Фактически B1 и B2 собраны 10.10 (раньше плана), FINAL — 15.10.

## 0. Сводная таблица

Срез — ночь 10→11.10 (круг 7). «В B2» — версия, которую интегратор R01 взял в сборку B2 (f54361d); «в FINAL-к.» — в последний FINAL-кандидат 0a7a346. Голова ветки может быть новее:
это правки после поставки (их забирает R01 в FINAL только по новому DELIVERY.json).

| Роль | Модуль | Ветка | Голова | code_sha (DELIVERY) | В B2 | Статус |
|---|---|---|---|---|---|---|
| R01 | Интегратор: сервер, шлюзы, оболочка | `claude/sharp-dijkstra-0t87gl` | cb6d336 | 0a7a346 (FINAL-кандидат) | — | B2 f54361d, B3 d9a8895, FINAL-кандидаты 2b9e837 → daec72a → ef1ef44 (приняты R10) → **0a7a346** (третья волна поставок; демо-жалобы для «Я тоже», `/similar` готов при старте; R01: pytest 2 638 / 1 FAIL — B-009) |
| R02 | Данные, синтетика, разметка | `claude/r14-R02` | 2a95286 | f62cc93 | 229f1aa | сдан; llm_v1 (3 979 текстов) — 2a95286; в FINAL-к. — f62cc93 |
| R03 | Классификатор v2 | `claude/r14-R03` | cc04b1f | ac0e954 | 252913e (без весов); в B3 — d472baf | **обучен (LOCAL-4, c19b889)**; probe_v2 0.828; в FINAL-к. — ac0e954 (R03 проверил: 814 passed); на утро — шаги ноутбука 8/8б/8в (ONNX повторно, int8 на probe_v2, транслит для трансформера) |
| R04 | Дубли и ML-API | `claude/r14-R04` | 94bd9ac | deeb1de | deeb1de | сдан (запасные пути); E5 ждёт LOCAL |
| R05 | 3D-превью | `claude/r14-R05` | a9d256d | f946157 | b0353ee | в FINAL-к. — fc03e19: без ж/д и трамвайных платформ и объектов вне районов (B-007, B-008), казахские названия улиц из OSM `name:kk`; S16 (id устройства) закрыта с 169c56b; f946157 — улица в kk-карточке проекта (B-033), ночь 4 — опоры освещения у бордюра — ждут сборки |
| R06 | Предложения, голоса, этапы | `claude/round-14-r06` | ef88235 | efafee9 | 7031afa; в B3 — b42e790 | в FINAL-к. — efafee9: простые пароли сотрудников запрещены (S15), демо-объекты на двух языках, одна карточка голоса |
| R07 | Тепловая карта | `claude/upbeat-knuth-i0rqaa` | 462a732 | 51935b6 (ночь 7) | 5a97636; в B3 — 306074b | в FINAL-к. — b28268b (подписи мест на казахском — B-029 закрыт с 597ec4f); ночью 5–7 — кнопки ≥ 44 px, пустая легенда без сервера (B-034), «меньше движения» — ждут сборки |
| R08 | Картина дня | `claude/r14-R08` | 61a7b3d | bedb753 (ночь 9) | 4ce8f08 | в FINAL-к. — c7646a1; ночь 9 — объекты с местом открывают карту (по желанию оболочки) — ждёт сборки |
| R09 | Жалоба жителя v2 | `claude/modest-shannon-0ki93p` → ночью `claude/wizardly-ptolemy-qy8ltw` | 356a683 | 1b3b639 (новая ветка) | fa49fc9 | в FINAL-к. — fa49fc9; ночные правки (даты «13 қазан», низкая шторка на телефоне) — в новой ветке, R01 их не взял (R11 круг 7) |
| R10 | Приёмка | `claude/r14-R10` | b6303bb | 3623f65 (тесты) | тесты — в FINAL-кандидатах | B1, B2, B3 и FINAL-кандидаты приняты; последний принятый — **ef1ef44**: все 6 шагов на 1366/375 × ru/kk, 114/4/0, UX 94/0/8; открыты B-021 (кабинет по-русски), B-030/B-032 (закрыты в 0a7a346 по R01 и повтору R14) |
| R11 | UX и казахский | `claude/r14-R11` | 3120520 | «последний коммит ветки» | 6102dfb; в B3 — 52d7c59 | в FINAL-к. — f0e5e80 (737 ключей); голова — 744 ключа и patch перевода кабинета; разбор 0a7a346: 44/44 кадра, 0 русских строк в ҚАЗ на трёх экранах демо |
| R12 | Точность карты | `claude/tender-brahmagupta-ef5ztl` → `claude/r14-R12` | 42c1350 | 8810221 / tested d13f49a | d13f49a | в FINAL-к. — d13f49a; день 2 (`claude/r14-R12`) — кабинет сотрудника на ҚАЗ (B-021), двор за границей удалён, проверка каждой вершины (B-009) — ждёт DELIVERY и сборки |
| R13 | Прогноз (прототип) | `claude/r14-R13` | 516c8e1 | a0133e9 | 8705829 | backtest на реальной погоде Open-Meteo (0.57/0.51/0.47); в FINAL-к. — a0133e9 |
| R14 | Документация и диплом | `claude/r14-R14` | см. STATUS | см. DELIVERY | 8e106a9 — в B3; 16ee4f7 — в FINAL-к. | этот документ |
| R15 | Ревью безопасности | `claude/r14-R15` | 8b3717a | тесты 054b056, patch b892532 | тесты и patch — в FINAL-кандидатах | 16 находок (0 критичных, 11 важных, 5 мелочей); на 0a7a346 **исправлены все 16** — `tests/civic/R15` 121 passed (R15 и повтор R14), браузер B1 15/15, B2 25/25 |

Общее для всех модулей:
- категории — только из `research/round-14/categories_v2.json` (12 штук);
- тексты интерфейса — ключи `web/civic/i18n/ru.json` и `kk.json` (R11);
- компоненты и токены — `web/civic/ui-kit/` (классы `bk-*`, R11);
- тесты лежат в `tests/civic/<роль>/` (для раунда 14 часто в подпапке `round14/`); **номера папок тестов раундов 11–13 не совпадают с ролями раунда 14** (например, `tests/civic/R06/` содержит и старые тесты жалоб v1, `tests/civic/R07/` — тесты сценариев).

---

## R01 · Интегратор: сервер, шлюзы, оболочка

- **Ветка:** `claude/sharp-dijkstra-0t87gl` (то же, что `claude/r14-R01`), голова d9a8895; DELIVERY: code b5c153d — **кандидат B2 f54361d** (сборки: I0 3adabe3, api_v2 caf2cff, shell_ru_kk 2eaeacb, b1_import bc7c961, b1_candidate d3c33d9, b2_step1 915143f, b2_step2 b5c153d, b2_candidate f54361d; после B2 — шаги B3 a8fabce, be82fa8, 7227fce, d9a8895). Актуальный SHA сборки — в `research/handoffs/astana/R01/round14/STATUS.md`.
- **Назначение:** собрать одну работающую версию Birge — перенести поставки ролей по закреплённым SHA (без merge, по путям), держать HTTP-шлюзы v1/v2 и оболочку страницы (шапка Birge, ҚАЗ/РУС, Акимат/Житель, Карта/Картина дня).
- **Файлы:**
  - `ui/web_server.py` (1437 строк) — сервер, шлюзы `CivicGateway` (v1) и `CivicV2Gateway` (v2), статика по белому списку `ASSETS`/`CIVIC_ASSETS`;
  - `app.py` — точка входа (`ui.web_server.main`);
  - `web/index.html` (226) — страница, порядок `<script defer>`;
  - `web/civic/shell/shell.js` (970) — оболочка раундов 11–13 (`window.CivicShell`): монтирует модули v1, режимы `#training`, `#school`, `#object=`, `#civic-receipt=`;
  - `web/civic/shell/birge.js` (271) — шапка Birge, режимы, «Картина дня», клиент API v2 (`window.BirgeShell`, ошибки `BirgeApiError`);
  - `web/civic/shell/shell-text.js` (241) — запасной словарь ru/kk (79 ключей `shell.*`);
  - `web/civic/shell/explore.js` (356) — районы и поиск улицы по `/civic/map/streets.json` без внешнего геокодера;
  - `web/civic/shell/shell.css`, `birge.css` — раскладка, панель справа 400 px, телефонная шапка.
- **Маршруты:** старое API симулятора (`/api/health`, `/api/bootstrap`, `/api/simulate`, `/api/optimize`, `/api/advisor`, …); `/api/civic/v1/*` — 30 маршрутов (объекты, редактор, сообщения, модерация, сценарии, помощник, staff); `/api/civic/v2/*` — 14 маршрутов CONTRACT §7 + геоданные R12, предложения и этапы R06, прогноз R13 + `GET /modules`; в B2 — **37 маршрутов v2, все `ready`** (проверка R14). Таблица `V2_HANDLERS` и правила проверки входа — `ARCHITECTURE.md` §5.
- **Аргументы и переменные:** `--port` (8501), `--host` (127.0.0.1), `--open`, `--civic-db` (или `CIVIC_DB_PATH` / `CIVIC_DB`, иначе `.runtime/civic.sqlite3`), `--civic-classifier off|r08` (`CIVIC_R08_CLASSIFIER=1`).
- **Тесты:**
  - всё сразу: `bash tests/civic/R01/run_checks.sh <папка>` (pytest, `python -B -m ui.web_check`, node, браузер Playwright);
  - шлюз v2: `python -m pytest -q tests/civic/R01/test_r01_api_v2.py`;
  - шапка: `node tests/civic/R01/browser/r14_shell.cjs <папка>`;
  - результаты (DELIVERY/BUILD_LOG): на 2eaeacb весь pytest 1458 passed / 11 skipped; `test_r01_api_v2` 61/61; браузер: шапка 35/0 (38/0 после правой панели), город 81/0, сценарии 16/0, P0 62 PASS / 1 FAIL / 2 NOT_RUN (FAIL — гонка `civic-r03-demo-ring` в модуле карты, есть и на I0); B1 шаг 1 (bc7c961): наборы R02/R07/R08/R09 — 784 passed / 1 skipped; **кандидат B1 (d3c33d9): весь pytest 1 793 passed / 11 skipped, путь демо `node tests/civic/R01/browser/r14_b1.cjs <папка>` — 15/0** (жалоба → +1 на карте → «Мои обращения» → «Картина дня» → горячее место → «Взять в работу» → «Исправлено»); Windows `run-city.bat` — NOT_RUN.
- **Проверки B2 (f54361d, код b5c153d):** весь pytest **2 377 passed / 20 skipped / 1 xfailed**; путь демо B1 15/0, путь B2 `node tests/civic/R01/browser/r14_b2.cjs <папка>` — 17/0 (20/0 с путём жителя через R12/R04); шапка 38/0, город 81/0, сценарии 16/0; P0 62/1/2 (гонка demo-ring). Приёмка R10 на B2: сценарий проходит целиком, блокеров нет.
- **FINAL-кандидат 2b9e837 (ночь 10→11.10; голова 13ae790 — тот же код + документы):** патчи безопасности R15 (CSP с хэшами
  встроенных скриптов, лимиты частоты v2 по адресу, журнал без строки запроса, цель жалобы по карте R12, огрубление точки,
  подписи из OSM, обезличивание отчеств), тесты R15 и R10 в сборке, телефонный каталог 3D, переход Tab к главной кнопке.
  Проверки: pytest 2 535 passed / 21 skipped / 6 failed + 1 ошибка сбора (известные стыки R07/R08 и данные R05/R12),
  `tests/civic/R15` 99/99, путь демо r14_b2 25/0 (R01); повтор R14 — те же числа, старт 37/37 ready. Приёмка R10 —
  `ACCEPTANCE_FINAL.md`: все 6 шагов на 1366/375 × ru/kk. Перед показом перезапускать сервер (лимиты в памяти).
- **FINAL-кандидаты daec72a → ef1ef44 → 0a7a346 (та же ночь, волны 2–3):** правки по приёмке R10 (ҚАЗ без русской ленты,
  шрифт ≥ 14 px, кнопки ≥ 40–44 px), ночные поставки ролей (R03 ac0e954, R05 fc03e19, R06 efafee9, R07 b28268b, R08 c7646a1,
  R11 f0e5e80, R13 a0133e9), демо-жалобы R09 у «Хан Шатыра» при `CIVIC_DEMO=1` (B-030), модули подключаются при старте
  (B-032). Приёмка R10 ef1ef44 — 114/4/0, UX 94/0/8. Проверки 0a7a346: R01 — pytest 2 638 / 1 FAIL (B-009), браузер B2
  25/0, B1 15/0, шапка 38/0, город 81/0; повтор R14 — pytest 2 639 passed / 21 skipped / 1 failed, R15 121 passed, 37/37
  ready, `/similar` по тексту демо — 3 совпадения.
- **Ограничения (B2):** веса модели R03 в Git нет — без них `/classify` отвечает словарём (`source: kw`); в оболочке временный адаптер R05 → R06 (после поставки 2 R06 сокращён в B3); R13 `/forecast` — только API; тексты модулей раунда 13 (лента работ, кабинет сотрудника) в ҚАЗ по-русски (B-012, B-021); подложка OpenFreeMap в облаке недоступна — после B3 (7227fce) карта рисует оси улиц OSM офлайн. Подробно — `ARCHITECTURE.md` §8.
- **Следующий шаг (DELIVERY B2):** FINAL 15.10 18:00 — повторные поставки R07/R06/R05 по DELIVERY, убрать адаптер R05 → R06, патчи R15 (INTEGRATION R15), CSS-правки B-019/B-020 (INTEGRATION R10 §3), `run_checks.sh` + r14_b1 + r14_b2, DEMO_SCRIPT, DELIVERY, STATUS.
- **Документы роли:** `research/round-14-results/R01/{DELIVERY.json, BUILD_LOG.md, RUN.txt, INTEGRATION.txt, DEMO_SCRIPT.md}`.

---

## R02 · Данные, синтетика, разметка

- **Ветка:** `claude/r14-R02`, голова 2a95286 (llm_v1: `ml/datasets/llm_v1/` — 3 979 текстов gpt-4.1-mini, $0.28, сгенерировано на ноутбуке); code/tested f62cc93; в B2 — 229f1aa; часть (инструмент разметки) также в `claude/round-14-package` @ 887ef4b.
- **Назначение:** корпуса для обучения и проверки классификатора (12 категорий, ru/kk/mixed), офлайн-инструмент ручной разметки, импорт и обезличивание ответов Google-формы, согласие разметчиков, скрипты LLM-синтетики и LLM-разметчика (запуск только локально с ключом).
- **Файлы:**
  - `ml/datasets/DATASHEET.md` (430) — описание всех корпусов, схема экспериментов A–E; `LABELING_GUIDE_v2.md` (245) — правила разметки, 25 спорных случаев;
  - `ml/datasets/synth_v3/{templates.py, slots.py, build.py}` + `data/corpus_v3.jsonl`, `manifest_v3.json`, `paraphrase_pairs_v3.jsonl`;
  - `ml/datasets/v1_in_v2/convert.py` + `corpus_v1_in_v2.jsonl`;
  - `ml/datasets/probe_v2/{source.py, build.py}` + `probe_v2.jsonl`;
  - `ml/datasets/llm_synth.py` (312);
  - `ml/labeling/{anonymize.py, import_form.py, agreement.py, llm_client.py, llm_label.py, guide.py, text_utils.py, gen_categories_js.py}`;
  - `web/labeling/{index.html, app.js, core.js, style.css, categories.js}` — офлайн-страница (file://), клавиши по `event.code` (работают в любой раскладке), автосохранение в localStorage, режим второго разметчика, экспорт JSONL `birge-labels-v1`.
- **Команды:**
  - `python -m ml.datasets.synth_v3.build [--check]`, `python -m ml.datasets.probe_v2.build [--check]`, `python -m ml.datasets.v1_in_v2.convert`;
  - `python -m ml.labeling.import_form private\form.csv` — согласие → обезличивание → дедупликация → язык → только дата → id; выход только в `private/`;
  - `python -m ml.labeling.anonymize "<текст>"`; `python -m ml.labeling.agreement A.jsonl B.jsonl --md …` (каппа Коэна, бутстрэп-ДИ);
  - `python -m ml.datasets.llm_synth --model … --n-total 4000 --max-usd 3 [--dry-run|--mock] [--provider nvidia]`;
  - `python -m ml.labeling.llm_label <файл> --model gpt-4o-mini --max-usd 1 --confirm-external`.
- **Данные** (подробно — `DATA.md` §3): synth_v3 4 260 (synthetic), v1_in_v2 2 725 (synthetic), probe_v2 300 (synthetic_agent_written), paraphrase_pairs_v3 781 пара, llm_v1 — не создан, human_form — собирается, в Git не попадает.
- **Тесты (DELIVERY):** `python -m pytest tests/civic/R02/round14` — 89 PASS; `node --test tests/civic/R02/round14/labeling_core.test.mjs` — 12 PASS; `node --test tests/civic/R02/round14/labeling_browser.test.mjs` — 7 PASS (Chromium); `synth_v3 build --check`, `probe_v2 --check`, `gen_categories_js --check` — PASS. NOT_RUN: LLM с настоящим API, Firefox/Safari, разметка 300 текстов владельцем.
- **Ограничения:** казахский не проверен носителем; шаблоны, правила и probe писал один автор — синтетический test оптимистичен; обезличивание на регулярных выражениях может пропустить имена и «голые» адреса; в v1_in_v2 нет smell_air и всего 5 parking.
- **Следующий шаг:** форма → `import_form` → разметка 300 текстов → второй разметчик (100) → `agreement` → LOCAL-8 (`llm_synth`, `llm_label`).

---

## R03 · Классификатор v2

- **Ветка:** `claude/r14-R03`, голова c2b4dda; code/tested d472baf; результаты обучения LOCAL-4 — коммит **c19b889** (Codex на ноутбуке, код 477f97b); данные из R02 (synth_v3, v1_in_v2, probe_v2 @ 73b97d2; llm_v1 @ 2a95286) — читаются по путям.
- **Назначение:** конвейер классификатора 12 категорий: три модели (словарная эвристика, логрегрессия метода v1, `FacebookAI/xlm-roberta-base`), сравнение режимов обучения с бутстрэпом, итоговая модель, экспорт ONNX int8, `Classifier.classify()` для `/classify`.
- **Файлы (`ml/civic_classifier_v2/`):** `config.py` (гиперпараметры), `labels.py` (категории из JSON), `data.py` (корпуса и разбиения), `heuristic.py` (словарь основ ru/kk), `logreg.py` (символьные 2–5-граммы + словарь), `transformer.py` (цикл PyTorch), `metrics.py` (macro-F1, бутстрэп, парная Δ, ECE, порог), `evaluate.py`, `experiments.py`, `train.py`, `export_onnx.py`, `predict.py`, `zeroshot.py`, `MODEL_CARD.md`; `results/` — `RESULTS.md` (генерируется, руками не править), `experiments.json`, `final_model_meta.json`, `onnx_export.json`, `train_log_*.jsonl`, `cloud_check_2026-10-10.json`; `artifacts/` (веса, ONNX) — **вне Git**, только на ноутбуке.
- **Команды** (полный порядок для ноутбука — `research/round-14-results/R03/RUN.txt`, шаги 0–9):
  - `python -m ml.civic_classifier_v2.experiments --probe-v2 … [--human private/labels_owner.jsonl] [--seeds 3] [--models …] [--regimes …] [--human-fraction …] [--smoke]`;
  - `python -m ml.civic_classifier_v2.train [--regime synth_template|synth_llm|synth_all|human|mix]`;
  - `python -m ml.civic_classifier_v2.export_onnx` (по умолчанию int8 per-channel);
  - `python -m ml.civic_classifier_v2.predict "текст" [--backend onnx|torch]`;
  - `python -m ml.civic_classifier_v2.evaluate render` — перегенерировать `RESULTS.md` из `experiments.json`;
  - `python -m ml.civic_classifier_v2.zeroshot --human … --model gpt-4o-mini --max-usd 1` (только с согласия владельца).
- **API для R04:** `predict.Classifier.load()` (ищет `artifacts/onnx`, затем `artifacts/final`, иначе `ModelUnavailable`; путь — `BIRGE_CLF_V2_DIR`, потоки — `BIRGE_CLF_V2_THREADS`, по умолчанию `min(4, ядер)`), `.classify(text) → {category, score, needs_review, model_version, top3}`.
- **Ключевые решения:** главный оценочный набор — тексты людей (≥ 200, иначе `NOT_EVALUATED`); до них — независимый тест вне шаблонов probe_v2 (не входит в обучение и выбор); синтетический test — справочно, бутстрэп по шаблонам; режим итоговой модели выбирается правилом (`synth_all` без людей, `mix` с людьми), не по probe; порог `needs_review` — минимальный t (0.30…0.95), при котором точность автоподсказок на val ≥ 0.90; **пока модель не проверена на людях, `needs_review = true` всегда**.
- **Результаты LOCAL-4 (RESULTS.md, MODEL_CARD.md):** итоговая модель `civic-clf-v2-xlm-roberta-base-synth_all-daaa6dae4-s20261011` — probe_v2 **0.828 [0.778–0.865]**, kk 0.81 / ru 0.83 / mixed 0.85, транслит 0.61; эксперимент на probe_v2: трансформер v3 + LLM 0.812, логрегрессия 0.797, словарь 0.684; трансформер − логрегрессия +0.015 [−0.034; +0.068] (не доказано); люди — NOT_EVALUATED. ONNX: штатный int8 — 96.5 % / 103 мс (FAIL), per-channel + 4 потока — 98 % / 22.7 мс (PASS, умолчание с d472baf). На Windows в сборке B2 модель работала (`source=v2`, `LOCAL_B2.md`).
- **Тесты (DELIVERY):** `python -m pytest tests/civic/R03/round14 -q` — на cc04b1f 109 passed + 1 xfailed (полная среда: torch CPU, transformers, onnx, sklearn); без тяжёлых библиотек — 101 passed + 8 skipped + 1 xfailed (на d472baf было 66/66 и 59 + 7). **Не запускать вместе с другими папками одной командой** (`pytest A B C`): тесты делают `from conftest import …` и берут чужой conftest (INTEGRATION §9 R01); полный `pytest tests` и папка отдельно — работают.
- **Ограничения:** только синтетика; один seed; метки llm_v1 не проверены людьми; ECE 0.144; слабые места — транслит, трудные случаи, noise_safety/roads; повторный экспорт с d472baf на ноутбуке и качество int8 на probe_v2 — NOT_RUN (RUN.txt шаги 8, 8б).
- **Следующий шаг:** ноутбук — RUN.txt шаги 8 и 8б, передать `artifacts/onnx` R04; после разметки ≥ 200 текстов людей — шаг 6 с `--human`, затем итоговая модель `mix` и шаг 8 заново.

---

## R04 · Дубли и ML-API

- **Ветка:** `claude/r14-R04`, голова 94bd9ac; code/tested deeb1de; статус ready_for_review (запасные пути), E5 и модель v2 ждут LOCAL.
- **Назначение:** `ml/civic_dedup/` — поиск похожих открытых жалоб рядом для «Я тоже»; `ui/civic_ml_api/` — функции для шлюза R01: `classify(text)` → `POST /classify`, `similar(text, point, days)` → `POST /similar`.
- **Файлы:** `ml/civic_dedup/{normalize.py (латиница → кириллица, казахские буквы → русские двойники), concepts.py (двуязычный словарь понятий, 48 тем), scorers.py (n-граммы + понятия), e5.py (E5 в ONNX), export_e5.py (экспорт E5 — на ноутбуке), search.py (Deduper), geo.py, config.py, loader.py, dedup_config.json, tune.py, bench.py, fixtures.py}`, `results/{dedup_eval_ngram.json, bench.json}`; `ui/civic_ml_api/{__init__.py, classify_chain.py, similar_search.py, evaluate.py, categories.py, errors.py}` (CLI `python -m ui.civic_ml_api`); `tests/civic/R04/round14/`; отчёты `research/round-14-results/R04/{DELIVERY.json, RESULTS.md, RUN.txt, INTEGRATION.txt, classify_eval.json, r01_similar_target.patch}`.
- **Правило «похоже»:** сходство ≥ порога И (та же цель ИЛИ ≤ 200 м) И не старше `days` (14 по умолчанию, 1…365) И статус `new|accepted|in_progress`; без точки и цели совпадений нет; тексты чужих жалоб в ответ не попадают. Без patch R01 условие «та же цель» работает только через точку ≤ 200 м.
- **Метод:** основной — эмбеддинги `intfloat/multilingual-e5-base` в ONNX (включается, только если есть веса в `ml/civic_dedup/artifacts/e5/` и порог подобран на dev с нужной точностью — LOCAL-R04-1); запасной, работает всегда — `ngram-concept-v1` (символьные n-граммы 3–5 + словарь понятий, α = 0.3, порог 0.18 с геофильтром / 0.40 только по тексту — `dedup_config.json`).
- **Цепочка classify:** v2 R03 (ONNX; после 3 сбоев подряд отключается) → транслит в кириллицу → словарь R03 (≥ 1 совпадение), иначе v1 (6 меток → v2) → словарь v1 → `other`. В запасном пути `needs_review` всегда true; для чипа подсказки жителю — поле `suggest` (≥ 2 совпадения словаря).
- **Команды:** `python -m ml.civic_dedup.tune [--method e5|all] [--write-config]`; `python -m ml.civic_dedup.bench`; `python -m ml.civic_dedup.export_e5` (ноутбук, LOCAL-R04-1); тесты — `python -m pytest -q tests/civic/R04/round14` (вместе с R03 — 137 passed / 6 skipped по DELIVERY; весь `tests` с локальными копиями соседей — 967 passed / 4 skipped).
- **Результаты (синтетика R02):** пары test с геофильтром — P 0.880 [0.833; 0.922], R 0.906 [0.863; 0.945], F1 0.893; только по тексту — P 0.616; цепочка classify без v2 — accuracy 0.784 на synth_v3 test (v1 одна — 0.518); скорость (облако, 4 vCPU) — classify p95 0.36 мс, similar p95 8.2 мс по городу, 39.3 мс в «горячей точке» на 5 000 жалоб, первый запрос без прогрева ~155 мс.
- **Ограничения:** все метрики на синтетике, test-пары просмотрены 5 раз за журнал экспериментов (`RESULTS.md`); E5 не подключён; словарь понятий — 48 тем; две разные проблемы одного понятия в 200 м (две ямы) считаются одной — житель жмёт «У меня другое».
- **Зависимости:** R02 (пары, маркеры обезличивания), R03 (`predict`, `heuristic`), v1 `ml/civic_classifier`, R09 (`ComplaintStore` через `connect_store`, прогрев кэша по событиям), R01 (`V2_HANDLERS`, patch target).

---

## R05 · 3D-превью предложений

- **Ветка:** `claude/r14-R05`, голова 169c56b; code/tested b0353ee (в B2). На ветке после поставки — клиент под контракт R06, правила монтажа R01, зоны нажатия 48 px (7f42cb3, b268dea); в FINAL — только по новому DELIVERY.json.
- **Назначение:** акимат выбирает в каталоге один из 5 объектов (сквер, детская площадка, спортплощадка, остановка, освещение), «призрак» следует за курсором, «Поставить» — объект «строится» в 3D на карте с меткой «Проект · 2027»; жители видят объекты и голосуют.
- **Файлы:** `web/civic/build3d/build3d.js` (1968, `window.CivicBuild3D`), `build3d-core.js` (931, логика без DOM, работает в Node), `build3d-models.js` (656, процедурные low-poly модели без внешних 3D-файлов), `build3d.css`, `demo.html`, `data/{nura-streets.json, astana-existing.json, astana-districts.json, demo-basemap.json, proposals.fixture.json}`; `web/vendor/three/three.module.min.js` (three.js 0.169.0, MIT, загружается лениво через `import()`).
- **Как стоит на карте:** custom layer MapLibre (`renderingMode: "3d"`, WebGL2), камера получает матрицу проекции карты × переход «метры сцены → меркатор»; проверено: смещение якоря 0.000 px при наклоне 0–60° и повороте; слой под подписями улиц; после смены стиля добавляется заново.
- **Анимация:** рост снизу вверх 1200 мс (шейдер прижимает вершины), лёгкий «пружинящий» масштаб, пыль ~1 с; при `prefers-reduced-motion` без анимации. Лимит 20 объектов; освещение — опоры через ~30 м вдоль участка улицы 20–900 м.
- **API модуля:** `CivicBuild3D.mount({map, root, role: "akimat"|"resident", store: "auto"|"api"|"local", apiPrefix, threeUrl, …}) → {start(kind), cancel(), select(id), refresh(), setVisible(), getState(), destroy()}`; событие `civic-build3d:tool`. Хранилище `auto`: сначала API R06, при 404/405/501/503/ошибке сети — `localStorage` (`birge.build3d.proposals.v1`).
- **Тесты (DELIVERY):** `node --test tests/civic/R05/build3d/test_core.mjs tests/civic/R05/build3d/test_models.mjs` — 25/25 (команда с каталогом вместо файлов на Node 22 не работает); `python -m unittest discover -s tests/civic/R05/build3d -p "test_*.py"` — 9/9 (освещение ≤ 0.5 м от рёбер при допуске 5 м, остановка 3–60 м от улицы, всё внутри Астаны); браузер `node tests/civic/R05/build3d/browser_check.mjs` — 25 PASS / 0 FAIL / 1 NOT_RUN (плавность на GPU).
- **Ограничения:** FPS на ноутбуке с GPU не проверен (в облаке SwiftShader: 8.3 → 2.9 кадр/с при 0 → 20 объектах); пересечение с настоящими зданиями не проверяется (контуров зданий в репозитории нет); освещение пока только в фокус-области Нуры; несостыковки с API R06 — `ARCHITECTURE.md` §8 п. 3.
- **Следующий шаг:** R01 применяет `research/round-14-results/R05/proposed_r01.patch`; R06 — поля 3D и удаление; R11 — ключи `build3d.*`.

---

## R06 · Предложения, голоса, этапы объектов

- **Ветка:** `claude/round-14-r06`, голова 6b9da27; в B2 — 7031afa; **поставка 2 — code/tested b42e790** (год проекта, DELETE для R05, функции akim_* для R08, миграция 7; в сборке с шага B3 a8fabce); восстановлено из `claude/elegant-franklin-jbhprq` @ 26793c8 (R02 раунда 13).
- **Назначение:** хранить предложения акимата (5 видов R05) и голоса жителей (один с устройства), 6 этапов объекта с автоматическим расчётом отставания и «давно не обновлялось»; API v2 и функции для R01/R08; карточки проекта и объекта.
- **Файлы:** `ui/civic_store/{db.py (миграция 6), proposals.py, stages.py, v2.py, districts.py, demo_r14.py, cli.py}`; `web/civic/proposals/{proposals.js (BirgeProposals), stage-editor.js (BirgeStageEditor), proposals.css, demo.html}`.
- **База (миграция 6, только новые таблицы):** `civic_object_stages`, `civic_stage_history` (только дополняется), `civic_proposals` (удаление запрещено триггером, статус `withdrawn`), `civic_proposal_history`, `civic_votes` (PK предложение + хэш устройства), `civic_v2_settings` (соль).
- **Расчёт этапа (`stages.compute_lifecycle`):** `delay_days = max(0, ожидаемое окончание − план)`, где ожидаемое — прогноз или план, а если сегодня позже обоих — сегодня; `late = delay > 0` и этап не `operating`; `stale = > 14 дней без обновления`. Конкурентная правка — `expected_revision` (409 при расхождении).
- **Голос:** `device_id` 16–128 символов, хранится только `sha256(соль:device_id)`; повтор той же кнопки — без изменений, другая — меняет голос; 30 голосов в минуту с IP; голосовать можно только по статусу `proposal`.
- **Маршруты (`CivicV2.handle`, ответ `{ok, data}`):** `GET /objects`, `GET /objects/lagging`, `GET /objects/{id}`, `PUT|POST /objects/{id}/stage` (сотрудник + CSRF), `GET /staff/objects/{id}/stage`, `GET /proposals`, `POST /proposals` (сотрудник), `GET /proposals/summary`, `GET /proposals/{id}`, `POST /proposals/{id}/vote`, `POST /proposals/{id}/approve|reject|withdraw` (сотрудник), `GET /meta`. Функции для шлюза R01 — в `ui.civic_store.v2` после `bind(service)`.
- **Демо:** `python -m ui.civic_store … seed-r14-demo` — синтетические предложения (`demo: true`) на реальных местах OSM (освещение ул. Ильяса Омарова 396 м по рёбрам графа, павильон на остановке «Жағалау-3», сквер/площадки внутри реальных кварталов).
- **Тесты (DELIVERY):** `python3 -m pytest -q tests/civic/R06` — 445 passed / 5 skipped (включает регрессию хранилища и старые тесты жалоб v1); `python3 -m pytest -q tests/civic/R06/round14` — 66 passed / 4 skipped; через шлюз R01 — 4/4; браузер: `python3 tests/civic/R06/round14/serve_r14.py --port 8616 --age-days 16 > /tmp/stand.json &` затем `NODE_PATH="$(npm root -g)" node tests/civic/R06/round14/browser_r14.cjs /tmp/stand.json <папка>` — 48/48.
- **Ограничения:** «один голос с устройства» ≠ «один голос на человека» (очистка браузера = новое устройство); шлюз R01 теряет `fields` у ответа 422; казахские тексты — черновик; **код раунда 13 не откроет базу после миграции 6 — перед обновлением нужна резервная копия**.
- **Патч для R12:** `research/round-14-results/R06/r12_editor_stage.patch` (блок «Этап работ» в редакторе) — R12 уже применил.

---

## R07 · Тепловая карта объектов

- **Ветка:** `claude/upbeat-knuth-i0rqaa`, голова 35e6feb; в B2 — 5a97636; **повторная поставка — code/tested 306074b** (правдоподобный 5-недельный демо-поток, `records()`/`generation` для R08, значки с числом в стартовом виде, зоны 48 px; в сборке с шага B3 a8fabce). Тесты 306074b: pytest 108 passed / 3 skipped, браузер 29/29.
- **Назначение:** главный экран акимата — какой объект, участок улицы или двор «краснеет» и сколько человек сообщили; свежие жалобы ярче, со временем «остывают»; после ремонта цель 7 дней зелёная «исправлено». Тот же расчёт отдаётся R08.
- **Файлы:** `ui/civic_heat/{engine.py (вес, уровни, «исправлено», районы), service.py (HeatService, кэш, зум), targets.py (форма и подпись цели по id), geo.py (ячейки 150 м, районы), osm_objects.py, config.py (всё из categories_v2.json), api.py (handle_get), build_fixtures.py, demo_seed.py, devserver.py (порт 8617)}`; `web/civic/heat/{heat.js (CivicHeat), heat.css, demo.html, fixtures/}`.
- **Формулы:** вклад жалобы = `(1 + metoo) · 0.5^(возраст_дней / 14)`; учитываются статусы `new|accepted|in_progress`; `count` — число людей без затухания (на значке); уровни по весу 1/3/6/10 (вес > 0 всегда даёт уровень ≥ 1 — отступление от `min_weight`, описано в INTEGRATION §5); районы — пороги × 5; «исправлено»: жалобы до последнего `fixed` закрыты, вес 0, `fixed_until = t_fixed + 7 дней`.
- **Смысловой зум:** сервер при `zoom < 12` отдаёт районы, иначе цели; фронтенд — значки с числом при z ≥ 15 (кроме уровня 4 и выбранной цели).
- **Формы на карте (MapLibre, слои `r07-*`):** объект — ореол, растущий с весом, + точка (+ контур площадки из OSM); участок улицы — линия по геометрии ребра OSM, ширина растёт с весом; двор/ячейка — заливка; «примерное место» — пунктир. Житель видит то же мягче (коэффициент 0.75). Анимация цвета 800 мс (`feature-state`), пульс-кольцо при новой жалобе.
- **HTTP:** `api.handle_get(path, query) → (status, body)`: `GET /api/civic/v2/heat?bbox&days&category&district&zoom`, `GET /heat/meta`, `GET /heat/target?kind&id&days`; кэш 60 с, `invalidate()`.
- **Фронтенд:** `CivicHeat.mount({root, map, role, lang, beforeId, apiBase}) → {refresh, pulse, focusTarget, setRole, destroy}`; слушает `birge:complaint`, `birge:lang`; шлёт `birge:heat-select`; фильтры: 12 категорий, 7/30/90 дней, район, «Сбросить».
- **Данные:** жалобы — synthetic (136 жалоб, 241 человек, seed 20261011); цели — реальные OSM (45: 26 рёбер графа, 7 дворов, 5 остановок Нуры, 2 площадки, 2 контейнерные площадки, 3 ячейки «запахов» у Коргалжинского шоссе — место не проверено).
- **Тесты (DELIVERY):** `python -m pytest tests/civic/R07 -q` — 97 PASS (новые файлы раунда 14 — `test_r07_heat.py`, `test_r07_heat_ui.py`; в том числе 6 500 жалоб за 90 дней < 300 мс); браузер: `python -m ui.civic_heat.devserver &` затем `NODE_PATH=$(npm root -g) node tests/civic/R07/browser/shots.js` — 16 PASS.
- **Ограничения:** демо-жалобы; «Я тоже» стареет вместе с жалобой (нет времени нажатия); «запахи» на ячейках (промзон в данных нет); фронтенд не передаёт bbox; 76 казахских строк ждут проверки.

---

## R08 · Картина дня

- **Ветка:** `claude/r14-R08`, голова 7101f46; **поставка 2 — code/tested 4ce8f08** (в B2): UX-правки R11, источники R06 (отстающие объекты и предложения), без собственного словаря. Тесты 4ce8f08: pytest 126 PASS + 1 XFAIL (ждёт демо-набор R07), UI 95/95.
- **Назначение:** одна функция `summary(date, district)` — всё, что аким должен понять за 10 секунд: 4 KPI, горячие места, темы, районы, объекты с отставанием, предложения; текстовая сводка ru/kk по шаблону без LLM.
- **Файлы:** `ui/civic_akim/{summary.py (AkimService, кэш 30 с), text.py (склонения ru/kk, «1 666», «40 %», «в 2,5 раза»), sources.py (R07, R06 или фикстуры), deadlines.py (DEADLINE_DAYS), api.py, __main__.py, fixtures/}`; `web/civic/akim/{index.html, akim.js (BirgeAkim), akim.css (+ печать), akim.i18n.json}`.
- **Что считает:** время Астаны UTC+5; дубли исключены; «новые за день» сравниваются с тем же отрезком суток неделю назад; «в работе» = accepted + in_progress; «просрочено» = открыта дольше срока исправления категории (`DEADLINE_DAYS`: roads 7, snow_ice 2, sidewalks 10, transport 5, lighting 3, yards 14, waste 2, utilities 1, smell_air 3, noise_safety 3, parking 14, other 10 — демо-норматив); «исправлено за неделю»; статус на любую дату восстанавливается по `status_history`; горячие места, темы и районы — **та же тепловая карта R07 за 7 дней**, топ-10; изменение < 10 — в штуках, ≥ 10 — в процентах, рост вдвое — «в N раз».
- **API:** Python `ui.civic_akim.summary(date=None, district=None, now=None)`, `configure(heat=, records=, objects=, proposals=)`; HTTP `GET /api/civic/v2/akim/summary?date=YYYY-MM-DD&district=<id|all>` (400 для даты в будущем/неизвестного района, 500 `akim_failed` без падения сервера); CLI `python -m ui.civic_akim [--date] [--district nura] [--lang kk] [--json]`.
- **Фронтенд:** `BirgeAkim.mount(el, {apiBase, mapHref, syncUrl})`; дата и район в адресе; клик по горячему месту → отменяемое событие `birge:open-target`; все состояния (загрузка, нет связи, пусто, жалобы не подключены, дата в будущем); печать на 2 листа A4.
- **Тесты (DELIVERY):** `python -m pytest tests/civic/R08 -q` — 112 PASS (summary 38, text 58, api 5, совпадение с тепловой картой 11); UI: `python tests/civic/R08/demo_server.py &` затем `NODE_PATH=$(npm root -g) node tests/civic/R08/ui_check.cjs` — 77/77 (1366 и 375, ru и kk, «числа, сводка и первое горячее место видны без прокрутки» на 1366).
- **Ограничения:** все данные пока синтетические («Пример»); сигнатура `mount` расходится с вызовом в `birge.js` R01; `store.list` R09 отдаёт не больше 5 000 записей; казахская сводка ждёт проверки.

---

## R09 · Жалоба жителя v2

- **Ветка:** `claude/modest-shannon-0ki93p`, голова 5dd6465; **code/tested fa49fc9** (в B2; совместный прогон с настоящими R12 `/targets` и R04 `/classify`, `/similar` — браузер 107/107); v1 восстановлен из `claude/focused-hypatia-z8h0no` @ 933cd90 побайтно.
- **Назначение:** запись жалобы по CONTRACT §5, «Я тоже» (одно на устройство), статусы с историей, дубли, миграция v1 → v2; мастер жителя из 5 шагов и «Мои обращения».
- **Файлы:** `ui/civic_feedback/v2/{store.py (ComplaintStore, SQLite), record.py (проверка записи, язык, ячейка 150 м, публичный/служебный вид), api.py (ComplaintsV2Service), migrate.py, categories.py (RESPONSE_DAYS), integration.py (make_service, ROUTES), web_assets.py, __main__.py}`; `web/civic/feedback/{complaint.js (BirgeComplaint), complaint-strings.js (81 ключ ru/kk), complaint.css, categories_v2.js (генерируется)}`; стенд `tests/civic/R09/stand/serve_r09.py`.
- **Маршруты (11, `/api/civic/v2`):** `GET /categories`; `POST /complaints` (201, повтор с тем же `request_id` → 200 `replayed`; устройство — заголовок `X-Birge-Device`); `GET /complaints?bbox&since&days&category&status` (без текстов); `GET /complaints/mine`; `GET /complaints/events?after=N`; `GET /complaints/summary?target_id&category&days`; `GET /complaints/place?lon&lat`; `GET /complaints/{id|B-код}`; `POST /complaints/{id}/metoo` (`added|already|author`); `POST /complaints/{id}/status` и `POST /complaints/{id}/duplicate` (только сотрудник + CSRF).
- **Статусы:** `new → accepted → in_progress → fixed`, `rejected`; разрешённые переходы заданы таблицей (`fixed → in_progress` — переоткрыть, `rejected → accepted`); `expected` защищает от одновременной правки (409); дубль переносит автора и «Я тоже» в исходную запись без двойного счёта.
- **Язык:** определяет сервер: нет казахских букв → ru; есть и встречаются русские слова-маркеры → mixed; иначе kk.
- **Привязка:** `target` из `/targets` R12; если цели нет — ячейка ~150 м с пометкой «Примерное место»; точка внутри bbox Астаны. Вопрос мастера — «Это здесь?» / «Осы жерде ме?» с вариантами-названиями (вопросительная частица в казахском зависит от последнего слова — поэтому название не вставляется в вопрос).
- **Шаги мастера:** ① «Сообщить о проблеме» → ② место (карта или «Моё местоположение») → ③ текст 3–2000 символов, подсказка категории (`/classify` через 700 мс после ввода, от 8 символов) → ④ «Об этом уже сообщили N» → «Я тоже» / «У меня другое» → ⑤ номер `B-…`, «Ответ — до …», шкала статуса.
- **Персональные данные:** публичный ответ не содержит текст, модель и устройство; устройство хранится как `sha256(соль + id)`; на шаге ③ подсказка «Не пишите телефон и ИИН»; серверного фильтра телефонов/ИИН в v2 нет (в v1 есть регулярные подсказки модератору). Лимит 20 жалоб в час с устройства.
- **Тесты (DELIVERY; в папке также тесты помощника раунда 12 — `test_r09_*.py`):** `python -m pytest -q tests/civic/R09/test_r09v2_store.py tests/civic/R09/test_r09v2_migrate.py tests/civic/R09/test_r09v2_api.py tests/civic/R09/test_r09v2_frontend.py tests/civic/R09/test_r09v2_stand_osm.py` — 83 PASS; вся папка `tests/civic/R09` — 205 PASS; браузер `node tests/civic/R09/browser_r09.cjs --screenshots <папка>` — 105/105 (и 105/105 с ui-kit R11); стенд: `python tests/civic/R09/stand/serve_r09.py --port 8790 --seed`.
- **Ограничения:** `/targets` и `/classify`/`/similar` на стенде — фикстуры; `district` = null, если клиент не прислал; ключ устройства `birge.device` отличается от `birge.device_id` других модулей; не сбрасывает кэш R07; два разных справочника сроков (R09 — первый ответ, R08 — исправление).

---

## R11 · UX и казахский язык

- **Ветка:** `claude/r14-R11`, голова a62a67c (в DELIVERY нет точного SHA — «последний коммит ветки»); в B2 — 6102dfb, в B3 — 52d7c59. Словари: 557 ключей в B2, 680 на голове ветки (ночь 10→11.10: +102 ключа из сборки — оболочка R01, R07, R12, R05, вход сотрудника; затем ключи кабинета сотрудника и кластеров R05); `tools/missing_keys.py` — ключи, которые роль использует, а в словаре их нет. Ранние версии ui-kit/i18n — в пакете (608e367). `UX_REVIEW.md` — разбор B1 и B2 по сценарию демо с правками по ролям.
- **Назначение:** UX-спецификация (`research/round-14-results/R11/UX_SPEC.md`, версия 1.2 в ветке), дизайн-токены и компоненты, словари ru/kk, проверка казахского, ежедневное UX-ревью модулей.
- **Файлы:** `web/civic/ui-kit/{tokens.css, components.css (префикс bk-, ~48 компонентов), icons.svg (49 иконок: 12 категорий + интерфейс), ui-kit.js (window.BirgeUI), index.html (витрина), fonts/ (Inter 4.0, OFL 1.1, «Birge Sans»), prototypes/}`; `web/civic/i18n/{i18n.js (window.BirgeI18n), ru.json, kk.json}`; `tests/civic/R11/{i18n_tools.py, test_r11_ui_kit.py, i18n.test.cjs, browser_check.cjs}`.
- **Токены:** текст `#152c26`, вторичный `#5b6a64`, бренд `#176b4a`, акцент `#d7f57c`, тепловая карта `#FAC775/#EF9F27/#E24B4A/#A32D2D`, «исправлено» `#639922` (значки уровня 3 и «исправлено» темнее для контраста ≥ 4.5); шрифт 14 (только мета)/16/18/20/24/32; зона нажатия 48 (56 у главной кнопки на телефоне); шапка 64/56 px, панель 400 px, шторка 120 px / 50 vh / 92 vh; анимации 200–800 мс.
- **i18n:** язык: параметр → `?lang=` (`kz` → `kk`) → `localStorage birge.lang` → ru; нет ключа в kk → ru + предупреждение `[i18n]`; склонения ru one/few/many/other; событие `birge:lang`; разметка `data-i18n`. В ветке R11 — 509 ключей ru = 509 kk (в сборке R01 — 257).
- **Проверка казахского:** `python3 tests/civic/R11/i18n_tools.py check` (полнота, шаблон имён ключей, формы склонений, одинаковые параметры, запрещённые слова «ребро», «граф», «сценарий», «payload»…, восклицательные знаки, соответствие `categories_v2.json`); `review` собирает `KK_REVIEW.md` — 29 мест с пометкой ⚑ для владельца. Носитель языка не проверял — NOT_RUN.
- **Тесты:** `python3 tests/civic/R11/i18n_tools.py check`; `python3 tests/civic/R11/test_r11_ui_kit.py` (14 проверок: контраст, цвета = JSON, ≥ 48 px, шрифт ≥ 14, лицензия шрифта, без интернета); `node tests/civic/R11/i18n.test.cjs`; `NODE_PATH="$(npm root -g)" node tests/civic/R11/browser_check.cjs --shots research/round-14-results/R11/screens` — всё PASS по отчёту.
- **Следующий шаг:** правки `kk.json` владельцем, перенос ключей модулей, UX-ревью дня 3; R01 — patch `CIVIC_ASSETS` (без него ui-kit отдаёт 404).

---

## R12 · Точность карты: цели, участки улиц, карта, редактор

- **Ветка:** `claude/tender-brahmagupta-ef5ztl`, голова 8bb7bf8; code 8810221, tested d13f49a; карта восстановлена из `claude/zen-mendel-e79iiv` (f0a52f7), редактор — из `claude/intelligent-sagan-7shpeh` (9c996c6); применён патч R06.
- **Назначение:** привязка жалоб и работ к реальным улицам и объектам OSM; участок улицы только по рёбрам графа; проверки точности CONTRACT §8; карта и редактор без линий «от руки».
- **Файлы:** `engine/civic_geo/` (только стандартная библиотека): `geo.py` (метры, проекция на ломаную, Дуглас–Пекер), `graph.py` (чтение графа со сверкой sha256, сеточный индекс 100 м), `segment.py` (`street_segment`, `snap`, `snap_along_one_street`), `objects.py` (объекты, дворы, ячейки, индекс 150 м), `targets.py`, `accuracy.py`, `api.py`, `build_geo_data.py`, `build_way_tags.py`, `snap_demo.py`; данные `data/civic/astana/geo/{objects.json, yards.json, way_tags.json, cells.json, demo_snapped.json, SOURCE.json}`; `web/civic/map/{civic-map.js, civic-map-core.js, civic-map.css}` (`window.CivicMap`); `web/civic/editor/{editor.js, editor-core.js, editor.css}` (`window.CivicEditor`).
- **Python API:** `targets(lon, lat, category=None, limit=3)`, `target_geometry({kind, id})`, `street_snap`, `segment_between`, `objects_near`, `yard_at`, `geo_status`; `api.handle(path, query)`.
- **Маршруты (подключает R01, `/api/civic/v2`):** `GET /targets?lon&lat&category[&limit≤3]`, `GET /street-segment?from=lon,lat&to=lon,lat[&kind=road|foot]`, `GET /street-snap`, `GET /objects-near`, `GET /yard`, `GET /geo/status`; ошибки 400 (`bad_point`, `outside_city`, `unknown_category`, `not_on_street`, `too_short`, `no_path`, `too_long`, `gap`), 503 `geo_unavailable`.
- **Алгоритм `targets`:** виды целей — из `target_kinds` категории; объект — до 3 ближайших в 150 м (фильтр видов: transport → остановки, yards → площадки/парки, waste → мусор); участок — рёбра в 80 м с предпочтением групп (дорога/тротуар) по категории и штрафами за безымянные рёбра, одна улица — один кандидат; двор — содержащий точку или ближайший в 40 м; иначе ячейка `cell-<ix>-<iy>` (150 м, `approximate: true`); сортировка по расстоянию + штрафы, не больше 3.
- **Участок улицы:** обе точки прилипают к рёбрам в 60 м; путь — Дейкстра с штрафом ×3 за другое название улицы и ×1.6 за чужую группу; предел min(6 км, 3 × прямая + 400 м); вершины OSM не меняются.
- **Карта:** не создаёт свою карту — использует MapLibre хоста (`CivicMap.mount({root, map, api, …})`); подложка — OpenFreeMap (стиль liberty, 3D-здания с z 14); без сети — офлайн-фон; «Примерное место» — мягкая область 120 м.
- **Редактор:** инструменты «Точка», «Участок улицы» (два нажатия, предпросмотр, проезжая часть/тротуар), «Выбрать двор», «Площадь по углам», «Изменить вершины»; линию «от руки» нарисовать нельзя; блок «Этап работ» R06.
- **Тесты (DELIVERY):** `python3 -m pytest -q tests/civic/R12/test_civic_geo.py` — 29/29; `python3 -m engine.civic_geo report` — 954/954 PASS; `python3 -m engine.civic_geo bench 3000` — p50 0.23 мс / p95 0.61 мс; `node --test tests/civic/R12/map/core.test.mjs` — 29/29; `node --test --test-concurrency=1 tests/civic/R12/map/browser.test.mjs` — 69/69; приёмка в настоящем приложении `NODE_PATH=$(npm root -g) node tests/civic/R12/map/app_acceptance.mjs <папка>` — 12 PASS / 0 FAIL / 1 NOT_RUN (OpenFreeMap 403); редактор на настоящем графе `node --test tests/civic/R12/editor/e2e_r12_real.test.cjs` — 1/1.
- **Сборка данных и CLI:** `python3 -m engine.civic_geo build-data` (из `data/civic/astana/osm-objects/raw/*.json.gz`), `build-way-tags`, `snap-demo`, затем `report [--json out.json]`; проверка одной точки — `python3 -m engine.civic_geo targets LON LAT CATEGORY`, участок — `python3 -m engine.civic_geo segment LON,LAT LON,LAT [--kind road|foot]`.
- **Ограничения:** 5 маршрутов кроме `/targets` не подключены у R01; 403 остановки без названия; 217 фонарей OSM не предлагаются как объекты; соседние рёбра одной улицы — разные цели (две жалобы в 20 м могут попасть в разные цели).

---

## R13 · Прогноз проблем (прототип)

- **Ветка:** `claude/r14-R13`, голова 7d60222; поставка 2 — code/tested **15fc856** (реальная погода LOCAL-9, kk-правки); поставка 1 — 8705829 (в B2/B3).
- **Назначение:** ежемесячный прогноз территорий с риском жалоб (кейс Gton «Предиктивная аналитика»); для диплома — вторая модель. Реальной истории обращений нет → честный прототип на синтетической истории с пометкой synthetic.
- **Файлы:** `ml/civic_forecast/{targets.py (2 334 территории из данных R12), weather.py (CSV Open-Meteo → месячные признаки), history.py (синтетическая история), features.py, model.py (градиентный бустинг + запасная модель без зависимостей), reasons.py (причины ru/kk), backtest.py, README.md, RESULTS.md, results.json, data/}`; `ui/civic_forecast/` (`forecast`, `forecast_response`, `attention_next_month`, кэш `data/forecast_cache.json`); `tests/civic/R13/`; patch маршрута для R01 — `research/round-14-results/R13/r01_forecast_route.patch`.
- **Модель:** признаки «территория × месяц» (жалобы за 1/3/12 месяцев по категориям, тот же месяц год назад, тренд, погода месяца, тип территории); цель — ≥ 4 жалоб в следующем месяце (в среднем 3.3 % территорий); `HistGradientBoosting` и запасная «сезонная наивная + взвешенная частота».
- **Backtest (история жалоб синтетическая, погода реальная Open-Meteo; 3 seed × 16 месяцев 2025-07…2026-10; 15fc856):** precision@10/20/30 — бустинг 0.57 / 0.51 / 0.47; без погоды 0.59 / 0.51 / 0.46; запасная 0.57 / 0.51 / 0.46; «как в прошлом месяце» 0.47 / 0.40 / 0.38; «год назад» 0.40 / 0.36 / 0.32; случайно 0.04. Ориентир Gton 60–70 % не достигнут; погода ≈ 0 (−0.006). На фикстуре (8705829) было 0.58 / 0.49 / 0.44.
- **API:** `forecast(month, district, k)` — из кэша < 1 мс (холодная загрузка ~30 мс; месяц вне кэша — ~3.5 с один раз); маршрут `GET /api/civic/v2/forecast` — после patch R01; блок «Внимание в следующем месяце» для R08 — `attention_next_month`.
- **Тесты (DELIVERY):** `python3 -m pytest tests/civic/R13` — 30 passed / 7 skipped (без шлюза R01); с `R13_R01_WEB_SERVER` (шлюз R01 @ d3c33d9 + patch) — 37/37; без scikit-learn — PASS (запасная модель).
- **Ограничения:** история жалоб синтетическая (погода с 15fc856 — реальная, LOCAL-9); территории — снимок данных R12 @ d13f49a (при обновлении — `build-targets` + `build-cache`); 138 из 1 307 безымянных территорий без ориентира в 800 м; казахские тексты причин — черновик; день записи в `history.to_records` считается через встроенный `hash()` (строка 276 на 8705829 — не исправлено): даты демо-записей зависят от `PYTHONHASHSEED`; счётчики и backtest от этого не зависят.

---

## R10 · Приёмка

- **Ветка:** `claude/r14-R10`, голова ac8508e; тесты — code 08392e7 (в сборке с шага B3 be82fa8 как 9c364c7); пути `tests/civic/R10/`, `tests/e2e/`, `research/round-14-results/R10/`.
- **Инструменты:** `tests/e2e/run_acceptance.cjs --root <рабочая копия сборки> --out <папка> --label B2` — одной командой поднимает сервер сборки как `run-city.bat` (`CIVIC_DEMO=1`, временная база, демо-данные, сотрудник) и прогоняет: сценарий `demo_flow.cjs` (API + интерфейс, 1366×768 и 375×812, ҚАЗ/РУС, только видимые слова), UX-чек-лист `ux_screens.cjs`, точность `tests/civic/R10/accuracy.py`. Для Windows — `CODEX_ACCEPTANCE_PROMPT.txt`.
- **Сделано:** приёмка B1 (d3c33d9) и **B2 (f54361d)** — `ACCEPTANCE_B1.md`, `ACCEPTANCE_B2.md`, протоколы и кадры `e2e/b1/`, `e2e/b2/`; проверка поставок ролей (`DELIVERIES_CHECK.md`); независимая точность CONTRACT §8 (`accuracy/*.json`); дефекты B-001…B-026 (`BUGS.md`, у каждого — владелец, статус, обход для демо, часто готовая правка).
- **Итог B2:** сценарий проходит целиком, блокеров нет (B-001 закрыт); API 19/19; интерфейс 1366 ru/kk — все 6 шагов, 375 — кроме постановки проекта (B-022); точность 24 PASS / 4 FAIL (B-007…B-009, данные R05 и R12).
- **Открытые важные:** B-019 (нажатие по значку остановки в «Где проблема?»), B-020 (панель «Территория» над шторкой на 375), B-021 (кабинет сотрудника: тех. слова, русский в ҚАЗ), B-012 (лента работ раунда 13 по-русски в ҚАЗ), B-013/B-014 (надписи < 14 px, кнопки < 40 px), B-016 (значки без числа ниже z15 — R07 306074b заявляет исправление), B-007 (ж/д платформы как остановки).
- **Дальше:** приёмка FINAL (15.10) и Codex на Windows по `CODEX_ACCEPTANCE_PROMPT.txt`.

---

## R15 · Ревью безопасности

- **Ветка:** `claude/r14-R15`, голова 77bd744; тесты — c5b98a0 (`tests/civic/R15/`), patch — b892532 (`research/round-14-results/R15/patches/P-R01|R02|R04|R07|R09.diff`). Проверена сборка R01 be82fa8 (шаг B3) и ветки ролей; только локально, своя временная база.
- **Как проверить:** `R15_ROOT=<рабочая копия сборки> python -m pytest tests/civic/R15 -q -rxX` — на be82fa8: 80 passed, 19 xfailed (каждая открытая находка воспроизводится); после всех patch — 19 XPASS (strict: pytest покажет их как failed с пометкой XPASS — это сигнал «исправлено», снять пометку и перенести ID в `FIXED` в `tests/civic/R15/r15_common.py`).
- **Итог:** критичных нет; важных 11 (S09 исправлена ещё в B1), мелочей 3. Главные: S04+S11 подпись цели из запроса жителя видна всем; S03+S13 точка жителя восстанавливается до метра; S02+S08+S12 накрутки; S07+S14 ФИО с отчеством проходят обезличивание и уходят в LLM. Раздел для жюри «как Birge защищает данные» — `SECURITY_REVIEW.md`.
- **Кому что:** patch P-R01 (CSP, лимиты v2 по адресу, журнал без строки запроса), P-R09 (огрубление точки, подписи с карты, сверка цели с точкой, CSRF, цифры), P-R07 (подпись из OSM), P-R04 (`/similar` от огрублённой точки), P-R02 (отчества, не слать в LLM тексты с подозрением на ПДн) — применяет R01 к FINAL.

---

## Модули раундов 11–13 (работают через `/api/civic/v1`)

| Модуль | Пути | Что делает |
|---|---|---|
| Хранилище объектов и сотрудников | `ui/civic_store/` | Реестр объектов работ на SQLite, сессии сотрудников (`create-editor`), импорт демо-среза (`init`, `seed-demo`), аудит. В раунде 14 расширен R06 |
| Сообщения жителей v1 | `ui/civic_feedback/service.py`, `text.py`; `web/civic/feedback/feedback.js` | Сообщения с очередью модерации, 6 категорий v1, публикация только с согласием; заменяется v2 R09 (миграция v1 → v2) |
| Сравнение перекрытий A/B | `engine/civic_scenarios/`, `web/civic/scenarios/` | Дейкстра на пешеходном графе (целые мм), дельта длины пути для базы и двух планов перекрытий; лимиты 25 стартов / 100 целей / 100 перекрытий. В шапке Birge скрыто |
| Помощник по фактам | `agent/civic_assistant/`, `web/civic/assistant/` | Ответы по проверенным фактам карточки, числа собирает код; в сборке без LLM (`provider=None`). Скрыто |
| Карта и редактор | `web/civic/map/`, `web/civic/editor/` | В раунде 14 у R12 |
| Классификатор v1 | `ml/civic_classifier/` (ветка `claude/wizardly-ptolemy-qy8ltw` @ 14c3384) | Логрегрессия SGD на символьных 2–5-граммах + словарь, 6 категорий; synthetic test macro-F1 0.871 [0.780–0.928]; модель `model.json.gz` (~105 КБ, JSON без pickle); `python -m ml.civic_classifier build-corpus|train|evaluate|predict|info`; тесты `python -m pytest tests/civic/R08 -q` (нумерация раунда 12) |

## Хакатонный симулятор «Аким на 5 часов» (заморожен)

- `engine/`: `load_data`, `validate`, `simulate`, `baseline`, `optimize` (полный перебор C(14,5) = 2 002 наборов мер × районы ≈ 1.4 млн сценариев, numpy), `list_events`, `robustness`, `compare`; формула Score = 0.7·D_avg + 0.3·min D − 1.0·N_crit (порог критического значения < 40). Эталоны: база 52.56, пример ТЗ 56.54 — `python check.py`.
- `agent/`: советник с function calling (OpenAI-совместимый API, ключ в `.env`), офлайн-разбор без ключа.
- Данные: `data/city_data.json` (учебный датасет ТЗ), `data/events.json`. Описание — `README.md`, `PROJECT_CONTEXT.md`, `engine/README.md`.
- В интерфейсе Birge доступен по ссылке `#training`.
