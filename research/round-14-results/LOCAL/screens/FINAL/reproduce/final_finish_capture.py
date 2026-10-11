import pathlib,time,subprocess,sys,os,json,re,hashlib,asyncio
from playwright.async_api import async_playwright
from offline_bridge import wait_js
WORK=pathlib.Path(__file__).parent;OUT=WORK/'final-evidence'
ROOT=pathlib.Path(r'C:\Users\LEGION\Desktop\hackalem\birge-final')
env=os.environ.copy();env['PYTHONUTF8']='1';env['PYTHONIOENCODING']='utf-8'
deadline=time.monotonic()+1800
while not (OUT/'R10_RUNS.json').exists():
 if time.monotonic()>deadline:raise TimeoutError('R10 completion marker missing')
 time.sleep(2)
print('R10 complete; starting isolated sequential timing checks',flush=True)
subprocess.run([sys.executable,'-B',str(WORK/'final_checks.py')],env=env,check=True)
print('Timing checks complete; recording RU then KK, no other browser tests running',flush=True)
subprocess.run([sys.executable,'-B',str(WORK/'final_demo.py')],env=env,check=True)

async def verify():
 videos=[]
 async with async_playwright() as pw:
  browser=await pw.chromium.launch()
  for lang in ['ru','kk']:
   path=ROOT/'video'/f'Birge_FINAL_{lang.upper()}_1366x768.webm'
   ctx=await browser.new_context(viewport={'width':1366,'height':768})
   page=await ctx.new_page();await page.goto(path.as_uri())
   await wait_js(page,'() => document.querySelector("video")?.readyState>=1')
   meta=await page.evaluate('() => {const v=document.querySelector("video");v.pause();return{duration_seconds:v.duration,width:v.videoWidth,height:v.videoHeight}}')
   assert meta['width']==1366 and meta['height']==768 and meta['duration_seconds']>70,meta
   for fraction in [.35,.75]:
    await page.evaluate('(t)=>new Promise(resolve=>{const v=document.querySelector("video");v.addEventListener("seeked",resolve,{once:true});v.currentTime=t;})',meta['duration_seconds']*fraction)
    await page.locator('video').screenshot(path=str(OUT/f'video-proof-{lang}-{int(fraction*100)}.png'))
   meta.update(language=lang,path=str(path),bytes=path.stat().st_size,sha256=hashlib.file_digest(path.open('rb'),'sha256').hexdigest(),codec='VP8/WebM',recorded_by='Playwright',playback_verified=True)
   videos.append(meta);await ctx.close();print(json.dumps(meta),flush=True)
  await browser.close()
 (OUT/'VIDEOS.json').write_text(json.dumps(videos,ensure_ascii=False,indent=2),encoding='utf-8')
asyncio.run(verify())
