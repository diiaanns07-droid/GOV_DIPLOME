# R09 — помощник по городским данным без выдумок (раунд 12, Астана)

Статус: DONE (финальная сдача раунда 12; ограничения — ниже)
Обновлено: 2026-10-07 10:50 UTC
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

- Checkpoint 2 (сценарий A/B только по результату движка R07, без пересчёта):
  длины пути без перекрытий / A / B и разницы — значения compare() (vs_baseline.pairs, a_vs_b.pairs), до 3 пар,
  иначе прежняя сводка; интервалы перекрытий из серверного входа сценария, проверенного по input.payload_digest,
  активность — по inactive_closures движка; сеть, дата снимка OSM (06.05.2026), дата получения (07.10.2026),
  лицензия ODbL — из MANIFEST, только если id+digest графа совпадают с расчётом; доля неизвестного доступа;
  предупреждение graph_is_slice; «не ранжирует варианты», «не время в пути / не пробки».
  api.r07_case_loader отдаёт {schema: civic-assistant-scenario-input-v1, result, payload, graph};
  ScenarioResultCache: сравнения пользователя, посчитанные сервером, доступны как scenario_id="result:<digest>"
  (нужно подключение R01 — см. INTEGRATION.txt). tests/civic/R09/test_r09_round12_scenario.py (14, реальный движок
  на городском кейсе). R09 pytest 168/168.

- Checkpoint 3 (устойчивость и UI):
  любое исключение провайдера (в т.ч. CancelledError/SystemExit из его потока) -> шаблон + provider_error;
  все слоты провайдера заняты зависшими вызовами -> сразу шаблон + provider_busy (раньше ложный provider_timeout
  после полного ожидания); слоты восстанавливаются. Ответ содержит object_revision/object_updated_at и sources
  (издатель, дата, ссылка http(s) из карточки). assistant.js: подпись источника «издатель, опубл. дата · ссылка»
  (ID — в подсказке), строка «По данным карточки: редакция N от DD.MM.YYYY», mount({revision}) и
  handle.update({objectId, scenarioId, revision}): ответ по другой редакции не показывается, запрос при
  обновлении карточки отменяется. Новый пример «Какие сведения отсутствуют?».
  tests/civic/R09/test_r09_round12_robustness.py (20), ui_check.cjs +6 проверок (22/22 в Chromium).
  R09 pytest 188/188. Скриншоты компонента (демо, не интеграция): research/round-12-results/R09/screenshots/.

- Checkpoint 4 (f8aea9a): eval-набор раунда 12 по запущенному приложению (база + R09) —
  tests/civic/R09/eval_r12_live.py: 7 опубликованных синтетических объектов x 12 вопросов RU/KK, 3 кейса R07 x 3
  вопроса, отрицательные (несуществующий объект, факты в теле, пароли, инъекция, лимит 20/мин); протокол ошибок и
  сценарий демонстрации — research/round-12-results/R09/EVAL_PROTOCOL.md; RUN.txt, INTEGRATION.txt;
  r01_integration.patch для файлов R01 (не применён; проверен на копии); скриншоты реального приложения.
- Финал: DELIVERY.json, отчёты eval (EVAL_REPORT.txt, eval_results.json, eval_live.json) сгенерированы на f8aea9a.

## Проверки (на code_sha f8aea9a)
- R09 pytest: 188 passed (база: 122).
- Adversarial eval `python3 -B -m agent.civic_assistant.evaluate --ui`: PASS 59 / FAIL 0 / NOT_RUN 1 (живой LLM).
- Live eval по приложению: 104/104 PASS.
- UI-компонент в Chromium (ui_check.cjs): 22/22 PASS.
- r01_integration.patch: `git apply --check` на 56538a3 OK; на копии base+R09+patch пользовательское сравнение
  объясняется как scenario_id=result:<digest>, неизвестный digest -> scenario_not_found.
- Независимые проверки R10 раунда 11 (standalone_r09.py, не мой файл): 20/22 (база 19/22). Остаются test_17 —
  служебная оговорка «UI exists now» (UI есть и на базе; XSS проверен в Chromium) и test_20 — намеренная замена
  ожидания на быстрый provider_busy при занятых слотах (см. DELIVERY.json).
- NOT_RUN: живой LLM (платный API вне бюджета); подложка/3D карты (OpenFreeMap заблокирован прокси).

## Не завершено
- Подключение в общих файлах R01 (shell.js передаёт revision; gateway кэширует результаты /scenarios/compare) —
  только предложенный patch; объяснение собственного сравнения пользователя без него недоступно.
- Экран сценариев R07 не монтирует помощник (предложение в INTEGRATION.txt п.2).
- Казахские формулировки не проверены носителем языка; все данные синтетические.

## Последний успешно отправленный SHA
f8aea9a763c81775c85bbdaa6c429b49a245d60a (код и тесты). Коммит сдачи (DELIVERY.json, отчёты eval, этот файл)
отправляется следом; его SHA — в итоговом сообщении роли (SHA коммита внутри самого коммита не пишется).

## Следующий шаг
Владелец R01 применяет research/round-12-results/R09/r01_integration.patch и перезапускает
tests/civic/R09/eval_r12_live.py по RUN.txt п.4.
