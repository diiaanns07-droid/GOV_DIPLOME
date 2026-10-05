"""K09: сборка K09_evidence.json из явно записанных записей (без сети).

Запуск из корня репозитория: python3 research/next-round/K09/scripts/build_evidence.py
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "K09_evidence.json"
ACC = "2026-10-05"
BLOCKED = ("api.crossref.org, doi.org, export.arxiv.org, api.openalex.org, api.semanticscholar.org, "
           "www.semanticscholar.org, scholar.archive.org, zenodo.org, joss.theoj.org, "
           "openresearchsoftware.metajnl.com, sesmo.org, www.rand.org, aclanthology.org, proceedings.mlr.press, "
           "proceedings.neurips.cc, dl.acm.org, onlinelibrary.wiley.com, www.sciencedirect.com, "
           "www.tandfonline.com, link.springer.com")

def repo_src(sid, repo, sha, files, note):
    return {"source_id": sid, "title": f"{repo} — авторские файлы ({', '.join(files)})",
            "publisher": repo.split('/')[0], "url": f"https://github.com/{repo}/tree/{sha}",
            "published_at": None, "accessed_at": ACC, "source_type": "author_repository",
            "access_status": "fetched_pinned_commit", "notes": note}

sources = [
    {"source_id": "K09-S001", "title": "Проверка доступа к научным хостам (agent proxy status)",
     "publisher": "среда Claude Code", "url": None, "published_at": None, "accessed_at": ACC,
     "source_type": "access_log", "access_status": "blocked_by_policy",
     "notes": "Один запрос на хост, 05:20–05:22 UTC; прокси: connect_rejected / 403 для: " + BLOCKED +
              ". Доступны github.com (анонимное чтение публичных репозиториев) и pypi.org. Повторов нет; WebSearch/WebFetch не использовались."},
    repo_src("K09-S002", "quaquel/EMAworkbench", "3798b375bc4208356a74432e67040f38c6cf75a5", ["CITATION.cff", "README.md"], "sha256 в sources/SHA256SUMS.txt; совпадают с AST-A13"),
    repo_src("K09-S003", "Project-Platypus/Rhodium", "1c09159c5b06fc0784ecfe13383c7a06a611d4e1", ["README.md"], "References стр. 133–145"),
    repo_src("K09-S004", "SALib/SALib", "c8b2be52a136d861caf4b1e53a4dae2e036ee390", ["CITATION.cff", "CITATIONS.rst", "paper/paper.md", "paper/codemeta.json"], "paper.md — исходный текст статьи JOSS"),
    repo_src("K09-S005", "gboeing/osmnx", "74e68ce2200b23c04f6ec2a864a6c24859bbf08d", ["CITATION.cff", "README.md"], ""),
    repo_src("K09-S006", "princeton-nlp/ALCE", "246c476a4edfc564266b7346b6e29ef4861ae937", ["README.md", "paper/ALCE.pdf"], "ALCE.pdf: 23 с., CreationDate 2023-05-24 (препринт); sha256 e10e1dacb25804558e6e801e331589ade47e0d9612f8e12ad1ba820f0b0021e8"),
    repo_src("K09-S007", "greshake/llm-security", "c312325bee5f16d8f6524bd6f41e1510c5623a1e", ["README.md"], "BibTeX стр. 150–161"),
    repo_src("K09-S008", "nl4opt/nl4opt-competition", "49f1e0d66b7fdcd33305a7f281c2a7c13f5620ea", ["README.md"], "BibTeX стр. 28–53"),
    repo_src("K09-S009", "teshnizi/OptiMUS", "59e8d99653459b40361f618eafdc91eee3a85ebb", ["README.md"], "версии стр. 7–11; лицензия NLP4LP стр. 21"),
    repo_src("K09-S010", "reasoning-machines/pal", "f81ca2a9777f002f98a6b4d0f10b61bd5c8feb02", ["CITATION.cff", "README.md"], "CITATION.cff фактически BibTeX"),
    repo_src("K09-S011", "r5py/r5py", "59c97d0a65f9b0dfd9488d0084613c96e0d92c45", ["README.md", "docs/user-guide/citation.md", "docs/_static/references.bib"], ""),
]

# Литература: (id, ссылка, уровень, source_ref, locator, origin_ids, notes)
L = [
 ("K09-L01", "Kwakkel J. (2017) The Exploratory Modeling Workbench… EMS 96:239–250. doi:10.1016/j.envsoft.2017.06.054", "R2", "K09-S002", "CITATION.cff стр. 9–21", ["A13-L006", "AST-A13-L01"], "текст не читан"),
 ("K09-L02", "Hadka D., Herman J., Reed P.M., Keller K. (2015) An Open Source Framework for Many-Objective Robust Decision Making. EMS 74:114–129. doi:10.1016/j.envsoft.2015.07.014", "R2", "K09-S003", "README.md стр. 141–143", ["AST-A13-L02"], "текст не читан"),
 ("K09-L03", "Hadjimichael A. et al. (2020) Rhodium… JORS 8:12. doi:10.5334/jors.293", "R2", "K09-S003", "README.md стр. 14–17, 144–145", ["AST-A13-L03"], "PDF par.nsf.gov не открывался"),
 ("K09-L04", "Lempert R.J., Groves D.G., Popper S.W., Bankes S.C. (2006) A General, Analytic Method for Generating Robust Strategies and Narrative Scenarios. Management Science 52(4):514–528", "R1", "K09-S003", "README.md стр. 136–137", [], "DOI не указан; новая для списка A13"),
 ("K09-L05", "Kasprzyk J.R., Nataraj S., Reed P.M., Lempert R.J. (2013) Many objective robust decision making for complex environmental systems undergoing change. EMS 42:55–71", "R1", "K09-S003", "README.md стр. 138–140", [], "DOI не указан"),
 ("K09-L06", "Bankes S. (1993), JSTOR stable/10.2307/171847 (название не указано в источнике)", "R1_incomplete", "K09-S002", "README.md стр. 9", [], "название/журнал не подтверждены"),
 ("K09-L07", "Herman J., Usher W. (2017) SALib: An open-source Python library for Sensitivity Analysis. JOSS 2(9). doi:10.21105/joss.00097", "R4", "K09-S004", "paper/paper.md (весь), CITATIONS.rst стр. 10–12", ["AST-A13-L05"], "прочитан исходник JOSS; CITATION.cff даёт 3 авторов для этого DOI — несогласованность"),
 ("K09-L08", "Iwanaga T., Usher W., Herman J. (2022) Toward SALib 2.0… SESMO 4. doi:10.18174/sesmo.18155", "R2", "K09-S004", "CITATION.cff стр. 18–38; CITATIONS.rst стр. 6–9", ["AST-A13-L04"], "страницы 1–15 vs номер статьи 18155"),
 ("K09-L09", "Lempert R., Popper S., Bankes S. (2003) Shaping the Next One Hundred Years. RAND MR-1626", "R0", None, None, ["A13-L005"], "rand.org заблокирован"),
 ("K09-L10", "Ramamonjison R. et al. NL4Opt Competition… Proc. NeurIPS 2022 Competitions Track, PMLR 220:189–203", "R2", "K09-S008", "README.md стр. 28–41", ["A13-L011", "AST-A13-L09"], "arXiv:2303.08233 из A13 не подтверждён"),
 ("K09-L11", "Ramamonjison R. et al. (2022) Augmenting Operations Research with Auto-Formulation of Optimization Models From Problem Descriptions. EMNLP 2022 Industry Track, 29–62", "R2", "K09-S008", "README.md стр. 43–53", [], "новая; полный список авторов не дан"),
 ("K09-L12", "AhmadiTeshnizi A., Gao W., Udell M. OptiMUS v0.1 arXiv:2310.06116; v0.2 arXiv:2402.10172; v0.3 arXiv:2407.19633 (+Brunborg, Talaei)", "R2", "K09-S009", "README.md стр. 7–11, 29–57", ["A13-L012", "AST-A13-L10"], "NLP4LP: CC BY-NC 4.0"),
 ("K09-L13", "Gao L. et al. (2022) PAL: Program-aided Language Models. arXiv:2211.10435", "R2", "K09-S010", "CITATION.cff стр. 1–6", ["AST-A13-L11"], ""),
 ("K09-L14", "Gao T., Yen H., Yu J., Chen D. (2023) Enabling Large Language Models to Generate Text with Citations. EMNLP; arXiv:2305.14627", "R4_partial_preprint", "K09-S006", "ALCE.pdf: аннотация, §1–§4.3, §6 (фрагмент), §8; README стр. 171–177", ["A13-L008", "AST-A13-L07"], "§5 и приложения не прочитаны полностью; сверки с версией EMNLP нет"),
 ("K09-L15", "Ji Z. et al. (2023) Survey of hallucination in natural language generation. ACM Computing Surveys 55(12):1–38", "R1", "K09-S006", "ALCE.pdf, References, с. 12", ["A13-L009"], ""),
 ("K09-L16", "Greshake K., Abdelnabi S., Mishra S., Endres C., Holz T., Fritz M. (2023) arXiv:2302.12173; название в авторском BibTeX: More than you've asked for: A Comprehensive Analysis of Novel Prompt Injection Threats to Application-Integrated Large Language Models", "R2", "K09-S007", "README.md стр. 150–161; описание стр. 6–7, 23–25", ["A13-L010", "AST-A13-L08"], "название «Not what you've signed up for…» не подтверждено (R0)"),
 ("K09-L17", "Lewis P. et al. (2020) Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. arXiv:2005.11401", "R0", None, None, ["A13-L007"], "нет в авторских файлах и в списке литературы ALCE"),
 ("K09-L18", "Boeing G. (2025) Modeling and Analyzing Urban Networks and Amenities with OSMnx. Geographical Analysis 57(4):567–577. doi:10.1111/gean.70009", "R2", "K09-S005", "CITATION.cff стр. 9–12, 19–32", ["AST-A13-L06"], "текст не читан"),
 ("K09-L19", "Fink C., Klumpenhouwer W., Saraiva M., Pereira R., Tenkanen H. (2022) r5py: Rapid Realistic Routing with R5 in Python. doi:10.5281/zenodo.7060437", "R2", "K09-S011", "README.md стр. 60–64; references.bib стр. 69–76", ["AST-A13-L12"], "ПО"),
 ("K09-L20", "Conway M.W., Byrd A., van der Linden M. (2017) Evidence-Based Transit and Land Use Sketch Planning… TRR 2653(1):45–53. doi:10.3141/2653-06", "R1", "K09-S011", "references.bib стр. 36–45", [], ""),
 ("K09-L21", "Conway M.W., Byrd A., van Eggermond M. (2018) Accounting for uncertainty and variation in accessibility metrics for public transport sketch planning. JTLU 11(1). doi:10.5198/jtlu.2018.1074", "R1", "K09-S011", "references.bib стр. 25–33", [], ""),
 ("K09-L22", "Conway M.W., Stewart A.F. (2019) Getting Charlie off the MTA… IJGIS 33(9):1759–1787. doi:10.1080/13658816.2019.1605075", "R1", "K09-S011", "references.bib стр. 12–22", [], ""),
 ("K09-L23", "Salonen M., Toivonen T. (2013) Modelling travel time in urban networks: comparable measures for private car and public transport. JTG 31:143–153. doi:10.1016/j.jtrangeo.2013.06.011", "R1", "K09-S011", "references.bib стр. 102–111", [], ""),
 ("K09-L24", "Malczewski J. (2006) GIS-based multicriteria decision analysis: a survey of the literature. IJGIS 20(7). doi:10.1080/13658810600661508", "R0", None, None, ["A13-L001"], "пробел GIS-MCDA"),
 ("K09-L25", "Malczewski J., Rinner C. (2015) Multicriteria Decision Analysis in Geographic Information Science. Springer", "R0", None, None, ["A13-L002"], ""),
 ("K09-L26", "Geertman S., Stillwell J. (2004) Planning support systems: an inventory of current practice. CEUS 28(4)", "R0", None, None, ["A13-L003"], ""),
 ("K09-L27", "Vonk G., Geertman S., Schot P. (2005) Bottlenecks blocking widespread usage of planning support systems. Environment and Planning A 37(5)", "R0", None, None, ["A13-L004"], ""),
]
for lid, ref, lvl, sref, loc, orig, note in L:
    sources.append({"source_id": lid, "title": ref, "publisher": None, "url": None, "published_at": None,
                    "accessed_at": ACC if sref else None, "source_type": "scientific_publication",
                    "access_status": f"verification_level_{lvl}",
                    "notes": "; ".join(x for x in [f"подтверждено через {sref} ({loc})" if sref else "в этой сессии не подтверждено",
                                                    ("ID в исходных отчётах: " + ", ".join(orig)) if orig else "", note] if x)})

def fact(fid, st, kind, refs, conf, cav="", value=None, unit=None, deriv=None):
    return {"fact_id": fid, "statement": st, "kind": kind, "value": value, "unit": unit,
            "geography": None, "period": None, "source_refs": refs, "derivation": deriv,
            "confidence": conf, "caveats": cav}

facts = [
 fact("K09-F001", "Научные и издательские хосты (Crossref, doi.org, arXiv, OpenAlex, Semantic Scholar, Zenodo, JOSS, RAND, ACL Anthology, PMLR, NeurIPS, ACM, Wiley, Elsevier, T&F, Springer) недоступны из среды K09 по политике сети.", "observed", [{"source_id": "K09-S001", "locator": "recentRelayFailures, 05:20–05:22 UTC"}], "high", "Статус среды на дату проверки; не свойство самих сайтов."),
 fact("K09-F002", "13 из 16 файлов из SHA256SUMS.txt AST-A13 получены K09 независимо и совпали по SHA-256; 3 файла K09 не получал.", "observed", [{"source_id": "K09-S002", "locator": "sources/SHA256SUMS.txt"}], "high", "Совпадение файлов не подтверждает интерпретацию их содержания в AST-A13.", 13, "files", "scripts/compare_with_ast_a13.py"),
 fact("K09-F003", "Авторский BibTeX для arXiv:2302.12173 называет работу «More than you've asked for: A Comprehensive Analysis of Novel Prompt Injection Threats to Application-Integrated Large Language Models»; название «Not what you've signed up for…», указанное в AST-A13-L08 как подтверждённое этим README, в файле отсутствует.", "observed", [{"source_id": "K09-S007", "locator": "README.md стр. 150–161"}], "high", "Возможна смена названия в поздних версиях arXiv — не проверено (arXiv заблокирован)."),
 fact("K09-F004", "Авторский README NL4Opt подтверждает PMLR 220:189–203 и не содержит arXiv:2303.08233 (A13-L011).", "observed", [{"source_id": "K09-S008", "locator": "README.md стр. 28–41"}], "high", ""),
 fact("K09-F005", "Набор NLP4LP (OptiMUS) распространяется по CC BY-NC 4.0 «only for research»; непригоден для коммерческого/продуктового использования без отдельного разрешения.", "observed", [{"source_id": "K09-S009", "locator": "README.md стр. 21"}], "high", "Лицензия по README; карточка на huggingface.co не открывалась."),
 fact("K09-F006", "ALCE: citation recall = доля утверждений, у которых есть ссылка и NLI признаёт вывод из конкатенации процитированных фрагментов; citation precision штрафует «нерелевантные» ссылки.", "observed", [{"source_id": "K09-S006", "locator": "ALCE.pdf §3.3, с. 5"}], "high", "Препринт 2023-05-24."),
 fact("K09-F007", "ALCE: согласие автоматической оценки с людьми — Cohen κ 0.698 (citation recall) и 0.525 (citation precision); точность 85.1 % и 77.6 %.", "observed", [{"source_id": "K09-S006", "locator": "ALCE.pdf §6, с. 10"}], "high", "Английский язык, NLI-модель TRUE; к ru/kk не переносится без проверки."),
 fact("K09-F008", "ALCE (аннотация): на ELI5 у лучшей модели 49 % генераций без полной поддержки цитатами.", "observed", [{"source_id": "K09-S006", "locator": "ALCE.pdf, аннотация, с. 1"}], "high", "Результат авторов на их данных 2023 г."),
 fact("K09-F009", "Ни одна работа по GIS-MCDA и системам поддержки планирования (Malczewski 2006; Malczewski & Rinner 2015; Geertman & Stillwell 2004; Vonk et al. 2005) в этой сессии не подтверждена.", "observed", [{"source_id": "K09-S001", "locator": "все издательские хосты заблокированы"}], "high", "Отсутствие проверки ≠ отсутствие работ."),
 fact("K09-F010", "В SALib CITATION.cff с DOI JOSS 10.21105/joss.00097 указаны три автора (Iwanaga, Usher, Herman), а в исходнике статьи paper/paper.md и в CITATIONS.rst — два (Herman, Usher).", "observed", [{"source_id": "K09-S004", "locator": "CITATION.cff стр. 3–15; paper/paper.md стр. 11–17; CITATIONS.rst стр. 10–12"}], "high", "Для цитирования статьи использовать двух авторов."),
]

doc = {
 "meta": {"agent_id": "K09", "topic": "Проверяемая научная основа диплома: библиография A13/AST-A13 и узкие темы",
          "city": "shared (Шымкент и Астана; данных городов в этом этапе нет)", "searched_at": "2026-10-05T05:20:00Z",
          "access_limitations": "Все научные и издательские хосты отклонены политикой сети (см. K09-S001). Использованы только публичные репозитории авторов на GitHub на закреплённых коммитах.",
          "stage": "1 — проверка библиографии", "branch": "claude/save-work-handoff-qho6eq",
          "verification_levels": {"R0": "не подтверждено", "R1": "в списке литературы другого источника", "R2": "метаданные в авторском файле", "R3": "прочитано авторское резюме", "R4": "прочитан текст (версия и разделы указаны)"}},
 "sources": sources, "facts": facts, "datasets": [], "opportunities": [],
 "open_questions": [
   {"question": "Каково актуальное название и место публикации arXiv:2302.12173 (Greshake et al.)?", "why": "AST-A13 указал название, не подтверждаемое авторским файлом", "how": "Открыть arxiv.org/abs/2302.12173 и историю версий при разрешённом доступе"},
   {"question": "Существуют ли и что содержат Malczewski 2006, Geertman & Stillwell 2004, Vonk et al. 2005?", "why": "Без них нет обзорной главы по GIS-MCDA/PSS", "how": "Crossref/doi.org или PDF от владельца"},
   {"question": "Совпадает ли препринт ALCE (2023-05-24) с версией EMNLP 2023 в определениях метрик?", "why": "Метрики citation recall/precision используются в протоколе", "how": "Сверить с aclanthology.org при доступе"}],
 "deliverables": {"files": ["research/next-round/K09/01_bibliography_verification.md", "research/next-round/K09/K09_evidence.json",
                            "research/next-round/K09/sources/SHA256SUMS.txt", "research/next-round/K09/scripts/fetch_bib_sources.sh",
                            "research/next-round/K09/scripts/compare_with_ast_a13.py", "research/next-round/K09/scripts/build_evidence.py"],
                  "not_committed": "Копии файлов авторов (README, CITATION, ALCE.pdf) не добавлены в репозиторий из-за лицензий; их можно воспроизвести скриптом fetch_bib_sources.sh и проверить по SHA256SUMS.txt."},
}
OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"written {OUT} sources={len(sources)} facts={len(facts)}")
