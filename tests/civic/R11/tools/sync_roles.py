"""R11: синхронизация словаря с запасными текстами модулей ролей (раунд 15).

    git fetch origin && DRY=1 python3 -B tests/civic/R11/tools/sync_roles.py   # что изменилось бы
    python3 -B tests/civic/R11/tools/sync_roles.py                             # записать ru.json, kk.json, key_sources.json

Новый ключ → добавить; текст роли изменился → обновить, если у ключа нет намеренной правки R11 (пометка «R11:» в
research/round-15-results/R11/kk_notes.json). Массивы, фрагменты с пробелами по краям и пустые половины фраз — не в словарь.
Исходники ролей читаются из git (origin/<ветка>); из файла берётся только объектный литерал словаря (extract_obj.cjs, vm)."""
import json, os, subprocess, sys, tempfile
DRY = os.environ.get("DRY") == "1"
from pathlib import Path
TOOLS = Path(__file__).resolve().parent; ROOT = TOOLS.parents[3]
SP = Path(tempfile.mkdtemp(prefix="r11-sync-"))
MODS = [  # роль, ветка, файл, имя объекта словаря
    ("R16", "claude/youthful-johnson-6nz5mp", "web/civic/together/together-text.js", "BirgeTogetherText"),
    ("R17", "claude/sweet-euler-5tiu5b", "web/civic/agencies/agencies.js", "KEYS"),
    ("R12", "claude/great-newton-8k3474", "web/civic/works-calendar/works-calendar.js", "KEYS"),
    ("R13", "claude/gifted-mayer-p86myv", "web/civic/meetings/meetings.js", "KEYS"),
    ("R08", "claude/laughing-euler-iv3on3", "web/civic/board/board.js", "FALLBACK"),
    ("R07", "claude/birge-r07-round-15-zjp4ob", "web/civic/replay/replay.js", "DICT"),
    ("R03", "claude/modest-mccarthy-lrl98u", "web/civic/assistant/analyst.js", "KEYS"),
    ("R01", "claude/brave-fermi-nhzetj", "web/civic/shell/shell-text.js", "TEXT"),
    ("R17", "claude/sweet-euler-5tiu5b", "web/civic/agencies/crisis-layer.js", "TEXT", "crisis.map."),
    ("R06", "claude/eloquent-einstein-wvuyje", "web/civic/notify/notify.js", "KEYS"),
    ("R06", "claude/eloquent-einstein-wvuyje", "web/civic/ideas/ideas.js", "KEYS"),
    ("R06", "claude/eloquent-einstein-wvuyje", "web/civic/proposals/works.js", "KEYS"),
    ("R09", "claude/quirky-ptolemy-k3z2mj", "web/civic/feedback/complaint-strings.js", "BirgeComplaintStrings"),
    ("R08", "claude/laughing-euler-iv3on3", "web/civic/akim/akim.js", "WAVE2_KEYS"),
    ("R08", "claude/laughing-euler-iv3on3", "web/civic/akim/week.js", "FALLBACK"),
    ("R07", "claude/birge-r07-round-15-zjp4ob", "web/civic/heat/heat.js", "DICT"),
    ("R05", "claude/bold-cray-dopshy", "web/civic/build3d/build3d.js", "STRINGS"),
    ("R12", "claude/great-newton-8k3474", "web/civic/qr/print.js", "TEXT"),
    ("R13", "claude/gifted-mayer-p86myv", "web/civic/qa/qa.js", "KEYS"),
]
ru = json.loads((ROOT / "web/civic/i18n/ru.json").read_text("utf-8"))
kk = json.loads((ROOT / "web/civic/i18n/kk.json").read_text("utf-8"))
notes = json.loads((ROOT / "research/round-15-results/R11/kk_notes.json").read_text("utf-8"))
sources = json.loads((ROOT / "research/round-15-results/R11/key_sources.json").read_text("utf-8"))
added, updated, kept = [], [], []
for role, branch, path, name, *pre in MODS:
    prefix = pre[0] if pre else ""
    src = subprocess.run(["git", "show", f"origin/{branch}:{path}"], capture_output=True, text=True, cwd=ROOT).stdout
    if not src: print("нет файла", role, path); continue
    f = SP / f"sync-{role}.js"; f.write_text(src, "utf-8")
    out = subprocess.run(["node", str(TOOLS / "extract_obj.cjs"), str(f), name, f"{role} · {path}"], capture_output=True, text=True)
    if out.returncode: print("не прочитан", role, out.stderr[:200]); continue
    for k, v in json.loads(out.stdout).items():
        k = prefix + k
        r, z = v["ru"], v["kk"]
        if isinstance(r, list) or isinstance(z, list): continue          # массивы — не в словарь (дни, месяцы, списки)
        if any(isinstance(x, str) and (x != x.strip() or x == "") for x in (r, z)): continue   # пробелы по краям, пустая половина фразы
        if isinstance(z, dict): z = z.get("other") or next(iter(z.values()))
        if k not in ru:
            ru[k], kk[k] = r, z; sources[k] = v["where"]; added.append(k)
        elif (ru[k] != r or kk[k] != z):
            if str(notes.get(k, "")).startswith("R11:"): kept.append(k)
            elif sources.get(k, "").startswith(role):                    # только ключи этой роли
                ru[k], kk[k] = r, z; updated.append(k)
if DRY:
    print("DRY: не записано")
    for k in updated: print("  обновил бы", k, "|", ru[k] if not isinstance(ru[k], dict) else ru[k].get("many"), "|", kk[k])
    for k in added: print("  добавил бы", k, "|", ru[k] if not isinstance(ru[k], dict) else ru[k].get("many"), "|", kk[k])
    sys.exit(0)
(ROOT / "web/civic/i18n/ru.json").write_text(json.dumps(ru, ensure_ascii=False, indent=1) + "\n", "utf-8")
(ROOT / "web/civic/i18n/kk.json").write_text(json.dumps(kk, ensure_ascii=False, indent=1) + "\n", "utf-8")
(ROOT / "research/round-15-results/R11/key_sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=1) + "\n", "utf-8")
print("добавлено", len(added), added[:12]); print("обновлено", len(updated), updated[:12]); print("оставлены правки R11", len(kept), kept)
