# Лист проверки кандидатов R05 (раунд 12)

Срез: 2026-10-07. Кандидатов к проверке: 44. Все найдены поиском; страницы в среде R05 не открывались (сеть закрыта). Подсказки «пересказ поиска» — ненадёжны, проверять по самой странице.

Порядок: открыть ссылку → сохранить текст страницы вне репозитория → заполнить drafts/<id>.json (дословные выдержки ≤ 300 символов) → `r12.py verify`.

## 1. Ливневки, канализационные очистные сооружения и водовод строят в Астане
- id кандидата: `cand-r12-livnevki-kanalizacionnye-ochistnye`; тип: construction; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-gov-a6b387ae` (Акимат города Астаны, official_gov): https://www.gov.kz/memleket/entities/astana/press/news/details/1242774?lang=ru
- место по выдаче: Астана (city-wide)
- дата-подсказка: 2026 (summary reports progress for the first five months of 2026) (происхождение: search_summary)
  - подсказка [заголовок] status: строят (under construction)
  - подсказка [пересказ поиска] other: technical water main for 50,000 m3/day: 3.2 km laid by end-2025, 5.8 km more in first 5 months of 2026
  - подсказка [пересказ поиска] budget.amount_kzt: Buzuluk reservoir (Esil counter-regulator) ~43 bn tenge, 2024-2027
  - подсказка [пересказ поиска] responsible.organization: Астана су арнасы
  - подсказка [пересказ поиска] status: Технический водовод: к концу 2025 г. проложено 3,2 км, за первые пять месяцев 2026 г. еще 5,8 км
  - подсказка [пересказ поиска] other: Технический водовод рассчитан на подачу 50 тыс. м3/сут на водоочистные станции
  - подсказка [пересказ поиска] other: Проектируются локальные очистные сооружения (Коктал, Ондирис, Индустриальный парк) общей мощностью 85 тыс. м3/сут; модернизация КОС-1 с увеличением на 25 тыс. м3/сут
  - подсказка [пересказ поиска] budget.amount_kzt: 1,512 млрд тенге из городского бюджета на развитие ливневой канализации в 2024–2026 гг.
- противоречия: The summary's '1,512 млрд тенге' for storm sewers in 2024–2026 is ambiguous (1.512 bn or 1,512 bn) and needs checking.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 2. Масштабное благоустройство общественных пространств продолжается в Астане
- id кандидата: `cand-r12-masshtabnoe-blagoustroistvo-obshes`; тип: landscaping; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-gov-118ae997` (Акимат города Астаны, official_gov): https://www.gov.kz/memleket/entities/astana/press/news/details/1267167?lang=ru
- источник `src-r12-inform-cb7478e4` (МИА «Казинформ», state_media): https://www.inform.kz/ru/bolee-11-mln-zelenih-nasazhdeniy-visadyat-v-astane-v-2026-godu-6a64cf5e
- место по выдаче: Астана (city-wide); GreenLine: ул. Омарова – ул. Тöле би (per summary)
- дата-подсказка: 'this year' (2026 inferred from the matching inform.kz 2026 plantings headline) (происхождение: search_summary)
  - подсказка [заголовок] status: благоустройство общественных пространств продолжается
  - подсказка [пересказ поиска] other: 173 public and courtyard spaces to be improved this year (parks, squares, boulevards, courtyards, pedestrian zones)
  - подсказка [пересказ поиска] location: GreenLine linear park 2nd phase from Omarova St to Tole bi St; pedestrian boulevard >3 km from Tole bi St to Aitmatov St
  - подсказка [пересказ поиска] other: over 1 million green plantings planned this year
- противоречия: Plantings: 'over 1 million' (this summary) vs 'more than 1.1 million' (inform.kz title). Compatible, but not the same figure.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 3. Подготовка к отопительному сезону: в Астане реализуют крупные проекты в сфере теплоснабжения
- id кандидата: `cand-r12-podgotovka-k-otopitelnomu-sezonu-v`; тип: construction; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-gov-a3d489bc` (Акимат города Астаны, official_gov): https://www.gov.kz/memleket/entities/astana/press/news/details/1261213?lang=ru
- источник `src-r12-kz-ae2f2745` (Kursiv Media, news): https://kz.kursiv.media/kk/2026-06-15/astana-zhylytu-mausymyna-dajyndala-bastady
- место по выдаче: Астана: газовая тепловая станция «Тельман», станция «Туран», ТЭЦ-2, ГТС «Юго-Запад» (проектирование)
- дата-подсказка: probably mid-2026 (news ID between July and August 2026 gov.kz items; inference, not stated) (происхождение: none)
  - подсказка [пересказ поиска] status: Строительная готовность газовой тепловой станции «Тельман» 76%
  - подсказка [пересказ поиска] other: В этом году планируется завершить вторую очередь станции «Туран», продолжить строительство «Тельмана», начать расширение ТЭЦ-2 и проектирование ГТС «Юго-Запад»
  - подсказка [пересказ поиска] responsible.organization: Аким Астаны Женис Касымбек (рассказал о проектах)
- противоречия: This summary says Telman construction continues at 76% readiness. The kursiv summary (2026-06-15) says the third stage of the Telman gas heating station has started. These may be different stages of the same project rather than a real conflict.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 4. Строительство развязок и дорог: как развивают дорожную сеть в Астане
- id кандидата: `cand-r12-stroitelstvo-razvyazok-i-dorog-kak`; тип: construction; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-gov-7b9c737a` (Акимат города Астаны, official_gov): https://www.gov.kz/memleket/entities/astana/press/news/details/1233855?lang=ru
- источник `src-r12-inform-ae29218b` (МИА «Казинформ», state_media): https://www.inform.kz/ru/kogda-otkroyut-novuyu-razvyazku-beysekovoy-tlendieva-v-astane-8ebee5ee
- источник `src-r12-bes-00377498` (Bes.media, news): https://bes.media/news/dvuhurovnevuyu-razvyazku-na-peresechenii-ulits-beysekovoy-i-tlendieva-v-astane-zavershat-do-kontsa-goda
- место по выдаче: Astana; Tlendiev ave x Sh. Beisekova st interchange; K. Mukhamedkhanov st (per summary)
- дата-подсказка: 2026: interchange to be finished 'by end of year'; Mukhamedkhanov St to be finished in 2026 with landscaping (publication date unknown) (происхождение: search_summary)
  - подсказка [заголовок] other: строительство развязок и дорог
  - подсказка [пересказ поиска] schedule.current_planned_end: Beisekova-Tlendiev two-level interchange: completion planned by end of year
  - подсказка [пересказ поиска] schedule.current_planned_end: K. Mukhamedkhanov street construction to be completed in 2026 with landscaping
  - подсказка [пересказ поиска] other: two-level interchange at Beisekova / Tlendiyev: engineering networks and metal structure assembly under way, completion planned by end of year
  - подсказка [пересказ поиска] schedule.current_planned_end: до конца года (year implied 2026 by summary, not confirmed)
  - подсказка [пересказ поиска] other: Tauelsizdik avenue section from Kabanbay Batyr to Uly Dala built as eight-lane highway
  - подсказка [пересказ поиска] other: Kazakh summary: in 2026 assembly of intermediate structures to be completed, then asphalt concrete laid on main carriageway and ramps
- противоречия: Interchange timing differs between the summaries. This page says it will be finished 'by end of year'. inform.kz says traffic opens by end of October and the Tlendiev asphalting finishes by 10 September. bes.media says the intersection was closed until 1 August and finishes 'by end of year'. These may be different stages (opening vs full completion), but that is unresolved. The year 2026 for 'end of year' comes only from the summary.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 5. В 2026 году в Астане построят еще 13 школ
- id кандидата: `cand-r12-v-2026-godu-v-astane-postroyat-esh`; тип: construction; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-gov-a5870e38` (Акимат города Астаны, official_gov): https://www.gov.kz/memleket/entities/astana/press/news/details/1141308?lang=ru
- место по выдаче: Астана (city-wide)
- дата-подсказка: 2026 (происхождение: search_title)
  - подсказка [заголовок] schedule.current_planned_end: 2026
  - подсказка [заголовок] other: 13 школ
  - подсказка [пересказ поиска] other: 44 schools with 109,000 places built in recent years
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 6. В Астане начался второй этап LRT: залита первая опора
- id кандидата: `cand-r12-v-astane-nachalsya-vtoroi-etap-lrt`; тип: construction; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-gov-5d47a9d5` (Акимат города Астаны, official_gov): https://www.gov.kz/memleket/entities/astana/press/news/details/1213149?lang=ru
- место по выдаче: Астана, линия LRT второй очереди (направление Косшы — per other result titles)
- дата-подсказка: 2026 (summary: Kosshy branch construction to start early 2026, ~1.5 years) (происхождение: search_summary)
  - подсказка [заголовок] status: второй этап LRT начался, залита первая опора
  - подсказка [пересказ поиска] schedule.current_planned_end: akim Kassymbek earlier said Kosshy branch construction would start early 2026 and take 1.5 years
  - подсказка [пересказ поиска] other: over 300 supports, 538 prefabricated reinforced concrete beams, 8 monolithic beams
- противоречия: The publication date is not visible. The gov.kz ID sits next to 1212421 (spring 2026), which is an inference only.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 7. В Астане стартовал сезон дорожно-строительных работ 2026 года
- id кандидата: `cand-r12-v-astane-startoval-sezon-dorozhno`; тип: roadworks; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-gov-2010a772` (Акимат города Астаны, official_gov): https://www.gov.kz/memleket/entities/astana/press/news/details/1193903?lang=ru
- источник `src-r12-inform-001616a2` (МИА «Казинформ», state_media): https://www.inform.kz/ru/desyatki-ulits-obnovyat-v-astane-osnovnie-dorozhnie-proekti-03ddd32d
- место по выдаче: Astana, citywide; summary names: Mangilik El / Syganak interchange; B. Sokpakbaev st (Sh. Beisekova - K. Kumisbekov); E68 st (A. Bekturov - Tole bi); 150 let Abaya st (Tlendiev - Beibarys Sultan; closure Beibarys Sultan - Sulukol); Kenesary st (A. Sembinov - Saryarka)
- дата-подсказка: 2026 season (title); summary: season start 3 April 2026; closures from 4-5 April, Sokpakbaev st until November 2026, 150 let Abaya (Beibarys Sultan - Sulukol) until 10 October 2026 (происхождение: search_title)
  - подсказка [заголовок] status: season started (стартовал сезон дорожно-строительных работ 2026 года)
  - подсказка [пересказ поиска] event_date: season start 3 April 2026
  - подсказка [пересказ поиска] closure: Mangilik El / Syganak interchange: medium repair, partial closure 4 April - 4 May
  - подсказка [пересказ поиска] closure: B. Sokpakbaev st from Sh. Beisekova to K. Kumisbekov: full closure 5 April - November (construction continues)
  - подсказка [пересказ поиска] closure: E68 st from A. Bekturov to Tole bi: full closure 5 April - June (start of construction)
  - подсказка [пересказ поиска] closure: 150 let Abaya st: section Beibarys Sultan - Sulukol fully closed 5 April - 10 October
  - подсказка [пересказ поиска] other: more than 70 streets planned for repair in 2026 (Al-Farabi Alash bridge - Pushkin, Valikhanov, Sh. Kudaiberdyuly, Tulpar bridge, Turan); 31 streets / 13 km to be built
  - подсказка [пересказ поиска] responsible.organization: ГУ «Управление транспорта и развития дорожно-транспортной инфраструктуры города Астаны»
  - подсказка [заголовок] event_date: сезон дорожно-строительных работ 2026 года
  - подсказка [пересказ поиска] closure: Mangilik El / Syganak interchange: medium repair from 4 April to 4 May, partial closure
  - подсказка [пересказ поиска] closure: E68 St from A. Bekturov St to Tole bi St: full closure from 5 April until June (Kazakh-language summary said May)
  - подсказка [пересказ поиска] closure: B. Sokpakbayev St from Sh. Beisekova St to K. Kumisbekov St: full closure from 5 April to November (construction)
  - подсказка [пересказ поиска] closure: 150 let Abaya St from Beibarys Sultan St to Sulukol St: full closure from 5 April to 10 October
  - подсказка [пересказ поиска] responsible.organization: Управление транспорта и развития дорожно-транспортной инфраструктуры города Астаны
  - подсказка [заголовок] schedule.planned_start: сезон дорожно-строительных работ 2026 года стартовал
  - подсказка [пересказ поиска] other: 31 streets totalling 13 km to be built: 4 completed in full, 19 continued, 8 started (summary hint)
  - подсказка [пересказ поиска] other: over 70 streets to be repaired this year (summary hint; conflicts with other results saying ~50 streets)
  - подсказка [заголовок] status: стартовал сезон дорожно-строительных работ 2026 года
  - подсказка [пересказ поиска] closure: С 4 апреля по 4 мая средний ремонт на развязке пр. Мангилик Ел / ул. Сыганак, движение частично перекрыто
  - подсказка [пересказ поиска] closure: С 5 апреля по июнь полное перекрытие ул. Е68 от ул. А. Бектурова до ул. Толе би
  - подсказка [пересказ поиска] closure: Строительство ул. Б. Сокпакбаева (Ш. Бейсековой – К. Кумисбекова): полное перекрытие с 5 апреля по ноябрь
  - подсказка [пересказ поиска] closure: Участок ул. Бейбарыс Султан – ул. Сулуколь полностью закрыт с 5 апреля по 10 октября
- противоречия: Number of streets differs: the summary for this page says more than 70 streets will be repaired; the inform.kz summary says about 50 streets / 60 km. The end of the E68 (Bekturov - Tole bi) closure is June in the Russian summary and May in the Kazakh summary. The inform.kz summary also lists Respubliki ave (Imanov - railway station) and the Beisekova-Tlendiev interchange, which do not appear in this page's summary. That is a difference in scope, not a direct conflict.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 8. Астана примет чемпионат мира по видам борьбы спустя семь лет
- id кандидата: `cand-r12-astana-primet-chempionat-mira-po-v`; тип: event; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-kazpravda-f290cf3d` («Казахстанская правда», state_media): https://kazpravda.kz/n/astana-primet-chempionat-mira-po-vidam-borby-spustya-sem-let
- место по выдаче: Barys Arena (per search summary)
- дата-подсказка: 2026-10-24..2026-11-01 (происхождение: search_summary)
  - подсказка [заголовок] status: Астана примет (will host) — seven years after previous
  - подсказка [пересказ поиска] event_date: 24 октября – 1 ноября 2026
  - подсказка [пересказ поиска] location: Barys Arena
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 9. Более 1,1 млн зеленых насаждений высадят в Астане в 2026 году
- id кандидата: `cand-r12-bolee-1-1-mln-zelenyh-nasazhdenii`; тип: landscaping; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-inform-cb7478e4` (МИА «Казинформ», state_media): https://www.inform.kz/ru/bolee-11-mln-zelenih-nasazhdeniy-visadyat-v-astane-v-2026-godu-6a64cf5e
- источник `src-r12-gov-118ae997` (Акимат города Астаны, official_gov): https://www.gov.kz/memleket/entities/astana/press/news/details/1267167?lang=ru
- место по выдаче: Астана (all six districts per summary: Алматы, Байконыр, Есиль, Нура, Сарайшык, Сарыарка)
- дата-подсказка: 2026 (происхождение: search_title)
  - подсказка [заголовок] other: более 1,1 млн зеленых насаждений высадят в 2026 году
  - подсказка [пересказ поиска] other: 70,000 trees, 600,000+ flowering shrubs, 40,000 hedge plants, 400,000+ perennial flowers
  - подсказка [пересказ поиска] location: all six districts: Almaty, Baikonyr, Yesil, Nura, Saraishyk, Saryarka
- противоречия: 'More than 1.1 million' (title) vs 'over 1 million' in the gov.kz summary. Minor.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 10. Улицу Алматы в Астане частично закроют до конца 2026 года
- id кандидата: `cand-r12-ulicu-almaty-v-astane-chastichno-z`; тип: roadworks; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-kazpravda-e43cc86a` («Казахстанская правда», state_media): https://kazpravda.kz/n/ulitsu-almaty-v-astane-chastichno-zakroyut-do-kontsa-2026-goda
- источник `src-r12-zakon-e0e1795d` (Zakon.kz, news): https://www.zakon.kz/sobytiia/6527998-izza-stroitelstva-tonnelya-v-astane-perekroyut-ulitsu-almaty-do-kontsa-2026-goda.html
- место по выдаче: Astana, Almaty street (Akmeshit - Sauran section per summary)
- дата-подсказка: until 2026-12-31 (title 'до конца 2026 года'); start 2026-07-20 per summary only (происхождение: search_title)
  - подсказка [заголовок] closure: улицу Алматы частично закроют до конца 2026 года
  - подсказка [заголовок] schedule.current_planned_end: до конца 2026 года
  - подсказка [пересказ поиска] closure: from 20 July through end of 2026, section Akmeshit - Sauran fully closed, related to transport tunnel construction from Mangilik El to Sauran
- противоречия: Kazpravda's title says 'частично закроют' (partial closure). The zakon.kz title says 'перекроют', and the summary says the Akmeshit–Sauran section is fully closed. This may simply be partial at street level and full on one section. zakon.kz is dated 13 Aug 2026, but the summary gives the start as 20 July, so it may be a later report or a second phase. Neither title names the exact section.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 11. Более 4,5 млрд тенге направят на обновление тепловых, электрических и водопроводных сетей Астаны
- id кандидата: `cand-r12-bolee-4-5-mlrd-tenge-napravyat-na`; тип: construction; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-bizmedia-d3e5a1cf` (Bizmedia.kz, news): https://bizmedia.kz/2026-06-05-bolee-45-mlrd-tenge-napravyat-na-obnovlenie-teplovyh-elektricheskih-i-vodoprovodnyh-setej-astany
- место по выдаче: Астана; технический водовод по ул. Досмухамедулы от ул. Акжол до пр. Алаш
- дата-подсказка: 2026-06-05 (происхождение: url)
  - подсказка [заголовок] budget.amount_kzt: Более 4,5 млрд тенге
  - подсказка [пересказ поиска] other: 1-й этап: обновление 7,08 км сетей за 1,4 млрд тенге; 4-й этап: реконструкция еще 9,59 км за 200 млн тенге
  - подсказка [пересказ поиска] responsible.organization: КГП «Астана су арнасы» — реконструкция технического водовода по ул. Досмухамедулы (ул. Акжол – пр. Алаш)
  - подсказка [пересказ поиска] budget.amount_kzt: Технический водовод: 2,47 млрд тенге, обновление более 3 км сетей
- противоречия: The summary's parts (1.4 bn, 0.2 bn and 2.47 bn) do not add up to the title's 'более 4,5 млрд', so items are missing. '9.59 km for 200 mn tenge' looks implausibly low and may be a garbled summary.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 12. Экопарк на Малом Талдыколе начнут строить в 2026 году: для сохранения уровня воды пробурят 73 скважины
- id кандидата: `cand-r12-ekopark-na-malom-taldykole-nachnut`; тип: landscaping; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-bes-31baedd3` (Bes.media, news): https://bes.media/ekopark-na-malom-taldikole-nachnut-stroit-v-2026-godu-dlya-sohraneniya-urovnya-vodi-postroyat-73-skvazhini-3d5b51
- источник `src-r12-kazpravda-c3c0b72d` («Казахстанская правда», state_media): https://kazpravda.kz/n/v-astane-poyavyatsya-novye-tochki-prityazheniya
- место по выдаче: Малый Талдыколь, Астана
- дата-подсказка: 2026 (planned construction start) (происхождение: search_title)
  - подсказка [заголовок] schedule.planned_start: 2026
  - подсказка [заголовок] other: 73 скважины для сохранения уровня воды
  - подсказка [пересказ поиска] other: documentation correction 85% complete; over 12,000 green plantings planned; tender of 5.3 bn tenge won by Sheberbuild not completed
- противоречия: The summary note that the tender 'was not completed' makes the actual 2026 start uncertain. The corroborating mention is summary-only.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 13. Экопарк на Малом Талдыколе появится в 2027 году
- id кандидата: `cand-r12-ekopark-na-malom-taldykole-poyavit`; тип: landscaping; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-inbusiness-ca006aba` (Inbusiness.kz, news): https://inbusiness.kz/ru/last/ekopark-na-malom-taldykole-poyavitsya-v-2027-godu
- источник `src-r12-vechastana-f09cd5ec` («Вечерняя Астана», city_media): https://www.vechastana.kz/news/svoi-kopengagen-i-ekopark-na-malom-taldykole
- место по выдаче: Малый Талдыколь, Астана
- дата-подсказка: 2027 (planned opening) (происхождение: search_title)
  - подсказка [заголовок] schedule.current_planned_end: 2027
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 14. На каких улицах Астаны перекроют движение из-за ремонта сетей
- id кандидата: `cand-r12-na-kakih-ulicah-astany-perekroyut`; тип: roadworks; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-bes-f00bbba0` (Bes.media, news): https://bes.media/na-kakih-ulitsah-astani-perekroyut-dvizhenie-iz-za-remonta-setey
- место по выдаче: ж/м Промышленный: ул. Атамура, Кокарал, Колтеген; ул. Карасай батыра (ТМ-12); участки ул. Ауэзова, Кумисбекова, Конституции
- дата-подсказка: 2026 investment programme; Promyshlenny networks by end of 2026 (subject to funding); TM-12 start late July – early August (year not explicit) (происхождение: search_summary)
  - подсказка [заголовок] closure: перекроют движение из-за ремонта сетей
  - подсказка [пересказ поиска] closure: Временно перекрыты ул. Атамура, Кокарал и Колтеген (ж/м Промышленный) из-за прокладки сетей водоснабжения, водоотведения и ливневой канализации
  - подсказка [пересказ поиска] schedule.current_planned_end: до конца 2026 года при достаточном финансировании (сети в ж/м Промышленный)
  - подсказка [пересказ поиска] closure: Временное перекрытие ул. Карасай батыра для строительно-монтажных работ по объекту ТМ-12 (в рамках национального проекта)
  - подсказка [пересказ поиска] schedule.planned_start: ТМ-12: ориентировочно конец июля – начало августа (год в сводке явно не указан)
  - подсказка [пересказ поиска] location: Позже ограничения на участках ул. Карасай батыра, Ауэзова, Кумисбекова и Конституции
  - подсказка [пересказ поиска] other: По инвестиционной программе 2026 года на 11 объектах вскрытие и восстановление благоустройства: 7 без вскрытия автодорог, 4 со вскрытием дорожного покрытия
- противоречия: The TM-12 start ('end of July – early August') has no explicit year. The end-2026 completion for Promyshlenny is conditional on funding.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 15. Сразу 50 улиц: Касымбек рассказал о дорожных планах Астаны
- id кандидата: `cand-r12-srazu-50-ulic-kasymbek-rasskazal-o`; тип: roadworks; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-kz-ddff58c7` (Kursiv Media, news): https://kz.kursiv.media/2026-09-04/svvo-srazu-50-ulicz-kasymbek-rasskazal-o-dorozhnyh-planah-astany
- источник `src-r12-bes-fd21add9` (Bes.media, news): https://bes.media/kakie-ulitsi-otremontiruyut-v-astane-v-2026-godu
- место по выдаче: Астана (city-wide)
- дата-подсказка: 2026-09-04 (происхождение: url)
  - подсказка [заголовок] other: 50 улиц
  - подсказка [пересказ поиска] other: ~50 streets, ~60 km repaired in 2026; asphalt on main carriageway and ramps by end of 2026 (summary)
- противоречия: gov.kz 1042433 also says 50 streets but is undated, and its ID suggests an earlier publication. The count may recur across years.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 16. v astane blagoustroyat 173 obshestvennyh i dvorovyh prostranstva
- id кандидата: `cand-r12-v-astane-blagoustroyat-173-obshest`; тип: landscaping; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-kapital-6bc0a124` (Kapital.kz, news): https://kapital.kz/gosudarstvo/151149/v-astane-blagoustroyat-173-obshestvennyh-i-dvorovyh-prostranstva.html
- место по выдаче: Астана (city-wide)
- дата-подсказка: 2026 (происхождение: search_summary)
  - подсказка [URL] other: благоустроят 173 общественных и дворовых пространства
  - подсказка [пересказ поиска] other: in 2026; includes 39 major public spaces; over 1.1 million trees, shrubs and seedlings
  - подсказка [пересказ поиска] location: GreenLine linear park 2nd phase, Omarova St to Tole bi St
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 17. В Астане появится новый мост через Есиль: какие дороги он разгрузит
- id кандидата: `cand-r12-v-astane-poyavitsya-novyi-most-che`; тип: construction; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-digitalbusiness-b9532dd5` (Digital Business, news): https://digitalbusiness.kz/2026-09-21/v-astane-poyavitsya-noviy-most-cherez-esil-kakie-dorogi-on-razgruzit
- место по выдаче: река Есиль, Астана; per summary: продолжение ул. Хусейн бен Талал между пр. Аль-Фараби и ул. Шамши Калдаякова
- дата-подсказка: 2026-09-21 (происхождение: url)
  - подсказка [заголовок] status: появится новый мост через Есиль (planned)
  - подсказка [пересказ поиска] location: continuation of Hussein bin Talal street between Al-Farabi avenue and Shamshi Kaldayakov street; eight lanes
  - подсказка [пересказ поиска] budget.amount_kzt: final cost unknown; investor is developing the design (summary)
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 18. 13.07.2026, 10:40 16251
- id кандидата: `cand-r12-13-07-2026-10-40-16251`; тип: construction; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-kt-beff66d8` (издатель не определён, other): https://www.kt.kz/eng/government/government_allocates_over_16_billion_tenge_for_astana_1377994792.html
- место по выдаче: Астана: канализационный коллектор от очистных сооружений района Есиль до оз. Карабидаик (Акмолинская обл.); новая подстанция; ТЭЦ-2
- дата-подсказка: 2026-07-13 (происхождение: search_title)
  - подсказка [пересказ поиска] budget.amount_kzt: 16,2 млрд тенге (постановление подписал премьер-министр Олжас Бектенов)
  - подсказка [пересказ поиска] budget.amount_kzt: 8,7 млрд тенге на строительство и модернизацию объектов водоотведения
  - подсказка [пересказ поиска] other: Реконструкция канализационного коллектора от очистных сооружений района Есиль до озера Карабидаик; новая подстанция; турбина ТЭЦ-2 +30 МВт (с 80 до 110 МВт)
- противоречия: The URL says 'over 16 billion' and the summary says 16.2 bn, which is consistent. Lake Karabidaik is in Akmola oblast, so the collector extends beyond the Astana city limits.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 19. UWW выбрал Астану для мирового турнира 2026
- id кандидата: `cand-r12-uww-vybral-astanu-dlya-mirovogo-tu`; тип: event; актуальность по выдаче: current_or_upcoming_2026
- источник `src-r12-24-a62036ad` (издатель не определён, other): https://24.kz/ru/news/sport/771073-uww-vybral-astanu-dlya-mirovogo-turnira-2026
- место по выдаче: Barys Arena (per search summary)
- дата-подсказка: 2026-10-24..2026-11-01 (происхождение: search_summary)
  - подсказка [заголовок] other: UWW chose Astana for 2026 world tournament
  - подсказка [пересказ поиска] event_date: 24 октября – 1 ноября
  - подсказка [пересказ поиска] location: Barys Arena
  - подсказка [заголовок] responsible.organization: United World Wrestling (UWW)
  - подсказка [пересказ поиска] other: moved from Bahrain due to Middle East conflict
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 20. Астанада өткен алғашқы UNICEF Charity Run қайырымдылық жүгірісіне 2000 адам қатысты
- id кандидата: `cand-r12-astanada-otken-algashky-unicef-cha`; тип: event; актуальность по выдаче: past_2026
- источник `src-r12-gov-823b8956` (Министерство туризма и спорта РК, official_gov): https://www.gov.kz/memleket/entities/tsm/press/news/details/1294963
- место по выдаче: Ботанический сад (per search summary)
- дата-подсказка: 2026-09-20 (происхождение: search_summary)
  - подсказка [заголовок] status: өткен (held); first edition; 2000 participants
  - подсказка [URL] responsible.organization: published by Ministry of Tourism and Sport (gov.kz entity 'tsm')
  - подсказка [пересказ поиска] event_date: 20 сентября 2026
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 21. Bala Fest: Астанада 200-ге жуық бала спорт пен шығармашылықтан сынға түсті
- id кандидата: `cand-r12-bala-fest-astanada-200-ge-zhuyk-ba`; тип: event; актуальность по выдаче: past_2026
- источник `src-r12-gov-ca64318a` (Акимат города Астаны, official_gov): https://www.gov.kz/memleket/entities/astana/press/news/details/1286417
- место по выдаче: Центральный парк (per search summary)
- дата-подсказка: 2026-09-05 (происхождение: search_summary)
  - подсказка [заголовок] other: ~200 children competed in sport and creative contests (200-ге жуық бала)
  - подсказка [пересказ поиска] event_date: 5 сентября 2026
  - подсказка [пересказ поиска] location: Центральный парк Астаны
  - подсказка [пересказ поиска] other: 11 competitions: robotics VEX, robo-sumo, asyk atu, boccia, traffic-safety classes
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 22. Более 30 новых дворов, скверов и спортплощадок открыли в Астане ко Дню города
- id кандидата: `cand-r12-bolee-30-novyh-dvorov-skverov-i-sp-2`; тип: landscaping; актуальность по выдаче: past_2026
- источник `src-r12-gov-c0c11753` (Акимат города Астаны, official_gov): https://www.gov.kz/memleket/entities/astana/press/news/details/1253881?lang=ru
- место по выдаче: Астана, all districts (per summary: Сарыарка — ул. Кутпанова, пр. Сарыарка; Нура — 2 сквера, 4 двора)
- дата-подсказка: ко Дню города (City Day, 6 July); year not in title; gov.kz news ID order suggests July 2026 (inference) (происхождение: search_title)
  - подсказка [заголовок] status: открыли (completed/opened) более 30 новых дворов, скверов и спортплощадок
  - подсказка [заголовок] event_date: ко Дню города
  - подсказка [пересказ поиска] location: Saryarka district: two courtyards on Kutpanov St and Saryarka Ave; Nura district: two squares, four courtyards and a new sports field
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 23. Фестиваль Comic Con Astana 2026 стартовал в столице
- id кандидата: `cand-r12-festival-comic-con-astana-2026-sta`; тип: event; актуальность по выдаче: past_2026
- источник `src-r12-gov-3fa6af4f` (Акимат города Астаны, official_gov): https://www.gov.kz/memleket/entities/astana/press/news/details/1269761?lang=ru
- место по выдаче: Barys Arena and Ледовый дворец «Алау» (per search summary)
- дата-подсказка: 2026 (title); 6-9 August 2026 (summary) (происхождение: search_title)
  - подсказка [заголовок] status: стартовал (festival started); year 2026 in title
  - подсказка [пересказ поиска] event_date: 6–9 августа 2026
  - подсказка [пересказ поиска] location: Barys Arena и Ледовый дворец «Алау»
  - подсказка [пересказ поиска] other: more than 40 countries participating; fifth edition
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 24. Участок улицы Баршын временно закроют в Астане
- id кандидата: `cand-r12-uchastok-ulicy-barshyn-vremenno-za`; тип: roadworks; актуальность по выдаче: past_2026
- источник `src-r12-gov-844b3675` (Акимат города Астаны, official_gov): https://www.gov.kz/memleket/entities/astana/press/news/details/1212421?lang=ru
- место по выдаче: Astana, Barshyn street, section from N. Tlendiev ave to S. Mukanov st (per summary)
- дата-подсказка: 2026-05-01..2026-05-10 (происхождение: search_summary)
  - подсказка [заголовок] closure: участок улицы Баршын временно закроют
  - подсказка [пересказ поиска] closure: partial closure 1-10 May ("текущего года"; one summary stated 2026)
  - подсказка [пересказ поиска] location: from N. Tlendiev ave to S. Mukanov st
  - подсказка [пересказ поиска] other: medium repair (средний ремонт)
  - подсказка [заголовок] closure: Участок улицы Баршын временно закроют
  - подсказка [заголовок] location: улица Баршын, Астана
- противоречия: Summaries say 'текущего года'; only one summary says 2026. The year has not been checked against a title or URL.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 25. bizmedia.kz
- id кандидата: `cand-r12-bizmedia-kz`; тип: construction; актуальность по выдаче: past_2026
- источник `src-r12-bizmedia-6da2f5d8` (Bizmedia.kz, news): https://bizmedia.kz/2026-05-12-lrt-v-astane-zapustyat-16-17-maya/md
- место по выдаче: Астана, линия LRT первой очереди (аэропорт — центр, per summary)
- дата-подсказка: article 2026-05-12; launch planned 16-17 May 2026 (происхождение: url)
  - подсказка [URL] event_date: LRT в Астане запустят 16-17 мая (article dated 2026-05-12)
  - подсказка [пересказ поиска] status: launched 16 May 2026 with President Tokayev; 22.4 km, 18 stations, depot
- противоречия: The URL says the launch was planned ('запустят 16-17 мая'). Only the summary says it actually took place on 16 May 2026.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 26. Два загруженных перекрестка закроют в Астане ᐈ новость от 16:55, 01 октября 2026 на zakon.kz
- id кандидата: `cand-r12-dva-zagruzhennyh-perekrestka-zakro`; тип: roadworks; актуальность по выдаче: past_2026
- источник `src-r12-zakon-f3d2c1b7` (Zakon.kz, news): https://www.zakon.kz/obshestvo/6533466-dva-zagruzhennykh-perekrestka-zakroyut-v-astane.html
- место по выдаче: R. Koshkarbayev Ave / B. Momyshuly Ave and R. Koshkarbayev Ave / M. Zhumabayev Ave, Astana
- дата-подсказка: 2026-10-01 (publication); closures 1–3 Oct 2026 per summary (происхождение: search_title)
  - подсказка [заголовок] closure: Два загруженных перекрестка закроют
  - подсказка [пересказ поиска] closure: Koshkarbayev / Momyshuly intersection closed from 23:00 1 October to 07:00 2 October
  - подсказка [пересказ поиска] closure: Koshkarbayev / Zhumabayev intersection closed from 23:00 2 October to 07:00 3 October
  - подсказка [пересказ поиска] other: reason: road works
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 27. Где и когда ограничат движение в Астане из-за концерта Кайрата Нуртаса ᐈ новость от 13:58, 26 сентября 2026 на zakon.kz
- id кандидата: `cand-r12-gde-i-kogda-ogranichat-dvizhenie-v`; тип: event; актуальность по выдаче: past_2026
- источник `src-r12-zakon-5ca5a9bc` (Zakon.kz, news): https://www.zakon.kz/obshestvo/6532842-gde-i-kogda-ogranichat-dvizhenie-v-astane-izza-kontserta-kayrata-nurtasa.html
- место по выдаче: Area around Astana Arena stadium (per summary)
- дата-подсказка: 2026-09-27 (event, per summary); article 2026-09-26 (title) (происхождение: search_summary)
  - подсказка [заголовок] other: ограничат движение в Астане из-за концерта Кайрата Нуртаса
  - подсказка [пересказ поиска] event_date: Sunday, 27 September 2026
  - подсказка [пересказ поиска] location: район стадиона «Астана Арена»
  - подсказка [заголовок] closure: ограничат движение в Астане (traffic restricted)
  - подсказка [пересказ поиска] event_date: 27 сентября, 19:00
  - подсказка [пересказ поиска] closure: проезд закрыт по ул. Марко Поло и ул. Месроп Маштоц рядом со стадионом
  - подсказка [пересказ поиска] other: free shuttle buses from 16:00 from four city parkings
- противоречия: Street names around the stadium are summary-only and unverified.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 28. Одну из улиц полностью перекроют в Астане в выходные: названа причина ᐈ новость от 19:18, 25 сентября 2026 на zakon.kz
- id кандидата: `cand-r12-odnu-iz-ulic-polnostyu-perekroyut`; тип: roadworks; актуальность по выдаче: past_2026
- источник `src-r12-zakon-bc223a78` (Zakon.kz, news): https://www.zakon.kz/obshestvo/6532785-odnu-iz-ulits-polnostyu-perekroyut-v-astane-v-vykhodnye-nazvana-prichina.html
- место по выдаче: Kosmonavtov St, from Alpamys Batyr St to Kabanbay Batyr Ave (per summaries)
- дата-подсказка: published 2026-09-25 (title); closure 26-27 September 2026 (summary) (происхождение: search_title)
  - подсказка [заголовок] closure: Одну из улиц полностью перекроют в выходные
  - подсказка [пересказ поиска] closure: Kosmonavtov St fully closed on 26–27 September (Saturday and Sunday) for repair
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 29. В Астане перекроют дороги из-за марафона: проверьте, затронет ли это ваш маршрут
- id кандидата: `cand-r12-v-astane-perekroyut-dorogi-iz-za-m`; тип: event; актуальность по выдаче: past_2026
- источник `src-r12-digitalbusiness-b4fdfb12` (Digital Business, news): https://digitalbusiness.kz/2026-06-05/v-astane-perekroyut-dorogi-iz-za-marafona-proverte-zatronet-li-eto-vash-marshrut
- место по выдаче: Tauelsizdik Ave (N. Nazhimedenov St to A. Baitursynuly St), Ivan Panfilov St, Zh. Nazhimedenov St (per summary)
- дата-подсказка: 2026-06-05 (article); event 7 June 2026 per summary (происхождение: url)
  - подсказка [заголовок] closure: перекроют дороги из-за марафона
  - подсказка [пересказ поиска] event_date: 7 June (5th anniversary Astana Half Marathon, about 7,000 participants)
  - подсказка [пересказ поиска] closure: Tauelsizdik Ave partially restricted from 06:00 6 June to 18:00 7 June; on 7 June: Panfilov St 07:00–08:45, Nazhimedenov St 07:14–08:45, Tauelsizdik Ave 07:00–08:55; traffic fully restored by 09:00
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 30. В Астане запустили LRT
- id кандидата: `cand-r12-v-astane-zapustili-lrt`; тип: construction; актуальность по выдаче: past_2026
- источник `src-r12-zakon-95af9e35` (Zakon.kz, news): https://www.zakon.kz/sobytiia/6518094-v-astane-zapustili-LRT.html
- место по выдаче: Астана
- дата-подсказка: 2026-05-16 (происхождение: search_summary)
  - подсказка [заголовок] status: запустили LRT
  - подсказка [пересказ поиска] schedule.actual_end: 16 May 2026 (launch by President Tokayev)
  - подсказка [пересказ поиска] other: 15 trains (4 reserve), driverless, 18 stations, ~40 min end-to-end, 5-6 min interval
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 31. В Астане 20 сентября пройдет благотворительный забег UNICEF Charity Run
- id кандидата: `cand-r12-v-astane-20-sentyabrya-proidet-bla`; тип: event; актуальность по выдаче: past_2026
- источник `src-r12-24-e486a296` (издатель не определён, other): https://24.kz/ru/news/sport/791320-v-astane-20-sentyabrya-projdet-blagotvoritelnyj-zabeg-unicef-charity-run
- место по выдаче: Ботанический сад (per search summary)
- дата-подсказка: 20 September (title); year 2026 inferred from 24.kz URL ID ordering (происхождение: search_title)
  - подсказка [заголовок] event_date: 20 сентября
  - подсказка [пересказ поиска] location: Ботанический сад
  - подсказка [пересказ поиска] other: distances 2, 5, 10 km; 2 km for children 7–15
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 32. В Астане на три дня перекроют участок дороги из-за работ на теплотрассе
- id кандидата: `cand-r12-v-astane-na-tri-dnya-perekroyut-uc`; тип: roadworks; актуальность по выдаче: past_2026
- источник `src-r12-liter-4a6c1245` (издатель не определён, other): https://liter.kz/v-astane-na-tri-dnia-perekroiut-uchastok-dorogi-iz-za-rabot-na-teplotrasse-1786718808
- место по выдаче: ул. К. Кайсенова в районе пересечения с ул. Т. Рыскулова
- дата-подсказка: 21:00 14 Aug 2026 - 05:00 17 Aug 2026 (summary; matches the URL numeric suffix = 2026-08-14) (происхождение: search_summary)
  - подсказка [заголовок] closure: на три дня перекроют участок дороги из-за работ на теплотрассе
  - подсказка [пересказ поиска] schedule.planned_start: 21:00 14 августа 2026
  - подсказка [пересказ поиска] schedule.current_planned_end: 05:00 17 августа 2026
  - подсказка [пересказ поиска] other: Работы по монтажу теплотрассы в рамках проекта строительства тепловых сетей к международной школе SABIS
  - подсказка [пересказ поиска] location: район ул. К. Кайсенова на пересечении с ул. Т. Рыскулова
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 33. В Астане полностью перекроют движение на одном из перекрестков: названы даты
- id кандидата: `cand-r12-v-astane-polnostyu-perekroyut-dviz`; тип: roadworks; актуальность по выдаче: past_2026
- источник `src-r12-24-2ebb2ffc` (издатель не определён, other): https://24.kz/ru/news/social/790905-v-astane-polnostyu-perekroyut-dvizhenie-na-odnom-iz-perekrestkov-nazvany-daty
- источник `src-r12-zakon-fc1fea08` (Zakon.kz, news): https://www.zakon.kz/sobytiia/6530987-v-astane-na-pyat-dney-polnostyu-perekroyut-dvizhenie-na-odnom-iz-vazhnykh-perekrestkov.html
- место по выдаче: перекресток ул. Хусейн бен Талал и пр. Аль-Фараби
- дата-подсказка: 2026-09-10..2026-09-15 (closure, per summaries); announced 2026-09-09 per zakon.kz title (происхождение: search_summary)
  - подсказка [заголовок] closure: полностью перекроют движение на одном из перекрестков
  - подсказка [пересказ поиска] schedule.planned_start: 10 сентября 2026
  - подсказка [пересказ поиска] schedule.current_planned_end: 15 сентября 2026
  - подсказка [пересказ поиска] other: Подрядчик выполняет работы по устройству инженерных сетей и подготовке дорожного основания
  - подсказка [пересказ поиска] location: пересечение ул. Хусейн бен Талал и пр. Аль-Фараби
- противоречия: zakon.kz says 'five days', while 10–15 Sep counts as 6 calendar days inclusive. Neither title names the intersection.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 34. Астанада «Халық қатысатын бюджет» жобасы аясында 60-тан астам аула абаттандырылды
- id кандидата: `cand-r12-astanada-halyk-katysatyn-byudzhet`; тип: landscaping; актуальность по выдаче: unknown
- источник `src-r12-gov-9adcb614` (Госорган на gov.kz (раздел entities/astana-uvp), official_gov): https://www.gov.kz/memleket/entities/astana-uvp/press/news/details/1276562
- место по выдаче: Астана (various districts, courtyards)
  - подсказка [заголовок] status: 60-тан астам аула абаттандырылды (completed)
  - подсказка [заголовок] other: «Халық қатысатын бюджет» жобасы аясында
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 35. 800-метровый тоннель появится на левобережье Астаны: что изменится для водителей
- id кандидата: `cand-r12-800-metrovyi-tonnel-poyavitsya-na`; тип: construction; актуальность по выдаче: unknown
- источник `src-r12-inform-ab83093f` (МИА «Казинформ», state_media): https://www.inform.kz/ru/800-metroviy-tonnel-poyavitsya-nalevoberezhe-astani-chto-izmenitsya-dlyavoditele-c8edae42
- источник `src-r12-vechastana-9b3b3aa4` («Вечерняя Астана», city_media): https://www.vechastana.kz/news/do-konca-goda-zakroiut-ulicy-akmesit-almaty
- место по выдаче: Astana, Esil district, Almaty street from Mangilik El ave to Sauran st (intersections with Sauran, Akmeshit, Turkestan stay open per summary)
- дата-подсказка: Almaty st closed from 15 August until the end of the year (year not stated); completion planned 2027 (происхождение: search_summary)
  - подсказка [заголовок] other: 800-метровый тоннель на левобережье
  - подсказка [пересказ поиска] closure: Almaty street fully closed from Mangilik El to Sauran from 15 August until end of year
  - подсказка [пересказ поиска] schedule.current_planned_end: completion planned in 2027
  - подсказка [пересказ поиска] responsible.organization: general contractor Integra Construction KZ; works by China Road and Bridge Corporation (CRBC)
- противоречия: Scope conflict: the inform.kz summary says the intersections with Sauran, Akmeshit and Turkestan stay open, while the vechastana.kz title says the Akmeshit-Almaty streets will be closed until the end of the year. Neither source shows the year.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 36. Когда откроют новую развязку Бейсековой — Тлендиева в Астане
- id кандидата: `cand-r12-kogda-otkroyut-novuyu-razvyazku-be`; тип: construction; актуальность по выдаче: unknown
- источник `src-r12-inform-ae29218b` (МИА «Казинформ», state_media): https://www.inform.kz/ru/kogda-otkroyut-novuyu-razvyazku-beysekovoy-tlendieva-v-astane-8ebee5ee
- источник `src-r12-gov-7b9c737a` (Акимат города Астаны, official_gov): https://www.gov.kz/memleket/entities/astana/press/news/details/1233855?lang=ru
- место по выдаче: Astana, intersection of N. Tlendiev ave and Sh. Beisekova st
- дата-подсказка: traffic to open by end of October; asphalting by 10 September (year not stated) (происхождение: search_summary)
  - подсказка [заголовок] other: новая развязка Бейсековой — Тлендиева
  - подсказка [пересказ поиска] schedule.current_planned_end: traffic on interchange planned to open by end of October; asphalting on Tlendiev to finish by 10 September
  - подсказка [пересказ поиска] status: as of late September metal span structures assembled, asphalt laid on Astykzhan side
- геометрия-предложение: Point, OSM: пересечение «улица Шабал Бейсековой» и «проспект Нургисы Тлендиева», узлы 13418022861, снимок 2026-05-06, ODbL
- противоречия: Opening 'by end of October' here vs completion 'by end of year' in the gov.kz summary and the bes.media slug.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 37. Национальный курултай Национальный курултай
- id кандидата: `cand-r12-nacionalnyi-kurultai-nacionalnyi-k-2`; тип: landscaping; актуальность по выдаче: unknown
- источник `src-r12-inform-69dbf4ea` (МИА «Казинформ», state_media): https://www.inform.kz/ru/nachalis-raboti-poblagoustroystvu-ekoparka-namalom-taldikole-vastane-99e4dfb6
- место по выдаче: Малый Талдыколь, Астана
- дата-подсказка: works started (year not stated); trail network and recreation zones to be finished in 2027 (происхождение: search_summary)
  - подсказка [URL] status: начались работы по благоустройству экопарка на Малом Талдыколе
  - подсказка [пересказ поиска] other: this year: technical facilities with filtration, wells to keep water level, first walking routes, start of large-scale greening
  - подсказка [пересказ поиска] schedule.current_planned_end: 2027: completion of walking/ecological trail network and recreation zones
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 38. Национальный курултай Национальный курултай
- id кандидата: `cand-r12-nacionalnyi-kurultai-nacionalnyi-k-3`; тип: landscaping; актуальность по выдаче: unknown
- источник `src-r12-inform-ddac7182` (МИА «Казинформ», state_media): https://www.inform.kz/ru/novie-tochki-prityazheniya-v-astane-nachalos-stroitelstvo-allei-minzhildik-1b899d
- место по выдаче: Аллея Мыңжылдық, Астана (per summary: сквер у театра им. К. Куанышбаева, привокзальный парк, территория вокзала «Нұрлы жол»)
  - подсказка [URL] status: началось строительство аллеи Мынжылдык
  - подсказка [пересказ поиска] location: work starting on three sections: square in front of Kuanyshbaev theatre, near-station park, Nurly Zhol station territory
  - подсказка [пересказ поиска] other: linear park more than 4 km long between Baitursynov and Nazhimedenov streets
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 39. Национальный курултай Национальный курултай
- id кандидата: `cand-r12-nacionalnyi-kurultai-nacionalnyi-k-4`; тип: construction; актуальность по выдаче: unknown
- источник `src-r12-inform-f8f1ffc0` (МИА «Казинформ», state_media): https://www.inform.kz/ru/vodovod-dlya-80-predpriyatiy-rekonstruiruyut-v-astane-c3f1ae3d
- место по выдаче: ул. Досмухамедулы от ул. Акжол до пр. Алаш
- дата-подсказка: до конца года (год не указан) (происхождение: search_summary)
  - подсказка [URL] other: vodovod-dlya-80-predpriyatiy-rekonstruiruyut-v-astane
  - подсказка [пересказ поиска] location: Технический водовод протяженностью ~3 км по ул. Досмухамедулы от ул. Акжол до пр. Алаш
  - подсказка [пересказ поиска] budget.amount_kzt: 2,38 млрд тенге
  - подсказка [пересказ поиска] status: Готовность около 55%, уложено ~1,7 км из 3 км
  - подсказка [пересказ поиска] schedule.current_planned_end: до конца года
  - подсказка [пересказ поиска] other: Параллельно готовится цифровая система управления водоснабжением и водоотведением стоимостью 916,4 млн тенге
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 40. Новый восьмиполосный мост планируют построить в Астане
- id кандидата: `cand-r12-novyi-vosmipolosnyi-most-planiruyu`; тип: construction; актуальность по выдаче: unknown
- источник `src-r12-inform-ab56e781` (МИА «Казинформ», state_media): https://www.inform.kz/ru/noviy-vosmipolosniy-most-planiruyut-postroit-vastane-c1e34cb5
- место по выдаче: Астана (per summary: продолжение ул. Хусейн бен Талал через Есиль)
  - подсказка [заголовок] status: планируют построить (planned)
  - подсказка [заголовок] other: восьмиполосный мост
  - подсказка [пересказ поиска] location: new road to link left bank with Almaty district and Nurly Zhol station area
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 41. Перекресток Акмешит — Алматы полностью перекроют в Астане
- id кандидата: `cand-r12-perekrestok-akmeshit-almaty-polnos`; тип: construction; актуальность по выдаче: unknown
- источник `src-r12-inform-46e9053b` (МИА «Казинформ», state_media): https://www.inform.kz/ru/perekrestok-akmeshit-almati-polnostyu-perekroyut-v-astane-40f40b73
- место по выдаче: Intersection of Akmeshit St and Almaty St, Yesil district, Astana
- дата-подсказка: с 21:00 19 сентября до конца года (год не указан) (происхождение: search_summary)
  - подсказка [заголовок] closure: Перекресток Акмешит — Алматы полностью перекроют
  - подсказка [пересказ поиска] schedule.planned_start: с 21:00 19 сентября
  - подсказка [пересказ поиска] schedule.current_planned_end: до конца года
  - подсказка [пересказ поиска] other: проект «Строительство транспортного тоннеля по ул. Алматы в районе Есиль города Астаны»
- геометрия-предложение: Point, OSM: пересечение «Ақмешіт көшесі» и «Алматы көшесі», узлы 2671166709,6539398108, снимок 2026-05-06, ODbL
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 42. Улицу Кенесары в Астане частично перекрыли
- id кандидата: `cand-r12-ulicu-kenesary-v-astane-chastichno`; тип: roadworks; актуальность по выдаче: unknown
- источник `src-r12-kazpravda-7d59b698` («Казахстанская правда», state_media): https://kazpravda.kz/n/ulitsu-kenesary-v-astane-chastichno-perekryli
- место по выдаче: Astana, Kenesary street (Sembinov - Saryarka section per summary)
- дата-подсказка: works from 20 April; Kenesary/Sembinov intersection fully closed 6–7 June (year not stated) (происхождение: search_summary)
  - подсказка [заголовок] closure: улицу Кенесары частично перекрыли
  - подсказка [пересказ поиска] other: medium repair; top layer works from 20 April on Kenesary from Sembinov to Saryarka; Kenesary/Sembinov intersection fully closed 6-7 June
- противоречия: The title says a partial closure; the summary also mentions a full intersection closure on 6–7 June. These are probably separate phases.
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 43. Появились детали и сроки строительства ЛРТ из Астаны в Косшы
- id кандидата: `cand-r12-poyavilis-detali-i-sroki-stroitels`; тип: construction; актуальность по выдаче: unknown
- источник `src-r12-inbusiness-0f38949f` (Inbusiness.kz, news): https://inbusiness.kz/ru/news/poyavilis-detali-i-sroki-stroitelstva-lrt-iz-astany-v-kosshy
- место по выдаче: Астана — Косшы
- дата-подсказка: construction from early 2026, ~1.5 years (per summary; article date unknown) (происхождение: search_summary)
  - подсказка [заголовок] location: ЛРТ из Астаны в Косшы
  - подсказка [пересказ поиска] other: project in two sections; route passes 510 m from Taldykol lake and crosses the Ishim river
  - подсказка [пересказ поиска] schedule.current_planned_end: construction to take 1.5 years from early 2026 (attributed to akim)
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)

## 44. Перекрёсток закроют на левом берегу Астаны более чем на две недели
- id кандидата: `cand-r12-perekrestok-zakroyut-na-levom-bere`; тип: roadworks; актуальность по выдаче: unknown
- источник `src-r12-informburo-1ab7be83` (издатель не определён, other): https://informburo.kz/novosti/perekrestok-zakroiut-na-levom-beregu-astany-bolee-cem-na-dve-nedeli
- место по выдаче: перекресток ул. Анет баба и ул. ЕК-26 (левый берег)
- дата-подсказка: 20 сентября – 5 октября (год не указан) (происхождение: search_summary)
  - подсказка [заголовок] closure: Перекрёсток закроют на левом берегу Астаны более чем на две недели
  - подсказка [пересказ поиска] schedule.planned_start: 20 сентября
  - подсказка [пересказ поиска] schedule.current_planned_end: 5 октября
  - подсказка [пересказ поиска] other: Прокладка инженерных сетей; полное ограничение движения автотранспорта
- проверить: открыть URL; убедиться, что речь об Астане и указана дата публикации; выписать дословно: что за работы/событие, где (улицы/участок), сроки (начало, окончание), кто ведёт; сумму и основание (план/договор/освоено) — только если названы на странице; отметить, что страница НЕ говорит (фактическое завершение, перенос срока и т.п.)
