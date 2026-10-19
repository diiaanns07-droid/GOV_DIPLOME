# R10 · API v2 раунда 15 (CONTRACT §7) превью pvR12

Сборка: `<превью pvR12>` · демо-мир: да · PASS 12 · FAIL 44 · NOT_RUN 0

| Роль | маршрутов | готово | ждёт модуль (503) | модуль упал | нет в шлюзе |
|---|---|---|---|---|---|
| R03 | 1 | 0 | 0 | 0 | 1 |
| R04 | 3 | 0 | 0 | 0 | 3 |
| R06 | 3 | 0 | 0 | 0 | 3 |
| R07 | 1 | 0 | 0 | 0 | 1 |
| R08 | 2 | 0 | 0 | 0 | 2 |
| R09 | 3 | 0 | 0 | 0 | 3 |
| R12 | 2 | 2 | 0 | 0 | 0 |
| R13 | 8 | 0 | 0 | 0 | 8 |
| R16 | 12 | 0 | 0 | 0 | 12 |
| R17 | 11 | 0 | 0 | 0 | 11 |

| Статус | Раздел | Проверка | Подробно | Владелец |
|---|---|---|---|---|
| PASS | FINAL-4 | маршруты FINAL-4 на месте (74) |  | R01 |
| PASS | FINAL-4 | модули FINAL-4 подключены, как в FINAL-4 (ready) |  | владелец модуля |
| FAIL | §7 | GET together/initiatives | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST together/initiatives | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET together/initiatives/{initiative} | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST together/initiatives/{initiative}/join | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST together/initiatives/{initiative}/leave | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST together/initiatives/{initiative}/support | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST together/initiatives/{initiative}/moderate | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST together/initiatives/{initiative}/report | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET together/yards/{yard} | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST together/yards/{yard}/join | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST together/yards/{yard}/leave | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET together/updates | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET agencies | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET agencies/board | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET agencies/joint | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET agencies/handoffs | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET incidents | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET incidents/{incident} | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST incidents | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST incidents/{incident}/task | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST incidents/{incident}/update | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST incidents/{incident}/close | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET incidents/updates | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST complaints/{complaint}/handoff | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST complaints/{complaint}/services | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST complaints/{complaint}/part | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET heat/replay | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET akim/board | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET akim/week | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET meetings | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET meetings/{meeting} | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET meetings/updates | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST meetings | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST meetings/{meeting}/order | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST meetings/{meeting}/result | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST meetings/{meeting}/register | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST meetings/{meeting}/question | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST route | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST reply-draft | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST moderate | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST assistant/ask | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET notifications | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST notifications/read | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST ideas/{idea}/to-initiative | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| PASS | подготовка | id записей для проверки | {"idea": "i-demo-929775e6"} |  |
| PASS | доступ | GET works-calendar: без входа → 401 |  | R12 |
| PASS | ответ | GET works-calendar: сотрудник → 200 |  | R12 |
| PASS | формат | GET works-calendar: сотрудник: §5 и §10 |  | R12 |
| PASS | ошибки | GET works-calendar: неверный параметр → 400 понятная ошибка |  | R12 |
| PASS | доступ | GET works-conflicts: без входа → 401 |  | R12 |
| PASS | ответ | GET works-conflicts: сотрудник → 200 |  | R12 |
| PASS | формат | GET works-conflicts: сотрудник: §5 и §10 |  | R12 |
| PASS | ошибки | GET works-conflicts: неверный параметр → 400 понятная ошибка |  | R12 |
| PASS | журнал | сервер без Traceback модулей во время проверки |  | по тексту ошибки |
