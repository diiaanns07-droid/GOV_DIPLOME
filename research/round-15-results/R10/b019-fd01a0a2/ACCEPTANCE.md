# R10 · приёмка сборки B0.19 R01 fd01a0a2

Код: `fd01a0a2` · отчёт: `/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/runs/b019-acc`

## Можно показывать: **да**

- блокеров нет

| Проверка | Итог |
|---|---|
| pytest tests/civic/R10 | 50 passed |
| API v2 (CONTRACT §7) | PASS 155 · FAIL 0 · NOT_RUN 0 (жёстких FAIL 0) |
| Согласованность чисел | PASS 16 · FAIL 0 · NOT_RUN 0 |
| Часть 1 (шаги 1–7 FINAL-4) | PASS 172 · FAIL 0 · NOT_RUN 2 (база FINAL-4: 172 / 0 / 0) |
| Время части 1, с | 1366-ru 191.1 (FINAL-4 226.9), 1366-kk 193.4 (FINAL-4 233.8), 375-ru 162.9 (FINAL-4 181.3), 375-kk 166.2 (FINAL-4 185.5) |
| Сцены 7–9 «Бірге» | PASS 337 · FAIL 0 · NOT_RUN 0 |
| Первый значок карты, мс | 1366x768-ru-resident 1751, 1366x768-ru-akimat 1844, 1366x768-kk-resident 1715, 1366x768-kk-akimat 1796, 375x812-ru-resident 1532, 375x812-ru-akimat 1594, 375x812-kk-resident 1590, 375x812-kk-akimat 1585 |
| Производительность | PASS первый значок с числом, 1366x768; ИНФО перемещение карты, 1366x768; PASS «Хроника города» доигрывает до конца, 13; ИНФО «Хроника города» плавность, 1366x768; PASS «Спросить Birge»: время ответа |
| Аудит экранов (VISUAL_BRIEF §4, П1) | PASS 549 · WARN 15 · FAIL 0 · NOT_RUN 0 |
| Эталон A (47 элементов) | совпадает/близко 18 из 47, пиксели 73.7 % (FINAL-4: 18 из 47, 75.1 %) |

Шаги (код возврата, время):

```
label B0.19 R01 fd01a0a2
root /tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/r01-b019
sha fd01a0a2
pytest {'rc': 0, 'time': '41s'}
api {'rc': 0, 'time': '16s'}
numbers {'rc': 0, 'time': '15s'}
e2e {'rc': 0, 'time': '728s'}
v2 {'rc': 0, 'time': '373s'}
map {'rc': 0, 'time': '310s'}
perf {'rc': 0, 'time': '65s'}
audit {'rc': 0, 'time': '428s'}
ref {'rc': 0, 'time': '56s'}
```
