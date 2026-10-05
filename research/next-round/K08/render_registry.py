#!/usr/bin/env python3
"""Строит REGISTRY.md из registry.json (K08). Только чтение и запись этих двух файлов."""
import json, pathlib
here = pathlib.Path(__file__).parent
d = json.loads((here / 'registry.json').read_text(encoding='utf-8'))
V = {'confirmed': 'подтверждено', 'refuted': 'опровергнуто', 'not_checked': 'не проверено'}
def verdict(v):
    for k, ru in V.items():
        v = v.replace(k, ru)
    return v
cell = lambda s: (s or '—').replace('|', '\\|').replace('\n', ' ')
n = len(d['claims'])
out = [f"# K08 — реестр проверки утверждений (Шымкент + Астана)", "",
       f"Статус: **{d.get('status', 'partial')}**, записей {n} (10 основных + доп.). Дата проверки: {d['checked_at']}.", "",
       d['method_note'] + " Госпорталы, Zenodo, OSM и операторские сайты заблокированы (см. `ACCESS_LOG.md`).", "",
       "| # | Город | Утверждение | Исходный ID | Источник | Дата источника | Вердикт | Объяснение | Что не проверено |",
       "|---|---|---|---|---|---|---|---|---|"]
for c in d['claims']:
    out.append("| " + " | ".join(cell(x) for x in [c['check_id'], c['city'], c['claim'], ', '.join(c['source_claim_ids']),
               c['primary_source'], c['source_date'], '**' + verdict(c['verdict']) + '**', c['explanation'], c.get('not_verified_parts')]) + " |")
sm = d.get('summary')
if sm:
    out += ["", "## Итог", "", sm['main_10']['note'], "", "### Уточнения к исходным отчётам", ""] + ["- " + x for x in sm['refinements']]
    out += ["", "### Что это значит для MVP", ""] + ["- " + x for x in sm['mvp_implications']]
out += ["", "Таблица сгенерирована `render_registry.py` из `registry.json`. Воспроизведение проверок: `bash verify_claims.sh <папка>`, вывод — `run_log.txt`.", ""]
(here / 'REGISTRY.md').write_text("\n".join(out), encoding='utf-8')
print('rows', n)
