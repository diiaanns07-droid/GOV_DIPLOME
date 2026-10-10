import json,os,pathlib,secrets,subprocess,time,sys
import playwright
WORK=pathlib.Path(__file__).resolve().parent
ROOT=pathlib.Path(os.environ.get('BIRGE_OFFLINE_ROOT', pathlib.Path(__file__).resolve().parents[4]))
OUT=ROOT/'research/round-14-results/OFFLINE/screens/r10-final'
OUT.mkdir(parents=True,exist_ok=True)
PY=pathlib.Path(os.environ.get('BIRGE_SERVER_PY',sys.executable))
NODE=pathlib.Path(playwright.__file__).parent/'driver/node.exe'
env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',PLAYWRIGHT_NODE=str(NODE.parent/'package'),OFFLINE_ORIGIN='http://127.0.0.1:8613',OFFLINE_CAPTURE=str(OUT/'raw-browser.jsonl'))
password=secrets.token_urlsafe(22)+'Aa1!'
subprocess.run([str(PY),'-B','-m','ui.civic_store','--db','.runtime/offline-final.sqlite3','create-editor','offline-r10','--password-stdin'],input=password+'\n',text=True,encoding='utf-8',cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
start=time.perf_counter()
with (OUT/'runner.txt').open('w',encoding='utf-8') as f:
 p=subprocess.run([str(NODE),'--require',str(WORK/'offline_capture.cjs'),str(ROOT/'tests/e2e/demo_flow.cjs'),'--root',str(ROOT),'--url','http://127.0.0.1:8613/?offline=1','--user','offline-r10','--pass',password,'--out',str(OUT)],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
print(json.dumps({'exit':p.returncode,'seconds':round(time.perf_counter()-start,3),'out':str(OUT)}))
