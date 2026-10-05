# K09-1. Проверка библиографии A13 / AST-A13

Исполнитель: K09 (Claude Code), ветка `claude/save-work-handoff-qho6eq`.
Проверка проводилась 2026-10-05, 05:20–05:45 UTC.
Входные материалы:
- `research/govtech-results/13_architecture_ai_thesis/extracted_files__21_/A13_report.md` (§7) и `A13_evidence.json` (A13-L001…L012);
- `research/astana-results/13_architecture_ai_thesis/extracted_files__34_/AST_A13_report.md` (§6), `AST_A13_evidence.json` (AST-A13-L01…L12) и `SHA256SUMS.txt`.

## 0. Доступ к источникам

Сначала я проверил доступ к научным источникам одним запросом на каждый хост. Повторных попыток не делал.

| Хост | Результат (2026-10-05 UTC) |
|---|---|
| api.crossref.org, doi.org, export.arxiv.org | `403` на CONNECT; прокси пишет `connect_rejected` («policy denial») |
| api.openalex.org, api.semanticscholar.org, www.semanticscholar.org, scholar.archive.org, zenodo.org | то же |
| joss.theoj.org, openresearchsoftware.metajnl.com, sesmo.org, www.rand.org, aclanthology.org, proceedings.mlr.press, proceedings.neurips.cc | то же |
| dl.acm.org, onlinelibrary.wiley.com, www.sciencedirect.com, www.tandfonline.com, link.springer.com | то же |
| github.com (анонимное чтение публичных репозиториев через git) | **доступен** |
| pypi.org | доступен; для проверки не понадобился |

Ограничения я не обходил. Инструменты WebSearch/WebFetch есть в сессии, но ими я не пользовался: их вызов к заблокированным издательским сайтам был бы обходом политики сети, которую вы просили соблюдать.

Отсюда следствие: **ни одна статья не проверена у издателя или по DOI.** Всё ниже подтверждено только файлами из репозиториев авторов на GitHub. Файлы получены на закреплённых коммитах, команды в `scripts/fetch_bib_sources.sh`, хэши в `sources/SHA256SUMS.txt`.

## 1. Уровни проверки

| Уровень | Что значит | Что НЕ значит |
|---|---|---|
| **R0** | В этой сессии не подтверждено. Есть только упоминание агента или кандидат «из памяти» | Не значит, что работы нет |
| **R1** | Работа есть в списке литературы другого источника (README соавторов ПО, список литературы прочитанной статьи) | Не подтверждает содержание; точность ограничена точностью цитирующего |
| **R2** | Выходные данные взяты из файла, который ведут сами авторы (CITATION.cff, BibTeX в README) | Содержание статьи не прочитано |
| **R3** | Прочитано авторское резюме (abstract или описание работы в README) | Полный текст не прочитан |
| **R4** | Прочитан текст статьи; указаны версия и прочитанные разделы | Не гарантирует совпадение с финальной издательской версией, если читался препринт |

## 2. Сверка с хэшами AST-A13

AST-A13 хэшировал 16 файлов. Я независимо получил те же файлы с GitHub. **Все 13 общих файлов совпали по SHA-256 побайтно** (сверку можно повторить скриптом `scripts/compare_with_ast_a13.py`). Три файла AST-A13 я не получал, потому что они не нужны для библиографии: `SALib README.rst`, `UDST/urbansim README.rst`, `explodinggradients/ragas README.md`.

Отсюда следует две вещи:
- файлы, на которые ссылается AST-A13, существуют и не выдуманы;
- выводы AST-A13 об их содержании нужно проверять построчно. В двух местах вывод не подтверждается: см. §4.

## 3. Таблица работ

Колонка «Тема» связывает работу с темами диплома в `02_thesis_topics.md` (если файл уже создан): **Т1** — поручение → ограничения (ru/kk); **Т2** — устойчивость рекомендаций портфеля мер; **Т3** — перенос индикатора доступности между городами. Колонка «Где подтверждено» указывает файл и строки на закреплённом коммите (см. `sources/SHA256SUMS.txt`).

### 3.1. Устойчивые решения, исследовательское моделирование, чувствительность (Т2)

| ID | Работа | Уровень | Где подтверждено | Примечания |
|---|---|---|---|---|
| K09-L01 | Kwakkel J. (2017). The Exploratory Modeling Workbench: An open source toolkit for exploratory modeling, scenario discovery, and (multi-objective) robust decision making. *Environmental Modelling & Software* 96:239–250. doi:10.1016/j.envsoft.2017.06.054 | **R2** | `quaquel/EMAworkbench@3798b37` `CITATION.cff` стр. 9–21 | Полное название есть только в CITATION.cff, у A13/AST-A13 оно сокращено. Текст не читан |
| K09-L02 | Hadka D., Herman J., Reed P.M., Keller K. (2015). An Open Source Framework for Many-Objective Robust Decision Making. *EMS* 74:114–129. doi:10.1016/j.envsoft.2015.07.014 | **R2** | `Project-Platypus/Rhodium@1c09159` `README.md` стр. 141–143 (ref. 4) | Hadka — автор Rhodium, поэтому источник авторский. Текст не читан |
| K09-L03 | Hadjimichael A. et al. (2020). Rhodium: Python Library for Many-Objective Robust Decision Making and Exploratory Modeling. *Journal of Open Research Software* 8:12. doi:10.5334/jors.293 | **R2** | Rhodium `README.md` стр. 14–17, 144–145 | В README есть ссылка на PDF в par.nsf.gov; я её не открывал, домен не проверялся |
| K09-L04 | Lempert R.J., Groves D.G., Popper S.W., Bankes S.C. (2006). A General, Analytic Method for Generating Robust Strategies and Narrative Scenarios. *Management Science* 52(4):514–528 | **R1** | Rhodium `README.md` стр. 136–137 (ref. 2) | DOI в цитате нет. Это базовая работа по RDM; её нет в списках A13/AST-A13 |
| K09-L05 | Kasprzyk J.R., Nataraj S., Reed P.M., Lempert R.J. (2013). Many objective robust decision making for complex environmental systems undergoing change. *EMS* 42:55–71 | **R1** | Rhodium `README.md` стр. 138–140 (ref. 3) | DOI в цитате нет |
| K09-L06 | Bankes S. (1993). [название в источнике не указано], ссылка JSTOR `stable/10.2307/171847` | **R1, неполно** | EMAworkbench `README.md` стр. 9 | В источнике есть только «Bankes, 1993» и ссылка. Название, журнал и страницы я **не подтвердил** |
| K09-L07 | Herman J., Usher W. (2017). SALib: An open-source Python library for Sensitivity Analysis. *JOSS* 2(9). doi:10.21105/joss.00097 | **R4** (исходник JOSS) | `SALib/SALib@c8b2be5` `paper/paper.md` (весь текст, 51 строка); выходные данные: `CITATIONS.rst` стр. 10–12 | Статья JOSS состоит из одного раздела Summary, и он прочитан целиком. Опубликованный PDF с исходником не сверялся. **Несогласованность:** в `CITATION.cff` (стр. 3–15) с этим DOI указаны три автора (Iwanaga, Usher, Herman), а в `paper.md` и `CITATIONS.rst` — два |
| K09-L08 | Iwanaga T., Usher W., Herman J. (2022). Toward SALib 2.0: Advancing the accessibility and interpretability of global sensitivity analyses. *Socio-Environmental Systems Modelling* 4. doi:10.18174/sesmo.18155 | **R2** | SALib `CITATION.cff` стр. 18–38; `CITATIONS.rst` стр. 6–9 | Страницы расходятся: в CFF 1–15, в RST номер статьи 18155. Текст не читан |
| K09-L09 | Lempert R., Popper S., Bankes S. (2003). Shaping the Next One Hundred Years. RAND MR-1626 | **R0** | — | rand.org заблокирован; в доступных авторских файлах работа не найдена |

### 3.2. Перевод текста в оптимизационную модель, LLM с программами (Т1)

| ID | Работа | Уровень | Где подтверждено | Примечания |
|---|---|---|---|---|
| K09-L10 | Ramamonjison R., Yu T., Li R., Li H., Carenini G., Ghaddar B., He S., Mostajabdaveh M., Banitalebi-Dehkordi A., Zhou Z., Zhang Y. NL4Opt Competition: Formulating Optimization Problems Based on Their Natural Language Descriptions. *Proc. NeurIPS 2022 Competitions Track*, PMLR 220:189–203 | **R2** | `nl4opt/nl4opt-competition@49f1e0d` `README.md` стр. 28–41 | В BibTeX указан `year = 2022`, в URL — `ramamonjison23a`. Цитировать как PMLR v220. **arXiv:2303.08233 из A13-L011 в авторских файлах не найден (R0)** |
| K09-L11 | Ramamonjison R. et al. (2022). Augmenting Operations Research with Auto-Formulation of Optimization Models From Problem Descriptions. *EMNLP 2022 Industry Track*, pp. 29–62 | **R2** | NL4Opt `README.md` стр. 43–53 | Новая работа, которой нет у A13. Автор в BibTeX записан как «Ramamonjison et al,.», остальные авторы не перечислены |
| K09-L12 | AhmadiTeshnizi A., Gao W., Udell M. OptiMUS. v0.1 arXiv:2310.06116 (2023); v0.2 «Scalable Optimization Modeling with (MI)LP Solvers and LLMs», arXiv:2402.10172 (2024); v0.3 «OptiMUS-0.3…», arXiv:2407.19633 (2024; добавлены Brunborg H., Talaei S.) | **R2** | `teshnizi/OptiMUS@59e8d99` `README.md` стр. 7–11, 29–57 | Это подтверждает поправку AST-A13 о версиях. **Лицензия набора NLP4LP — CC BY-NC 4.0, только для исследований** (README стр. 21); для GovTech-продукта его использовать нельзя |
| K09-L13 | Gao L., Madaan A., Zhou S., Alon U., Liu P., Yang Y., Callan J., Neubig G. (2022). PAL: Program-aided Language Models. arXiv:2211.10435 | **R2** | `reasoning-machines/pal@f81ca2a` `CITATION.cff` стр. 1–6 | Файл назван CITATION.cff, но внутри BibTeX, а не формат CFF. Площадка публикации (не arXiv) в авторских файлах не указана |

### 3.3. Проверяемость и безопасность LLM (Т1, а также объяснения советника)

| ID | Работа | Уровень | Где подтверждено | Примечания |
|---|---|---|---|---|
| K09-L14 | Gao T., Yen H., Yu J., Chen D. (2023). Enabling Large Language Models to Generate Text with Citations. *EMNLP 2023*; arXiv:2305.14627 | **R4, частично** (препринт) | `princeton-nlp/ALCE@246c476` `paper/ALCE.pdf` (23 с., PDF создан 2023-05-24); площадка EMNLP — по `README.md` стр. 171–177 | **Прочитаны:** аннотация, §1, §2, §3.1–3.4, §4.1–4.3, фрагмент §6 о согласии с людьми, §8. **Не прочитаны полностью:** §5 (результаты) и приложения. Читался препринт; с версией EMNLP не сверялся. Подробности ниже |
| K09-L15 | Ji Z., Lee N., Frieske R., Yu T., Su D., Xu Y., Ishii E., Bang Y.J., Madotto A., Fung P. (2023). Survey of hallucination in natural language generation. *ACM Computing Surveys* 55(12):1–38 | **R1** | Список литературы ALCE.pdf (раздел References, с. 12 PDF) | Это подтверждает выходные данные A13-L009. Текст не читан |
| K09-L16 | Greshake K., Abdelnabi S., Mishra S., Endres C., Holz T., Fritz M. (2023). arXiv:2302.12173. Название в авторском BibTeX: **«More than you've asked for: A Comprehensive Analysis of Novel Prompt Injection Threats to Application-Integrated Large Language Models»** | **R2** (id, авторы, год); **R3** (авторское описание в README) | `greshake/llm-security@c312325` `README.md` стр. 150–161 (BibTeX); стр. 6–7, 23–25 (описание) | A13-L010 и AST-A13-L08 называют работу «Not what you've signed up for…». В авторских файлах **этого названия нет**: см. §4 |
| K09-L17 | Lewis P. et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. arXiv:2005.11401 | **R0** | — | Работы нет в авторских файлах и в списке литературы ALCE. AST-A13 тоже исключил её из своего списка |

### 3.4. Сетевой анализ и доступность (Т3)

| ID | Работа | Уровень | Где подтверждено | Примечания |
|---|---|---|---|---|
| K09-L18 | Boeing G. (2025). Modeling and Analyzing Urban Networks and Amenities with OSMnx. *Geographical Analysis* 57(4):567–577. doi:10.1111/gean.70009 | **R2** | `gboeing/osmnx@74e68ce` `CITATION.cff` стр. 9–12, 19–32 | Текст не читан |
| K09-L19 | Fink C., Klumpenhouwer W., Saraiva M., Pereira R., Tenkanen H. (2022). r5py: Rapid Realistic Routing with R5 in Python. doi:10.5281/zenodo.7060437 | **R2** (ПО) | `r5py/r5py@59c97d0` `README.md` стр. 60–64; `docs/_static/references.bib` стр. 69–76 | Это программа, а не статья. AST-A13-L12 указывает её без авторов и года, здесь они дополнены |
| K09-L20 | Conway M.W., Byrd A., van der Linden M. (2017). Evidence-Based Transit and Land Use Sketch Planning Using Interactive Accessibility Methods on Combined Schedule and Headway-Based Networks. *Transportation Research Record* 2653(1):45–53. doi:10.3141/2653-06 | **R1** | r5py `references.bib` стр. 36–45; `docs/user-guide/citation.md` стр. 14–23 | Описывает методику движка R5. Текст не читан |
| K09-L21 | Conway M.W., Byrd A., van Eggermond M. (2018). Accounting for uncertainty and variation in accessibility metrics for public transport sketch planning. *Journal of Transport and Land Use* 11(1). doi:10.5198/jtlu.2018.1074 | **R1** | r5py `references.bib` стр. 25–33 | Неопределённость в метриках доступности напрямую относится к Т2 и Т3. Текст не читан |
| K09-L22 | Conway M.W., Stewart A.F. (2019). Getting Charlie off the MTA: a multiobjective optimization method to account for cost constraints in public transit accessibility metrics. *IJGIS* 33(9):1759–1787. doi:10.1080/13658816.2019.1605075 | **R1** | r5py `references.bib` стр. 12–22 | Текст не читан |
| K09-L23 | Salonen M., Toivonen T. (2013). Modelling travel time in urban networks: comparable measures for private car and public transport. *Journal of Transport Geography* 31:143–153. doi:10.1016/j.jtrangeo.2013.06.011 | **R1** | r5py `references.bib` стр. 102–111 | О сопоставимости метрик между видами транспорта; методически близко к Т3. Текст не читан |

### 3.5. GIS-MCDA и системы поддержки планирования — главный пробел

| ID | Работа | Уровень | Примечания |
|---|---|---|---|
| K09-L24 | Malczewski J. (2006). GIS-based multicriteria decision analysis: a survey of the literature. *IJGIS* 20(7). doi:10.1080/13658810600661508 | **R0** | Издатель, doi.org и Crossref заблокированы. Авторских репозиториев нет |
| K09-L25 | Malczewski J., Rinner C. (2015). *Multicriteria Decision Analysis in Geographic Information Science*. Springer | **R0** | То же |
| K09-L26 | Geertman S., Stillwell J. (2004). Planning support systems: an inventory of current practice. *CEUS* 28(4) | **R0** | То же |
| K09-L27 | Vonk G., Geertman S., Schot P. (2005). Bottlenecks blocking widespread usage of planning support systems. *Environment and Planning A* 37(5) | **R0** | То же |

Обзорная глава диплома (GIS-MCDA и PSS) сейчас **не опирается ни на одну проверенную работу.** Без проверки этих четырёх работ нельзя утверждать, что тема новая или связана с литературой о «разрыве внедрения» PSS.

## 4. Расхождения с отчётами A13 / AST-A13

1. **Greshake et al. (K09-L16).** AST-A13-L08 пишет: «Not what you've signed up for… — подтверждено: README greshake/llm-security, BibTeX». Файл README побайтно совпадает с хэшем AST-A13, но BibTeX в нём (стр. 150–161) содержит другое название: «More than you've asked for: A Comprehensive Analysis of Novel Prompt Injection Threats to Application-Integrated Large Language Models». Заголовок README (стр. 3) — «Compromising LLMs using Indirect Prompt Injection». Из этого файла подтверждаются только arXiv:2302.12173, авторы и год. Название «Not what you've signed up for…» и возможная публикация на конференции в этой сессии **не подтверждены (R0)**. Перед цитированием нужно открыть arXiv и посмотреть историю версий.
2. **NL4Opt (K09-L10).** A13-L011 даёт arXiv:2303.08233 (2023), AST-A13 даёт PMLR 220:189–203. Авторский README подтверждает только PMLR. Номер arXiv не подтверждён.
3. **SALib JOSS (K09-L07).** AST-A13-L05 пишет «Herman J., Usher W. … подтверждено: CITATION.cff». В `CITATION.cff` с этим DOI указаны три автора, и это запись о программе. Два автора статьи подтверждаются в `paper/paper.md` и `CITATIONS.rst`. Вывод AST-A13 верен, но указан не тот файл.
4. **Уровень чтения AST-A13.** Все 12 работ AST-A13 помечены как `metadata_verified_author_repo_fulltext_not_read`. Это соответствует R2, местами R1–R3. Утверждение резюме «библиографию 12 работ подтвердил» верно для выходных данных и не распространяется на содержание. Исключение — ALCE: в репозитории авторов лежит PDF препринта (`paper/ALCE.pdf`), но AST-A13 его не прочитал.

## 5. Что взято из полного текста ALCE (K09-L14) для протоколов

Цитаты взяты из препринта `paper/ALCE.pdf` (`princeton-nlp/ALCE@246c476`, sha256 `e10e1dac…`). Ниже то, что пригодится для метрик Т1 и проверки объяснений.

- **Citation recall** (с. 5, §3.3). Утверждение s_i получает 1, если у него есть хотя бы одна ссылка и NLI-модель признаёт, что конкатенация процитированных фрагментов влечёт s_i. Итог усредняется по утверждениям ответа.
- **Citation precision** (с. 5, §3.3). Ссылка c_ij «нерелевантна», если она сама не поддерживает s_i, а без неё остальные ссылки поддерживают s_i. Авторы оговаривают, что частичная поддержка при этом штрафуется ошибочно.
- **Согласие с людьми** (с. 10, §6). Коэффициент Коэна κ = 0.698 для citation recall и 0.525 для citation precision. Точность автоматической метрики против человеческой разметки — 85.1 % и 77.6 % соответственно.
- **Масштаб проблемы** (с. 1, аннотация). На ELI5 даже у лучшей модели 49 % ответов не имеют полной поддержки ссылками.
- **Важное для нас ограничение.** ALCE проверяет поддержку утверждений **текстовыми фрагментами** с помощью англоязычной NLI-модели (TRUE, T5-11B; с. 5). Для советника STUPITS, где числа приходят из отчёта движка, а ответы на русском и казахском, метрику нужно адаптировать: «поддержка» = совпадение числа или утверждения с полем evidence, а не NLI. Переносимость англоязычной NLI на ru/kk в ALCE не изучалась.

Это наблюдения из текста статьи, а не результаты нашего эксперимента.

## 6. Минимум, без которого обзор литературы не готов

1. Открыть doi.org, Crossref или arXiv, либо получить от владельца PDF или ссылки. Проверить K09-L24…L27 (GIS-MCDA и PSS), K09-L04 (Lempert 2006) и K09-L16 (название и версия Greshake).
2. Прочитать хотя бы аннотации K09-L01, L02, L08, L10, L12, L18. Сейчас по ним известны только выходные данные.
3. Найти 2–3 работы о многокритериальном выборе в городском планировании с применением в городах Центральной Азии или похожих постсоветских городах. Сейчас таких нет ни одной.
