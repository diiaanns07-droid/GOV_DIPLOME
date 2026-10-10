# R05 · ответ на разбор R11 «День 3» (пп. 20–26) и замечания по сборке B2

Источник замечаний: `claude/r14-R11`, `research/round-14-results/R11/UX_REVIEW.md`, раздел «День 3 · 13 октября 2026»
(таблица R05, пп. 20–26) и «Главное», п. 4. Разделы «День 4» (B1, B2 шаг 1, ключи) прочитаны: пунктов для R05 там
нет, кроме правок казахского (внесены, п. 26) и строки «3D-превью R05 в оболочке не проверено» (проверено, ниже).

Код — `code_sha` из `DELIVERY.json`. Проверки — в Chromium (SwiftShader, без GPU), ui-kit и словари R11 @ 52d7c59
(`--kit`). Скриншоты — `screens/`, у каждого пункта 1366 и 375 × ru и kk.

| # | Замечание R11 | Что сделано | Проверка (PASS) | Скриншоты |
|---|---|---|---|---|
| 20 | Стартовый вид 16,4: объекты крошечные, видны только подписи | Без `?center` камера сразу к проектам: крупный план 17.4 у проекта, ближайшего к центру группы (`flyToProposals`, есть и в ручке для R01). Выбор в каталоге с дальнего вида — плавный `easeTo` к 17.5 | `ux_day3_check`: `r11_20_start_close_up_*`, `r11_20_catalog_pick_zooms_to_17_5_*`; `browser_check`: `r11_20_start_close_up_17_4`, `r11_20_catalog_pick_zooms_to_17_5` | `d3_20_start_{1366,375}_{ru,kk}.png`, `d3_20_pick_{1366,375}_{ru,kk}.png` |
| 21 | Нажать можно только подпись 121×30; одна подпись уходит под карточку | Нажимается сама модель (проверка попадания по экранному контуру, курсор-рука). Подпись — кнопка с зоной 48 px и «таблеткой» 40 px. Открыв карточку, камера ставит объект в свободную часть карты: слева от карточки на ноутбуке, над ней на телефоне, выше тоста; в оболочке R01 — и не под шапкой / «Территорией» / панелью (`avoid`) | `ux_day3_check`: `r11_21_model_click_opens_card_object_visible_*`; `browser_check`: `r11_21_model_clickable_pointer_label_40_zone_48`, `r11_21_selected_object_not_under_card_1366_375`; `app_b2_smoke`: `selected_object_visible_in_free_part_of_shell_map` | `d3_21_card_{1366,375}_{ru,kk}.png`, `b2_1366_ru_card.png` |
| 22 | Метка «Проект» рядом с Birge в шапке демо | Метки нет; в шапке демо — «3D-превью» / «3D-көрініс» (ключ `build3d.demo.title`). В сборке шапку даёт R01 | `ux_day3_check`: `r11_22_23_header_title_and_3d_label_*`; `browser_check`: `r11_22_23_demo_header_title_and_3d_label` | `d3_20_start_*` (шапка) |
| 23 | Кнопка 3D — кубик без подписи | Видимая подпись «3D» рядом с иконкой, кнопка ≥ 44×44 | то же | `d3_20_start_*` (справа вверху) |
| 24 | Житель: каталога нет, подсказки нет | Строка «Нажмите на проект, чтобы проголосовать» / «Дауыс беру үшін жобаны басыңыз» (нет проектов рядом — «Здесь пока нет проектов»). В оболочке R01 на телефоне — над опущенной шторкой, при открытой шторке скрыта (строка `birge.css` в патче) | `ux_day3_check`: `r11_24_resident_hint_*`; `browser_check`: `r11_24_resident_hint_ru_kk`, `r01_birge_mode_event_update_dock`; `app_b2_smoke`: `phone_kk_resident_hint_*`, `shell_mode_switch_to_resident_without_remount` | `d3_24_resident_{1366,375}_{ru,kk}.png`, `b2_375_kk_resident.png`, `b2_1366_ru_resident.png` |
| 25 | Без 3D-домов сцена пустая (офлайн) | Демо-подложка из LOCAL-1: дворы OSM (560 контуров) поверх улиц и границы Нуры; примеры сквера и площадки стоят внутри настоящих дворов (Evolution, BI City Seoul). Контуров зданий в LOCAL-1 нет — выгрузка поручена LOCAL-R05-3 (INTEGRATION §6), генератор и демо их уже понимают. Подложку сборки решает R01 (R11 день 4, п. 4) | `ux_day3_check`: `r11_25_offline_basemap_osm_yards_*`; `browser_check`: `r11_25_offline_basemap_real_osm_yards`; `test_build3d_fixtures`: примеры внутри дворов | `d3_20_start_*` |
| 26 | Ключей `build3d.*` нет в общем словаре | `i18n_build3d.json` — 43 ключа в формате R11 (`{key:{ru,kk,where}}`); R11 взял 40 в 6102dfb, новые 3 — `build3d.resident.hint`, `build3d.resident.empty`, `build3d.demo.title`. Правки kk дня 4 (5 строк) внесены в модуль и файл | `ux_day3_check`: `r11_26_no_raw_keys_*`; `test_core`: файл ключей = строки модуля, ru и kk у всех; `browser_check`: `kk_locale_no_raw_keys_no_i18n_warnings` | все `d3_*` |

## Найдено при проверке в сборке B2 (R01 @ f54361d) и исправлено

| Что | Исправление | Проверка | Скриншоты |
|---|---|---|---|
| После «Житель» у жителя оставался тост акимата «Проект поставлен · Отменить» | Смена вида закрывает тост | `browser_check`: `mode_switch_clears_akimat_undo_toast`; `app_b2_smoke`: `shell_mode_switch_to_resident_without_remount` | `b2_1366_ru_resident.png` |
| Объект открытой карточки уходил под тост и панели оболочки (свободная часть считалась по полосе корня модуля) | Свободная часть — от всего холста: своя панель → панели хозяина (`avoid`, отрезается сторона, после которой больше места) → тост; тост «Проект поставлен» закрывается при открытии карточки (в ней есть «Удалить»), ошибки с «Повторить» остаются | `app_b2_smoke`: `selected_object_visible_in_free_part_of_shell_map`; `r11_21_*` | `b2_1366_ru_card.png` |
| В 720 px оболочки «Спортплощадка» выходила за рамку карточки каталога | `@container` по ширине строки каталога: ≤ 700 px — подпись 14 px, поля 4 px; карточка не уже самого длинного слова | `browser_check`: `catalog_labels_fit_cards_in_narrow_host` (на прежнем CSS — FAIL «Спортплощадка» в 720 и 600 px); `app_b2_smoke`: `catalog_labels_inside_cards_ru`, `kk_catalog_in_shell` | `b2_1366_ru_akimat.png`, `b2_1366_kk_akimat.png` |
| Подсказка жителя закрывала фильтры открытой шторки на телефоне | Строка в `birge.css` R01 (патч): скрыта при открытой шторке, как каталог | `app_b2_smoke`: `phone_kk_resident_hint_does_not_cover_open_sheet`, `phone_kk_resident_hint_above_lowered_sheet` | `b2_375_kk_resident.png` |

## Чего здесь нет (честно)

- Плавность на ноутбуке с GPU — `NOT_RUN` (в облаке только программный WebGL): LOCAL-R05-1.
- Здания: ни в демо, ни в офлайн-фоне сборки контуров домов нет, пока LOCAL не выгрузит их (LOCAL-R05-3); примеры
  с настоящими 3D-зданиями посмотреть — LOCAL-R05-2.
- Казахские строки 3 новых ключей — на вычитку R11.

## Ночь 1 · замечания R10 (BUGS.md, ACCEPTANCE_B3) и Codex (LOCAL_B2.md) для R05

| Замечание | Что сделано | Проверка (PASS) | Скриншоты |
|---|---|---|---|
| R10 B-007 (важно), LOCAL_B2 №6: 41 ж/д платформа записана как «остановка», 2 — в 75–98 м от улицы | Генератор не берёт пути и точки с `railway=*`, `train=yes`, `tram=yes` (то же правило, что в R10 `accuracy.py`) | R10 `accuracy.py`: «остановки — не ж/д платформы · R05», «остановки ≤ 60 м от улицы · R05» — PASS (`runs/r10_accuracy_r05.json`); `test_existing_objects_are_real_osm` | — (данные) |
| R10 B-008, LOCAL_B2 №5: 337 координат `astana-existing.json` вне границы Астаны | Точки — только внутри полигонов районов OSM (`geofence.json`, чётно-нечётное правило как у R10); дворы — только если ВСЕ вершины внутри | R10 `accuracy.py`: «граница Астаны · R05 astana-existing.json» — PASS; тот же тест Python | — (данные) |
| R10 B-026, LOCAL_B2 №9: таблички проектов на мелком масштабе — точки 18 px, пять проектов в одной точке | Точка 32 px со значком вида проекта (зона нажатия 48); совпавшие точки — одна метка с числом, aria «4 проекта рядом — показать ближе»; нажатие приближает к группе | `browser_check`: `r10_b026_far_zoom_dots_24px_and_cluster_1366_375_ru_kk` | `b026_cluster_{1366,375}_{ru,kk}.png` |
| R10 B-022, LOCAL_B2 №3 (R01 + R05): на 375 у акимата нет каталога | Сделал R01 (кнопка «Что построить?» опускает шторку); со стороны R05 — патч `proposed_r01_b3.patch` (подсказка жителя не закрывает шторку) | `app_b2_smoke` на R01 2b9e837 + патч: `phone_ru_akimat_catalog_above_peek_sheet`, `phone_kk_resident_hint_*`; `r14_b2.cjs` R01 25/25 | `b2_375_ru_akimat.png`, `b2_375_kk_resident.png` |
| R10 B-023 (R01 + R05 + R07): каталог закрывает низ карты | Каталог свёрнут в кнопку у R01; остаток — кнопка R01 над тостом R07 (не код R05) | — | — |
| Самопроверка по UX_BRIEF п. 6: в kk названия улиц были русскими («Жанында: улица Сыганак») | Казахское название из OSM (`name:kk`, 13 из 59 улиц Нуры), иначе русское (как R12) | `browser_check`: `kk_street_names_from_osm_card_and_lighting_hint_1366_375`; `test_street_names_kk_only_from_osm` | `kk_street_{1366,375}_card.png` |

## Ночь 2 · UX_REVIEW R11 (ночь, круги 1–4), R15 U1

| Замечание | Что сделано | Проверка (PASS) | Скриншоты |
|---|---|---|---|
| R11 ночь B3 п. 5: «Жанында: улица Керей и Жанибек хандар» — по-русски в kk; «без kk — без улицы» | name:kk из OSM → правило R07 («… көшесі», «… даңғылы») → без улицы; язык подсказки освещения меняется при ҚАЗ/РУС | `browser_check`: `kk_no_russian_street_names_in_card_and_hint`, `kk_street_names_from_osm_card_and_lighting_hint_1366_375`; `test_core`: правило R07, все 59 улиц Нуры | `kk_street_rule_1366_card.png`, `kk_street_{1366,375}_card.png` |
| R11 ночь B3 п. 6 (= R10 B-026) | см. «Ночь 1» | `r10_b026_*` | `b026_cluster_*` |
| R11 ночь B3 п. 7: «Спортплощадка» упирается в края карточки 116 px | сделано в поставке 2 (`@container`, 14 px в узкой оболочке) | `catalog_labels_fit_cards_in_narrow_host`; `app_b2_smoke`: `catalog_labels_inside_cards_ru` | `b2_1366_ru_akimat.png` |
| R11 ночь B3 п. 9: карточка проекта у жителя закрывает легенду R07 | строка в патче R01 b3: легенда скрыта, пока открыта карточка 3D | `app_b2_smoke`: `r07_legend_hidden_while_3d_card_open` | `b2_1366_ru_card.png` |
| R11 ночь круг 4 п. 1: две разные карточки проекта у жителя | в FINAL с R06 — одна, карточка R06 внутри панели 3D (так уже работает поставка R05; своя — только без R06) | `r06_stand_check`: `r06_card_inside_3d_panel`, `resident_r06_card_no_staff_actions` | `r06_375_kk_resident_card.png` |
| R15 U1: 429 показывается как сбой связи | «Слишком много действий подряд…» без «Повторить» (голос, «Поставить», «Удалить») | `browser_check`: `rate_limit_429_says_too_many_without_retry_ru_kk` | `toast_429_1366_kk.png` |

## Ночь 8 · R01 BUGS I-05

| Замечание | Что сделано | Проверка (PASS) | Скриншоты |
|---|---|---|---|
| R01 I-05: «[build3d] предложения не загрузились TypeError: Failed to fetch» в консоли, когда перезагрузка обрывает запрос списка | По `pagehide` модуль помечен «уходит»: оборванные запросы списка и сохранения не пишутся в консоль, тоста нет. Настоящий обрыв связи без ухода — тост «Повторить» и `console.warn`, а не `console.error` | `browser_check`: `reload_during_list_request_logs_no_console_error` (1366/375 × ru/kk; до правки FAIL — воспроизводит I-05 каждый раз); `app_b2_smoke` п. 9 внутри R01 4ca9aef; `r14_shell.cjs` R01 3 из 3 без сообщений build3d | `net_toast_{1366,375}_{ru,kk}.png` (тост при настоящем обрыве) |

## Ночь 9 · самопроверка в сборке R01 1dd5b53, R10 B-033

| Замечание | Что сделано | Проверка (PASS) | Скриншоты |
|---|---|---|---|
| Самопроверка (UX_BRIEF: шапка всегда доступна, объект не под карточкой): 375, акимат, шторка «half» — карточка проекта (391 px) закрывала шапку оболочки и сам объект | R05: высота панели — до нижнего края верхних полос хозяина (`avoid`), прокрутка внутри, пересчёт при смене шторки. Патч R01 2: выбор проекта на телефоне у акимата опускает шторку; легенда R07 скрыта под карточкой | `browser_check`: `card_never_covers_host_header_and_refits_when_sheet_lowers_375_ru_kk` (на старом коде FAIL); `app_b2_smoke`: `phone_akimat_card_with_half_sheet_does_not_cover_shell_header` (kk, ru) | `phone_akimat_half_card_375_{kk,ru}_before.png` → `phone_akimat_half_card_375_{kk,ru}.png`; `fit_header_375_{ru,kk}_{half,peek}.png` |
| R10 B-033 (в ACCEPTANCE_FINAL перенесён с ef1ef44) | Уже исправлено в R05 f946157/38cfc4a; проверено в R01 1dd5b53 как есть | `final_kk_street_check.mjs`: 1366/375 × kk/ru 4/4 | `final_kk_street_{1366,375}_{kk,ru}.png` |
