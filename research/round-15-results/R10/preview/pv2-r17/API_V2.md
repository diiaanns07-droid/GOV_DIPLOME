# R10 · API v2 раунда 15 (CONTRACT §7) превью pv2 (R02+R16+R17 + патчи R02, R17)

Сборка: `<превью pv2>` · демо-мир: да · PASS 42 · FAIL 35 · NOT_RUN 0

| Роль | маршрутов | готово | ждёт модуль (503) | модуль упал | нет в шлюзе |
|---|---|---|---|---|---|
| R03 | 1 | 0 | 0 | 0 | 1 |
| R04 | 3 | 0 | 0 | 0 | 3 |
| R06 | 3 | 0 | 0 | 0 | 3 |
| R07 | 1 | 0 | 0 | 0 | 1 |
| R08 | 2 | 0 | 0 | 0 | 2 |
| R09 | 3 | 0 | 0 | 0 | 3 |
| R12 | 2 | 0 | 0 | 0 | 2 |
| R13 | 8 | 0 | 0 | 0 | 8 |
| R16 | 12 | 0 | 0 | 0 | 12 |
| R17 | 11 | 11 | 0 | 0 | 0 |

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
| FAIL | §7 | POST complaints/{complaint}/handoff | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST complaints/{complaint}/services | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | POST complaints/{complaint}/part | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET works-calendar | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
| FAIL | §7 | GET works-conflicts | "маршрута нет в шлюзе (DELETE → не 405 с этим методом)" | R01 |
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
| PASS | подготовка | id записей для проверки | {"incident": "inc-w15-buran", "idea": "i-demo-5dff7c2a"} |  |
| PASS | ответ | GET agencies: житель без входа → 200 |  | R17 |
| PASS | формат | GET agencies: житель без входа: §5 и §10 |  | R17 |
| PASS | доступ | GET agencies/board: без входа → 401 |  | R17 |
| PASS | ответ | GET agencies/board: сотрудник → 200 |  | R17 |
| PASS | формат | GET agencies/board: сотрудник: §5 и §10 |  | R17 |
| PASS | ошибки | GET agencies/board: неверный параметр → 400 понятная ошибка |  | R17 |
| PASS | доступ | GET agencies/joint: без входа → 401 |  | R17 |
| PASS | ответ | GET agencies/joint: сотрудник → 200 |  | R17 |
| PASS | формат | GET agencies/joint: сотрудник: §5 и §10 |  | R17 |
| PASS | доступ | GET agencies/handoffs: без входа → 401 |  | R17 |
| PASS | ответ | GET agencies/handoffs: сотрудник → 200 |  | R17 |
| PASS | формат | GET agencies/handoffs: сотрудник: §5 и §10 |  | R17 |
| PASS | ошибки | GET agencies/handoffs: неверный параметр → 400 понятная ошибка |  | R17 |
| PASS | ответ | GET incidents: житель без входа → 200 |  | R17 |
| PASS | формат | GET incidents: житель без входа: §5 и §10 |  | R17 |
| PASS | ответ | GET incidents/{incident}: житель без входа → 200 |  | R17 |
| PASS | формат | GET incidents/{incident}: житель без входа: §5 и §10 |  | R17 |
| PASS | доступ | POST incidents: без входа → 401 |  | R17 |
| PASS | доступ | POST incidents: вход без CSRF → 403 |  | R17 |
| PASS | ответ | POST incidents: сотрудник → 201 |  | R17 |
| PASS | формат | POST incidents: сотрудник: §5 и §10 |  | R17 |
| PASS | ошибки | POST incidents: сотрудник, пустое тело → 422 понятная ошибка |  | R17 |
| PASS | доступ | POST incidents/{incident}/task: без входа → 401 |  | R17 |
| PASS | доступ | POST incidents/{incident}/task: вход без CSRF → 403 |  | R17 |
| PASS | ответ | POST incidents/{incident}/task: сотрудник → 200 |  | R17 |
| PASS | ошибки | POST incidents/{incident}/task: сотрудник, пустое тело → 422 понятная ошибка |  | R17 |
| PASS | доступ | POST incidents/{incident}/update: без входа → 401 |  | R17 |
| PASS | доступ | POST incidents/{incident}/update: вход без CSRF → 403 |  | R17 |
| PASS | ответ | POST incidents/{incident}/update: сотрудник → 200 |  | R17 |
| PASS | ошибки | POST incidents/{incident}/update: сотрудник, пустое тело → 422 понятная ошибка |  | R17 |
| PASS | доступ | POST incidents/{incident}/close: без входа → 401 |  | R17 |
| PASS | доступ | POST incidents/{incident}/close: вход без CSRF → 403 |  | R17 |
| PASS | ответ | POST incidents/{incident}/close: сотрудник → 200 |  | R17 |
| PASS | ошибки | POST incidents/{incident}/close: сотрудник, пустое тело → 422 понятная ошибка |  | R17 |
| PASS | доступ | GET incidents/updates: житель без X-Birge-Device → 200 (общая часть) |  | R17 |
| PASS | ответ | GET incidents/updates: житель → 200 |  | R17 |
| PASS | формат | GET incidents/updates: житель: §5 и §10 |  | R17 |
| PASS | ошибки | GET incidents/updates: неверный параметр → 400 понятная ошибка |  | R17 |
| PASS | журнал | сервер без Traceback модулей во время проверки |  | по тексту ошибки |
