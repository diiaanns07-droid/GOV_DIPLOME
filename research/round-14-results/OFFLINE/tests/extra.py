import asyncio,json,time,pathlib,secrets,subprocess,os
import os, sys
from playwright.async_api import async_playwright
from offline_bridge import install_bridge, wait_js
ROOT=pathlib.Path(os.environ.get('BIRGE_OFFLINE_ROOT', pathlib.Path(__file__).resolve().parents[4]))
OUT=ROOT/'research/round-14-results/OFFLINE/screens/extra'
OUT.mkdir(parents=True,exist_ok=True)
RESULT=[]; PASSWORD=secrets.token_urlsafe(20)+'Aa1!'
env=os.environ.copy();env['PYTHONUTF8']='1'
subprocess.run([os.environ.get('BIRGE_SERVER_PY',sys.executable),'-B','-m','ui.civic_store','--db','.runtime/offline-final.sqlite3','create-editor','offline-extra','--password-stdin'],input=PASSWORD+'\n',text=True,encoding='utf-8',cwd=ROOT,env=env,stdout=subprocess.DEVNULL,check=True)
SHOW="""async p => { map.jumpTo({center:p,zoom:17,pitch:0,bearing:0});const wait=ms=>new Promise(r=>setTimeout(r,ms));await wait(600);const c=map.getCanvas(),r=c.getBoundingClientRect();let want;for(let y=innerHeight*.40;y>r.top+70&&!want;y-=20)for(const fx of [.5,.3,.7])if(document.elementFromPoint(innerWidth*fx,y)===c){want={x:innerWidth*fx,y};break;}if(want)for(let i=0;i<2;i++){let q=map.project(p);map.panBy([q.x+r.left-want.x,q.y+r.top-want.y],{duration:0});await wait(200);}await wait(500);let q=map.project(p),x=q.x+r.left,y=q.y+r.top;for(let rad=0;rad<=60;rad+=10)for(const [dx,dy]of [[0,rad],[rad,0],[-rad,0],[0,-rad]])if(document.elementFromPoint(x+dx,y+dy)===c)return{x:x+dx,y:y+dy,point:map.unproject([q.x+dx,q.y+dy]).toArray()};return{x,y,blocked:true};}"""
async def main():
 async with async_playwright() as pw:
  browser=await pw.chromium.launch()
  for vi,(w,h,lang) in enumerate([(1366,768,'ru'),(1366,768,'kk'),(375,812,'ru'),(375,812,'kk')]):
   ctx=await browser.new_context(viewport={'width':w,'height':h},is_mobile=w<761,has_touch=w<761,locale='kk-KZ' if lang=='kk' else 'ru-RU',device_scale_factor=1)
   network=[];await install_bridge(ctx,'http://127.0.0.1:8613',network)
   page=await ctx.new_page();page.set_default_timeout(9000)
   item={'profile':f'{w}-{lang}','steps':[],'errors':[],'network':network}; RESULT.append(item)
   page.on('pageerror',lambda e:item['errors'].append({'kind':'pageerror','text':str(e)}))
   page.on('console',lambda m:item['errors'].append({'kind':m.type,'text':m.text}) if m.type in ['error','warning'] else None)
   async def save(name,detail=None):
    f=f'{w}-{lang}-{name}.jpg';t=time.perf_counter();await page.screenshot(path=str(OUT/f),type='jpeg',quality=85,timeout=15000)
    item['steps'].append({'name':name,'file':f,'detail':detail,'text':(await page.locator('body').inner_text())[:12000],'screenshot_seconds':round(time.perf_counter()-t,2)})
    (OUT/'EXTRA.json').write_text(json.dumps(RESULT,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'{w}-{lang}: {name}',flush=True)
   async def header(selector):
    loc=page.locator('#birge-header '+selector)
    if not await loc.is_visible():await page.locator('.birge-menu-btn').click()
    await loc.click();await page.wait_for_timeout(400)
   try:
    await page.goto('http://127.0.0.1:8613/');await wait_js(page,'() => window.CivicShell?.heat?.state().status === "ready" && window.CivicShell?.build3d?.getState().phase === "ready"',timeout=45000)
    await header(f'[data-lang={lang}]');await header('[data-mode=resident]')
    if vi==0:
     await page.reload()
     await wait_js(page,'() => window.CivicShell?.heat?.state().status === "ready"')
     await page.keyboard.press('Tab')
     first=await page.evaluate('() => ({tag:document.activeElement.tagName,cls:document.activeElement.className,text:document.activeElement.textContent})')
     await page.keyboard.press('Enter')
     item['keyboard_skip']={'first_tab':first,'after_enter':await page.evaluate('() => document.activeElement.className')}
    await page.locator('.bc-fab').click();await save('01-mixed-location')
    xy=await page.evaluate(SHOW,[71.406553,51.131155]);await page.mouse.click(xy['x'],xy['y'])
    await page.locator('.bc-option--first').wait_for();await save('02-mixed-target',xy);await page.locator('.bc-option--first').click()
    async with page.expect_response(lambda r:'/api/civic/v2/classify' in r.url and r.request.method=='POST',timeout=15000) as pred:
     await page.locator('#bc-text').fill('Аялдамада жарық жоқ, вечером на остановке темно')
    prediction=await (await pred.value).json();await page.wait_for_timeout(500)
    await save('03-mixed-category',prediction)
    await page.locator('.bc-send').click();await page.wait_for_timeout(1000)
    if await page.locator('.bc-different').is_visible():
     await save('04-mixed-similar');await page.locator('.bc-different').click()
    await page.locator('.bc-panel[data-step="5"]').wait_for();await save('05-mixed-sent')
    await page.keyboard.press('Escape')
    await header('[data-mode=akimat]')
    # R10 already tested login through the UI. Here bootstrap only the disposable local demo session.
    await page.evaluate('async v=>window.CivicShell.api.login(v.user,v.pass)',{'user':'offline-extra','pass':PASSWORD})
    if not await page.locator('.civic-explore-row select').is_visible():await page.locator('.civic-explore-toggle').click()
    await page.locator('.civic-explore-row select').select_option('nura');await page.wait_for_timeout(900)
    await save('06-catalog-after-district',{'sheet':await page.locator('#civic-panel').get_attribute('data-sheet')})
    if not await page.locator('#birge-build3d-root [data-kind=square]').is_visible():await page.locator('.birge-b3d-toggle').click()
    await page.locator('#birge-build3d-root [data-kind=square]').click()
    xy=await page.evaluate(SHOW,[71.4148,51.1131+.0007*vi]);await page.mouse.move(xy['x'],xy['y']);await page.mouse.click(xy['x'],xy['y'])
    await page.locator('#birge-build3d-root [data-action=rotate-right]').click();await page.wait_for_timeout(500)
    before=await page.evaluate('() => window.CivicShell.build3d.getState()')
    await save('07-project-rotate',before)
    await page.locator('#birge-build3d-root [data-action=place]').click();await page.wait_for_timeout(1800)
    after=await page.evaluate('() => window.CivicShell.build3d.getState()')
    old={p['id'] for p in before['proposals']};new=next((p for p in after['proposals'] if p['id'] not in old),None)
    await save('08-project-placed',{'new':new,'state':after})
    if not new:raise RuntimeError('No newly placed proposal in build3d state')
    if await page.locator('#birge-build3d-root').get_attribute('data-catalog')=='open':await page.locator('.birge-b3d-toggle').click()
    for pitch,bearing in [(0,0),(45,-16),(60,40)]:
     await page.evaluate('(v)=>map.jumpTo({center:v.p,zoom:18,pitch:v.pitch,bearing:v.bearing})',{'p':new['geometry']['coordinates'],'pitch':pitch,'bearing':bearing})
     await page.wait_for_timeout(1000)
     d=await page.evaluate('(p)=>{const a=map.project(p.geometry.coordinates),b=window.CivicShell.build3d._project(p.id,[0,0,0]);return{map:a,three:b,errorPx:Math.hypot(a.x-b.x,a.y-b.y),pitch:map.getPitch(),bearing:map.getBearing()}}',new)
     await save(f'09-placed-pitch-{pitch}',d)
   except Exception as e:
    item['error']=str(e)[:1400]
    try:await save('99-blocked')
    except:pass
   await ctx.close()
   (OUT/'EXTRA.json').write_text(json.dumps(RESULT,ensure_ascii=False,indent=2),encoding='utf-8')
  await browser.close()
asyncio.run(main())
