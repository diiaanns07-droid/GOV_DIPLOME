"""R04 раунд 15 · поправка владельца П1 «Без ИИ-слопа» (research/round-15/AMENDMENTS.md, 15 окт 17:05).

У R04 нет своего экрана: всё, что видит человек, — тексты (объяснение «2 службы», черновик ответа, подсказка модерации,
«Тоже уборка, 70 м»). Правило 4 П1 для текстов: без эмодзи, пиктограмм и украшений — только буквы, цифры и обычная
пунктуация (тире, кавычки-ёлочки).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from ml.civic_replies import templates as T
from ui.civic_ml_api import moderate, reply_draft, route, similar_initiatives
from ui.civic_ml_api import routing as R
from ui.civic_ml_api.route_eval import load_cases

# Эмодзи и пиктограммы: дополнительные плоскости символов, «разные символы» и дингбаты, стрелки-украшения,
# вариационный селектор эмодзи, звёзды, галочки и т. п.
_PICTO = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍←-⇿✀-➿]")


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from strings(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            yield from strings(value)


def test_no_pictographs_in_any_r04_text_output():
    texts = []
    for case in load_cases():
        res = route(text=case["text"] or None, category=case["category"], subtopic=case["subtopic"])
        texts += [res["summary_ru"], res["summary_kk"], res["why_ru"], res["why_kk"]]
        texts += [s[k] for s in res["services"] for k in ("why_ru", "why_kk", "name_ru", "name_kk")]
    now = datetime(2026, 10, 15, 12, 0, tzinfo=timezone(timedelta(hours=5)))
    record = {"id": "c-abc1234", "code": "B-0042", "category": "roads", "subtopic": "pothole", "status": "new",
              "due_at": "2026-10-29T10:00:00+05:00", "passport": {}}
    for status in ("new", "accepted", "in_progress", "fixed", "rejected"):
        res = reply_draft(record=record, status=status, now=now)
        texts += [res["draft_ru"], res["draft_kk"]] + res["warnings"]
    res = moderate("Звоните 8 701 123 45 67, опять эта блядская яма")
    texts += list(strings(res))
    res = similar_initiatives("Субботник", [71.41, 51.10], 30, now=now, records=[
        {"id": "i-1", "kind": "cleanup", "title": "Субботник во дворе", "point": [71.411, 51.10],
         "starts_at": (now + timedelta(days=2)).isoformat(), "status": "published"}])
    texts += list(strings(res))
    texts += list(strings(T.TOPIC)) + list(strings(T.SENT)) + list(strings(T.PART_STATUS))
    texts += list(strings(R._JOINT_WHY)) + list(strings(R._ROLE_WHY))
    bad = sorted({t for t in texts if isinstance(t, str) and _PICTO.search(t)})
    assert not bad, bad
    assert len(texts) > 1000


def test_r04_has_no_images_in_its_paths():
    """П1 правило 1–2: у R04 нет картинок и рисунков — ни в коде, ни в результатах раунда 15."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[4]
    images = [p for base in ("ml/civic_replies", "ui/civic_ml_api", "tests/civic/R04/round15", "research/round-15-results/R04")
              for p in (root / base).rglob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp")]
    assert images == []
    json.dumps(images)
