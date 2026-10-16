"""R17 · житель двора в зоне кризиса видит обновления (R16 «Я живу здесь» → R17 incidents/updates → лента R06).

    python3 -B research/round-15-results/R17/checks/e2e_yard_feed.py <папка сборки с R16 и миром R02>

Свой сервер на временной базе (CIVIC_DEMO=1, CIVIC_DEMO_WORLD=1), печатает числа; настоящие данные не трогает.
"""
import json, os, random, subprocess, sys, tempfile, time, urllib.request
REPO = sys.argv[1]
sys.path.insert(0, REPO)
tmp = tempfile.mkdtemp(prefix="r17y-"); db = os.path.join(tmp, "c.sqlite3")
env = {**os.environ, "CIVIC_DB_PATH": db, "CIVIC_DEMO": "1", "CIVIC_DEMO_WORLD": "1"}
for a in ("init", "seed-demo --package data/civic/astana/demo_synthetic.json"):
    subprocess.run(f"python3 -B -m ui.civic_store --db {db} {a}", shell=True, cwd=REPO, env=env, check=True, stdout=subprocess.DEVNULL)
port = 8950 + random.randint(0, 40)
srv = subprocess.Popen(["python3", "-B", "app.py", "--host", "127.0.0.1", "--port", str(port)], cwd=REPO, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f"http://127.0.0.1:{port}"
def req(method, path, body=None, headers=None):
    h = {"Origin": base, "Content-Type": "application/json", **(headers or {})}
    r = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")
try:
    for _ in range(150):
        try:
            if urllib.request.urlopen(base + "/api/health", timeout=2).status == 200: break
        except Exception: time.sleep(0.2)
    time.sleep(2)
    from ui.civic_agencies import geo
    nura = [y for y, v in geo.yards().items() if v["district"] == "nura"]
    esil = [y for y, v in geo.yards().items() if v["district"] == "esil"]
    dev, other = "device-r17-yard-01", "device-r17-yard-02"
    print("before:", req("GET", "/api/civic/v2/incidents/updates", headers={"X-Birge-Device": dev})[1].get("zone_known"))
    print("join nura:", req("POST", f"/api/civic/v2/together/yards/{nura[0]}/join", {"device_id": dev}, {"X-Birge-Device": dev})[0])
    print("join esil:", req("POST", f"/api/civic/v2/together/yards/{esil[0]}/join", {"device_id": other}, {"X-Birge-Device": other})[0])
    st, body = req("GET", "/api/civic/v2/incidents/updates", headers={"X-Birge-Device": dev})
    print("nura resident:", st, body.get("zone_known"), len(body.get("items", [])), [i["incident_id"] for i in body.get("items", [])][:3])
    st, body2 = req("GET", "/api/civic/v2/incidents/updates", headers={"X-Birge-Device": other})
    print("esil resident:", st, body2.get("zone_known"), len(body2.get("items", [])))
    st, notes = req("GET", "/api/civic/v2/notifications", headers={"X-Birge-Device": dev})
    items = notes.get("items") or notes.get("data", {}).get("items") or []
    r17 = [i for i in items if i.get("module") == "R17" or str(i.get("id", "")).startswith("incident.")]
    print("R06 notifications:", st, len(items), "R17:", len(r17), [i.get("title_ru", "")[:60] for i in r17][:2])
finally:
    srv.terminate()
