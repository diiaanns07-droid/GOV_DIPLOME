import subprocess, time, json, urllib.request, concurrent.futures as cf, os
env = dict(os.environ, OPENAI_API_KEY="", OPENAI_MODEL="")
p = subprocess.Popen(["python3","-B","app.py","--host","127.0.0.1","--port","8612"], cwd="/home/claude/stupits",
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
B="http://127.0.0.1:8612"
def call(path, body=None, headers=None, timeout=60):
    req = urllib.request.Request(B+path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type":"application/json", **(headers or {})}, method="GET" if body is None else "POST")
    t=time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, json.loads(r.read()), time.perf_counter()-t
    except urllib.error.HTTPError as e: return e.code, e.read()[:200].decode(errors="replace"), time.perf_counter()-t
out={}
try:
    for _ in range(30):
        try: out["health"]=call("/api/health",timeout=2)[:2]; break
        except Exception: time.sleep(0.3)
    s,d,t=call("/api/bootstrap"); out["bootstrap"]={"status":s,"keys":list(d)[:15],"t":round(t,3)}
    s,d,t=call("/api/optimize",{"top_n":1}); out["optimize"]={"status":s,"best":d["results"][0]["score"],"stats":d["stats"],"wall":round(t,2)}
    plan=[{"measure":"M7","district":"nura"},{"measure":"M8","district":"nura"},{"measure":"M10","district":"nura"},{"measure":"M12","district":None},{"measure":"M5","district":"saryarka"}]
    s,d,t=call("/api/simulate",{"decisions":plan}); out["simulate_tz_example"]={"status":s,"score":d.get("score"),"wall":round(t,3)}
    out["foreign_host"]=call("/api/simulate",{"decisions":plan},headers={"Host":"evil.example"})[:2]
    s,d,t=call("/api/advisor",{"question":"Почему Нура важна?","decisions":[]},timeout=30)
    out["advisor_nokey"]={"status":s,"keys":list(d)[:10] if isinstance(d,dict) else d,"wall":round(t,2)}
    t=time.perf_counter()
    with cf.ThreadPoolExecutor(4) as ex: rs=list(ex.map(lambda _: call("/api/optimize",{"top_n":1})[2], range(4)))
    out["optimize_x4_parallel"]={"each":[round(x,2) for x in rs],"total_wall":round(time.perf_counter()-t,2)}
finally:
    p.terminate(); p.wait(5)
print(json.dumps(out,ensure_ascii=False,indent=1))
