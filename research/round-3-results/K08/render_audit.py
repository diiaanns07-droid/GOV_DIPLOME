#!/usr/bin/env python3
"""Строит AUDIT.md из verdicts.json (K08, раунд 3). Читает и пишет только эти два файла."""
import json, pathlib
h = pathlib.Path(__file__).parent
d = json.loads((h / 'verdicts.json').read_text(encoding='utf-8'))
RU = {'confirmed': 'подтверждено', 'confirmed_with_corrections': 'подтверждено с поправками',
      'refuted': 'опровергнуто', 'not_reproduced': 'не воспроизведено', 'not_checked': 'не проверено'}
c = lambda s: (s or '—').replace('|', '\\|').replace('\n', ' ')
a = d['audited']
out = ["# K08 — независимый аудит K10 (раунд 3)", "",
       f"Объект: K10, ветка `{a['branch']}` @ `{a['sha']}`, `research/next-round/K10/`. Задание: `research/round-3/prompts/K08.txt`. Дата: {d['checked_at']}.",
       "Отчёт K10 — материал проверки. Вердикт «подтверждено» ставится только после собственного действия K08: повторной выгрузки, пересчёта или чтения первичного текста.", ""]
if d.get('summary'):
    out += ["## Главное", ""] + ["- " + x for x in d['summary']['main_findings']] + [""]
out += ["## Вердикты", "", "| ID | Тема | Утверждение K10 | Вердикт | Что сделал K08 | Поправки | Ограничения | Доказательства |", "|---|---|---|---|---|---|---|---|"]
for x in d['claims']:
    out.append("| " + " | ".join(c(v) for v in [x['id'], x['topic'], x['claim'], '**' + RU[x['verdict']] + '**', x['own_action'],
               x.get('corrections'), x['limitations'], '<br>'.join(x['evidence'])]) + " |")
out += ["", "Таблица построена `render_audit.py` из `verdicts.json`.", ""]
(h / 'AUDIT.md').write_text("\n".join(out), encoding='utf-8')
print(len(d['claims']))
