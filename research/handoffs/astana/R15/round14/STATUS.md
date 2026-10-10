# R15 — раунд 14 (Birge): независимое ревью безопасности · handoff

Роль: R15 Ревью безопасности и защиты данных. Ветка: **`claude/r14-R15`** (от claude/round-14-package @ 4bbf456).
Свои пути: tests/civic/R15/, research/round-14-results/R15/, этот файл. Чужой код не меняем — patch в INTEGRATION.txt.

## Статус (2026-10-10, старт)
- Ветка создана, пакет раунда прочитан (COMMON, CONTRACT, BRANCHES, prompts/R15.txt).
- Скачаны ветки ролей раунда 14 (см. BRANCHES.md), идёт чтение кода.

## Checkpoint 1 (2026-10-10)
- tests/civic/R15: conftest (R15_ROOT — проверка любой рабочей копии), r15_common (каталог находок S01…),
  test_r15_server.py. На сборке R01 bc7c961: 38 passed, 2 xfailed (S01 CSP, S09 путь cookie).
- Проверено: статика R01 — только белый список (15 попыток выхода за web/ -> 404); Origin/Sec-Fetch-Site/415/OPTIONS;
  Host чужого сайта -> 403; staff-маршруты v1/v2 без сессии -> 401/403/503; cookie HttpOnly+SameSite=Strict.
- Цепочка поставки: three.js 0.169.0 и MapLibre 5.6.2 побайтно = пакеты npm (sha256 сверены); CDN в рантайме нет.
- История веток раунда 14: ключей API нет; телефоны/ИИН — только тестовые образцы обезличивания.

## Следующий шаг
1. Ревью ui/web_server.py сборки R01 (claude/sharp-dijkstra-0t87gl): статика, cookie, CSRF, CSP, шлюз v2.
2. Ревью модулей ролей (R04, R06, R07, R08, R09, R12) по 6 пунктам prompts/R15.txt.
3. Тесты tests/civic/R15/, SECURITY_REVIEW.md, INTEGRATION.txt.
