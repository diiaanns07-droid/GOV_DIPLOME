import os,pathlib,secrets,subprocess,time,json,urllib.request,sys
import playwright
ROOT=pathlib.Path(r'C:\Users\LEGION\Desktop\hackalem\birge-final')
WORK=pathlib.Path(__file__).parent
OUT=WORK/'final-evidence';OUT.mkdir(exist_ok=True)
PY=ROOT/'.venv/Scripts/python.exe'
NODE=pathlib.Path(playwright.__file__).parent/'driver/node.exe'
env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',CIVIC_DEMO='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OPENAI_API_KEY='',PLAYWRIGHT_NODE=str(NODE.parent/'package'),FINAL_ORIGIN='http://127.0.0.1:8614')
summary=[]
for mode in ['online','offline']:
 folder=OUT/mode;folder.mkdir(exist_ok=True)
 db=ROOT/f'.runtime/final-r10-{mode}.sqlite3'
 if db.exists():raise RuntimeError('Refusing to reuse a test DB: '+str(db))
 env.update(CIVIC_DB_PATH=str(db),FINAL_OFFLINE='1' if mode=='offline' else '0',FINAL_CAPTURE=str(folder/'browser.jsonl'))
 password=secrets.token_urlsafe(20)+'Aa1!'
 for command in [['init'],['seed-demo','--package','data/civic/astana/demo_synthetic.json'],['create-editor','final-r10','--password-stdin']]:
  subprocess.run([str(PY),'-B','-m','ui.civic_store','--db',str(db),*command],input=password+'\n' if command[0]=='create-editor' else None,text=True,encoding='utf-8',cwd=ROOT,env=env,stdout=subprocess.DEVNULL,check=True)
 with (folder/'server.log').open('w',encoding='utf-8') as log:
  server=subprocess.Popen([str(PY),'-B','app.py','--host','127.0.0.1','--port','8614'],cwd=ROOT,env=env,stdout=log,stderr=log)
  try:
   for i in range(100):
    try:
     urllib.request.urlopen(env['FINAL_ORIGIN']+'/api/health',timeout=1);break
    except Exception:time.sleep(.3)
   else:raise RuntimeError('Test server failed')
   t=time.monotonic()
   with (folder/'runner.txt').open('w',encoding='utf-8') as log2:
    result=subprocess.run([str(NODE),'--require',str(WORK/'final_capture.cjs'),str(ROOT/'tests/e2e/demo_flow.cjs'),'--root',str(ROOT),'--url',env['FINAL_ORIGIN']+'/','--user','final-r10','--pass',password,'--out',str(folder/'e2e')],cwd=ROOT,env=env,stdout=log2,stderr=subprocess.STDOUT)
   summary.append({'mode':mode,'exit':result.returncode,'seconds':round(time.monotonic()-t,2)})
   print(json.dumps(summary[-1]),flush=True)
   if mode=='online':
    with (folder/'ux-runner.txt').open('w',encoding='utf-8') as log2:
     subprocess.run([str(NODE),'--require',str(WORK/'final_capture.cjs'),str(ROOT/'tests/e2e/ux_screens.cjs'),'--screens',str(ROOT/'tests/e2e/screens_build.json'),'--base',env['FINAL_ORIGIN']+'/','--out',str(folder/'ux')],cwd=ROOT,env=env,stdout=log2,stderr=subprocess.STDOUT)
  finally:server.terminate();server.wait(timeout=20)
(OUT/'R10_RUNS.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
