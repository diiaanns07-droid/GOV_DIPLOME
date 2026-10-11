import asyncio,json,os,pathlib,subprocess,time,urllib.request,secrets
from playwright.async_api import async_playwright
from offline_bridge import install_bridge,wait_js
ROOT=pathlib.Path(r'C:\Users\LEGION\Desktop\hackalem\birge-final')
OUT=pathlib.Path(__file__).parent/'final-evidence/checks';OUT.mkdir(parents=True,exist_ok=True)
PY=ROOT/'.venv/Scripts/python.exe';BASE='http://127.0.0.1:8616'
env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',CIVIC_DEMO='1',CIVIC_DB_PATH=str(ROOT/f'.runtime/final-checks-{int(time.time())}.sqlite3'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OPENAI_API_KEY='')
for cmd in [['init'],['seed-demo','--package','data/civic/astana/demo_synthetic.json']]:subprocess.run([str(PY),'-B','-m','ui.civic_store',*cmd],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
password=secrets.token_urlsafe(20)+'Aa1!'
subprocess.run([str(PY),'-B','-m','ui.civic_store','create-editor','qa-staff','--password-stdin'],cwd=ROOT,env=env,input=password+'\n',text=True,encoding='utf-8',check=True,stdout=subprocess.DEVNULL)
log=(OUT/'server.txt').open('w',encoding='utf-8');server=subprocess.Popen([str(PY),'-B','app.py','--host','127.0.0.1','--port','8616'],cwd=ROOT,env=env,stdout=log,stderr=log)
RESULT=[]
async def main():
 for i in range(100):
  try:urllib.request.urlopen(BASE+'/api/health',timeout=1);break
  except Exception:await asyncio.sleep(.25)
 async with async_playwright() as pw:
  browser=await pw.chromium.launch()
  for offline in [False,True]:
   for w,h,lang in [(1366,768,'ru'),(1366,768,'kk'),(375,812,'ru'),(375,812,'kk')]:
    name=f'{"offline" if offline else "online"}-{w}-{lang}'
    d={'profile':name,'network':[],'errors':[]};RESULT.append(d)
    ctx=await browser.new_context(viewport={'width':w,'height':h},is_mobile=w==375,has_touch=w==375,locale='ru-RU' if lang=='ru' else 'kk-KZ',service_workers='block')
    await ctx.add_init_script('localStorage.setItem("birge.lang",'+json.dumps(lang)+');')
    if offline:await install_bridge(ctx,BASE,d['network'])
    page=await ctx.new_page();page.set_default_timeout(10000)
    if not offline:page.on('response',lambda r:d['network'].append({'url':r.url,'status':r.status}))
    page.on('pageerror',lambda e:d['errors'].append({'type':'pageerror','text':str(e)}))
    page.on('console',lambda m:d['errors'].append({'type':m.type,'text':m.text}) if m.type in ['warning','error'] else None)
    page.on('requestfailed',lambda r:d['errors'].append({'type':'requestfailed','url':r.url,'text':r.failure}))
    try:
     t=time.monotonic();await page.goto(BASE+'/')
     await wait_js(page,'() => window.CivicShell?.heat?.state().status==="ready" && window.CivicShell?.build3d?.getState().phase==="ready" && map.areTilesLoaded()',timeout=60000)
     d['ready_seconds']=round(time.monotonic()-t,3)
     d['navigation']=await page.evaluate('() => {let p=performance.getEntriesByType("navigation")[0];return{dom_ms:p.domContentLoadedEventEnd,load_ms:p.loadEventEnd}}')
     d['automatic_mode']=await page.evaluate('() => ({navigatorOnline:navigator.onLine,basemap:BirgeOffline.state(),lang:document.documentElement.lang})')
     await page.screenshot(path=str(OUT/(name+'-overview.png')))
     await page.evaluate('() => map.jumpTo({center:[71.406553,51.131155],zoom:16.7,pitch:50,bearing:-15})')
     await page.wait_for_timeout(1800)
     await wait_js(page,'() => map.areTilesLoaded()')
     d['map']=await page.evaluate('() => {const ls=map.getStyle().layers;return{pitch:map.getPitch(),buildingParts:map.queryRenderedFeatures({layers:ls.filter(l=>l.type==="fill-extrusion").map(l=>l.id)}).length,labels:map.queryRenderedFeatures({layers:ls.filter(l=>l.id.startsWith("offline-label-")).map(l=>l.id)}).length,renderer:map.getCanvas().getContext("webgl2")?.getParameter(7937)}}')
     await page.screenshot(path=str(OUT/(name+'-buildings.png')))
     if w==375:
      await page.locator('.bc-fab').click()
      await page.evaluate('() => {map.jumpTo({center:[71.406553,51.131155],zoom:17,pitch:0,bearing:0});map.panBy([0,140],{duration:0});}');await page.wait_for_timeout(1400)
      await wait_js(page,'() => !!CivicShell.heat.badges().find(x=>x.key==="object:osm-node-4109037549")',timeout=15000)
      point=await page.evaluate('() => CivicShell.heat.badges().find(x=>x.key==="object:osm-node-4109037549")')
      assert point
      await page.mouse.click(point['cx'],point['cy']);await page.locator('.bc-option--first').wait_for();await page.locator('.bc-option--first').click()
      await page.locator('#bc-text').fill('Аялдамада жарық жоқ, вечером на остановке темно');await page.wait_for_timeout(2200)
      d['complaint_header_visibility']=await page.locator('.bc-title').evaluate('(e)=>{let r=e.getBoundingClientRect(),p=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return{title:e.innerText,uncovered:e===p||e.contains(p),top:p?.className}}')
      await page.screenshot(path=str(OUT/(name+'-resident-form.png')))
      await page.locator('.bc-send').click();await page.locator('.bc-panel[data-step="4"]').wait_for();await page.screenshot(path=str(OUT/(name+'-similar.png')))
      await page.locator('.bc-different').click();await page.locator('.bc-panel[data-step="5"]').wait_for();await page.keyboard.press('Escape');await page.wait_for_timeout(1200)
      d['rapid_close_test']='separate complaint -> success -> immediate Escape'
      await page.screenshot(path=str(OUT/(name+'-after-close.png')))
    except Exception as e:
     d['failure']=type(e).__name__+': '+str(e);await page.screenshot(path=str(OUT/(name+'-failure.png')))
    await ctx.close();(OUT/'CHECKS.json').write_text(json.dumps(RESULT,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in d.items() if k not in ['network','errors']},ensure_ascii=False),flush=True)
  await browser.close()
  request=await pw.request.new_context()
  summary=await (await request.get(BASE+'/api/civic/v2/complaints/summary?target_id=osm-node-4109037549&category=lighting&days=14')).json()
  summary=summary.get('data',summary);cid=summary['top']['id']
  heat=await (await request.get(BASE+'/api/civic/v2/heat?bbox=71.375,51.115,71.420,51.140&category=lighting&days=14&zoom=17')).json()
  heat=heat.get('data',heat);stop_heat=next(x for x in heat['items'] if x['target']['id']=='osm-node-4109037549')
  (OUT/'COUNTS_COMPARISON.json').write_text(json.dumps({'same_target':'osm-node-4109037549','category':'lighting','days':14,'complaint_summary_reporters':summary['reporters'],'heat_count':stop_heat['count'],'heat':stop_heat},ensure_ascii=False,indent=2),encoding='utf-8')
  public=await (await request.get(BASE+'/api/civic/v2/complaints/'+cid)).json();public=public.get('data',public)['complaint']
  auth=await request.post(BASE+'/api/civic/v1/session/login',data={'username':'qa-staff','password':password},headers={'Origin':BASE});assert auth.status==200
  staff=await (await request.get(BASE+'/api/civic/v2/complaints/'+cid)).json();staff=staff.get('data',staff)['complaint']
  proof={'complaint_id':cid,'public_has_reporters':'reporters' in public,'public_reporters':public.get('reporters'),'staff_has_reporters':'reporters' in staff,'staff_metoo':staff.get('metoo'),'summary_reporters':summary['reporters'],'ui_gate':'match.reporters > 0','ui_result_if_staff':'step 4 skipped; sends a new complaint'}
  (OUT/'R09_AUTH.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(proof),flush=True)
  await request.dispose()
try:asyncio.run(main())
finally:server.terminate();server.wait(timeout=20);log.close()
