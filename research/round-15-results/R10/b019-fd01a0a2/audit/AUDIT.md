# R10 · аудит новых экранов (VISUAL_BRIEF §4) — B0.19 R01 fd01a0a2

Сборка: `/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/r01-b019` @ fd01a0a2 · демо-мир: да · 2026-10-16T06:00:39.674Z

Итог: PASS 549 · WARN 15 · FAIL 0 · NOT_RUN 0

WARN — правило брифа, которое приёмку не валит (4+ размеров шрифта на экране, зоны 40–43 px при цели 44).
В облаке подложка карты — упрощённый фон; стекло оценивается поверх белого (как светлая карта).

| Экран | Владелец | Вариант | FAIL | WARN | NOT_RUN | Что именно |
|---|---|---|---:|---:|---:|---|
| yard | R16 | 1366-ru | 0 | 1 | 0 | ⚠ не больше 3 размеров шрифта (VISUAL_BRIEF §4 п. 3): {"n":4,"sizes":[13,14,15,22]} |
| yard | R16 | 1366-kk | 0 | 1 | 0 | ⚠ не больше 3 размеров шрифта (VISUAL_BRIEF §4 п. 3): {"n":4,"sizes":[13,14,15,22]} |
| yard | R16 | 375-ru | 0 | 1 | 0 | ⚠ не больше 3 размеров шрифта (VISUAL_BRIEF §4 п. 3): {"n":5,"sizes":[13,14,15,19,22]} |
| yard | R16 | 375-kk | 0 | 1 | 0 | ⚠ не больше 3 размеров шрифта (VISUAL_BRIEF §4 п. 3): {"n":5,"sizes":[13,14,15,19,22]} |
| together | R16 | 1366-ru | 0 | 0 | 0 |  |
| together | R16 | 1366-kk | 0 | 0 | 0 |  |
| together | R16 | 375-ru | 0 | 0 | 0 |  |
| together | R16 | 375-kk | 0 | 0 | 0 |  |
| together-card | R16 | 1366-ru | 0 | 1 | 0 | ⚠ не больше 3 размеров шрифта (VISUAL_BRIEF §4 п. 3): {"n":5,"sizes":[13,14,15,16,19]} |
| together-card | R16 | 1366-kk | 0 | 1 | 0 | ⚠ не больше 3 размеров шрифта (VISUAL_BRIEF §4 п. 3): {"n":5,"sizes":[13,14,15,16,19]} |
| together-card | R16 | 375-ru | 0 | 1 | 0 | ⚠ не больше 3 размеров шрифта (VISUAL_BRIEF §4 п. 3): {"n":5,"sizes":[13,14,15,16,19]} |
| together-card | R16 | 375-kk | 0 | 1 | 0 | ⚠ не больше 3 размеров шрифта (VISUAL_BRIEF §4 п. 3): {"n":5,"sizes":[13,14,15,16,19]} |
| meetings | R13 | 1366-ru | 0 | 0 | 0 |  |
| meetings | R13 | 1366-kk | 0 | 0 | 0 |  |
| meetings | R13 | 375-ru | 0 | 0 | 0 |  |
| meetings | R13 | 375-kk | 0 | 0 | 0 |  |
| crisis-card | R17 | 1366-ru | 0 | 0 | 0 |  |
| crisis-card | R17 | 1366-kk | 0 | 0 | 0 |  |
| crisis-card | R17 | 375-ru | 0 | 0 | 0 |  |
| crisis-card | R17 | 375-kk | 0 | 0 | 0 |  |
| agencies-board | R17 | 1366-ru | 0 | 1 | 0 | ⚠ зоны нажатия ≥ 44 px (п. 10): {"under40":[],"from40to43":[{"h":40,"w":316,"t":"Служба"},{"h":40,"w":68,"frame":"58×40","t":"Открыто"},{"h":4 |
| agencies-board | R17 | 1366-kk | 0 | 1 | 0 | ⚠ зоны нажатия ≥ 44 px (п. 10): {"under40":[],"from40to43":[{"h":40,"w":316,"t":"Қызмет"},{"h":40,"w":58,"t":"Ашық"},{"h":40,"w":120,"frame":" |
| agencies-board | R17 | 375-ru | 0 | 0 | 0 |  |
| agencies-board | R17 | 375-kk | 0 | 0 | 0 |  |
| agencies-joint | R17 | 1366-ru | 0 | 1 | 0 | ⚠ зоны нажатия ≥ 44 px (п. 10): {"under40":[],"from40to43":[{"h":40,"w":577,"t":"Тротуары · Участок: улиц"},{"h":40,"w":693,"t":"Дворы и площа |
| agencies-joint | R17 | 1366-kk | 0 | 1 | 0 | ⚠ зоны нажатия ≥ 44 px (п. 10): {"under40":[],"from40to43":[{"h":40,"w":569,"t":"Жаяу жүргіншілер жолы · "},{"h":40,"w":660,"t":"Аулалар мен а |
| agencies-joint | R17 | 375-ru | 0 | 0 | 0 |  |
| agencies-joint | R17 | 375-kk | 0 | 0 | 0 |  |
| agencies-handoffs | R17 | 1366-ru | 0 | 0 | 0 |  |
| agencies-handoffs | R17 | 1366-kk | 0 | 0 | 0 |  |
| agencies-handoffs | R17 | 375-ru | 0 | 0 | 0 |  |
| agencies-handoffs | R17 | 375-kk | 0 | 0 | 0 |  |
| agencies-calendar | R12 + R17 | 1366-ru | 0 | 0 | 0 |  |
| agencies-calendar | R12 + R17 | 1366-kk | 0 | 0 | 0 |  |
| agencies-calendar | R12 + R17 | 375-ru | 0 | 0 | 0 |  |
| agencies-calendar | R12 + R17 | 375-kk | 0 | 0 | 0 |  |
| crisis-hq | R17 | 1366-ru | 0 | 1 | 0 | ⚠ не больше 3 размеров шрифта (VISUAL_BRIEF §4 п. 3): {"n":4,"sizes":[13,14,15,19]} |
| crisis-hq | R17 | 1366-kk | 0 | 1 | 0 | ⚠ не больше 3 размеров шрифта (VISUAL_BRIEF §4 п. 3): {"n":4,"sizes":[13,14,15,19]} |
| crisis-hq | R17 | 375-ru | 0 | 0 | 0 |  |
| crisis-hq | R17 | 375-kk | 0 | 1 | 0 | ⚠ зоны нажатия ≥ 44 px (п. 10): {"under40":[],"from40to43":[{"h":52,"w":40,"frame":"40×40","t":"Белгілеу: басталмаған — "}],"n":1} |
| analyst | R03 | 1366-ru | 0 | 0 | 0 |  |
| analyst | R03 | 1366-kk | 0 | 0 | 0 |  |
| analyst | R03 | 375-ru | 0 | 0 | 0 |  |
| analyst | R03 | 375-kk | 0 | 0 | 0 |  |
| meetings-staff | R13 | 1366-ru | 0 | 0 | 0 |  |
| meetings-staff | R13 | 1366-kk | 0 | 0 | 0 |  |
| meetings-staff | R13 | 375-ru | 0 | 0 | 0 |  |
| meetings-staff | R13 | 375-kk | 0 | 0 | 0 |  |
| board-page | R08 | 1366-ru | 0 | 0 | 0 |  |
| board-page | R08 | 1366-kk | 0 | 0 | 0 |  |
| board-page | R08 | 375-ru | 0 | 0 | 0 |  |
| board-page | R08 | 375-kk | 0 | 0 | 0 |  |
| week-page | R08 | 1366-ru | 0 | 0 | 0 |  |
| week-page | R08 | 1366-kk | 0 | 0 | 0 |  |
| week-page | R08 | 375-ru | 0 | 0 | 0 |  |
| week-page | R08 | 375-kk | 0 | 0 | 0 |  |
| * | по тексту ошибки | 1366-ru | 0 | 0 | 0 |  |
| * | по тексту ошибки | 1366-kk | 0 | 0 | 0 |  |
| * | по тексту ошибки | 375-ru | 0 | 0 | 0 |  |
| * | по тексту ошибки | 375-kk | 0 | 0 | 0 |  |

## По владельцам (FAIL)

- нет
