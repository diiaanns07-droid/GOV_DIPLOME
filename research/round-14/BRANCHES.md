# Раунд 14 — где чья ветка (ведёт координатор)

Новая сессия роли: если здесь для твоей роли указана ветка — это ПРОДОЛЖЕНИЕ. Переключись на неё, прочитай
research/handoffs/astana/<роль>/round14/STATUS.md в этой ветке и продолжи с «следующего шага». Новую ветку не создавай.

| Роль | Ветка | Последний checkpoint (10 окт) |
|---|---|---|
| R01 Интегратор | claude/sharp-dijkstra-0t87gl | база I0 готова, оболочка ru/kk, шлюз API v2; дальше включение поставок → B1 |
| R02 Данные | claude/r14-R02 (первые коммиты ушли в claude/round-14-package @ 887ef4b) | ГОТОВО (ready_for_review): разметка, synth_v3, v1_in_v2, LLM-скрипты (запуск локально) |
| R03 Модель v2 | claude/r14-R03 | конвейер v2 готов (проверен на крошечной модели); дальше тесты, RUN.txt, обучение на GPU |
| R04 Дубли и ML-API | (ветка сессии появится после первого push) | запущена 10 окт на b2 |
| R05 3D-превью | claude/r14-R05 | все 5 объектов ставятся; дальше тесты, скриншоты, DELIVERY |
| R06 Предложения и этапы | claude/round-14-r06 | ГОТОВО (поставка 3d10f7d): 445 тестов, браузер 48/48; ждёт R01 и patch для R12 |
| R07 Тепловая карта | claude/upbeat-knuth-i0rqaa | ГОТОВО на демо-данных (ready_for_review); ждёт R01 и живые данные R09/R12 |
| R08 Картина дня | claude/r14-R08 | ПОСТАВКА 1 (код 9f1d9c0), UI 77/77; ждёт функции R06 и сборку B1 |
| R09 Жалоба жителя v2 | claude/modest-shannon-0ki93p | ГОТОВО (код da295be, реальные объекты OSM): ждёт R01, R04, R12 /targets |
| R10 Приёмка | — | запуск 13 окт |
| R11 UX и казахский | claude/r14-R11 | день 1 закрыт: UX_SPEC v1.1, ui-kit, 257 ключей ru/kk, KK_REVIEW |
| R13 Прогноз (прототип) | claude/r14-R13 | запуск 10 окт, b4 (новая сессия) |
| R12 Точность карты | claude/tender-brahmagupta-ef5ztl | geo-данные из реальных OSM (940 остановок, 334 площадки…), карта по OSM |

Входные данные LOCAL готовы в claude/round-14-package @ bdf12c8: data/civic/astana/osm-objects/ (12 наборов OSM, 3513 объектов), web/vendor/three/ (three.js 0.169.0), research/round-14-results/LOCAL/ENV.md (Python 3.12 + CUDA, модели в кэше). Забрать в свою ветку: git fetch origin claude/round-14-package && git checkout origin/claude/round-14-package -- <путь>
