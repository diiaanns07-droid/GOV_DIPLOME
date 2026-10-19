import asyncio,json,pathlib,secrets
import os, sys
from playwright.async_api import async_playwright
from offline_bridge import install_bridge,wait_js
ROOT=pathlib.Path(os.environ.get('BIRGE_OFFLINE_ROOT', pathlib.Path(__file__).resolve().parents[4]))
OUT=ROOT/'research/round-14-results/OFFLINE/screens/heat';OUT.mkdir(parents=True,exist_ok=True)
BASE='http://127.0.0.1:8613'
async def main():
 result={}
 async with async_playwright() as pw:
  browser=await pw.chromium.launch();ctx=await browser.new_context(viewport={'width':1366,'height':768},service_workers='block')
  network=[];await install_bridge(ctx,BASE,network);page=await ctx.new_page()
  await page.goto(BASE+'/?offline=1')
  await wait_js(page,'() => window.CivicShell?.heat?.state().status === "ready"')
  await page.wait_for_timeout(1500)
  tag='offline-heat-'+secrets.token_hex(6)
  body={'text':'Синтетическая проверка офлайн-карты: у остановки погасло освещение','lang':'ru','category':'lighting','category_source':'resident','point':[71.406553,51.131155],'target':{'kind':'object','id':'osm-node-4109037549','label_ru':'Остановка «Хан Шатыр»'},'device_id':tag,'demo':True}
  response=await ctx.request.post(BASE+'/api/civic/v2/complaints',data=body,headers={'Origin':BASE})
  data=await response.json();data=data.get('data',data);rec=data.get('complaint',data)
  result['create_status']=response.status
  if response.status not in [200,201]:raise RuntimeError('create failed '+str(response.status))
  async def capture(name):
   r=await ctx.request.get(BASE+'/api/civic/v2/heat?days=30&zoom=17');d=await r.json();d=d.get('data',d)
   target=next(x for x in d['items'] if x['target']['id']=='osm-node-4109037549')
   await page.locator('[data-days="30"]').click()
   await page.evaluate('map.stop();map.jumpTo({center:[71.406553,51.131155],zoom:17,pitch:0,bearing:0})')
   await page.wait_for_timeout(1800)
   await page.screenshot(path=str(OUT/(name+'.jpg')),type='jpeg',quality=85)
   result[name]={'api':target,'map':await page.evaluate('''() => ({offline:!navigator.onLine,basemap:BirgeOffline.state(),badges:[...document.querySelectorAll('.r07-badge')].filter(e=>/Шатыр/.test(e.getAttribute('aria-label')||e.title||'')).map(e=>({label:e.getAttribute('aria-label'),text:e.textContent,html:e.outerHTML,background:getComputedStyle(e).backgroundColor}))})''')}
  await capture('before')
  result['metoo_http']=[]
  for i in range(12):
   r=await ctx.request.post(BASE+f'/api/civic/v2/complaints/{rec["id"]}/metoo',data={'device_id':tag+'-'+str(i)},headers={'Origin':BASE})
   result['metoo_http'].append(r.status)
  await capture('after');result['network']=network
  result['pass']=all(code in [200,201] for code in result['metoo_http']) and result['after']['api']['count']>result['before']['api']['count'] and not any(r.get('blocked') for r in network)
  await ctx.close();await browser.close()
 (OUT/'HEAT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:result[k] for k in ['pass','create_status','metoo_http','before','after']},ensure_ascii=False),flush=True)
asyncio.run(main())
