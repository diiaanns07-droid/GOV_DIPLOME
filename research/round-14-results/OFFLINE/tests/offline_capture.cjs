// Instrument the unmodified R10 flow. Chromium is offline; the only transport
// exception is the same local Birge server, forwarded through APIRequestContext.
const fs=require('fs'), path=require('path'), Module=require('module');
const pw=require(process.env.PLAYWRIGHT_NODE);
const load=Module._load;
Module._load=function(id,...args){return id==='playwright'?pw:load.call(this,id,...args);};
const origin=process.env.OFFLINE_ORIGIN, output=process.env.OFFLINE_CAPTURE;
const emit=x=>fs.appendFileSync(output,JSON.stringify({at:new Date().toISOString(),...x})+'\n');
const launch=pw.chromium.launch.bind(pw.chromium);
pw.chromium.launch=async (...args)=>{
 const browser=await launch(...args);emit({event:'browser',version:browser.version()});
 const nc=browser.newContext.bind(browser);
 browser.newContext=async opts=>{
  const ctx=await nc({...opts,serviceWorkers:'block'});
  let active=0;const waiting=[];
  const acquire=async()=>{if(active>=4)await new Promise(r=>waiting.push(r));active++;};
  const release=()=>{active--;waiting.shift()?.();};
  const label=`${opts.viewport.width}-${opts.locale}`;const network=[];
  await ctx.setOffline(true);
  await ctx.route('**/*',async route=>{
   const req=route.request();
   if(new URL(req.url()).origin!==origin){network.push({url:req.url(),blocked:true});await route.abort('internetdisconnected');return;}
   await acquire();
   try {
    const response=await ctx.request.fetch(req,{timeout:60000,maxRetries:2});
    network.push({url:req.url(),method:req.method(),status:response.status(),range:req.headers().range});
    await route.fulfill({response});
   } catch(e) { if(!String(e).includes('closed')) emit({event:'bridge-error',label,url:req.url(),error:String(e).split('\n')[0]});await route.abort().catch(()=>{}); }
   finally {release();}
  });
  ctx.on('page',page=>{
   const counts={};
   const err=(kind,text)=>{const k=kind+': '+text;counts[k]=(counts[k]||0)+1;};
   page.on('console',m=>{if(['error','warning'].includes(m.type()))err(m.type(),m.text());});
   page.on('pageerror',e=>err('pageerror',e.message));
   page.on('requestfailed',r=>err('requestfailed',r.url()+' '+r.failure()?.errorText));
   const shot=page.screenshot.bind(page);
   page.screenshot=async options=>{
    const result=await shot(options);let state;
    try {state=await page.evaluate(()=>{
     const m=typeof map!=='undefined'?map:null;if(!m?.getStyle)return{map:false};
     const ls=m.getStyle().layers||[],extr=ls.filter(l=>l.type==='fill-extrusion').map(l=>l.id);
     return{offline:!navigator.onLine,basemap:window.BirgeOffline?.state(),zoom:m.getZoom(),pitch:m.getPitch(),center:m.getCenter(),tilesLoaded:m.areTilesLoaded(),buildings:extr.length?m.queryRenderedFeatures({layers:extr}).length:0,labelCount:m.queryRenderedFeatures({layers:ls.filter(l=>l.id.startsWith('offline-label-')).map(l=>l.id)}).length};
    });}catch(e){state={error:e.message};}
    emit({event:'screenshot',label,file:path.basename(options.path),state});return result;
   };
   page.on('close',()=>emit({event:'errors',label,counts}));
  });
  ctx.on('close',()=>emit({event:'network',label,requests:network}));
  return ctx;
 };
 return browser;
};
