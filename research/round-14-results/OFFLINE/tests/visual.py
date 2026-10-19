import asyncio, json, time, pathlib
import os, sys
from playwright.async_api import async_playwright
from offline_bridge import install_bridge, wait_js
ROOT=pathlib.Path(os.environ.get('BIRGE_OFFLINE_ROOT', pathlib.Path(__file__).resolve().parents[4]))
OUT=ROOT/'research/round-14-results/OFFLINE/screens/visual'
OUT.mkdir(parents=True,exist_ok=True)
REPORT=[]
STATE="""() => { const m=map,s=m.getStyle(),layers=s.layers||[], ids=layers.filter(l=>l.type==='fill-extrusion').map(l=>l.id); const b=window.CivicShell.build3d, p=b.getState().proposals.filter(p=>p.geometry.type==='Point'); return {offline:!navigator.onLine,basemap:BirgeOffline.state(),labels:m.queryRenderedFeatures({layers:layers.filter(l=>l.id.startsWith('offline-label-')).map(l=>l.id)}).map(f=>({layer:f.layer.id,name:f.properties.name,ru:f.properties['name:ru']})).slice(0,80),labelExpressions:layers.filter(l=>l.id.startsWith('offline-label-')).map(l=>({id:l.id,text:l.layout['text-field']})),center:m.getCenter(),zoom:m.getZoom(),pitch:m.getPitch(),bearing:m.getBearing(),styleLoaded:m.isStyleLoaded(),tilesLoaded:m.areTilesLoaded(),sources:Object.fromEntries(Object.entries(s.sources).map(([k,v])=>[k,{type:v.type,url:v.url,tiles:v.tiles}])),extrusionLayers:layers.filter(l=>l.type==='fill-extrusion'),buildings:m.queryRenderedFeatures({layers:ids}).map(f=>({layer:f.layer.id,height:f.properties.render_height||f.properties.height})).slice(0,40),buildingCount:m.queryRenderedFeatures({layers:ids}).length,heat:window.CivicShell.heat.state(),anchors:p.map(p=>{const a=m.project(p.geometry.coordinates),c=b._project(p.id,[0,0,0]); return {id:p.id,coords:p.geometry.coordinates,map:a,three:c,errorPx:c?Math.hypot(a.x-c.x,a.y-c.y):null};})}; }"""
async def main():
 async with async_playwright() as pw:
  browser=await pw.chromium.launch()
  for width,height in [(1366,768),(375,812)]:
   for lang in ['ru','kk']:
    tag=f'{width}-{lang}'; t=time.perf_counter()
    ctx=await browser.new_context(viewport={'width':width,'height':height},is_mobile=width<761,has_touch=width<761,locale='kk-KZ' if lang=='kk' else 'ru-RU',device_scale_factor=1)
    network=[];await install_bridge(ctx,'http://127.0.0.1:8613',network)
    page=await ctx.new_page(); page.set_default_timeout(7000); errors=[]; responses=[]
    page.on('console',lambda m:errors.append({'kind':m.type,'text':m.text}) if m.type in ['error','warning'] else None)
    page.on('pageerror',lambda e:errors.append({'kind':'pageerror','text':str(e)}))
    page.on('requestfailed',lambda r:errors.append({'kind':'requestfailed','url':r.url,'error':r.failure}))
    page.on('response',lambda r:responses.append({'url':r.url,'status':r.status}) if 'openfreemap' in r.url else None)
    item={'profile':tag,'steps':[]};REPORT.append(item)
    async def header(selector):
     loc=page.locator('#birge-header '+selector)
     if not await loc.is_visible():await page.locator('.birge-menu-btn').click()
     await loc.click();await page.wait_for_timeout(300)
    async def shot(name):
     f=f'{tag}-{name}.jpg';await page.screenshot(path=str(OUT/f),type='jpeg',quality=85)
     state=await page.evaluate(STATE)
     item['steps'].append({'name':name,'file':f,'state':state,'text':(await page.locator('body').inner_text())[:14000]})
     (OUT/'VISUAL.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding='utf-8')
     print(json.dumps({'profile':tag,'step':name,'buildings':state['buildingCount'],'pitch':state['pitch']},ensure_ascii=False),flush=True)
    try:
     await page.goto('http://127.0.0.1:8613/',wait_until='load')
     item['browser']=browser.version
     item['navigation']=await page.evaluate('() => performance.getEntriesByType("navigation")[0].toJSON()')
     await wait_js(page,'() => window.CivicShell?.heat?.state().status === "ready" && window.CivicShell?.build3d?.getState().phase === "ready" && map.isStyleLoaded() && map.areTilesLoaded()',timeout=45000)
     item['initial_ready_seconds']=round(time.perf_counter()-t,3)
     await header(f'[data-lang={lang}]');await header('[data-mode=akimat]');await page.wait_for_timeout(500)
     await shot('00-initial')
     if not await page.locator('.civic-explore-row select').is_visible():await page.locator('.civic-explore-toggle').click()
     await page.locator('.civic-explore-row select').select_option('nura');await page.wait_for_timeout(1100)
     await page.evaluate('() => map.jumpTo({center:[71.406553,51.131155],zoom:16.7,pitch:0,bearing:0})')
     await page.wait_for_timeout(2500);await shot('01-real-basemap')
     await page.locator('#toggle-3d').click();await page.wait_for_timeout(2200);await shot('02-real-buildings-3d')
     # Street centreline visual comparison at three locations; no app geometry is replaced.
     for i,p in enumerate([[71.369041,51.1364283],[71.402,51.131],[71.409,51.127]]):
      await page.evaluate('(p)=>map.jumpTo({center:p,zoom:16.5,pitch:0,bearing:0})',p)
      await page.wait_for_timeout(1300);await shot(f'03-street-{i+1}')
     # Seeded proposal, ground anchor vs MapLibre projection at multiple camera angles.
     for pitch,bearing in [(0,0),(45,-16),(60,40)]:
      await page.evaluate('(v)=>map.jumpTo({center:[71.36554,51.139097],zoom:18,pitch:v[0],bearing:v[1]})',[pitch,bearing])
      await page.wait_for_timeout(1500);await shot(f'04-anchor-{pitch}')
     # Real UI controls for category/period filters. Record failures without forcing hidden controls.
     try:
      if width<761 and not await page.locator('[data-cats-toggle]').is_visible():await page.locator('#civic-sheet-handle').click()
      await page.locator('[data-cats-toggle]').click()
      await page.locator('[data-cat=lighting]').click()
      await page.locator('[data-days="30"]').click();await page.wait_for_timeout(800);await shot('05-lighting-30days')
      await page.locator('[data-reset]').click();await page.wait_for_timeout(800);await shot('06-filters-reset')
     except Exception as e:item['filter_error']=str(e)[:500];await shot('05-filter-blocked')
     # Scroll the dashboard to capture more than the four KPI tiles.
     await header('[data-section=day]');await page.wait_for_timeout(1500);await shot('07-day-top')
     await page.mouse.move(width//2,height//2);await page.mouse.wheel(0,640);await page.wait_for_timeout(500);await shot('08-day-bottom')
    except Exception as e:
     item['error']=str(e)[:1000]
     try:await shot('99-blocked')
     except:pass
    item['duration_seconds']=round(time.perf_counter()-t,2);item['errors']=errors;item['tile_responses']=responses;item['network']=network
    await ctx.close()
    (OUT/'VISUAL.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding='utf-8')
  await browser.close()
asyncio.run(main())
