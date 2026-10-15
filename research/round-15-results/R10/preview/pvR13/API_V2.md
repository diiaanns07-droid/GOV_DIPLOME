# R10 · API v2 раунда 15 (CONTRACT §7) превью pvR13

Сборка: `<превью pvR13>` · демо-мир: да · PASS 26 · FAIL 39 · NOT_RUN 0

| Роль | маршрутов | готово | ждёт модуль (503) | модуль упал | нет в шлюзе |
|---|---|---|---|---|---|
| R03 | 1 | 0 | 0 | 0 | 1 |
| R04 | 3 | 0 | 0 | 0 | 3 |
| R06 | 3 | 0 | 0 | 0 | 3 |
| R07 | 1 | 0 | 0 | 0 | 1 |
| R08 | 2 | 0 | 0 | 0 | 2 |
| R09 | 3 | 0 | 0 | 0 | 3 |
| R12 | 2 | 0 | 0 | 0 | 2 |
| R13 | 8 | 8 | 0 | 0 | 0 |
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
| FAIL | §7 | GET works-calendar | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET works-conflicts | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET heat/replay | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET akim/board | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET akim/week | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST route | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST reply-draft | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST moderate | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST assistant/ask | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET notifications | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST notifications/read | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST ideas/{idea}/to-initiative | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| PASS | подготовка | id записей для проверки | {"meeting": "m-w15-2", "idea": "i-demo-817b3669", "complaint": "c-404c47cbb523925a"} |  |
| PASS | ответ | GET meetings: житель без входа → 200 |  | R13 |
| PASS | формат | GET meetings: житель без входа: §5 и §10 |  | R13 |
| PASS | ответ | GET meetings/{meeting}: житель без входа → 200 |  | R13 |
| PASS | формат | GET meetings/{meeting}: житель без входа: §5 и §10 |  | R13 |
| FAIL | ответ | GET meetings/updates: житель без входа → 400 на примере по §5 | "bad_request: device_id: строка 8–128 символов." | R13 |
| PASS | ошибки | GET meetings/updates: неверный параметр → 400 понятная ошибка |  | R13 |
| PASS | доступ | POST meetings: без входа → 401 |  | R13 |
| PASS | доступ | POST meetings: вход без CSRF → 403 |  | R13 |
| PASS | ответ | POST meetings: сотрудник → 201 |  | R13 |
| PASS | формат | POST meetings: сотрудник: §5 и §10 |  | R13 |
| PASS | ошибки | POST meetings: сотрудник, пустое тело → 422 понятная ошибка |  | R13 |
| PASS | доступ | POST meetings/{meeting}/order: без входа → 401 |  | R13 |
| PASS | доступ | POST meetings/{meeting}/order: вход без CSRF → 403 |  | R13 |
| PASS | ответ | POST meetings/{meeting}/order: сотрудник → 201 |  | R13 |
| PASS | ошибки | POST meetings/{meeting}/order: сотрудник, пустое тело → 422 понятная ошибка |  | R13 |
| PASS | доступ | POST meetings/{meeting}/result: без входа → 401 |  | R13 |
| PASS | доступ | POST meetings/{meeting}/result: вход без CSRF → 403 |  | R13 |
| PASS | ответ | POST meetings/{meeting}/result: сотрудник → 409 (правило модуля) | "not_started: Итог можно написать, когда встреча начнётся." | R13 |
| PASS | ошибки | POST meetings/{meeting}/result: сотрудник, пустое тело → 422 понятная ошибка |  | R13 |
| PASS | доступ | POST meetings/{meeting}/register: житель без X-Birge-Device → 400 |  | R13 |
| PASS | ответ | POST meetings/{meeting}/register: житель → 200 |  | R13 |
| PASS | доступ | POST meetings/{meeting}/question: житель без X-Birge-Device → 400 |  | R13 |
| PASS | ответ | POST meetings/{meeting}/question: житель → 201 |  | R13 |
| PASS | журнал | сервер без Traceback модулей во время проверки |  | по тексту ошибки |
