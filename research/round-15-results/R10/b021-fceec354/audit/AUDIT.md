# R10 · аудит новых экранов (VISUAL_BRIEF §4) — B0.21 R01 fceec354

Сборка: `/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/r01-b021` @ fceec354 · демо-мир: да · 2026-10-16T08:00:19.076Z

Итог: PASS 554 · WARN 10 · FAIL 0 · NOT_RUN 0

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
| agencies-board | R17 | 1366-ru | 0 | 0 | 0 |  |
| agencies-board | R17 | 1366-kk | 0 | 0 | 0 |  |
| agencies-board | R17 | 375-ru | 0 | 0 | 0 |  |
| agencies-board | R17 | 375-kk | 0 | 0 | 0 |  |
| agencies-joint | R17 | 1366-ru | 0 | 0 | 0 |  |
| agencies-joint | R17 | 1366-kk | 0 | 0 | 0 |  |
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
| crisis-hq | R17 | 375-kk | 0 | 0 | 0 |  |
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
