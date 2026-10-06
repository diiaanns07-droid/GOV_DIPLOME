"""K08 R9: envelope-фикстуры city-resilience-v1 (только вход, без производных) над реальными срезами d865dd4.
План = r8-фикстура (synthetic demo inputs) с snapshot BUILD. Исключения — реальные source IDs срезов; выбор — пользовательский
сценарий анализа, не утверждение о закрытии. Usage: python make_envelopes.py --app-root APP --out DIR
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_compat
P = build_compat.use_build_snapshot()

def plan(ctx, name):
    sc = json.loads((build_compat.R8 / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))
    sc["source_snapshot"] = build_compat.build_snapshot(ctx, sc["city_id"])
    return sc

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--app-root", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args(); ctx = P.Context(a.app_root); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    sh = plan(ctx, "shymkent_school_demo")
    sh_all = sorted(r["id"] for r in ctx.records("shymkent", "school"))
    qa = sorted(i for i in ctx.obs["cities"]["shymkent"]["qa"]["category_doubt"] if i in sh_all)
    near2 = ["18df815b-170a-437c-977f-0769690315d4", "51ac9e88-456d-4b3a-a657-d3cbc516c708"]
    envs = {
        "shymkent_school_r9": {"schema_version": "city-resilience-v1", "plan": sh, "cases": [
            {"id": "qa_doubt", "label": "QA: сомнение в категории — условно не учитываем", "disabled_source_ids": qa},
            {"id": "near_two", "label": "Без двух ближайших записей", "disabled_source_ids": near2},
            {"id": "дубль_near_two", "label": "Тот же набор, другая подпись <b>не тег</b>", "disabled_source_ids": list(reversed(near2))},
            {"id": "все_записи", "label": "Все записи школ условно исключены", "disabled_source_ids": sh_all}]},
        "astana_clinic_r9": {"schema_version": "city-resilience-v1", "plan": plan(ctx, "astana_clinic_demo"), "cases": [
            {"id": "foursquare_one", "label": "Без записи Foursquare", "disabled_source_ids": ["771c278a-af10-4c57-b9fc-52755437345d"]},
            {"id": "near_three", "label": "Без трёх ближайших записей", "disabled_source_ids":
                ["3fba1026-8464-41ab-88f8-633e3df0de30", "410f0193-f0bc-4553-bee5-660aab0287a5", "fcdc8d2f-41ff-42ea-99fe-726d7d844050"]}]},
    }
    for k, v in envs.items():
        (out / f"{k}.json").write_text(json.dumps(v, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(list(envs))

if __name__ == "__main__":
    main()
