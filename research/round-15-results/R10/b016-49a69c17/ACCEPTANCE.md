# R10 · приёмка сборки B0.16 R01 49a69c17

Код: `49a69c17` · отчёт: `/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/runs/b016-acc`

## Можно показывать: **да**

- блокеров нет

Смотреть (не блокирует):
- сцены 7–9, проверить на ноутбуке (облако — программный WebGL): UI show-ru 7 Ctrl+K «Сцена 7 · Двор вместе» → раздел yard: 1139 мс, без кадров карты 59 мс; UI show-kk 7 Ctrl+K «7-көрініс · Аула бірге» → раздел yard: 1018 мс, без кадров карты 156 мс

| Проверка | Итог |
|---|---|
| pytest tests/civic/R10 | 50 passed |
| API v2 (CONTRACT §7) | PASS 155 · FAIL 0 · NOT_RUN 0 (жёстких FAIL 0) |
| Согласованность чисел | PASS 16 · FAIL 0 · NOT_RUN 0 |
| Часть 1 (шаги 1–7 FINAL-4) | PASS 172 · FAIL 0 · NOT_RUN 2 (база FINAL-4: 172 / 0 / 0) |
| Время части 1, с | 1366-ru 188.8 (FINAL-4 226.9), 1366-kk 194.8 (FINAL-4 233.8), 375-ru 163.3 (FINAL-4 181.3), 375-kk 167.1 (FINAL-4 185.5) |
| Сцены 7–9 «Бірге» | PASS 335 · FAIL 0 · NOT_RUN 0 · ИНФО 2 |
| Первый значок карты, мс | 1366x768-ru-resident 1816, 1366x768-ru-akimat 1732, 1366x768-kk-resident 1751, 1366x768-kk-akimat 1803, 375x812-ru-resident 1550, 375x812-ru-akimat 1512, 375x812-kk-resident 1585, 375x812-kk-akimat 1599 |
| Производительность | PASS первый значок с числом, 1366x768; ИНФО перемещение карты, 1366x768; PASS «Хроника города» доигрывает до конца, 13; ИНФО «Хроника города» плавность, 1366x768; PASS «Спросить Birge»: время ответа |
| Аудит экранов (VISUAL_BRIEF §4, П1) | PASS 534 · WARN 40 · FAIL 0 · NOT_RUN 0 |
| Эталон A (47 элементов) | совпадает/близко 18 из 47, пиксели 73.7 % (FINAL-4: 18 из 47, 75.1 %) |

Шаги (код возврата, время):

```
label B0.16 R01 49a69c17
root /tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/r01-b016
sha 49a69c17
pytest {'rc': 0, 'time': '41s'}
api {'rc': 0, 'time': '16s'}
numbers {'rc': 0, 'time': '13s'}
e2e {'rc': 0, 'time': '728s'}
v2 {'rc': 0, 'time': '390s'}
map {'rc': 0, 'time': '313s'}
perf {'rc': 0, 'time': '65s'}
audit {'rc': 0, 'time': '426s'}
ref {'rc': 0, 'time': '53s'}
```
