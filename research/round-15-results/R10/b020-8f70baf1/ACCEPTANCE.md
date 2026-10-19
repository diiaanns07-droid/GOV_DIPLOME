# R10 · приёмка сборки B0.20 R01 8f70baf1

Код: `8f70baf1` · отчёт: `/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/runs/b020-acc`

## Можно показывать: **да**

- блокеров нет

| Проверка | Итог |
|---|---|
| pytest tests/civic/R10 | 50 passed |
| API v2 (CONTRACT §7) | PASS 155 · FAIL 0 · NOT_RUN 0 (жёстких FAIL 0) |
| Согласованность чисел | PASS 16 · FAIL 0 · NOT_RUN 0 |
| Часть 1 (шаги 1–7 FINAL-4) | PASS 172 · FAIL 0 · NOT_RUN 2 (база FINAL-4: 172 / 0 / 0) |
| Время части 1, с | 1366-ru 178.7 (FINAL-4 226.9), 1366-kk 182.9 (FINAL-4 233.8), 375-ru 162.2 (FINAL-4 181.3), 375-kk 165.2 (FINAL-4 185.5) |
| Сцены 7–9 «Бірге» | PASS 337 · FAIL 0 · NOT_RUN 0 |
| Первый значок карты, мс | 1366x768-ru-resident 1653, 1366x768-ru-akimat 1559, 1366x768-kk-resident 1567, 1366x768-kk-akimat 1666, 375x812-ru-resident 1562, 375x812-ru-akimat 1551, 375x812-kk-resident 1494, 375x812-kk-akimat 1618 |
| Производительность | PASS первый значок с числом, 1366x768; ИНФО перемещение карты, 1366x768; PASS «Хроника города» доигрывает до конца, 13; ИНФО «Хроника города» плавность, 1366x768; PASS «Спросить Birge»: время ответа |
| Аудит экранов (VISUAL_BRIEF §4, П1) | PASS 554 · WARN 10 · FAIL 0 · NOT_RUN 0 |
| Эталон A (47 элементов) | совпадает/близко 18 из 47, пиксели 73.7 % (FINAL-4: 18 из 47, 75.1 %) |

Шаги (код возврата, время):

```
label B0.20 R01 8f70baf1
root /tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/r01-b020
sha 8f70baf1
pytest {'rc': 0, 'time': '38s'}
api {'rc': 0, 'time': '15s'}
numbers {'rc': 0, 'time': '14s'}
e2e {'rc': 0, 'time': '702s'}
v2 {'rc': 0, 'time': '370s'}
map {'rc': 0, 'time': '300s'}
perf {'rc': 0, 'time': '63s'}
audit {'rc': 0, 'time': '427s'}
ref {'rc': 0, 'time': '54s'}
```
