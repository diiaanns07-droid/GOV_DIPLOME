"""Contract used by the demo build: k05-obs-v1.2+k12r4+k05r5 (see inputs/contract/CONTRACT_MANIFEST.json).

Thin wrapper only: strict JSON in/out + per-record validate + dataset validate. All rules live in the
K05/K12 modules under inputs/contract/ (built by tools/setup_contract.py).
"""
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
CDIR = APP / "inputs" / "contract" / "research"
if not (CDIR / "round-4-results" / "K05" / "k05r4_contract.py").exists():
    raise ImportError("inputs/contract/ отсутствует — запустите tools/setup_contract.py")
sys.path.insert(0, str(CDIR / "round-4-results" / "K05"))
import k05r4_contract as C4  # noqa: E402  (imports the K12-patched k05r3_contract as C4.C3)

C3 = C4.C3
CONTRACT_ID = "k05-obs-v1.2+k12r4+k05r5"
SCHEMA_VERSION = C4.SCHEMA_VERSION
assert hasattr(C3, "loads_strict") and hasattr(C3, "validate_dataset"), "K12 patch is not applied"


class ContractError(ValueError):
    pass


def loads_strict(text):
    """Reject NaN/±Infinity tokens, numbers overflowing to inf (1e999) and duplicate keys."""
    try:
        return C3.loads_strict(text)
    except ValueError as e:
        raise ContractError(str(e)) from None


def dumps_strict(obj, **kw):
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, **kw)


def validate(obs, as_of):
    return C4.validate(obs, as_of=as_of)


def validate_all(observations, as_of):
    """(errors, warnings) for a list of records: per-record (v1.2 -> v1.1+K12) plus dataset checks."""
    errors, warnings = [], []
    for o in observations:
        e, w = validate(o, as_of)
        errors += [f"{o.get('obs_id')}: {x}" for x in e]
        warnings += [f"{o.get('obs_id')}: {x}" for x in w]
    de, dw = C3.validate_dataset([C4._to_v11(o) for o in observations])
    return errors + de, warnings + dw
