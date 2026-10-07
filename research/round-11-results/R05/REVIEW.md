# R05 — независимая adversarial-проверка пакета (раунд 11)

Метод: workflow из 5 искателей (контракт, происхождение, сборка/импорт R02, даты, безопасность) и 5 скептиков,
каждый из которых сам повторял воспроизведение и пытался опровергнуть находку. Проверяемое дерево: e4ab1ff.
Агенты не меняли файлы репозитория; исправления внесены после проверки, с регрессионными тестами
(`tests/civic/R05/test_review_regressions.py`, обновлённые `test_import_helper.py`).

| Измерение | Находок | Подтверждено | Опровергнуто |
|---|---|---|---|
| contract | 12 | 10 | 2 |
| provenance | 8 | 6 | 2 |
| pipeline | 7 | 5 | 2 |
| dates | 6 | 6 | 0 |
| security | 7 | 6 | 1 |
| **итого** | 40 | 33 | 7 |

## contract

Исправления: civic_v1.py: guarded hashing/.get on wrong types, OverflowError-safe numbers, urlparse errors -> issue, Astana-time date comparison, R05 policies = warnings in contract profile, label-based proprietary host match, coarse field paths accepted in contract profile, full HTML entity/tag-opener check, polygon zero-area and hole-outside-shell checks.

- **FIXED** [medium] Contract profile crashes (TypeError) when budget.source_id is a list or object
- **FIXED** [low] OverflowError on large JSON integers in amount_kzt or geometry coordinates
- **FIXED** [low] source_refs[].url with a bracketed host makes urlparse raise ValueError
- **FIXED** [medium] validate_collection (and so the CLI) crashes when kind is a list or object
- **FIXED** [medium] real/demo profiles crash on wrong container types that the contract profile reports cleanly
- **FIXED** [low] retrieved_before_published falsely rejects UTC retrieval times on the publication day
- **FIXED** [low] Contract profile turns R05-only policies (PII, proprietary hosts, length caps) into errors
- **FIXED** [low] source_refs[].fields rejects valid civic-v1 paths such as 'schedule' or 'budget'
- **REFUTED** [low] Contract profile silently accepts zero amount_kzt standing in for an unknown budget
  - почему опровергнуто: Mechanically reproduced: budget {0,'unknown',None} returns [] in the contract profile and [budget_zero, demo_budget] in demo. This is documented design, not a defect. The docstring and README define contract as shape-only; CONTRACT.txt types amount_kzt as 'finite nonnegative number|null', so 0 is shape-valid. The 'не маскировать нулём' rule (do not mask with zero) is a producer obligation, and R05
- **REFUTED** [low] Timestamps in the contract profile are stricter than the contract and R02 (date-only or naive retrieved_at)
  - почему опровергнуто: Mechanically reproduced: retrieved_at='2026-10-06' and updated_at='2026-10-06T12:00:00' give timestamp_format errors, and '+06', '+0600' and 7-digit fractions are rejected. This is a documented, defensible interpretation, not a defect. The README contract-profile bullet explicitly lists 'ISO8601 с offset' (ISO 8601 with offset). updated_at is server-assigned, and a naive timestamp is ambiguous bet
- **FIXED** [low] Plain-text check misses most HTML entities, including hex numeric ones
- **FIXED** [low] Polygon holes outside the shell and zero-area rings are accepted

## provenance

Исправления: import_helper checks exact version/as_of and recorded inputs on disk; civic_v1 real profile requires as_of, CLI takes slice.as_of; build_slice refuses expected claims for in_progress/cancelled, geometry claims on approximate points, keeps geometry_basis in evidence_notes, flags undated sources in public_readiness; stricter demo marker regex.

- **REFUTED** [low] Any fetched registry entry (license texts, READMEs) is accepted as evidence for civic facts
  - почему опровергнуто: Reproduced with /tmp/claude-0/-home-user-GOV-DIPLOME/c174a64a-00cd-5472-a358-4074c0498b28/scratchpad/review/verify-provenance/f1.py. It prints valid True, status completed, budget 5e9 contract from src-openmaptiles-license, organisation from src-openfreemap-readme, and public_readiness notes []. The behaviour is real, but I do not count it as a defect against the contract, the brief or the package
- **FIXED** [low] import_helper.load_package never checks slice.inputs or source_refs against the sources.json on disk, so a stale slice imports with ok:true
- **FIXED** [low] slice.as_of can be edited without detection, which turns the freshness checks off; the civic_v1 CLI ignores the envelope's as_of
- **FIXED** [medium] status in_progress or cancelled is accepted from a claim_type='expected' claim
- **FIXED** [low] Undated sources escape the public-readiness freshness note that old sources get
- **FIXED** [medium] A geometry claim silently upgrades an intake marked 'approximate' to geometry_precision='source', and geometry_basis is dropped from every output
- **FIXED** [low] Demo 'visibly synthetic' check matches ordinary words such as Демонтаж, демонстрация, синтетическое покрытие and Demolition
- **REFUTED** [low] registry_checks accepts a 'fetched' source with no successful attempt or a malformed sha256
  - почему опровергнуто: verify-provenance/f8.py confirms the builder behaviour. sha256='not-a-hash' with access_attempts=[] gives valid True with only a no_access_record warning. A source whose only attempt is egress_denied but whose access_status is 'fetched' gives valid True with registry_issues []. However, the package's own test suite already enforces exactly these invariants. I loaded tests/civic/R05/test_license_re

## pipeline

Исправления: Limits and rules aligned with R02 validate.py (notes 2000, description 5000, contact 200, single-line title/organization/publisher, bidi/zero-width, end<start and amount-without-basis = errors); plan() fails closed unless edited_after_import is explicitly False; report_missing considers objects.json+historical.json; status age is a parameter stored in the slice; BOM/invalid JSON -> IntakeError/PackageError. INTEGRATION.txt corrected: R02 uses its own importer and digest.

- **FIXED** [medium] R05-valid records are rejected by R02's importer, which refuses the whole package (amount with basis=unknown, evidence_notes >2000, \n/bidi in title, end dates before planned_start)
- **FIXED** [low] import_helper digest/existing-state recipe in INTEGRATION.txt does not match R02's import_digest; a missing edited_after_import fails open to update_import_draft
- **REFUTED** [low] create_body POSTed to /staff/objects does not keep the external id, so re-running creates duplicates
  - почему опровергнуто: Command: `python3 -I -B $V/scripts/create_body.py $V`. It reproduces as described: two HTTP 201 responses, random ids ast-b8caeb0759 and ast-9e54c5100d, and import_* columns None.  However, R05 never documents HTTP POST as the import path. import_helper.py:4 says "R02's importer (ui/civic_store) owns the transaction". INTEGRATION.txt:18-20 says the linkage lives in R02's import_source/import_exter
- **REFUTED** [low] Slice integrity check is self-referential and ignores recorded inputs: hand-edited or stale slices pass import_helper
  - почему опровергнуто: Command: `python3 -I -B $V/scripts/integrity.py $V`. Both (a) and (b) reproduce as described.  (a) requires deliberately recomputing content_sha256 and version with the builder's formula, which is forgery. Anyone who can do that can equally edit intake/. No tamper-proofing (a key or signature) is claimed. A plain hand edit is refused. I checked by appending ' X' to a demo title without recomputing
- **FIXED** [low] objects.json and historical.json share import source r05-astana-real, so each import reports the other file's records as report_missing
- **FIXED** [low] status_max_age_days leaks through a module global; import_helper ignores slice_config thresholds
- **FIXED** [low] Builder and import_helper crash with a raw JSONDecodeError traceback (rc=1) on UTF-8 BOM input

## dates

Исправления: schedule_diff: sentence splitter keeps 30.11.2026 and 'г.'; clause-scoped roles with negation/modal/percent vetoes, anchored prepositions, nearest-verb rule, 'перенесён с X на Y' -> previous_end/expected_end; invalid calendar dates -> invalid_date (editor), cross-year ranges; None guards; retrieval date as cut-off when published_on is missing.

- **FIXED** [medium] Negated, modal, old-plan and percentage completion phrases become candidate_actual ('источник сообщает о завершении')
- **FIXED** [medium] diff crashes with TypeError on an impossible calendar date (e.g. '31 сентября 2026') in a completion sentence; related None values leak into other findings
- **FIXED** [high] Snapshot sentence splitter breaks at every '.', so DD.MM.YYYY dates are dropped and a 'г.'-split postponement gives a confident 'Нет изменений сроков.'
- **FIXED** [medium] 'перенесён с <old> года на <new> года' proposes the new deadline as schedule.planned_start and misses the current_planned_end change
- **FIXED** [medium] Unanchored prepositions in END_RE ('по', 'к', 'срок') turn start announcements and progress-status dates into expected_end, then into a current_planned_end change
- **FIXED** [low] Cross-year range without a start year gives the start the end's year (start after end)

## security

Исправления: Digit-normalised KZ phone/IIN and Unicode e-mail detection; URL check mirrors R02 clean_url (host required, no userinfo/whitespace/quotes/controls); C1/zero-width/bidi/LS/PS rejected; snapshot capped (<= half text, <= 1500 chars) with contacts redacted.

- **FIXED** [low] PII guard misses common KZ phone formats (8 (7172) landlines, +7 7172, '7 701 ...') and IIN, although README says phones in text are an error
- **FIXED** [low] source_refs URL check accepts malformed URLs (no hostname, whitespace/newline, quotes) and URLs with userinfo
- **FIXED** [medium] 'Plain text, без HTML' check misses unclosed tags, hex entities and all named entities except lt/gt/amp/quot
- **FIXED** [medium] Validator crashes (TypeError/AttributeError) on wrong JSON types; import_helper aborts with a traceback instead of listing the item in rejected
- **FIXED** [low] C1 controls (U+0085), line/paragraph separators, bidi overrides and zero-width chars pass the control-character check
- **REFUTED** [low] probe_sources reports a cross-host or https->http redirect as 'fetched' and opens file:// URLs
  - почему опровергнуто: verify-security/redirect_test.py, run on loopback only, reproduces the behaviour. http://127.0.0.1:<port>/news/1 → 302 → localhost gives outcome='fetched', http_status=200 and final_url='http://localhost:<port>/other-host-page'. probe('file:///etc/hostname') gives outcome='partial' with a sha256. It is not a genuine defect: - The docstring says the tool 'Records what happened'. Every attempt recor
- **FIXED** [low] schedule_diff snapshot has no cap on total excerpts, so a date-dense notice is stored (almost) whole despite the 'статья целиком не хранится' claim

## Дополнительно после проверки
- Источники с ролью license_text/license_terms/service_terms/documentation не могут подтверждать факты о работах.
- registry_checks требует sha256 из 64 hex, корректный retrieved_at и успешную попытку для fetched.
- Перекрёстная проверка с реальным импортёром R02 (597ff2c): `r02_import_check.json` — демо create 9, повтор skip_unchanged 9.

## Проверки после исправлений
- `python3 -m pytest tests/civic/R05 -q` → 120 passed; `python3 -m unittest discover -s tests/civic/R05` → Ran 120, OK.
- `python3 -I data/civic/astana/tools/build_slice.py --check` → valid, без изменений (версии срезов прежние).

## Раунд 2 — проверка исправлений (diff e4ab1ff..01f89df)

Workflow r05-review-round2: искатели validator / dates / pipeline + скептики (часть агентов перезапущена после
лимита сессии). Плюс первый отчёт искателя dates (14 находок) до перезапуска — все воспроизведены и закрыты.
Исправлено в коммите после ee7516f; регрессионные тесты — классы Round2* и R02CharacterParity в
`tests/civic/R05/test_review_regressions.py`.

| Измерение | Находок | Подтверждено | Опровергнуто |
|---|---|---|---|
| validator | 8 | 7 | 1 |
| dates | 13 | 13 | 0 |
| pipeline | 11 | 9 | 2 |
| dates (первый прогон, без скептика) | 14 | воспроизведены | — |
| **итого со скептиком** | 32 | 29 | 3 |

### validator

Исправления: PII: только телефоны вида +7/8 с кодом 7xx/7xxx, ИИН по метке или дате+контрольной цифре, БИН и суммы с разрядами не флагуются; дыра полигона может касаться оболочки в точке; именованные сущности сверяются с таблицей HTML5; апостроф в URL допустим; окно лет в parse_ts; CLI не падает на суррогатах и глубокой вложенности; geometry_too_long — предупреждение в профиле contract. Дополнительно — паритет с R02 7d5e39a: категории Cc/Cf/Co/Cn/Cs, bidi, невидимые «буквы», текст без видимых символов, невидимые символы в URL, пути fields как SOURCE_FIELD_PATHS.

- **FIXED** [medium] New PII digit-run heuristic flags ordinary tenge budgets (7.x bn, 77.x/87.x bn, contiguous 12-digit sums) as phone/IIN; error in real/demo
- **FIXED** [low] New polygon hole check rejects OGC-valid holes that touch the shell at one point, and only on the right/top sides
- **REFUTED** [low] Widened CTRL_RE rejects emoji ZWJ sequences (U+200D), which R02 accepts
  - почему опровергнуто: The behaviour reproduces: '...👨‍👩‍👧...' and '...👷‍♂️...' give [('text_control_chars','error')] at HEAD, while e4ab1ff and R02 accept them; U+200C/200E/2028/2060/FEFF are rejected too. It is not a defect, though. It is deliberate and documented policy, not an accidental regression. README.md:61 lists 'без управляющих/zero-width/bidi-символов' as par
- **FIXED** [low] New HTML entity regex treats any '&Word;' as a named entity, so 'Ernst&Young;', 'Procter&Gamble;' and 'Johnson&Johnson;' are rejected
- **FIXED** [low] check_url rejects RFC 3986-valid URLs containing an apostrophe, although its docstring says it mirrors R02 clean_url
- **FIXED** [low] Out-of-window retrieved_at overflows in the new astana_date(); the catch-all replaces every issue with one validator_exception
- **FIXED** [low] civic_v1 CLI dies with a traceback on valid JSON: lone surrogate in an id/key (UnicodeEncodeError at print) or deep nesting (RecursionError)
- **FIXED** [low] geometry_too_long (R05's 60 km heuristic) is still a hard error in the contract profile, contrary to the documented 'R05 rules beyond the form are warnings in contract'

### dates

Исправления: schedule_diff v3: нормализация NFKC и склейка мягких переносов строк; разбиение предложений после «2026 г.» и перед цифрой/казахской заглавной, но не после «г. Астана», «ул.», «тел.», «дек.»; клауза режется по , ; ( : — и концу предложения, дата в начале предложения читается по словам после неё; ближайший глагол сильнее слова о завершении; перенос различает начало/окончание/неизвестное (previous_start/previous_end); модальность только в формах сказуемого; приостановка/снятие/возобновление → unclassified; диапазоны со временем, 15.10.2026–16.10.2026 и 7.10–8.10.2026 → period; «до конца октября», квартал, полугодие, год, «30 окт.», «30.10.2026г.»; окна вокруг каждой даты вместо обрезки [:300]; приоритет сроков при лимите 1500; snapshot_truncated и unclassified_changed доходят до редактора; редактирование контактов не трогает даты.

- **FIXED** [high] Snapshot size cap (new in the fix) drops later dated sentences, and diff ignores `truncated`, so a real postponement is reported as 'Нет изменений сроков.' and an unchanged deadline as 'removed'
- **FIXED** [medium] Excerpt cap [:300] cuts the date off the end of a long sentence, giving 'Нет изменений сроков.' (the abbreviation-aware splitter makes such sentences common)
- **FIXED** [medium] Role cues leak across sentence boundaries: no split after 'г.' or before a digit-led sentence, and the clause cut ignores '.', so a start date becomes candidate_actual
- **FIXED** [medium] A completion word earlier in the clause overrides the verb nearest the date and the 'по состоянию на' status cue, so start and status dates become candidate_actual
- **FIXED** [medium] MOVE+'на' rule turns a postponed START into expected_end, and 'продлится с' becomes previous_end, so the start is silently dropped
- **FIXED** [medium] MODAL veto fires on the attributive participle 'Запланированный' ('Ожидаемый'), so a reported completion becomes a current_planned_end change
- **FIXED** [medium] A closure written with clock times or numeric dates bypasses the 'period' protection and is proposed as planned_start/current_planned_end (with differs_from_record)
- **FIXED** [medium] Missed coarse/variant date forms ('до конца октября 2026', '30.10.2026г.', quarter, year, '30 окт.') give a confident 'Нет изменений сроков.'
- **FIXED** [medium] split_sentences treats every newline as a sentence end, so in hard-wrapped page text a date that extract_dates finds is lost from the snapshot
- **FIXED** [low] 'Окончание перекрытия … запланировано на X' is classified as start and proposed as a planned_start change
- **FIXED** [low] PII redaction (new in the fix) deletes numeric dates such as 'до 7.10.2026 (120 ...' and '7.10-8.10.2026' from excerpts
- **FIXED** [low] Snapshot note claims excerpts total 'не больше половины текста' and 'статья целиком не хранится', but short notices are stored whole
- **FIXED** [low] 'Работы приостановлены до X' (resumption date) is classified as expected_end and proposed as a current_planned_end change

### pipeline

Исправления: INTEGRATION: рецепт edited_after_import исправлен (было инвертировано); параметры среза (name/as_of/demo/status_max_age_days) входят в content_sha256; ID_RE и даты через \Z; формат id источника и сумма ≤ 10^13 как в R02; geofence с BOM читается, битый — IntakeError/PackageError; dot-файлы игнорируются как в glob сборщика; проверка списка intake для демо-среза; historical.json читается через проверку целостности; QA.md — два примера переноса срока.

- **FIXED** [medium] INTEGRATION.txt recipe for edited_after_import is inverted, so plan() would overwrite a draft an editor has edited
- **REFUTED** [low] The historical/current report_missing fix exists only in R05 plan(); R02's real importer still reports the other file's records as missing
  - почему опровергнуто: The mechanics reproduce. In verify-pipeline/r02: import objects.json gives create 1. import historical.json gives missing=[ast-r05-test-street-repair]. Dry-run of objects.json gives {skip_unchanged:1, report_missing:1} with ast-r05-test-old-park. `plan_hist.py` gives only [('skip_unchanged','ast-r05-test-street-repair')]. It is not a genuine R05 de
- **FIXED** [low] slice.status_max_age_days is outside the integrity hash, so editing it by hand switches off stale_status in import_helper and the civic_v1 CLI
- **FIXED** [low] ID_RE ends with '$', so an id with a trailing newline passes the builder, the validator and import_helper, and R02 then rejects the whole package
- **FIXED** [low] R02 limits are still not mirrored: source_refs[].id / budget.source_id format and amount_kzt <= 10^13
- **FIXED** [low] BOM fix is incomplete: geofence.json with a BOM still crashes build_slice and import_helper with a raw JSONDecodeError traceback
- **FIXED** [low] A dot-file *.json in intake/real (macOS ._ AppleDouble, Emacs .# lock) makes import_helper refuse the package, and rebuilding cannot fix it
- **FIXED** [low] The stale-input check covers only real slices: a new intake/demo file leaves demo_synthetic.json stale and import_helper still returns ok:true
- **FIXED** [low] load_package now reads historical.json even without --include-historical, and crashes with AttributeError when it is not an object
- **REFUTED** [low] Slice versions depend on where the package sits, and import_helper now refuses a package built anywhere except .../data/civic/astana
  - почему опровергнуто: The behaviour reproduces in verify-pipeline/elsewhere/astana. build_slice gives new versions (...-b64dd2f82a45) with inputs ['verify-pipeline/elsewhere/astana/sources.json', ...]. import_helper gives {"ok": false, "error": "objects.json: unexpected input path 'verify-pipeline/elsewhere/astana/sources.json'"}, rc=2. The e4ab1ff tools also give locat
- **FIXED** [low] QA.md says the demo slice has one deadline-shift example, but two demo records have original_planned_end != current_planned_end

### dates — первый прогон искателя (до перезапуска)

- **FIXED** [high] Merged sentences let the previous sentence's verb set the role: a start date becomes candidate_actual, and a real completion becomes a current_planned_end change (regression)
- **FIXED** [high] The new snapshot budget drops the deadline sentence from an ordinary 414-char article, and diff ignores 'truncated', so it reports 'Нет изменений сроков.' (regression)
- **FIXED** [medium] A per-sentence 300-char cut silently drops dates from sentences merged at 'г.' and from semicolon lists, with truncated=False (regression for the 'г.' merge)
- **FIXED** [medium] split_sentences breaks at every newline: hard-wrapped page text loses dates and loses negation/modal cues, so an old plan becomes candidate_actual
- **FIXED** [medium] Postponement wordings other than the past perfective ('переносится', 'Перенос', 'сдвигается', 'откладывается' с X на Y) propose the old deadline as planned_start and drop the new deadline
- **FIXED** [medium] The modal veto matches adjectives and nouns ('Запланированный', 'должностных', 'Ожидаемый'), so reported completions become current_planned_end changes (regression)
- **FIXED** [medium] The clause is not cut at ':' or '—', so an old contract deadline and a following start date are reported as actual completion
- **FIXED** [medium] A closure period written with clock times is not treated as a period: the closure end is proposed as the works' current_planned_end, and the start loses its year
- **FIXED** [medium] Dates classified 'unclassified' ('the editor decides') never reach the editor: an event moved by a week gives 'Нет изменений сроков.' even when it differs from the record
- **FIXED** [low] Quarter, half-year and year-end deadlines are not extracted at all, so a move from IV квартал 2026 to II квартал 2027 gives 'Нет изменений сроков.'
- **FIXED** [low] A range without a start month whose start day is after its end day becomes a 12-month 'day'-precision period (cross-year fix applied wrongly)
- **FIXED** [low] 'с <date>' after a suspension, lift or resumption verb is proposed as planned_start
- **FIXED** [low] The snapshot of a short notice stores the whole text, although the note in the same JSON says 'не больше половины текста ... статья целиком не хранится'
- **FIXED** [low] extract_dates and the snapshot CLI crash with ValueError on Cyrillic Extended-C letters that re.I matches as month letters

### Проверки после раунда 2
- `python3 -m pytest tests/civic/R05 -q` → 149 passed; `python3 -m unittest discover -s tests/civic/R05` → 149 OK.
- `build_slice.py --check` → valid; новые версии срезов (параметры теперь в хэше).
- R02 7d5e39a: импорт демо create 9 → skip_unchanged 9; дифференциальный fuzz 12 000 мутаций — 0 расхождений.
- ZWJ-эмодзи: скептик отклонил находку, но R02 7d5e39a теперь сам запрещает категорию Cf (включая ZWJ);
  R05 повторяет политику R02, чтобы запись R05 всегда импортировалась.
