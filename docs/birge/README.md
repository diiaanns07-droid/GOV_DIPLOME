# Birge · документация для продолжения работы

Документы роли R14 (раунд 14) по фактическому коду веток ролей; срез — ночь 10→11 октября 2026, сборка **B2**
(R01 `claude/sharp-dijkstra-0t87gl` @ f54361d: сценарий демо проходит, весь pytest 2 377 passed). Начните с нужного вопроса:

| Вопрос | Документ |
|---|---|
| Как устроена система, кто с кем говорит, как идут данные | `ARCHITECTURE.md` |
| Где код модуля, его функции, маршруты, тесты, ограничения, ветка и SHA | `MODULES.md` |
| Как запустить на Windows с нуля, где модели и данные, частые ошибки | `RUNBOOK.md` |
| Какие данные есть, откуда, лицензия, что реальное и что синтетическое | `DATA.md` |
| Как продолжать с ChatGPT/Codex: правила, открытые задачи, готовые промпты | `CONTINUE_WITH_GPT.md` |
| Ключевые цифры проекта с источниками (для диплома и презентации) | `../../research/round-14-results/R14/FACTS.md` |
| Черновик дипломной работы | `../diploma/README.md` |
| Приёмка сборки, дефекты с владельцами | `research/round-14-results/R10/ACCEPTANCE_B2.md`, `BUGS.md` (ветка `claude/r14-R10`) |
| Безопасность и персональные данные | `research/round-14-results/R15/SECURITY_REVIEW.md` (ветка `claude/r14-R15`) |
| Проверка на Windows с настоящей подложкой и моделью | `research/round-14-results/LOCAL/LOCAL_B2.md` (ветка `claude/round-14-package`) |

Первоисточники, которые эти документы пересказывают: `research/round-14/CONTRACT.md` (контракт),
`research/round-14/UX_BRIEF.md` и `research/round-14-results/R11/UX_SPEC.md` (интерфейс),
`research/round-14/categories_v2.json` (категории), `research/round-14-results/<роль>/DELIVERY.json` и
`research/handoffs/astana/<роль>/round14/STATUS.md` (состояние каждого модуля).
Если документ расходится с кодом — прав код; исправьте документ.
