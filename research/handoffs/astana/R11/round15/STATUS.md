# R11 · раунд 15 · STATUS

Роль: R11 (UX, схема меню, ui-kit, казахский язык)
Ветка роли: claude/gracious-mendel-eopem6 (ветка сессии; push в claude/r15-R11 средой запрещён)
Начато: 2026-10-15 16:23 по Астане (11:23 UTC)
База: origin/claude/clever-hypatia-q6ts4g @ e91acb69 (код FINAL-4 a4937462 + пакет раунда 15)
restored_from: — (роль начата с нуля; прошлая передача — claude/r14-R11)

## План (по research/round-15/prompts/R11.txt)
1. До 17:53 по Астане — research/round-15-results/R11/IA_ROUND15.md (меню жителя и акимата, экраны, Хроника, Ситуационный центр) → push.
2. ui-kit: компоненты новых экранов (двор, инициатива, служба, передачи, календарь работ, конфликт, кризис, хроника, ситуационный центр, встреча) + пример в web/civic/ui-kit/index.html.
3. Словарь: новые ключи ролей в ru.json и kk.json; KK_REVIEW_R15.md.
4. Разбор экранов кругами (каждые 2–3 часа): кадры 1366/1024/375 × ru/kk → патчи в INTEGRATION.txt; DESIGN_BOOK_R15.md.
5. Дефекты VISUAL_BRIEF §3 вместе с R01 (знак Birge, меню «Ещё», поиск телефона).

## Сделано
- 16:23 — роль занята, ветка сессии переведена на основу пакета. Продолжение: scheduled task `trig_016AzLZ5EWKJKcbj4CTsPN44`
  (раз в час, :23, «Продолжи роль R11 по своему STATUS.md и research/round-15/prompts/R11.txt»); после 17 окт 23:59 — удалить.
- 16:37 — **IA_ROUND15.md опубликован** (research/round-15-results/R11/IA_ROUND15.md): меню жителя «Карта · Мои обращения ·
  Мой двор · Идеи · Ещё (Сделаем вместе, Вопросы и встречи)» + колокольчик; акимат «Карта · Картина дня · Обращения ·
  Ведомства · Ещё (С жителями: Проекты и идеи, Сделаем вместе, Вопросы и встречи; Инструменты: Спросить Birge,
  Ситуационный центр, QR)»; «Ведомства» = R17 с вкладкой календаря R12; «Хроника» — чип в легенде; ситуационный центр —
  страница /civic/board/; запасные места FINAL-4; шаг 5 демо не длиннее. 22 ключа меню в ru/kk (check PASS).
- Найдено: имя `BirgeAsk` занято «Вопросом акиму» R13 → модуль R03 «Спросить Birge» должен называться `BirgeAnalyst`
  (IA §5.6, §9); оболочке нужны `#раздел/путь` и `map` в опциях экрана (IA §7.3–7.4).

## Соседи (find_branches.py, 15 окт 16:30)
R01 claude/brave-fermi-nhzetj · R02 claude/affectionate-shannon-jm6ws5 · R03 claude/modest-mccarthy-lrl98u ·
R04 claude/gifted-maxwell-i66wwi · R05 claude/bold-cray-dopshy · R06 claude/eloquent-einstein-wvuyje ·
R07 claude/birge-r07-round-15-zjp4ob · R08 claude/inspiring-johnson-j7wksj · R09 claude/quirky-ptolemy-k3z2mj ·
R10 claude/zen-wozniak-69d41q · R12 claude/great-newton-8k3474 · R13 claude/gifted-mayer-p86myv ·
R15 claude/practical-fermi-c58v1u · R16 claude/youthful-johnson-6nz5mp · R17 claude/sweet-euler-5tiu5b · R14 — ещё нет.

## Дальше
- ui-kit: компоненты новых экранов + новые значки (bell, play, monitor, sparkle…) + иллюстрации видов идей и пустых состояний.
- Словарь: ключи ролей из их INTEGRATION; KK_REVIEW_R15.md.
- Круг разбора экранов — когда у ролей появятся экраны (проверять ветки каждые 2–3 часа).

## Вопросы владельцу (решено по умолчанию, см. IA_ROUND15 §10)
1. «Ведомства» или «Службы» в меню акимата? — взял «Ведомства» (как в IDEA и речи демо).
2. Ситуационный центр — в той же вкладке (демо на одном ноутбуке) или в новом окне? — взял ту же вкладку.
3. «Вопрос акиму» — вкладкой внутри «Вопросы и встречи» (+1 нажатие жителю) или отдельным пунктом «Ещё»? — взял вкладку.
