"""Real UI demo on a fresh synthetic DB; only camera bookmarks use MapLibre API."""
import asyncio,json,os,pathlib,secrets,subprocess,time,urllib.request,argparse
from playwright.async_api import async_playwright
from offline_bridge import install_bridge,wait_js
ROOT=pathlib.Path(r'C:\Users\LEGION\Desktop\hackalem\birge-final')
WORK=pathlib.Path(__file__).parent
OUT=WORK/'final-evidence'
PY=ROOT/'.venv/Scripts/python.exe'
ORIGIN='http://127.0.0.1:8615'
STOP=[71.406553,51.131155]
PLACE=[71.4148,51.1131]
args=argparse.ArgumentParser();args.add_argument('--rehearsal',action='store_true');args.add_argument('--langs',default='ru,kk');args=args.parse_args()
PAUSE=.25 if args.rehearsal else 1.6

async def perform(lang):
 name=('rehearsal-' if args.rehearsal else 'demo-')+lang
 folder=OUT/name;folder.mkdir(parents=True,exist_ok=True)
 db=ROOT/f'.runtime/{name}-{int(time.time())}.sqlite3'
 env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',CIVIC_DEMO='1',CIVIC_DB_PATH=str(db),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OPENAI_API_KEY='')
 password=secrets.token_urlsafe(20)+'Aa1!'
 for cmd in [['init'],['seed-demo','--package','data/civic/astana/demo_synthetic.json'],['create-editor','demo-operator','--password-stdin']]:
  subprocess.run([str(PY),'-B','-m','ui.civic_store','--db',str(db),*cmd],cwd=ROOT,env=env,input=password+'\n' if cmd[0]=='create-editor' else None,text=True,encoding='utf-8',stdout=subprocess.DEVNULL,check=True)
 log=(folder/'server.txt').open('w',encoding='utf-8')
 server=subprocess.Popen([str(PY),'-B','app.py','--host','127.0.0.1','--port','8615'],cwd=ROOT,env=env,stdout=log,stderr=log)
 result={'language':lang,'rehearsal':args.rehearsal,'offline':True,'steps':[],'errors':[],'network':[]}
 def flush(): (folder/'DEMO.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 try:
  for i in range(100):
   try:urllib.request.urlopen(ORIGIN+'/api/health',timeout=1);break
   except Exception:await asyncio.sleep(.25)
  else:raise RuntimeError('Video server failed')
  async with async_playwright() as pw:
   browser=await pw.chromium.launch()
   options=dict(viewport={'width':1366,'height':768},device_scale_factor=1,locale='ru-RU' if lang=='ru' else 'kk-KZ',service_workers='block')
   if not args.rehearsal:options.update(record_video_dir=str(ROOT/'video/raw'/lang),record_video_size={'width':1366,'height':768})
   ctx=await browser.new_context(**options)
   # Workaround for verified R09 issue: staff_view omits reporters, causing the
   # resident wizard to skip metoo when already signed in. Login at step 5.
   await ctx.add_init_script('localStorage.setItem("birge.lang",'+json.dumps(lang)+');localStorage.setItem("birge.mode","akimat");')
   await install_bridge(ctx,ORIGIN,result['network'])
   page=await ctx.new_page();page.set_default_timeout(10000)
   page.on('pageerror',lambda e:result['errors'].append({'kind':'pageerror','text':str(e),'stack':e.stack}))
   page.on('console',lambda m:result['errors'].append({'kind':m.type,'text':m.text}) if m.type in ['warning','error'] else None)
   started=time.monotonic()
   async def pause(n=1):await page.wait_for_timeout(int(PAUSE*n*1000))
   async def click(selector):
    loc=page.locator(selector).first;await loc.wait_for(state='visible');box=await loc.bounding_box()
    if box:await page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2,steps=12)
    await loc.click();await pause()
   async def shot(name,detail=None):
    await pause();f=name+'.png';await page.screenshot(path=str(folder/f))
    result['steps'].append({'name':name,'file':f,'seconds':round(time.monotonic()-started,2),'detail':detail,'text':(await page.locator('body').inner_text())[:14000]});flush();print(name,lang,flush=True)
   async def camera(p,zoom=17,pitch=0,bearing=0):
    await page.evaluate('(v)=>map.easeTo({center:v.p,zoom:v.zoom,pitch:v.pitch,bearing:v.bearing,offset:[-70,0],duration:1600,essential:true})',dict(p=p,zoom=zoom,pitch=pitch,bearing=bearing))
    await page.wait_for_timeout(1900);await wait_js(page,'() => !map.isMoving() && map.areTilesLoaded()')
   async def badge():
    coords=await page.evaluate('() => CivicShell.heat.badges().find(x=>x.key==="object:osm-node-4109037549")')
    if not coords:raise RuntimeError('Stop badge not visible')
    await page.mouse.move(coords['cx'],coords['cy'],steps=18);await page.mouse.click(coords['cx'],coords['cy']);await pause()
   try:
    await page.goto(ORIGIN+'/')
    await wait_js(page,'() => window.CivicShell?.heat?.state().status==="ready" && window.CivicShell?.build3d?.getState().phase==="ready" && map.areTilesLoaded()',timeout=60000)
    result['initial_ready_seconds']=round(time.monotonic()-started,3)
    await shot('01-overview',await page.evaluate('BirgeOffline.state()'))
    await click('#birge-header [data-lang="'+('kk' if lang=='ru' else 'ru')+'"]');await pause()
    await click('#birge-header [data-lang="'+lang+'"]')
    await camera(STOP,16.7,48,-12);await shot('02-real-buildings')
    await camera(STOP)
    await click('#birge-header [data-mode=resident]')
    await click('.bc-fab');await shot('03-complaint-location')
    await badge();await page.locator('.bc-option--first').wait_for();await shot('04-stop-target');await click('.bc-option--first')
    await page.locator('#bc-text').press_sequentially('Аялдамада жарық жоқ, вечером на остановке темно',delay=65 if not args.rehearsal else 10)
    await wait_js(page,'() => document.querySelector(".bc-send") && !document.querySelector(".bc-send").disabled')
    await page.wait_for_timeout(1200);await shot('05-model-lighting')
    await click('.bc-send');await page.locator('.bc-panel[data-step="4"]').wait_for();await shot('06-similar-three')
    await click('.bc-panel[data-step="4"] .bk-btn--primary');await page.locator('.bc-panel[data-step="5"]').wait_for();await shot('07-metoo-four')
    await click('.bc-close');await click('#birge-header [data-mode=akimat]');await shot('08-heat')
    await click('[data-cats-toggle]');await click('[data-cat=lighting]');await click('[data-days="30"]');await shot('09-lighting-filter')
    await click('[data-reset]')
    await camera([71.3999,51.1267],15.2,0,-15);await shot('10-street-axis')
    await click('#birge-header [data-section=day]');await page.locator('.akim-kpis').wait_for();await shot('11-day-kpi');await pause(2)
    await page.locator('.birge-day').evaluate('(e)=>e.scrollTo({top:Math.min(570,e.scrollHeight),behavior:"smooth"})');await page.wait_for_timeout(1200);await shot('12-day-detail')
    await page.locator('.akim-objects').evaluate('(e)=>e.scrollIntoView({behavior:"smooth",block:"start"})');await page.wait_for_timeout(1400);await shot('12a-day-lagging');await pause(2)
    await click('#birge-header [data-section=map]')
    await click('#civic-staff-button')
    await page.locator('input[autocomplete=username]').fill('demo-operator')
    await page.locator('input[type=password]').fill(password)
    await page.locator('input[type=password]').press('Enter');await pause()
    await page.get_by_role('button',name='Шығу' if lang=='kk' else 'Выйти',exact=True).wait_for()
    await shot('12b-staff-localized')
    await page.get_by_role('button',name='Кабинетті жабу' if lang=='kk' else 'Закрыть кабинет',exact=True).click();await pause()
    await camera(PLACE,17)
    await click('.birge-b3d-toggle');await shot('13-catalog');await click('#birge-build3d-root [data-kind=square]')
    xy=await page.evaluate('(p)=>{const q=map.project(p),r=map.getCanvas().getBoundingClientRect();return{x:q.x+r.left,y:q.y+r.top}}',PLACE)
    await page.mouse.move(xy['x'],xy['y'],steps=18);await pause();await page.mouse.click(xy['x'],xy['y']);await pause()
    await click('#birge-build3d-root [data-action=rotate-right]');await shot('14-preview-rotate')
    before=await page.evaluate('CivicShell.build3d.getState().proposals.map(p=>p.id)')
    await click('#birge-build3d-root [data-action=place]')
    await wait_js(page,'() => CivicShell.build3d.getState().proposals.length > '+str(len(before)))
    new=await page.evaluate('(ids)=>CivicShell.build3d.getState().proposals.find(p=>!ids.includes(p.id))',before)
    result['proposal']=new
    if await page.locator('#birge-build3d-root').get_attribute('data-catalog')=='open':await click('.birge-b3d-toggle')
    await shot('15-project-placed',new)
    await click('#toggle-3d');await pause(2)
    anchor=await page.evaluate('(p)=>{const a=map.project(p.geometry.coordinates),b=CivicShell.build3d._project(p.id,[0,0,0]);return{pitch:map.getPitch(),errorPx:Math.hypot(a.x-b.x,a.y-b.y)}}',new)
    await shot('16-project-3d',anchor)
    await camera(new['geometry']['coordinates'],17.8,60,28);await shot('17-project-angle')
    await click('#birge-header [data-mode=resident]');await camera(new['geometry']['coordinates'],17)
    await click('.b3d-label[data-id="'+new['id']+'"]');await shot('18-project-vote')
    await click('.r06-vote__btn[data-value="1"]');await shot('19-vote-saved')
    await click('[data-action=close-card]');await click('#birge-header [data-mode=akimat]');await camera(STOP)
    await badge();await shot('20-complaint-card')
    if await page.locator('[data-act=take]').is_visible():await click('[data-act=take]')
    await shot('21-in-progress');await click('[data-act=fixed]');await shot('22-fixed-green')
    await page.keyboard.press('Escape');await pause();await click('#birge-header [data-mode=resident]');await click('#birge-header [data-action=mine]')
    await page.locator('.bc-panel[data-step=mine]').wait_for();await shot('23-mine-fixed')
    assert await page.locator('.bc-panel .bk-steps--fixed').count()>0
    await click('.bc-close');await click('#birge-header [data-mode=akimat]');await camera(STOP,16.5,48,-16);await shot('24-finale');await pause(3)
    result['completed']=True
   except Exception as e:
    result['failure']=str(e);await page.screenshot(path=str(folder/'99-failure.png'));raise
   finally:
    result['duration_seconds']=round(time.monotonic()-started,2);flush()
    video=page.video
    await ctx.close()
    if video:
     target=ROOT/'video'/f'Birge_FINAL_{lang.upper()}_1366x768.webm'
     await video.save_as(str(target));result['video']=str(target);result['video_bytes']=target.stat().st_size
    await browser.close();flush()
 finally:server.terminate();server.wait(timeout=20);log.close()

async def main():
 for lang in args.langs.split(','):await perform(lang)
asyncio.run(main())
