"""R12 · воспроизведение (для R07/R01): «Взять в работу» у остановки с демо-записями R07 → 404 на c-demo-* (ночь 11 окт).

Запуск на дереве сборки (сервер поднимается сам, временная база, CIVIC_DEMO=1; в репозиторий ничего не пишет):
    python3 -I research/round-14-results/R12/tools/repro_step6.py <папка сборки>
Ожидается до правки R07: «status of heat open_id c-demo-0457 404» — R07 heat.js на этом id обрывает цикл и пишет «Сақталмады».
"""
import json, os, subprocess, sys, tempfile, time, urllib.request, http.cookiejar, socket
ROOT = sys.argv[1]; PY = sys.executable
tmp = tempfile.mkdtemp(); db = os.path.join(tmp, "civic.sqlite3")
env = dict(os.environ, CIVIC_DB_PATH=db, PYTHONDONTWRITEBYTECODE="1", CIVIC_DEMO="1")
cli = lambda *a, inp=None: subprocess.run([PY, "-B", "-m", "ui.civic_store", "--db", db, *a], cwd=ROOT, env=env, input=inp, capture_output=True, text=True, check=True)
cli("init"); cli("seed-demo", "--package", "data/civic/astana/demo_synthetic.json"); cli("seed-r14-demo")
cli("create-editor", "repro-operator", "--password-stdin", inp="R10-e2e-repro-Aa1!x\n")
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
srv = subprocess.Popen([PY, "-B", "app.py", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=open(os.path.join(tmp, "srv.log"), "w"), stderr=subprocess.STDOUT)
base = f"http://127.0.0.1:{port}"
jar = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def call(m, p, body=None, headers=None):
    h = {"Content-Type": "application/json", "Accept": "application/json", "Origin": base, "X-Birge-Device": "repro-device-0123456789"}; h.update(headers or {})
    req = urllib.request.Request(base + p, method=m, data=None if body is None else json.dumps(body).encode(), headers=h)
    try:
        r = op.open(req, timeout=60); return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")
for _ in range(150):
    try:
        if call("GET", "/api/health")[0] == 200: break
    except Exception: time.sleep(0.2)
try:
    stop = [71.40432, 51.1251454]
    st, t = call("GET", f"/api/civic/v2/targets?lon={stop[0]}&lat={stop[1]}")
    target = t["candidates"][0]["target"]; print("target", target)
    body = {"text": "Аялдамада жарық жоқ, вечером на остановке темно", "category": "lighting", "category_source": "model",
            "model": None, "point": stop, "target": target, "request_id": "repro-req-1"}
    st, c = call("POST", "/api/civic/v2/complaints", body); print("create", st, json.dumps(c, ensure_ascii=False)[:400])
    cid = (c.get("data") or c).get("complaint", {}).get("id") if isinstance(c, dict) else None
    st, l = call("POST", "/api/civic/v1/session/login", {"username": "repro-operator", "password": "R10-e2e-repro-Aa1!x"}); print("login", st)
    csrf = (l.get("data") or l).get("csrf_token")
    for hdr in ({}, {"X-CSRF-Token": csrf}):
        st, r = call("POST", f"/api/civic/v2/complaints/{cid}/status", {"status": "in_progress"}, hdr)
        print("status", "with csrf" if hdr else "no csrf", st, json.dumps(r, ensure_ascii=False)[:600])
    st, h = call("GET", f"/api/civic/v2/heat?bbox=71.39,51.12,71.42,51.13&days=30")
    items = (h.get("data") or h).get("items", [])
    for i in items:
        if i["target"]["id"] == target["id"]:
            for oid in i.get("open_ids") or []:
                st2, r2 = call("POST", f"/api/civic/v2/complaints/{oid}/status", {"status": "in_progress"}, {"X-CSRF-Token": csrf})
                print("status of heat open_id", oid, st2, json.dumps(r2, ensure_ascii=False)[:300])
            st3, g = call("GET", f"/api/civic/v2/complaints?bbox=71.40,51.12,71.41,51.13")
            print("store complaints near stop", st3, [ (x.get("id"), x.get("status"), (x.get("target") or {}).get("id")) for x in ((g.get("data") or g).get("complaints") or (g.get("data") or g).get("items") or [])][:10])
    items = (h.get("data") or h).get("items", [])
    print("heat", st, [ (i["target"]["id"], i.get("open_ids"), i.get("status")) for i in items if i["target"]["id"] == target["id"]])
finally:
    srv.terminate(); srv.wait()
    print("--- server log tail ---"); print(open(os.path.join(tmp, "srv.log")).read()[-2500:])
