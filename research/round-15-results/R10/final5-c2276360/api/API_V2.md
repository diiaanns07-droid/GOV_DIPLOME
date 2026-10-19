# R10 · API v2 раунда 15 (CONTRACT §7) FINAL5 R01 c2276360

Сборка: `/tmp/claude-0/-home-user-GOV-DIPLOME/62d68526-d416-54f0-b206-35e3353bc4a5/scratchpad/builds/r01-final5` · демо-мир: да · PASS 155 · FAIL 0 · NOT_RUN 0

| Роль | маршрутов | готово | ждёт модуль (503) | модуль упал | нет в шлюзе |
|---|---|---|---|---|---|
| R03 | 1 | 1 | 0 | 0 | 0 |
| R04 | 3 | 3 | 0 | 0 | 0 |
| R06 | 3 | 3 | 0 | 0 | 0 |
| R07 | 1 | 1 | 0 | 0 | 0 |
| R08 | 2 | 2 | 0 | 0 | 0 |
| R09 | 3 | 3 | 0 | 0 | 0 |
| R12 | 2 | 2 | 0 | 0 | 0 |
| R13 | 8 | 8 | 0 | 0 | 0 |
| R16 | 12 | 12 | 0 | 0 | 0 |
| R17 | 11 | 11 | 0 | 0 | 0 |

| Статус | Раздел | Проверка | Подробно | Владелец |
|---|---|---|---|---|
| PASS | FINAL-4 | маршруты FINAL-4 на месте (74) |  | R01 |
| PASS | FINAL-4 | модули FINAL-4 подключены, как в FINAL-4 (ready) |  | владелец модуля |
| PASS | подготовка | id записей для проверки | {"initiative": "i-w15-04", "yard": "yard-1531186335", "_yard_point": [71.2768929, 51.1308766], "incident": "inc-w15-buran", "meeting": "m-w15-2", "idea": "idea- |  |
| PASS | ответ | GET together/initiatives: житель без входа → 200 |  | R16 |
| PASS | формат | GET together/initiatives: житель без входа: §5 и §10 |  | R16 |
| PASS | ошибки | GET together/initiatives: неверный параметр → 400 понятная ошибка |  | R16 |
| PASS | доступ | POST together/initiatives: житель без X-Birge-Device → 400 |  | R16 |
| PASS | ответ | POST together/initiatives: житель → 201 |  | R16 |
| PASS | формат | POST together/initiatives: житель: §5 и §10 |  | R16 |
| PASS | ответ | GET together/initiatives/{initiative}: житель без входа → 200 |  | R16 |
| PASS | формат | GET together/initiatives/{initiative}: житель без входа: §5 и §10 |  | R16 |
| PASS | доступ | POST together/initiatives/{initiative}/join: житель без X-Birge-Device → 400 |  | R16 |
| PASS | ответ | POST together/initiatives/{initiative}/join: житель → 200 |  | R16 |
| PASS | доступ | POST together/initiatives/{initiative}/leave: житель без X-Birge-Device → 400 |  | R16 |
| PASS | ответ | POST together/initiatives/{initiative}/leave: житель → 200 |  | R16 |
| PASS | доступ | POST together/initiatives/{initiative}/support: без входа → 401 |  | R16 |
| PASS | доступ | POST together/initiatives/{initiative}/support: вход без CSRF → 403 |  | R16 |
| PASS | ответ | POST together/initiatives/{initiative}/support: сотрудник → 200 |  | R16 |
| PASS | ошибки | POST together/initiatives/{initiative}/support: сотрудник, пустое тело → 200 |  | R16 |
| PASS | доступ | POST together/initiatives/{initiative}/moderate: без входа → 401 |  | R16 |
| PASS | доступ | POST together/initiatives/{initiative}/moderate: вход без CSRF → 403 |  | R16 |
| PASS | ответ | POST together/initiatives/{initiative}/moderate: сотрудник → 409 (правило модуля) | "already_moderated: Инициатива уже проверена." | R16 |
| PASS | ошибки | POST together/initiatives/{initiative}/moderate: сотрудник, пустое тело → 422 понятная ошибка |  | R16 |
| PASS | доступ | POST together/initiatives/{initiative}/report: не автор и не сотрудник → 400 |  | R16 |
| PASS | ошибки | POST together/initiatives/{initiative}/report: сотрудник, пустое тело → 422 понятная ошибка |  | R16 |
| PASS | ответ | GET together/yards/{yard}: житель без входа → 200 |  | R16 |
| PASS | формат | GET together/yards/{yard}: житель без входа: §5 и §10 |  | R16 |
| PASS | доступ | POST together/yards/{yard}/join: житель без X-Birge-Device → 400 |  | R16 |
| PASS | ответ | POST together/yards/{yard}/join: житель → 200 |  | R16 |
| PASS | доступ | POST together/yards/{yard}/leave: житель без X-Birge-Device → 400 |  | R16 |
| PASS | ответ | POST together/yards/{yard}/leave: житель → 200 |  | R16 |
| PASS | доступ | GET together/updates: житель без X-Birge-Device → 400 |  | R16 |
| PASS | ответ | GET together/updates: житель → 200 |  | R16 |
| PASS | формат | GET together/updates: житель: §5 и §10 |  | R16 |
| PASS | ошибки | GET together/updates: неверный параметр → 400 понятная ошибка |  | R16 |
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
| PASS | доступ | POST complaints/{complaint}/handoff: без входа → 401 |  | R09 |
| PASS | доступ | POST complaints/{complaint}/handoff: вход без CSRF → 403 |  | R09 |
| PASS | ответ | POST complaints/{complaint}/handoff: сотрудник → 200 |  | R09 |
| PASS | ошибки | POST complaints/{complaint}/handoff: сотрудник, пустое тело → 422 понятная ошибка |  | R09 |
| PASS | доступ | POST complaints/{complaint}/services: без входа → 401 |  | R09 |
| PASS | доступ | POST complaints/{complaint}/services: вход без CSRF → 403 |  | R09 |
| PASS | ответ | POST complaints/{complaint}/services: сотрудник → 200 |  | R09 |
| PASS | ошибки | POST complaints/{complaint}/services: сотрудник, пустое тело → 422 понятная ошибка |  | R09 |
| PASS | доступ | POST complaints/{complaint}/part: без входа → 401 |  | R09 |
| PASS | доступ | POST complaints/{complaint}/part: вход без CSRF → 403 |  | R09 |
| PASS | ответ | POST complaints/{complaint}/part: сотрудник → 200 |  | R09 |
| PASS | ошибки | POST complaints/{complaint}/part: сотрудник, пустое тело → 422 понятная ошибка |  | R09 |
| PASS | доступ | GET works-calendar: без входа → 401 |  | R12 |
| PASS | ответ | GET works-calendar: сотрудник → 200 |  | R12 |
| PASS | формат | GET works-calendar: сотрудник: §5 и §10 |  | R12 |
| PASS | ошибки | GET works-calendar: неверный параметр → 400 понятная ошибка |  | R12 |
| PASS | доступ | GET works-conflicts: без входа → 401 |  | R12 |
| PASS | ответ | GET works-conflicts: сотрудник → 200 |  | R12 |
| PASS | формат | GET works-conflicts: сотрудник: §5 и §10 |  | R12 |
| PASS | ошибки | GET works-conflicts: неверный параметр → 400 понятная ошибка |  | R12 |
| PASS | ответ | GET heat/replay: житель без входа → 200 |  | R07 |
| PASS | формат | GET heat/replay: житель без входа: §5 и §10 |  | R07 |
| PASS | ошибки | GET heat/replay: неверный параметр → 400 понятная ошибка |  | R07 |
| PASS | доступ | GET akim/board: без входа → 401 |  | R08 |
| PASS | ответ | GET akim/board: сотрудник → 200 |  | R08 |
| PASS | доступ | GET akim/week: без входа → 401 |  | R08 |
| PASS | ответ | GET akim/week: сотрудник → 200 |  | R08 |
| PASS | ошибки | GET akim/week: неверный параметр → 400 понятная ошибка |  | R08 |
| PASS | ответ | GET meetings: житель без входа → 200 |  | R13 |
| PASS | формат | GET meetings: житель без входа: §5 и §10 |  | R13 |
| PASS | ответ | GET meetings/{meeting}: житель без входа → 200 |  | R13 |
| PASS | формат | GET meetings/{meeting}: житель без входа: §5 и §10 |  | R13 |
| PASS | ответ | GET meetings/updates: житель без входа → 200 |  | R13 |
| PASS | формат | GET meetings/updates: житель без входа: §5 и §10 |  | R13 |
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
| PASS | ответ | POST route: житель без входа → 200 |  | R04 |
| PASS | формат | POST route: житель без входа: §5 и §10 |  | R04 |
| PASS | ошибки | POST route: пустое тело → 400 понятная ошибка |  | R04 |
| PASS | доступ | POST reply-draft: без входа → 401 |  | R04 |
| PASS | доступ | POST reply-draft: вход без CSRF → 403 |  | R04 |
| PASS | ответ | POST reply-draft: сотрудник → 200 |  | R04 |
| PASS | ошибки | POST reply-draft: сотрудник, пустое тело → 400 понятная ошибка |  | R04 |
| PASS | ответ | POST moderate: житель без входа → 200 |  | R04 |
| PASS | формат | POST moderate: житель без входа: §5 и §10 |  | R04 |
| PASS | ошибки | POST moderate: пустое тело → 400 понятная ошибка |  | R04 |
| PASS | доступ | POST assistant/ask: без входа → 401 |  | R03 |
| PASS | доступ | POST assistant/ask: вход без CSRF → 403 |  | R03 |
| PASS | ответ | POST assistant/ask: сотрудник → 200 |  | R03 |
| PASS | ошибки | POST assistant/ask: сотрудник, пустое тело → 400 понятная ошибка |  | R03 |
| PASS | доступ | GET notifications: житель без X-Birge-Device → 400 |  | R06 |
| PASS | ответ | GET notifications: житель → 200 |  | R06 |
| PASS | формат | GET notifications: житель: §5 и §10 |  | R06 |
| PASS | ошибки | GET notifications: неверный параметр → 400 понятная ошибка |  | R06 |
| PASS | доступ | POST notifications/read: житель без X-Birge-Device → 400 |  | R06 |
| PASS | ответ | POST notifications/read: житель → 200 |  | R06 |
| PASS | доступ | POST ideas/{idea}/to-initiative: без входа → 401 |  | R06 |
| PASS | доступ | POST ideas/{idea}/to-initiative: вход без CSRF → 403 |  | R06 |
| PASS | ответ | POST ideas/{idea}/to-initiative: сотрудник → 201 |  | R06 |
| PASS | ошибки | POST ideas/{idea}/to-initiative: сотрудник, пустое тело → 201 |  | R06 |
| PASS | поведение | «Я приду»: дважды с одного устройства → +1 (6 → 7) |  | R16 |
| PASS | поведение | «Я приду»: «Не приду / выйти» → обратно 6 |  | R16 |
| PASS | поведение | «Я живу здесь»: дважды с одного устройства → +1 (59 → 60) |  | R16 |
| PASS | поведение | «Я живу здесь»: «Не приду / выйти» → обратно 59 |  | R16 |
| PASS | поведение | передача в другую службу: с причиной, срок ответа не начинается заново |  | R09 |
| PASS | журнал | сервер без Traceback модулей во время проверки |  | по тексту ошибки |
