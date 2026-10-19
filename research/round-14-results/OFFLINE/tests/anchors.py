import asyncio,json,pathlib
import os, sys
from playwright.async_api import async_playwright
from offline_bridge import install_bridge,wait_js
ROOT=pathlib.Path(os.environ.get('BIRGE_OFFLINE_ROOT', pathlib.Path(__file__).resolve().parents[4]))
OUT=ROOT/'research/round-14-results/OFFLINE/screens/anchors';OUT.mkdir(parents=True,exist_ok=True)
created=json.loads((OUT.parent/'extra/EXTRA.json').read_text(encoding='utf-8'))
async def main():
 result=[]
 async with async_playwright() as pw:
  browser=await pw.chromium.launch()
  for item in created:
   width,lang=item['profile'].split('-');width=int(width);height=768 if width==1366 else 812
   proposal=next(s['detail']['new'] for s in item['steps'] if s['name']=='08-project-placed')
   ctx=await browser.new_context(viewport={'width':width,'height':height},is_mobile=width<761,has_touch=width<761,service_workers='block')
   network=[];await install_bridge(ctx,'http://127.0.0.1:8613',network);page=await ctx.new_page()
   await page.goto('http://127.0.0.1:8613/?offline=1&lang='+lang)
   await wait_js(page,'() => window.CivicShell?.build3d?.getState().phase === "ready" && mapReady')
   target=page.locator('#birge-header [data-mode=akimat]')
   if not await target.is_visible():await page.locator('.birge-menu-btn').click()
   await target.click();await page.wait_for_timeout(600)
   await page.locator('.birge-b3d-toggle').click();await page.locator('.birge-b3d-toggle').click()
   await page.wait_for_timeout(600)
   row={'profile':item['profile'],'proposal_id':proposal['id'],'steps':[],'network':network};result.append(row)
   for pitch,bearing in [(0,0),(45,-16),(60,40)]:
    await page.evaluate('(v)=>{map.stop();map.jumpTo({center:v.p,zoom:18,pitch:v.pitch,bearing:v.bearing});}',{'p':proposal['geometry']['coordinates'],'pitch':pitch,'bearing':bearing})
    await page.wait_for_timeout(1400)
    state=await page.evaluate('''p=>{const q=window.CivicShell.build3d.getState().proposals.find(q=>q.id===p.id);if(!q)throw Error('new proposal absent from real API');const a=map.project(q.geometry.coordinates),b=window.CivicShell.build3d._project(q.id,[0,0,0]);return{coordinates:q.geometry.coordinates,offline:!navigator.onLine,pitch:map.getPitch(),map:a,three:b,errorPx:Math.hypot(a.x-b.x,a.y-b.y),catalog:document.querySelector('#birge-build3d-root').dataset.catalog};}''',proposal)
    filename=f'{item["profile"]}-project-pitch-{pitch}.jpg'
    await page.screenshot(path=str(OUT/filename),type='jpeg',quality=85)
    row['steps'].append({'file':filename,'state':state})
   await ctx.close();print(item['profile']+' anchors complete',flush=True)
  await browser.close()
 (OUT/'ANCHORS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
asyncio.run(main())
