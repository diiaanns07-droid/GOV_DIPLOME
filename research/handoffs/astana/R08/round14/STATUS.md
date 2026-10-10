Задача: Раунд 14 · R08 · «Картина дня» для акима
Агент: Claude Code (облачная сессия) · Астана · Birge
Обновлено: 2026-10-10 (поставка 2 — день 3, для сборки B2)
Статус: done (поставка 2) — замечания UX_REVIEW R11 «День 3» закрыты; ждёт R01 (монтаж B-011), R07 (демо-набор)
Ветка: claude/r14-R08 · основа claude/round-14-package @ 2131c15 · код 4ce8f08 (поставка 1 — 9f1d9c0)
Пути: ui/civic_akim/, web/civic/akim/, tests/civic/R08/, research/round-14-results/R08/

Поставка 2 — замечания R11 (UX_REVIEW.md, ветка claude/r14-R11, «День 3»):
 9  демо-числа как авария → тест test_r08_demo_plausible.py (просрочено < новых за неделю и ≤ 10, неделя ±40 %,
    районы ≤ ×10). Сейчас XFAIL на наборе R07 @ 3eb3f9d (56 просрочено; 104 против 15; Нура 149 / Есиль 1).
    Данные правит R07 — INTEGRATION.txt п. 4а. Строгий режим: BIRGE_STRICT_DEMO=1.
 10 телефон: одно изменение в карточке, «За 7 дней» только на ноутбуке (< 480 px). ui_check PASS.
 11 «Пример» — одна метка у заголовка + строка «Пример: …» сверху; в карточках нет. ui_check PASS ×4.
 12 горячее место → карта: R08-часть (ссылка /#target=kind:id&days=7 + birge:open-target) PASS; разбор — R01/R07.
 13 поле даты: формат задаёт ОС. С LANG=ru_RU.UTF-8 → 10.10.2026 (screens/akim-date-*-os-ru_RU.png).
    kk_KZ в контейнере нет — проверка на ноутбуке с казахской Windows NOT_RUN.
 14 полоса этапов .bk-stages--compact (+ --late) и «Этап 4 из 6: Строительство» / «Кезең 4/6: Құрылыс». PASS.
 +  «в 6,9 раз» → «в 6,9 раза» (обход формы в словаре R11, просьба R11); kk «дерек» → «деректер».

Запросы соседей — что закрыто:
 - R06 функции → ЗАКРЫТО: ui.civic_store.v2.lagging_objects / list_proposals (словари разворачиваются сами;
   до bind() — фикстуры с «Пример»; ошибка R06 — «не отвечает»). Проверено вживую на базе R06 @ 3d10f7d.
 - R11 31 ключ akim.* → ЗАКРЫТО: akim.i18n.json удалён, тексты только из общего словаря (R11 @ 6102dfb, 0 пропусков).
 - R10 B-005 (стенд без R07) → ЗАКРЫТО: RUN.txt п. 1–3, demo_server.py печатает «ВНИМАНИЕ» и команду.
 - R10 B-010 (osm-relation) → R08 не задевает: id целей не фильтрует.
 - ОТКРЫТО: R07 records()/generation (нет в 3eb3f9d; работаем через _records), R07 демо-набор (п. 4а),
   R01 монтаж экрана и маршрут (B-011, INTEGRATION п. 1–3), R11 akim.delta.ratio ru other (п. 7),
   R06 title_kk у демо-объектов (п. 6, мелочь).

Проверки (облако, Python 3.13, Node 22, Playwright 1.56.1 + Chromium 1194):
 - pytest tests/civic/R08: 126 PASS + 1 XFAIL (демо R07); без ui/civic_heat — 110 PASS + 2 SKIP с причиной.
 - node tests/civic/R08/ui_check.cjs (demo_server --kit-dir R11 @ 6102dfb): 95/95 PASS, 1366/375 × ru/kk,
   скриншоты research/round-14-results/R08/screens/ (+ akim-*-r06-objects.png с живым R06).
 - NOT_RUN: экран в сборке R01 (не смонтирован, B-011), открытие цели картой (R01/R07).

Важно для следующей сессии:
 - ui/civic_heat — ВРЕМЕННАЯ копия R07 (в git не добавлена, .git/info/exclude):
     git fetch origin claude/upbeat-knuth-i0rqaa && git archive origin/claude/upbeat-knuth-i0rqaa ui/civic_heat | tar -x
 - Словарь/ui-kit R11 для стенда: git archive origin/claude/r14-R11 web/civic/ui-kit web/civic/i18n | tar -x -C <папка>
   python tests/civic/R08/demo_server.py --kit-dir <папка>   (без него — ключи вместо текста, сервер предупредит)
 - Живой R06: отдельная рабочая копия claude/round-14-r06 + копия ui/civic_akim; RUN.txt п. 4 (--r06-db).

Следующий шаг:
 - Когда R01 соберёт B2 — node tests/civic/R08/ui_check.cjs http://127.0.0.1:8501 на общем сервере, проверить
   клик «горячее место → карточка цели» вживую и что akim.i18n.json нет в CIVIC_ASSETS.
 - Когда R07 обновит demo_seed — test_r08_demo_plausible.py должен стать PASS; затем переснять 4 скриншота.
 - Когда R11 добавит akim.delta.ratio other — ratioText в akim.js можно оставить (ничего не меняет) или убрать.
