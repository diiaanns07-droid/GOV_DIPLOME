# R10 · приёмка сборки B0.13 R01 2184795b

Код: `2184795b` · отчёт: `/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/runs/b013-acc`

## Можно показывать: **да**

- блокеров нет

Смотреть (не блокирует):
- сцены 7–9, проверить на ноутбуке (облако — программный WebGL): UI show-ru 7 Ctrl+K «Сцена 7 · Двор вместе» → раздел yard: 1571 мс, без кадров карты 170 мс
- сцены 7–9, качество вида: 10 FAIL (шрифт / зоны / контраст / термины) у R16 — BUGS
- аудит экранов: FAIL 10 у R16 — BUGS

| Проверка | Итог |
|---|---|
| pytest tests/civic/R10 | 50 passed |
| API v2 (CONTRACT §7) | PASS 155 · FAIL 0 · NOT_RUN 0 (жёстких FAIL 0) |
| Согласованность чисел | PASS 16 · FAIL 0 · NOT_RUN 0 |
| Часть 1 (шаги 1–7 FINAL-4) | PASS 172 · FAIL 0 · NOT_RUN 2 (база FINAL-4: 172 / 0 / 0) |
| Время части 1, с | 1366-ru 211.1 (FINAL-4 226.9), 1366-kk 217.6 (FINAL-4 233.8), 375-ru 171.3 (FINAL-4 181.3), 375-kk 172.6 (FINAL-4 185.5) |
| Сцены 7–9 «Бірге» | PASS 322 · FAIL 10 · NOT_RUN 0 · ИНФО 1 |
| Первый значок карты, мс | 1366x768-ru-resident 2180, 1366x768-ru-akimat 2294, 1366x768-kk-resident 2295, 1366x768-kk-akimat 2273, 375x812-ru-resident 2018, 375x812-ru-akimat 1913, 375x812-kk-resident 1867, 375x812-kk-akimat 1957 |
| Производительность | PASS первый значок с числом, 1366x768; ИНФО перемещение карты, 1366x768; PASS «Хроника города» доигрывает до конца, 13; ИНФО «Хроника города» плавность, 1366x768; PASS «Спросить Birge»: время ответа |
| Аудит экранов (VISUAL_BRIEF §4, П1) | PASS 512 · WARN 52 · FAIL 10 · NOT_RUN 0 |
| Эталон A (47 элементов) | совпадает/близко 18 из 47, пиксели 73.7 % (FINAL-4: 18 из 47, 75.1 %) |

Шаги (код возврата, время):

```
label B0.13 R01 2184795b
root /tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/r01-b013
sha 2184795b
pytest {'rc': 0, 'time': '50s'}
api {'rc': 0, 'time': '21s'}
numbers {'rc': 0, 'time': '19s'}
e2e {'rc': 0, 'time': '791s'}
v2 {'rc': 1, 'time': '415s'}
map {'rc': 0, 'time': '343s'}
perf {'rc': 0, 'time': '76s'}
audit {'rc': 0, 'time': '443s'}
ref {'rc': 0, 'time': '62s'}
```
