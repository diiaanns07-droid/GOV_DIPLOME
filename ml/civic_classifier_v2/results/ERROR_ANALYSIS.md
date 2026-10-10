# Разбор ошибок классификатора v2 на probe_v2 (R03)

> Сгенерировано `python -m ml.civic_classifier_v2.analysis errors` из `results/experiments.json` и прогнозов по текстам (preds_probe_v2_synth_all_logreg, preds_probe_v2_synth_all_heuristic). Руками не править.

probe_v2 — 300 текстов агента R02 вне шаблонов (25 на категорию). Это не тексты жителей: разбор показывает, где модели путаются за пределами шаблонов обучения.

## 1. Где путаются модели (обучение на v3 + LLM)

### словарь — macro-F1 0.684, ошибок 100 из 300

| Истина → прогноз | Текстов | Доля категории |
|---|---|---|
| ЖКХ: тепло и вода → Другое | 13 | 52% |
| Шум и безопасность → Другое | 6 | 24% |
| Парковки → Другое | 5 | 20% |
| Запахи и воздух → Другое | 5 | 20% |
| Освещение → Другое | 4 | 16% |
| Другое → Дворы и площадки | 4 | 16% |
| Парковки → Дворы и площадки | 4 | 16% |
| Дороги → Другое | 4 | 16% |
| Остановки и транспорт → Другое | 4 | 16% |
| Парковки → Тротуары | 3 | 12% |

Категории-«магниты» (предсказаны чаще, чем есть): Другое — 64 вместо 25 (precision 0.20); Дворы и площадки — 37 вместо 25 (precision 0.62); Остановки и транспорт — 28 вместо 25 (precision 0.75).

### логрегрессия — macro-F1 0.797, ошибок 61 из 300

| Истина → прогноз | Текстов | Доля категории |
|---|---|---|
| Шум и безопасность → ЖКХ: тепло и вода | 3 | 12% |
| Тротуары → Шум и безопасность | 3 | 12% |
| Тротуары → Дороги | 3 | 12% |
| Запахи и воздух → Шум и безопасность | 3 | 12% |
| Снег и гололёд → Дворы и площадки | 3 | 12% |
| Шум и безопасность → Дворы и площадки | 2 | 8% |
| Парковки → Другое | 2 | 8% |
| Дороги → Парковки | 2 | 8% |
| Снег и гололёд → Тротуары | 2 | 8% |
| Освещение → ЖКХ: тепло и вода | 1 | 4% |

Категории-«магниты» (предсказаны чаще, чем есть): Дворы и площадки — 30 вместо 25 (precision 0.73); Освещение — 29 вместо 25 (precision 0.83); Дороги — 28 вместо 25 (precision 0.68); ЖКХ: тепло и вода — 27 вместо 25 (precision 0.74).

### трансформер — macro-F1 0.812, ошибок 57 из 300

| Истина → прогноз | Текстов | Доля категории |
|---|---|---|
| Шум и безопасность → Дороги | 3 | 12% |
| Тротуары → Дороги | 3 | 12% |
| Снег и гололёд → Тротуары | 3 | 12% |
| Мусор → Запахи и воздух | 3 | 12% |
| Шум и безопасность → Тротуары | 2 | 8% |
| Другое → Остановки и транспорт | 2 | 8% |
| Другое → Дворы и площадки | 2 | 8% |
| Парковки → Шум и безопасность | 2 | 8% |
| Запахи и воздух → Дороги | 2 | 8% |
| ЖКХ: тепло и вода → Освещение | 2 | 8% |

Категории-«магниты» (предсказаны чаще, чем есть): Дороги — 33 вместо 25 (precision 0.64); Освещение — 32 вместо 25 (precision 0.75); Тротуары — 31 вместо 25 (precision 0.68); ЖКХ: тепло и вода — 27 вместо 25 (precision 0.78).

## 2. Что трансформер исправил и что испортил по сравнению с логрегрессией (v3 + LLM)

| Категория | F1 логрегрессия | F1 трансформер | Δ | Recall лр → тр | Precision лр → тр |
|---|---|---|---|---|---|
| Другое | 0.81 | 0.89 | +0.08 | 0.84 → 0.80 | 0.78 → 1.00 |
| Снег и гололёд | 0.81 | 0.87 | +0.06 | 0.68 → 0.80 | 1.00 → 0.95 |
| Парковки | 0.77 | 0.82 | +0.05 | 0.72 → 0.80 | 0.82 → 0.83 |
| Шум и безопасность | 0.67 | 0.71 | +0.05 | 0.68 → 0.60 | 0.65 → 0.88 |
| ЖКХ: тепло и вода | 0.77 | 0.81 | +0.04 | 0.80 → 0.84 | 0.74 → 0.78 |
| Мусор | 0.85 | 0.89 | +0.04 | 0.80 → 0.80 | 0.91 → 1.00 |
| Запахи и воздух | 0.77 | 0.78 | +0.02 | 0.72 → 0.80 | 0.82 → 0.77 |
| Дворы и площадки | 0.80 | 0.82 | +0.02 | 0.88 → 0.80 | 0.73 → 0.83 |
| Дороги | 0.72 | 0.72 | +0.01 | 0.76 → 0.84 | 0.68 → 0.64 |
| Тротуары | 0.78 | 0.75 | -0.03 | 0.76 → 0.84 | 0.79 → 0.68 |
| Освещение | 0.89 | 0.84 | -0.05 | 0.96 → 0.96 | 0.83 → 0.75 |
| Остановки и транспорт | 0.94 | 0.84 | -0.10 | 0.96 → 0.84 | 0.92 → 0.84 |

По 25 текстов на категорию: Δ меньше ±0.08 (два текста) — шум.

## 3. Почему трансформер на одной шаблонной v3 провалился на её же невиданных шаблонах

Macro-F1 на test v3 — 0.482 (логрегрессия 0.632). Категории с нулевым или почти нулевым F1:

- Тротуары: F1 0.00, support 66, предсказано 30; уходят в Дороги (37), ЖКХ: тепло и вода (22), Дворы и площадки (4)
- Шум и безопасность: F1 0.04, support 43, предсказано 11; уходят в Тротуары (16), Запахи и воздух (15), Дворы и площадки (6)
- Парковки: F1 0.00, support 44, предсказано 4; уходят в Остановки и транспорт (44)

Train loss в конце обучения 0.03 при val macro-F1 0.756: модель запоминает формулировки шаблонов. Невиданные шаблоны тех же категорий (другие слова) она относит к соседним темам. С LLM-синтетикой (другие формулировки) test v3 — 0.779: разнообразие данных важнее размера модели.

## 4. Примеры ошибок (тексты probe_v2)

Из 300 текстов: ошибаются обе модели — 50; только `preds_probe_v2_synth_all_logreg` — 11; только `preds_probe_v2_synth_all_heuristic` — 50.

### `preds_probe_v2_synth_all_logreg` — 61 ошибок

Языки: {'ru': 29, 'kk': 22, 'mixed': 10}; стили: {'colloquial': 17, 'translit': 12, 'typos': 7, 'slang': 7, 'official': 6, 'question': 5, 'long': 5, 'short': 1, 'thanks': 1}; трудных случаев: 27.

| id | Текст (до 140 знаков) | Истина | Прогноз | Язык / стиль | Правило трудного случая |
|---|---|---|---|---|---|
| probe2-lighting-11 | фанарь у третьего подъезда мигает всю ночь , в окна бьёт | lighting | utilities | ru / typos |  |
| probe2-noise_safety-01 | Третий месяц рядом с домом строят торговый центр. Работы начинаются в шесть утра и идут до полуночи: перфораторы, бетономешалки, сигналы … | noise_safety | utilities | ru / long |  |
| probe2-noise_safety-02 | По нашему двору каждый вечер носятся подростки на питбайках и электросамокатах без света. Вчера чуть не сбили ребёнка у песочницы. Мы про… | noise_safety | yards | ru / long |  |
| probe2-noise_safety-03 | Біздің мектептің алдындағы жолда жаяу жүргіншілер өткелі жоқ. Балалар жолды кез келген жерден кесіп өтеді, көліктер жылдам жүреді. Ата-ан… | noise_safety | parking | kk / long | нет перехода → noise_safety |
| probe2-noise_safety-10 | Qarausyz qalgan uige balalar kirip oinaidy, qabyrgalary qulaiyn dep tur | noise_safety | yards | kk / translit |  |
| probe2-noise_safety-19 | Жолдың ортасындағы люктің қақпағы жоқ, көлік те, адам да түсіп кетуі мүмкін | noise_safety | roads | kk / colloquial | открытый люк → noise_safety |
| probe2-noise_safety-22 | Бұзылып жатқан ескі үйді неге қоршамайды? Балалар сол жерде ойнайды. | noise_safety | utilities | kk / question |  |
| probe2-noise_safety-23 | Возле подъезда сорвало крышку канализационного люка, дыра прямо на тропинке | noise_safety | utilities | ru / colloquial | открытый люк → noise_safety |
| probe2-noise_safety-25 | Аулада фонарь жоқ, но главная проблема — там ночью компания собирается, драка была, опасно | noise_safety | lighting | mixed / colloquial | опасность от людей, а не от темноты → noise_safety |
| probe2-other-03 | Аулада жаңа балалар алаңын салғандарыңыз үшін үлкен рақмет! Балалар таңертеңнен кешке дейін сол жерде ойнайды, аналар да риза. Осындай жұ… | other | yards | kk / long | благодарность → other |
| probe2-other-08 | Жаңа велодорожка просто бомба, үлкен рақмет | other | sidewalks | mixed / slang | благодарность → other |
| probe2-other-21 | Когда закончат строить развязку на Тауелсиздик? Хочется планировать маршрут. | other | transport | ru / question | вопрос о сроках без проблемы → other |
| probe2-other-23 | Спасибо, что так быстро починили фонари у нас во дворе! | other | lighting | ru / thanks | благодарность о свете → other |
| probe2-parking-07 | Какой-то гений на джипе каждый день встаёт поперёк выезда, хоть через забор прыгай | parking | other | ru / slang |  |
| probe2-parking-08 | Тағы біреу паркуется на зебре, вообще ничего не боятся | parking | lighting | mixed / slang | парковка на переходе → parking |
| probe2-parking-09 | mashiny stoyat pryamo na trotuare u magazina, peshekhody idut po doroge | parking | sidewalks | ru / translit | машина на тротуаре → parking |
| probe2-parking-10 | Aula ishinde kolikterdi eki qatar qoiyp, shygatyn zholdy zhauyp tastaidy | parking | smell_air | kk / translit |  |
| probe2-parking-12 | на газоне у дома стоят грузовики,газон весь в колеях | parking | roads | ru / typos |  |
| probe2-parking-14 | Прошу рассмотреть возможность обустройства парковочного кармана у школы №64 для высадки детей в утренние часы. | parking | other | ru / official |  |
| probe2-parking-25 | Газонға тағы машина тұрды, ағаштардың тамыры бүлінеді, сделайте ограждение | parking | yards | mixed / colloquial | машины на газоне → parking |
| probe2-roads-09 | na kabanbay batyra u perekrestka s dostyk ogromnaya yama, uzhe tret'yu nedelyu ne zadelyvayut | roads | sidewalks | ru / translit |  |
| probe2-roads-13 | аула жолында шуңкыр бар, кеше машинам тусип кетти | roads | parking | kk / typos | яма во дворе → roads |
| probe2-roads-16 | Құрметті әкімдік, Сарайшық көшесіндегі жаяу жүргіншілер өткелінің таңбасы толық өшіп кеткен. Жүргізушілер өткелді байқамай, балалар қауіп… | roads | noise_safety | kk / official | «зебра» → roads |
| probe2-roads-20 | Біздің аулаға кіретін жерде лужа огромная, жаңбырдан кейін машиналар тұрып қалады | roads | parking | mixed / colloquial | вода на проезжей части → roads |
| probe2-roads-22 | Хусейн бен Талал көшесіндегі ойықтарды қашан жабасыздар? Күн сайын бір көлік зақымданады. | roads | other | kk / question |  |
| probe2-roads-24 | У школы и фонари не горят, и на дороге яма, но больше всего просим заделать яму — машины резко тормозят прямо у перехода. | roads | lighting | ru / colloquial | несколько проблем → о чём просят |
| probe2-sidewalks-10 | Zhayau zholdagy plitkalar synyp, oryndarynan koterilip ketken | sidewalks | roads | kk / translit |  |
| probe2-sidewalks-11 | на тратуаре возле садика огромная дыра ,закрыта только картонкой | sidewalks | noise_safety | ru / typos |  |
| probe2-sidewalks-16 | Құрметті әкімдік, Жұбанов көшесіндегі жерасты өткелінің баспалдақтары бұзылған, кейбір тақталары жоқ. Жөндеу жұмыстарын жүргізуді сұраймыз. | sidewalks | noise_safety | kk / official |  |
| probe2-sidewalks-19 | Емханаға баратын жаяу жолды қазып тастап, қалпына келтірмеді | sidewalks | roads | kk / colloquial |  |
| probe2-sidewalks-24 | Застройщик огородил территорию прямо по пешеходной части, обойти можно только по дороге, где ездят самосвалы. | sidewalks | roads | ru / colloquial | проход перекрыт стройкой → sidewalks |
| probe2-sidewalks-25 | Өткелдің астын су басып қалды, аяқ киімді суламай өту мүмкін емес, опять затопило | sidewalks | noise_safety | mixed / colloquial | вода в переходе → sidewalks |
| probe2-smell_air-07 | Опять кто-то включил «аромат» с очистных, на балконе как в туалете, спасибо, блин | smell_air | other | ru / slang |  |
| probe2-smell_air-09 | kazhduyu noch' pakhnet khimiey so storony promzony, golova bolit | smell_air | noise_safety | ru / translit |  |
| probe2-smell_air-10 | Qurylystan shan kop, terezeni ashsaq bari shanga tolady | smell_air | waste | kk / translit | пыль от стройки → smell_air |
| probe2-smell_air-12 | на улице сильно пахнет газом возле трубы у забора , страшно | smell_air | noise_safety | ru / typos | газ на улице → smell_air |
| probe2-smell_air-13 | кошеде сасык ийис, шыдауга болмайды, кешке кушейеди | smell_air | noise_safety | kk / typos |  |
| probe2-smell_air-16 | Құрметті әкімдік! Көктемнен бері ауданымызда кәріз тазалау станциясының иісі сезіледі, әсіресе түнде. Бұл мәселені зерттеп, шешуді сұраймыз. | smell_air | utilities | kk / official |  |
| probe2-smell_air-17 | От асфальтового завода у трассы такой запах битума, что голова кружится | smell_air | roads | ru / colloquial |  |
| probe2-snow_ice-08 | Тротуар это просто каток, мен бүгін екі рет құладым, кто-нибудь песком посыпьте уже | snow_ice | sidewalks | mixed / slang | снег на тротуаре → snow_ice |
| probe2-snow_ice-09 | u nas na ulitse Pushkina trotuar ves' vo l'du, babushki boyatsya vyhodit' | snow_ice | sidewalks | ru / translit | снег на тротуаре → snow_ice |
| probe2-snow_ice-10 | Mektep aldynda qar uiilip zhatyr, balalar zholdyn ortasymen zhuredi | snow_ice | yards | kk / translit |  |
| probe2-snow_ice-13 | аулада кар тазаланбаган бир апта болды, машинаны шыгара алмаймыз | snow_ice | parking | kk / typos |  |
| probe2-snow_ice-17 | Площадку у подъезда завалило, дворник появляется раз в неделю, без лопаты не пройти | snow_ice | yards | ru / colloquial |  |
| probe2-snow_ice-20 | Подъездке кіре берісте мұз, вчера бабушка упала, қолын сындырып алды | snow_ice | utilities | mixed / colloquial |  |
| probe2-snow_ice-22 | Неге біздің аялдаманың маңындағы қар тазаланбайды? Автобусқа жету қиын. | snow_ice | transport | kk / question | снег на остановке → snow_ice |
| probe2-snow_ice-24 | Горка на детской площадке вся обледенела, а вокруг сугробы — детям даже не подойти | snow_ice | yards | ru / colloquial | снег на площадке → snow_ice |
| probe2-transport-07 | Водитель 12-го вообще без тормозов: закрыл двери перед носом и укатил, хотя я махала. Сервис уровня бог. | transport | noise_safety | ru / slang |  |
| probe2-utilities-04 | опять без горячей | utilities | noise_safety | ru / short |  |
| probe2-utilities-10 | Uide ystyq su zhoq, eshkim eshteme aitpaidy | utilities | other | kk / translit |  |
| probe2-utilities-16 | Құрметті әкімдік! Біздің үйде газ иісі шығады, кіреберісте әсіресе қатты сезіледі. Газ қызметін тез арада жіберуді сұраймыз. | utilities | smell_air | kk / official | газ в подъезде → utilities |
| probe2-utilities-17 | Из крана идёт ржавая вода, стирать невозможно, бельё всё жёлтое | utilities | roads | ru / colloquial |  |
| probe2-utilities-18 | Кіреберістегі шамдар жанбайды, кешке баспалдақпен көтерілу қорқынышты | utilities | lighting | kk / colloquial | свет в подъезде → utilities |
| probe2-waste-10 | Aulanyn burishinda ulken qoqys uiindisi paida boldy, eshkim alyp ketpeidi | waste | roads | kk / translit |  |
| probe2-waste-14 | Прошу ликвидировать несанкционированную свалку вдоль железнодорожных путей в районе Байконур. | waste | other | ru / official |  |
| probe2-waste-17 | После выходных весь берег Есиля в бутылках и пакетах, кто-то же должен это убирать | waste | utilities | ru / colloquial |  |
| probe2-waste-21 | Почему у нас во дворе так и не поставили отдельные баки для пластика? Обещали ещё весной. | waste | yards | ru / question |  |
| probe2-waste-25 | Свалка жанынан қатты иіс шығады, но главное — убрать саму свалку, ол балалар алаңының қасында | waste | smell_air | mixed / colloquial | несколько проблем → о чём просят |
| probe2-yards-02 | Весной во дворе спилили четыре старых тополя, сказали — аварийные. Обещали посадить новые деревья, но прошло полгода, остались только пни… | yards | roads | ru / long | вопрос с проблемой → по проблеме |
| probe2-yards-08 | Аулада газон вытоптан, бәрі шаң-топырақ, жасыл ештеңе жоқ, грустно | yards | smell_air | mixed / slang |  |
| probe2-yards-09 | na detskoy ploshchadke u gorki otorvalsya bortik, ostrye kraya | yards | waste | ru / translit |  |

### `preds_probe_v2_synth_all_heuristic` — 100 ошибок

Языки: {'ru': 53, 'kk': 32, 'mixed': 15}; стили: {'colloquial': 27, 'translit': 22, 'slang': 9, 'official': 9, 'typos': 8, 'short': 8, 'long': 8, 'question': 7, 'thanks': 2}; трудных случаев: 44.

| id | Текст (до 140 знаков) | Истина | Прогноз | Язык / стиль | Правило трудного случая |
|---|---|---|---|---|---|
| probe2-lighting-06 | Көшеде свет жоқ | lighting | other | mixed / short |  |
| probe2-lighting-09 | na nashey ulitse vecherom ni odnogo rabotayushchego fonarya, idti strashno | lighting | other | ru / translit |  |
| probe2-lighting-10 | Sayabaqtagy shamdardyn barlygy sonip qalgan, keshke ol zhaqqa baru qauipti | lighting | other | kk / translit |  |
| probe2-lighting-21 | Почему на новой улице в Нуре поставили столбы, а свет так и не включили? | lighting | other | ru / question |  |
| probe2-noise_safety-01 | Третий месяц рядом с домом строят торговый центр. Работы начинаются в шесть утра и идут до полуночи: перфораторы, бетономешалки, сигналы … | noise_safety | other | ru / long |  |
| probe2-noise_safety-02 | По нашему двору каждый вечер носятся подростки на питбайках и электросамокатах без света. Вчера чуть не сбили ребёнка у песочницы. Мы про… | noise_safety | yards | ru / long |  |
| probe2-noise_safety-03 | Біздің мектептің алдындағы жолда жаяу жүргіншілер өткелі жоқ. Балалар жолды кез келген жерден кесіп өтеді, көліктер жылдам жүреді. Ата-ан… | noise_safety | sidewalks | kk / long | нет перехода → noise_safety |
| probe2-noise_safety-04 | люк открыт у школы | noise_safety | other | ru / short | открытый люк → noise_safety |
| probe2-noise_safety-07 | Сосед сверху каждую ночь устраивает дискотеку, басы такие, что люстра трясётся, участковый не приезжает | noise_safety | other | ru / slang |  |
| probe2-noise_safety-09 | noch'yu vo dvore kompaniya p'yot i oryot do treh chasov, spat' nevozmozhno | noise_safety | other | ru / translit |  |
| probe2-noise_safety-10 | Qarausyz qalgan uige balalar kirip oinaidy, qabyrgalary qulaiyn dep tur | noise_safety | other | kk / translit |  |
| probe2-noise_safety-15 | Сообщаю о торчащей арматуре и открытом котловане на заброшенной стройплощадке рядом с жилыми домами, территория не огорожена. | noise_safety | yards | ru / official |  |
| probe2-noise_safety-19 | Жолдың ортасындағы люктің қақпағы жоқ, көлік те, адам да түсіп кетуі мүмкін | noise_safety | roads | kk / colloquial | открытый люк → noise_safety |
| probe2-noise_safety-22 | Бұзылып жатқан ескі үйді неге қоршамайды? Балалар сол жерде ойнайды. | noise_safety | other | kk / question |  |
| probe2-noise_safety-23 | Возле подъезда сорвало крышку канализационного люка, дыра прямо на тропинке | noise_safety | utilities | ru / colloquial | открытый люк → noise_safety |
| probe2-noise_safety-24 | Бродячие собаки у остановки бросаются на людей, особенно утром | noise_safety | transport | ru / colloquial | бездомные собаки → noise_safety |
| probe2-other-01 | Хочу сказать огромное спасибо бригаде, которая в субботу меняла трубы у нас во дворе. Работали быстро, всё за собой убрали, даже газон об… | other | yards | ru / long | благодарность → other |
| probe2-other-03 | Аулада жаңа балалар алаңын салғандарыңыз үшін үлкен рақмет! Балалар таңертеңнен кешке дейін сол жерде ойнайды, аналар да риза. Осындай жұ… | other | yards | kk / long | благодарность → other |
| probe2-other-04 | спасибо за уборку снега | other | snow_ice | ru / short | благодарность о снеге → other |
| probe2-other-06 | Үлкен спасибо коммунальщикам | other | utilities | mixed / short | благодарность → other |
| probe2-other-07 | Кайф, новый сквер огонь, наконец-то есть где погулять вечером | other | yards | ru / slang | благодарность → other |
| probe2-other-08 | Жаңа велодорожка просто бомба, үлкен рақмет | other | sidewalks | mixed / slang | благодарность → other |
| probe2-other-12 | спасибо огромное за ремонт дороги на сауране,теперь ездить одно удовольствие | other | roads | ru / typos | благодарность о дороге → other |
| probe2-other-15 | Предлагаю организовать в районе ежегодный конкурс на лучший двор — это мотивирует жителей следить за территорией. | other | yards | ru / official |  |
| probe2-other-21 | Когда закончат строить развязку на Тауелсиздик? Хочется планировать маршрут. | other | transport | ru / question | вопрос о сроках без проблемы → other |
| probe2-other-23 | Спасибо, что так быстро починили фонари у нас во дворе! | other | lighting | ru / thanks | благодарность о свете → other |
| probe2-other-24 | Подскажите, кто отвечает за уборку снега во дворе — КСК или акимат? | other | snow_ice | ru / question | вопрос о порядке без проблемы → other |
| probe2-other-25 | Рақмет за новую остановку, енді жаңбырда тұрмаймыз | other | transport | mixed / thanks | благодарность об остановке → other |
| probe2-parking-01 | Во дворе нашего дома парковочных мест втрое меньше, чем квартир. Вечером машины стоят на тротуарах, на газонах и даже у мусорных баков, м… | parking | waste | ru / long |  |
| probe2-parking-03 | Біздің ауланың ортасында бір көлік бір жылдан бері тұр: дөңгелектері жоқ, әйнегі сынған. Маңында балалар ойнайды, ішіне де кіріп кетеді. … | parking | yards | kk / long |  |
| probe2-parking-06 | Тротуарда машина тұр опять | parking | sidewalks | mixed / short | машина на тротуаре → parking |
| probe2-parking-07 | Какой-то гений на джипе каждый день встаёт поперёк выезда, хоть через забор прыгай | parking | other | ru / slang |  |
| probe2-parking-08 | Тағы біреу паркуется на зебре, вообще ничего не боятся | parking | other | mixed / slang | парковка на переходе → parking |
| probe2-parking-09 | mashiny stoyat pryamo na trotuare u magazina, peshekhody idut po doroge | parking | other | ru / translit | машина на тротуаре → parking |
| probe2-parking-10 | Aula ishinde kolikterdi eki qatar qoiyp, shygatyn zholdy zhauyp tastaidy | parking | other | kk / translit |  |
| probe2-parking-12 | на газоне у дома стоят грузовики,газон весь в колеях | parking | roads | ru / typos |  |
| probe2-parking-17 | Таксисты устроили стоянку прямо на остановке, автобус встаёт посреди дороги | parking | transport | ru / colloquial | такси на остановке → parking |
| probe2-parking-18 | Көліктер көгалды таптап, ауланы батпаққа айналдырды | parking | yards | kk / colloquial | машины на газоне → parking |
| probe2-parking-19 | Үйдің алдына көлік қоятын орын салып беріңіздерші, қазір көше бойына тұрамыз | parking | other | kk / colloquial |  |
| probe2-parking-20 | Біздің аулаға бөтен машиналар кіріп, стоят целый день, өзімізге орын жоқ | parking | yards | mixed / colloquial |  |
| probe2-parking-23 | Машина стоит прямо на тротуаре у подъезда, обходим по проезжей части | parking | sidewalks | ru / colloquial | машина на тротуаре → parking |
| probe2-parking-24 | Пешеходную дорожку у школы заставили машины родителей, дети идут по газону | parking | sidewalks | ru / colloquial | машины на дорожке → parking |
| probe2-parking-25 | Газонға тағы машина тұрды, ағаштардың тамыры бүлінеді, сделайте ограждение | parking | yards | mixed / colloquial | машины на газоне → parking |
| probe2-roads-07 | Народ, кто ездит по Улы Дала — там у развязки ямища на ямище, подвеска плачет. Дорожники вообще в курсе, что у нас тут ралли? | roads | other | ru / slang |  |
| probe2-roads-09 | na kabanbay batyra u perekrestka s dostyk ogromnaya yama, uzhe tret'yu nedelyu ne zadelyvayut | roads | other | ru / translit |  |
| probe2-roads-10 | Qoshqarbaev koshesinde asfalt oiylyp ketken, zhurgizushiler qarsy zholaqqa shygyp ketip zhatyr | roads | other | kk / translit |  |
| probe2-roads-16 | Құрметті әкімдік, Сарайшық көшесіндегі жаяу жүргіншілер өткелінің таңбасы толық өшіп кеткен. Жүргізушілер өткелді байқамай, балалар қауіп… | roads | sidewalks | kk / official | «зебра» → roads |
| probe2-roads-20 | Біздің аулаға кіретін жерде лужа огромная, жаңбырдан кейін машиналар тұрып қалады | roads | yards | mixed / colloquial | вода на проезжей части → roads |
| probe2-roads-22 | Хусейн бен Талал көшесіндегі ойықтарды қашан жабасыздар? Күн сайын бір көлік зақымданады. | roads | other | kk / question |  |
| probe2-roads-24 | У школы и фонари не горят, и на дороге яма, но больше всего просим заделать яму — машины резко тормозят прямо у перехода. | roads | lighting | ru / colloquial | несколько проблем → о чём просят |
| probe2-sidewalks-09 | trotuar u shkoly ves' razbit, plitka provalilas', deti spotykayutsya | sidewalks | other | ru / translit |  |
| probe2-sidewalks-10 | Zhayau zholdagy plitkalar synyp, oryndarynan koterilip ketken | sidewalks | other | kk / translit |  |
| probe2-sidewalks-11 | на тратуаре возле садика огромная дыра ,закрыта только картонкой | sidewalks | other | ru / typos |  |
| probe2-sidewalks-16 | Құрметті әкімдік, Жұбанов көшесіндегі жерасты өткелінің баспалдақтары бұзылған, кейбір тақталары жоқ. Жөндеу жұмыстарын жүргізуді сұраймыз. | sidewalks | noise_safety | kk / official |  |
| probe2-sidewalks-17 | От остановки до дома идём по грязи, потому что тротуар так и не доделали после прокладки кабеля | sidewalks | transport | ru / colloquial |  |
| probe2-sidewalks-20 | Переход астындағы лестница сломана, қарттар түсе алмайды | sidewalks | snow_ice | mixed / colloquial |  |
| probe2-sidewalks-23 | После дождя на тротуаре у остановки такая лужа, что обходить приходится по газону | sidewalks | transport | ru / colloquial | лужа на тротуаре → sidewalks |
| probe2-sidewalks-24 | Застройщик огородил территорию прямо по пешеходной части, обойти можно только по дороге, где ездят самосвалы. | sidewalks | roads | ru / colloquial | проход перекрыт стройкой → sidewalks |
| probe2-sidewalks-25 | Өткелдің астын су басып қалды, аяқ киімді суламай өту мүмкін емес, опять затопило | sidewalks | noise_safety | mixed / colloquial | вода в переходе → sidewalks |
| probe2-smell_air-07 | Опять кто-то включил «аромат» с очистных, на балконе как в туалете, спасибо, блин | smell_air | other | ru / slang |  |
| probe2-smell_air-09 | kazhduyu noch' pakhnet khimiey so storony promzony, golova bolit | smell_air | other | ru / translit |  |
| probe2-smell_air-10 | Qurylystan shan kop, terezeni ashsaq bari shanga tolady | smell_air | other | kk / translit | пыль от стройки → smell_air |
| probe2-smell_air-12 | на улице сильно пахнет газом возле трубы у забора , страшно | smell_air | other | ru / typos | газ на улице → smell_air |
| probe2-smell_air-13 | кошеде сасык ийис, шыдауга болмайды, кешке кушейеди | smell_air | other | kk / typos |  |
| probe2-smell_air-16 | Құрметті әкімдік! Көктемнен бері ауданымызда кәріз тазалау станциясының иісі сезіледі, әсіресе түнде. Бұл мәселені зерттеп, шешуді сұраймыз. | smell_air | utilities | kk / official |  |
| probe2-smell_air-17 | От асфальтового завода у трассы такой запах битума, что голова кружится | smell_air | roads | ru / colloquial |  |
| probe2-snow_ice-09 | u nas na ulitse Pushkina trotuar ves' vo l'du, babushki boyatsya vyhodit' | snow_ice | other | ru / translit | снег на тротуаре → snow_ice |
| probe2-snow_ice-10 | Mektep aldynda qar uiilip zhatyr, balalar zholdyn ortasymen zhuredi | snow_ice | other | kk / translit |  |
| probe2-snow_ice-13 | аулада кар тазаланбаган бир апта болды, машинаны шыгара алмаймыз | snow_ice | yards | kk / typos |  |
| probe2-snow_ice-17 | Площадку у подъезда завалило, дворник появляется раз в неделю, без лопаты не пройти | snow_ice | yards | ru / colloquial |  |
| probe2-snow_ice-22 | Неге біздің аялдаманың маңындағы қар тазаланбайды? Автобусқа жету қиын. | snow_ice | transport | kk / question | снег на остановке → snow_ice |
| probe2-snow_ice-24 | Горка на детской площадке вся обледенела, а вокруг сугробы — детям даже не подойти | snow_ice | yards | ru / colloquial | снег на площадке → snow_ice |
| probe2-transport-05 | Табло өшіп тұр | transport | other | kk / short |  |
| probe2-transport-07 | Водитель 12-го вообще без тормозов: закрыл двери перед носом и укатил, хотя я махала. Сервис уровня бог. | transport | other | ru / slang |  |
| probe2-transport-09 | avtobus 70 ne ostanavlivaetsya na ostanovke u kolledzha, proezzhaet mimo | transport | other | ru / translit |  |
| probe2-transport-10 | Ayaldamadagy tablo zhumys istemeidi, avtobus qashan keletinin bilmeimiz | transport | other | kk / translit |  |
| probe2-utilities-03 | Үйіміздің жертөлесінде құбыр жарылып, екі аптадан бері су тұр. Кіреберісте дымқыл, қабырғаларда зең пайда болды, сасық иіс бар. Басқарушы… | utilities | smell_air | kk / long | вонь из подвала → utilities |
| probe2-utilities-04 | опять без горячей | utilities | other | ru / short |  |
| probe2-utilities-06 | Лифт тағы сломался | utilities | other | mixed / short |  |
| probe2-utilities-07 | Лифт у нас работает по настроению: сегодня есть, завтра стоим на [адрес] и ждём чуда | utilities | other | ru / slang |  |
| probe2-utilities-09 | v nashem podezde lampochki ne menyali s leta, na lestnitse polnaya temnota | utilities | other | ru / translit | свет в подъезде → utilities |
| probe2-utilities-10 | Uide ystyq su zhoq, eshkim eshteme aitpaidy | utilities | other | kk / translit |  |
| probe2-utilities-11 | с потолка капает,крыша течёт после каждого дождя,уже обои отклеились | utilities | other | ru / typos |  |
| probe2-utilities-13 | лифт еки апта болды иштемейди, карттарга киын | utilities | other | kk / typos |  |
| probe2-utilities-14 | Прошу провести проверку качества теплоснабжения жилого дома по улице Шокана Валиханова [адрес]: температура в квартирах не соответствует … | utilities | other | ru / official |  |
| probe2-utilities-15 | Сообщаю об утечке воды из трубопровода в техническом подполье дома, вода поступает на придомовую территорию. | utilities | other | ru / official |  |
| probe2-utilities-16 | Құрметті әкімдік! Біздің үйде газ иісі шығады, кіреберісте әсіресе қатты сезіледі. Газ қызметін тез арада жіберуді сұраймыз. | utilities | smell_air | kk / official | газ в подъезде → utilities |
| probe2-utilities-17 | Из крана идёт ржавая вода, стирать невозможно, бельё всё жёлтое | utilities | other | ru / colloquial |  |
| probe2-utilities-18 | Кіреберістегі шамдар жанбайды, кешке баспалдақпен көтерілу қорқынышты | utilities | lighting | kk / colloquial | свет в подъезде → utilities |
| probe2-utilities-20 | Үйде свет өшіп қалды, вся улица без электричества с утра | utilities | other | mixed / colloquial | электричество в доме → utilities |
| probe2-utilities-22 | Неге біздің үйдегі лифт жиі бұзылады және оны кім жөндейді? | utilities | other | kk / question |  |
| probe2-utilities-23 | В подъезде пахнет газом, особенно внизу у почтовых ящиков, соседи тоже чувствуют | utilities | other | ru / colloquial | газ в подъезде → utilities |
| probe2-utilities-25 | Подъезде лампочки жоқ, қараңғы, кто-то упал на лестнице | utilities | lighting | mixed / colloquial | свет в подъезде → utilities |
| probe2-waste-09 | musor vo dvore ne vyvozyat s pyatnitsy, vse baki polnye | waste | other | ru / translit |  |
| probe2-waste-10 | Aulanyn burishinda ulken qoqys uiindisi paida boldy, eshkim alyp ketpeidi | waste | other | kk / translit |  |
| probe2-waste-16 | Құрметті әкімдік! Саябақтың кіреберісіндегі қоқыс жәшіктері күнделікті тазаланбайды, айналасы ластанып жатыр. | waste | smell_air | kk / official | переполненная урна в парке → waste |
| probe2-waste-17 | После выходных весь берег Есиля в бутылках и пакетах, кто-то же должен это убирать | waste | other | ru / colloquial |  |
| probe2-waste-25 | Свалка жанынан қатты иіс шығады, но главное — убрать саму свалку, ол балалар алаңының қасында | waste | smell_air | mixed / colloquial | несколько проблем → о чём просят |
| probe2-yards-09 | na detskoy ploshchadke u gorki otorvalsya bortik, ostrye kraya | yards | other | ru / translit |  |
| probe2-yards-10 | Aulada agashtar qurap qaldy, eshkim su quimaidy | yards | other | kk / translit |  |

## 5. Трудные случаи по правилам гайда (LABELING_GUIDE_v2)

Доля верных ответов на текстах probe_v2 с данным правилом; n — число таких текстов. Правила с n ≤ 2 показывают отдельные примеры, а не закономерность.

| Правило | n | `preds_probe_v2_synth_all_logreg` | `preds_probe_v2_synth_all_heuristic` |
|---|---|---|---|
| свет в подъезде → utilities | 3 | 67% | 0% |
| газ в подъезде → utilities | 2 | 50% | 0% |
| машины на газоне → parking | 2 | 50% | 0% |
| «зебра» → roads | 1 | 0% | 0% |
| снег на остановке → snow_ice | 1 | 0% | 0% |
| лужа на тротуаре → sidewalks | 1 | 100% | 0% |
| проход перекрыт стройкой → sidewalks | 1 | 0% | 0% |
| вода в переходе → sidewalks | 1 | 0% | 0% |
| электричество в доме → utilities | 1 | 100% | 0% |
| бездомные собаки → noise_safety | 1 | 100% | 0% |
| опасность от людей, а не от темноты → noise_safety | 1 | 0% | 100% |
| такси на остановке → parking | 1 | 100% | 0% |
| машины на дорожке → parking | 1 | 100% | 0% |
| благодарность о снеге → other | 1 | 100% | 0% |
| благодарность о дороге → other | 1 | 100% | 0% |
| благодарность о свете → other | 1 | 0% | 0% |
| вопрос о порядке без проблемы → other | 1 | 100% | 0% |
| благодарность об остановке → other | 1 | 100% | 0% |
| открытый люк → noise_safety | 4 | 50% | 25% |
| машина на тротуаре → parking | 4 | 75% | 25% |
| благодарность → other | 7 | 71% | 29% |
| несколько проблем → о чём просят | 3 | 33% | 33% |
| снег на тротуаре → snow_ice | 4 | 50% | 75% |
| яма во дворе → roads | 2 | 50% | 100% |
| вода на проезжей части → roads | 2 | 50% | 50% |
| снег на площадке → snow_ice | 2 | 50% | 50% |
| вопрос с проблемой → по проблеме | 2 | 50% | 100% |
| переполненная урна в парке → waste | 2 | 100% | 50% |
| вонь из подвала → utilities | 2 | 100% | 50% |
| газ на улице → smell_air | 2 | 50% | 50% |
| парковка на переходе → parking | 2 | 50% | 50% |
| пыль от стройки → smell_air | 3 | 67% | 67% |
| вопрос о сроках без проблемы → other | 3 | 67% | 67% |
| нет перехода → noise_safety | 4 | 75% | 75% |
| светофор → roads | 2 | 100% | 100% |
| лёд на остановке → snow_ice | 2 | 100% | 100% |
| скамейка на остановке → transport | 2 | 100% | 100% |
| свет на остановке → lighting | 2 | 100% | 100% |
| сломана скамейка в сквере → yards | 2 | 100% | 100% |
| мусор на остановке → waste | 2 | 100% | 100% |
| дым от сжигания → smell_air | 2 | 100% | 100% |
| лежачий полицейский → roads | 1 | 100% | 100% |
| снег на переходе/тротуаре → snow_ice | 1 | 100% | 100% |
| темно во дворе → lighting | 1 | 100% | 100% |
| темно в переходе → lighting | 1 | 100% | 100% |
| лужа на площадке → yards | 1 | 100% | 100% |
| сломана урна в парке → yards | 1 | 100% | 100% |
| канализация → utilities | 1 | 100% | 100% |
| дым от сжигания мусора → smell_air | 1 | 100% | 100% |
| запах от свалки → smell_air | 1 | 100% | 100% |
| вопрос без проблемы → other | 1 | 100% | 100% |

## 6. Подсказка «Похоже на …»: доля предвыбора и его точность на probe_v2

R04 предвыбирает категорию жителю, если она не «Другое» и score ≥ порога модели (у итоговой — 0.3, подобран на синтетической validation). Точность — доля верных среди предвыбранных; житель всегда может сменить категорию. score не калиброван, на людях эти числа будут другими.

| Прогнозы | Порог | Доля текстов с предвыбором | Точность предвыбора | n |
|---|---|---|---|---|
| `preds_probe_v2_synth_all_logreg` | 0.3 | 88% | 81% | 300 |
| `preds_probe_v2_synth_all_logreg` | 0.5 | 83% | 84% | 300 |
| `preds_probe_v2_synth_all_logreg` | 0.7 | 75% | 89% | 300 |
| `preds_probe_v2_synth_all_logreg` | 0.9 | 64% | 93% | 300 |

