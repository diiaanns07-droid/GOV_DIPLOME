import asyncio,json,pathlib,time
import os, sys
from playwright.async_api import async_playwright
from offline_bridge import install_bridge, wait_js
ROOT=pathlib.Path(os.environ.get('BIRGE_OFFLINE_ROOT', pathlib.Path(__file__).resolve().parents[4]))
OUT=ROOT/'research/round-14-results/OFFLINE/screens/modes';OUT.mkdir(parents=True,exist_ok=True)
async def main():
 result=[]
 async with async_playwright() as pw:
  browser=await pw.chromium.launch()
  for name,offline,missing,url in [('automatic-online',False,False,'/'),('automatic-offline',True,False,'/'),('missing-archive',True,True,'/?offline=1')]:
   ctx=await browser.new_context(viewport={'width':1366,'height':768},service_workers='block')
   network=[];await install_bridge(ctx,'http://127.0.0.1:8613',network,offline=offline)
   if missing:
    await ctx.route('**/civic/offline/status.json',lambda route:route.fulfill(status=200,json={'available':False}))
   page=await ctx.new_page();errors=[]
   page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto('http://127.0.0.1:8613'+url)
   await wait_js(page,'mapReady && map.isStyleLoaded() && map.areTilesLoaded()',timeout=40000)
   await page.wait_for_timeout(1800)
   await page.evaluate('map.stop();map.jumpTo({center:[71.406553,51.131155],zoom:16.5,pitch:52,bearing:-16})')
   await page.wait_for_timeout(1500)
   state=await page.evaluate('''() => ({offline:!navigator.onLine,basemap:BirgeOffline.state(),mapReady,sources:Object.keys(map.getStyle().sources),status:document.querySelector('#map-status').textContent,buildings:map.getLayer('akim-3d')?map.queryRenderedFeatures({layers:['akim-3d']}).length:0})''')
   await page.screenshot(path=str(OUT/(name+'.jpg')),type='jpeg',quality=85)
   item={'mode':name,'state':state,'errors':errors,'network':network,'expected_missing_status_mock':missing};result.append(item)
   if not missing:
    await page.locator('#birge-header [data-lang=kk]').click();await page.wait_for_timeout(500)
    item['kk']=await page.evaluate("({lang:document.documentElement.lang,expression:map.getLayoutProperty('offline-label-road','text-field')})")
    await page.screenshot(path=str(OUT/(name+'-kk.jpg')),type='jpeg',quality=85)
   item['pass']=bool(state['basemap']['active']!=missing and state['offline']==offline and not errors and not any(n.get('blocked') for n in network) and (missing or state['buildings']>0))
   await ctx.close();print(json.dumps({'mode':name,'pass':item['pass'],'state':state},ensure_ascii=False),flush=True)
  await browser.close()
 (OUT/'MODES.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 if not all(i['pass'] for i in result):raise SystemExit(1)
asyncio.run(main())
