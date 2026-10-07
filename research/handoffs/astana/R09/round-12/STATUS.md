# R09 — помощник по городским данным без выдумок (раунд 12, Астана)

Статус: PARTIAL (checkpoint 1)
Обновлено: 2026-10-07 10:30 UTC
Ветка: claude/fervent-dijkstra-1cqrg5 (назначенная ветка сессии)
CODE_BASE_SHA: 56538a3a7504d4589c38ab4d3c5107f12aa7f8a6 — влит обычным merge (56885d5), без reset/force push.
Ветка до merge содержала только файлы R10 раунда 11 (tests/civic/R10, research/round-11-results/R10, их handoff) —
их нет в базе, конфликтов нет. Работа R09 ограничена путями:
agent/civic_assistant/, web/civic/assistant/, tests/civic/R09/, research/round-12-results/R09/, этот файл.
Сравнение: `git diff 56538a3 -- agent/civic_assistant web/civic/assistant tests/civic/R09`.

## Сделано
- Прочитаны facts/answer/render/audit/providers/scenario/api на базе; R09 pytest на базе 122/122.
- Независимые проверки R10 (tests/civic/R10/standalone/standalone_r09.py) на базе: исправлены прежние D003/D004/D005;
  остаются: CancelledError провайдера выходит из build_answer; зависшие вызовы провайдера занимают пул.
- Checkpoint 1: вопросы жителя RU/KK, которые уходили в угаданный обзор:
  новый intent `missing_data` («Какие сведения отсутствуют?», «Қандай мәліметтер жоқ?») — список полей с known=False,
  оговорка «пусто ≠ ноль», отметка о сдвиге срока без опубликованной причины; маршрутизация
  «Это реальные данные?», «Работы уже идут?», «Куда жаловаться?», «Құны қайдан алынды?», «Неше күнге ұзартылды?».
- tests/civic/R09/test_r09_round12_questions.py — 32 регрессии; R09 pytest 154/154.

## Следующий шаг
Сценарий A/B по фактическому результату движка: длины маршрутов, разница, активные интервалы, неизвестный доступ,
дата снимка OSM, пределы модели.
