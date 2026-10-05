# BUILD r5 — HANDOFF
Работает (как в r4): `cd prototypes/city-evidence && python3 serve.py` → http://127.0.0.1:8765/.
Новое: контракт `tools/contract.py` + `tools/setup_contract.py`; тест `python3 -m unittest tests.test_contract -v`.
Незавершено: `tools/build_evidence.py` ещё на v1.1; ISSUE_MATRIX.json/MIGRATION.md — черновики.
Следующий шаг: переключить build_evidence на contract.py (v1.2), обновить facts.js/explain_ref и тесты.
