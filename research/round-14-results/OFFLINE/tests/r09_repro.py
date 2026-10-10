import ast,asyncio,json,pathlib
from playwright.async_api import async_playwright
from offline_bridge import install_bridge,wait_js
ROOT=pathlib.Path(__file__).resolve().parents[4]
OUT=ROOT/'research/round-14-results/OFFLINE/screens/r09-repro';OUT.mkdir(parents=True,exist_ok=True)
tree=ast.parse((pathlib.Path(__file__).parent/'extra.py').read_text(encoding='utf-8'))
SHOW=next(n.value.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SHOW' for t in n.targets))
async def main():
 results=[]
 async with async_playwright() as pw:
  browser=await pw.chromium.launch()
  for offline in [True,False]:
   ctx=await browser.new_context(viewport={'width':375,'height':812},is_mobile=True,has_touch=True,service_workers='block')
   network=[];await install_bridge(ctx,'http://127.0.0.1:8613',network,offline=offline)
   page=await ctx.new_page();errors=[]
   page.on('pageerror',lambda e:errors.append({'text':str(e),'stack':e.stack}))
   await page.goto('http://127.0.0.1:8613/?offline=1')
   await wait_js(page,'() => window.CivicShell?.heat?.state().status === "ready"')
   await page.locator('.bc-fab').click()
   xy=await page.evaluate(SHOW,[71.406553,51.131155]);await page.mouse.click(xy['x'],xy['y'])
   await page.locator('.bc-option--first').click()
   async with page.expect_response(lambda r:'/api/civic/v2/classify' in r.url and r.request.method=='POST'):
    await page.locator('#bc-text').fill('Аялдамада жарық жоқ, вечером на остановке темно')
   await page.locator('.bc-send').click()
   await page.locator('.bc-different').wait_for()
   await page.locator('.bc-different').click()
   await page.locator('.bc-panel[data-step="5"]').wait_for()
   await page.keyboard.press('Escape')
   await page.wait_for_timeout(900)
   filename=('offline' if offline else 'online-control')+'-after-close.jpg'
   await page.screenshot(path=str(OUT/filename),type='jpeg',quality=85)
   item={'context_offline':offline,'errors':errors,'screenshot':filename,'network':network,'map_active':await page.evaluate('BirgeOffline.state()')};results.append(item)
   await ctx.close();print(json.dumps({'context_offline':offline,'errors':errors},ensure_ascii=False),flush=True)
  await browser.close()
 (OUT/'R09_REPRO.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
asyncio.run(main())
