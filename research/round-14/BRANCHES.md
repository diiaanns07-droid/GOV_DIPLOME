# Раунд 14 — где чья ветка (ведёт координатор)

Новая сессия роли: если здесь для твоей роли указана ветка — это ПРОДОЛЖЕНИЕ. Переключись на неё, прочитай
research/handoffs/astana/<роль>/round14/STATUS.md в этой ветке и продолжи с «следующего шага». Новую ветку не создавай.

| Роль | Ветка | Последний checkpoint (10 окт) |
|---|---|---|
| R01 Интегратор | claude/sharp-dijkstra-0t87gl | шлюз API v2 с ответом module_not_ready |
| R02 Данные | claude/r14-R02 (первые коммиты ушли в claude/round-14-package @ 887ef4b) | инструмент разметки, обезличивание, импорт формы, kappa |
| R03 Модель v2 | — | не запущена или ещё без push |
| R04 Дубли и ML-API | — | не запущена |
| R05 3D-превью | claude/r14-R05 | three.js 0.169.0, ядро build3d |
| R06 Предложения и этапы | claude/round-14-r06 | предложения, голоса, демо на реальных участках OSM |
| R07 Тепловая карта | claude/upbeat-knuth-i0rqaa | демо-цели из OSM, демо-жалобы, API тепловой карты |
| R08 Картина дня | — | не запущена или ещё без push |
| R09 Жалоба жителя v2 | claude/modest-shannon-0ki93p | мастер жалобы v2, «Мои обращения» |
| R10 Приёмка | — | запуск 13 окт |
| R11 UX и казахский | claude/r14-R11 | день 1 закрыт: UX_SPEC v1.1, ui-kit, 257 ключей ru/kk, KK_REVIEW |
| R12 Точность карты | claude/tender-brahmagupta-ef5ztl | линии улиц по форме OSM, «примерное место» |

Входные данные LOCAL готовы в claude/round-14-package @ bdf12c8: data/civic/astana/osm-objects/ (12 наборов OSM, 3513 объектов), web/vendor/three/ (three.js 0.169.0), research/round-14-results/LOCAL/ENV.md (Python 3.12 + CUDA, модели в кэше). Забрать в свою ветку: git fetch origin claude/round-14-package && git checkout origin/claude/round-14-package -- <путь>
