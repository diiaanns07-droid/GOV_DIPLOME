"""B1: исходный baseline A13-E4 (baseline_parse) без изменений логики.

Из constraints_eval.py через ast берутся только присваивания LEX, DIST, NEG и функция
baseline_parse; остальной код A13 (прогон GOLD, optimize) не исполняется.
B1 не умеет определять город и отказываться: статус всегда «ok», город = context_city.
"""
import ast, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "research/govtech-results/13_architecture_ai_thesis/extracted_files__21_/constraints_eval.py"


def load_b1(data):
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    keep = [n for n in tree.body
            if (isinstance(n, ast.Assign) and any(getattr(t, "id", None) in ("LEX", "DIST", "NEG") for t in n.targets))
            or (isinstance(n, ast.FunctionDef) and n.name == "baseline_parse")]
    assert len(keep) == 4, [type(n).__name__ for n in keep]
    ns = {"re": re, "json": json, "data": data}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(SRC), "exec"), ns)
    return ns["baseline_parse"]


class B1:
    name = "B1_A13_baseline_parse"

    def __init__(self, data):
        self.parse = load_b1(data)

    def predict(self, text, context_city):
        return {"status": "ok", "reason": None, "city": context_city, "constraints": self.parse(text)}
