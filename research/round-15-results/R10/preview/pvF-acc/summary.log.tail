# R10 · приёмка сборки pvF (R01 B0.4 197ad600 + роли 17:25 UTC)

Код: `197ad600` · отчёт: `/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/runs/pvF-acc`

## Можно показывать: **нет**

- ❌ сцены 7–9: UI show-ru 7 Ctrl+K «Сцена 7 · Двор вместе» → раздел yard ≤ 1 с; UI show-kk 7 Ctrl+K «7-көрініс · Аула бірге» → раздел yard ≤ 1 с

Смотреть (не блокирует):
- часть 1, качество вида: UI 1366-ru 0 контраст текста ≥ 4.5:1 (крупный ≥ 3:1), UX_BRIEF ; UI 1366-ru 0 зоны нажатия ≥ 40 px (цель — 48 px); UI 1366-kk 0 контраст текста ≥ 4.5:1 (крупный ≥ 3:1), UX_BRIEF ; UI 1366-kk 0 зоны нажатия ≥ 40 px (цель — 48 px)
- сцены 7–9, качество вида: 16 FAIL (шрифт / зоны / контраст / термины) у R09, R16 — BUGS
- аудит экранов: FAIL 31 у R08, R12 + R17, R13, R16 — BUGS

| Проверка | Итог |
|---|---|
| pytest tests/civic/R10 | 50 passed |
| API v2 (CONTRACT §7) | PASS 155 · FAIL 0 · NOT_RUN 0 (жёстких FAIL 0) |
| Согласованность чисел | PASS 16 · FAIL 0 · NOT_RUN 0 |
| Часть 1 (шаги 1–7 FINAL-4) | PASS 166 · FAIL 6 · NOT_RUN 2 (база FINAL-4: 172 / 0 / 0) |
| Время части 1, с | 1366-ru 226.8 (FINAL-4 226.9), 1366-kk 228.4 (FINAL-4 233.8), 375-ru 174.8 (FINAL-4 181.3), 375-kk 178.7 (FINAL-4 185.5) |
| Сцены 7–9 «Бірге» | PASS 311 · FAIL 18 · NOT_RUN 0 |
| Первый значок карты, мс | 1366x768-ru-resident 2562, 1366x768-ru-akimat 2499, 1366x768-kk-resident 2434, 1366x768-kk-akimat 2513, 375x812-ru-resident 1936, 375x812-ru-akimat 2156, 375x812-kk-resident 2108, 375x812-kk-akimat 2168 |
| Производительность | PASS первый значок с числом, 1366x768; ИНФО перемещение карты, 1366x768; PASS «Хроника города» доигрывает до конца, 13; ИНФО «Хроника города» плавность, 1366x768; PASS «Спросить Birge»: время ответа |
| Аудит экранов (VISUAL_BRIEF §4, П1) | PASS 482 · WARN 61 · FAIL 31 · NOT_RUN 0 |
| Эталон A (47 элементов) | совпадает/близко 18 из 47, пиксели 73.6 % (FINAL-4: 18 из 47, 75.1 %) |

Шаги (код возврата, время):

```
label pvF (R01 B0.4 197ad600 + роли 17:25 UTC)
root /tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/pvF
sha 197ad600
pytest {'rc': 0, 'time': '48s'}
api {'rc': 0, 'time': '20s'}
numbers {'rc': 1, 'time': '18s'}
e2e {'rc': 1, 'time': '826s'}
v2 {'rc': 1, 'time': '383s'}
map {'rc': 0, 'time': '357s'}
perf {'rc': 0, 'time': '84s'}
audit {'rc': 0, 'time': '445s'}
ref {'rc': 0, 'time': '63s'}
numbers-rerun {'rc': 0, 'time': '18:25'}
```
