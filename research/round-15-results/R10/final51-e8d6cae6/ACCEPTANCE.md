# R10 · приёмка сборки FINAL51 R01 e8d6cae6

Код: `e8d6cae6` · отчёт: `<облако R10: runs/final51-acc>`

## Можно показывать: **да**

- блокеров нет

| Проверка | Итог |
|---|---|
| pytest tests/civic/R10 | 50 passed |
| API v2 (CONTRACT §7) | PASS 155 · FAIL 0 · NOT_RUN 0 (жёстких FAIL 0) |
| Согласованность чисел | PASS 16 · FAIL 0 · NOT_RUN 0 |
| Часть 1 (шаги 1–7 FINAL-4) | PASS 172 · FAIL 0 · NOT_RUN 2 (база FINAL-4: 172 / 0 / 0) |
| Время части 1, с | 1366-ru 183.4 (FINAL-4 226.9), 1366-kk 184.2 (FINAL-4 233.8), 375-ru 161.4 (FINAL-4 181.3), 375-kk 164.1 (FINAL-4 185.5) |
| Сцены 7–9 «Бірге» | PASS 248 · FAIL 0 · NOT_RUN 0 |
| Первый значок карты, мс | 1366x768-ru-resident 1578, 1366x768-ru-akimat 1675, 1366x768-kk-resident 1584, 1366x768-kk-akimat 1658, 375x812-ru-resident 1390, 375x812-ru-akimat 1498, 375x812-kk-resident 1466, 375x812-kk-akimat 1567 |
| Производительность | PASS первый значок с числом, 1366x768; ИНФО перемещение карты, 1366x768; PASS «Хроника города» доигрывает до конца, 13; ИНФО «Хроника города» плавность, 1366x768; PASS «Спросить Birge»: время ответа |

Шаги (код возврата, время):

```
label FINAL51 R01 e8d6cae6
root <облако R10: worktree FINAL-5.1>
sha e8d6cae6
pytest {'rc': 0, 'time': '38s'}
api {'rc': 0, 'time': '15s'}
numbers {'rc': 0, 'time': '14s'}
e2e {'rc': 0, 'time': '708s'}
v2 {'rc': 0, 'time': '268s'}
map {'rc': 0, 'time': '296s'}
perf {'rc': 0, 'time': '60s'}
```
