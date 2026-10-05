"""Build inputs/k02v4/verified_explainer.py: local adaptation of K02 r4 fixed/verified_explainer.py.

Original (byte-exact): inputs/r4/K02/fixed/verified_explainer.py. Each replacement must match exactly once.
Changes (BUILD r5 requirements):
  1. catalog_digest also covers unit and missing_reason (fingerprint depends on units and coverage/reason);
  2. a missing value shows its missing_reason in the verified text (ru/kk);
  3. units used by the demo: segments, places, persons.
MANIFEST.json records original and adapted sha256. The adapted file is not upstream K02.
"""
import hashlib
import json
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SRC = APP / "inputs" / "r4" / "K02" / "fixed" / "verified_explainer.py"
OUT = APP / "inputs" / "k02v4" / "verified_explainer.py"
REPL = [
    ('    payload = sorted((f.fact_id, repr(f.value), f.kind, f.coverage_complete) for f in catalog.values())',
     '    payload = sorted((f.fact_id, repr(f.value), f.kind, f.coverage_complete, f.unit, f.missing_reason)\n'
     '                     for f in catalog.values())  # BUILD r5: + unit, missing_reason'),
    ('          "records": {"ru": " записей", "kk": " жазба"}, "schools": {"ru": " школ", "kk": " мектеп"}}',
     '          "records": {"ru": " записей", "kk": " жазба"}, "schools": {"ru": " школ", "kk": " мектеп"},\n'
     '          # BUILD r5: единицы демо; kk — черновик\n'
     '          "segments": {"ru": " сегментов", "kk": " сегмент"}, "places": {"ru": " мест", "kk": " орын"},\n'
     '          "persons": {"ru": " чел.", "kk": " адам"}}'),
    ('            if fact.coverage_complete is False and fact.value is not None:\n'
     '                kind += ", " + _TEXT["incomplete"][lang]\n',
     '            if fact.coverage_complete is False and fact.value is not None:\n'
     '                kind += ", " + _TEXT["incomplete"][lang]\n'
     '            if fact.value is None and fact.missing_reason:  # BUILD r5: причина пропуска видна в тексте\n'
     '                kind += ", " + _REASON.get(fact.missing_reason, {}).get(lang, fact.missing_reason)\n'),
    ('def _num(value):',
     '# BUILD r5: подписи причин отсутствия (коды k05-obs missing_reason); kk — черновик\n'
     '_REASON = {\n'
     '    "source_access_denied": {"ru": "источник недоступен", "kk": "дереккөзге қол жетімсіз"},\n'
     '    "not_collected": {"ru": "не собиралось", "kk": "жиналмаған"},\n'
     '    "not_in_source": {"ru": "нет в источнике", "kk": "дереккөзде жоқ"},\n'
     '    "zero_in_partial_coverage": {"ru": "ноль при неполном охвате", "kk": "толық емес қамтудағы нөл"},\n'
     '    "suppressed_by_publisher": {"ru": "скрыто публикатором", "kk": "жариялаушы жасырған"},\n'
     '}\n\n\ndef _num(value):'),
]


def main():
    src = SRC.read_text(encoding="utf-8")
    out = src
    for old, new in REPL:
        if out.count(old) != 1:
            raise SystemExit(f"replacement does not match exactly once: {old[:60]!r}")
        out = out.replace(old, new)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(out, encoding="utf-8")
    h = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
    (OUT.parent / "MANIFEST.json").write_text(json.dumps({
        "original": {"path": str(SRC.relative_to(APP)), "sha256": h(SRC.read_bytes()), "source": "K02 @ 7020637 fixed/"},
        "adapted": {"path": str(OUT.relative_to(APP)), "sha256": h(OUT.read_bytes())},
        "changes": ["catalog_digest + unit + missing_reason", "missing_reason shown in text", "units segments/places/persons"],
        "note": "local adaptation for the demo, not upstream K02",
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("k02v4 written", h(OUT.read_bytes())[:16])


if __name__ == "__main__":
    main()
