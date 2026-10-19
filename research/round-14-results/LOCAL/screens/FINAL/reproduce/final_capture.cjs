// Observe unmodified R10 tests. Offline loopback bridge sends actual HTTP only.
const fs=require('fs'),Module=require('module'),path=require('path');
const pw=require(process.env.PLAYWRIGHT_NODE),load=Module._load;
Module._load=function(id,...args){return id==='playwright'?pw:load.call(this,id,...args);};
const origin=process.env.FINAL_ORIGIN,offline=process.env.FINAL_OFFLINE==='1';
const emit=x=>fs.appendFileSync(process.env.FINAL_CAPTURE,JSON.stringify({at:new Date().toISOString(),...x})+'\n');
const launch=pw.chromium.launch.bind(pw.chromium);
pw.chromium.launch=async(...args)=>{
 const b=await launch(...args);emit({event:'browser',version:b.version(),offline});const nc=b.newContext.bind(b);
 b.newContext=async opts=>{
  const ctx=await nc({...opts,serviceWorkers:'block'}),network=[],label=`${opts.viewport?.width}-${opts.locale||'network-test'}`;
  let active=0;const queue=[];
  if(offline){
   await ctx.setOffline(true);
   await ctx.route('**/*',async route=>{
    const req=route.request();if(new URL(req.url()).origin!==origin){network.push({url:req.url(),blocked:true});return route.abort('internetdisconnected');}
    if(active>=4)await new Promise(r=>queue.push(r));active++;
    try{const res=await ctx.request.fetch(req,{timeout:60000,maxRetries:2});network.push({url:req.url(),status:res.status(),method:req.method()});await route.fulfill({response:res});}
    catch(e){if(!String(e).includes('closed'))emit({event:'bridge-error',label,url:req.url(),text:String(e).split('\n')[0]});await route.abort().catch(()=>{});}
    finally{active--;queue.shift()?.();}
   });
  }
  ctx.on('page',p=>{
   const counts={};const error=(kind,text)=>{const k=kind+': '+text;counts[k]=(counts[k]||0)+1;};
   p.on('console',m=>{if(['error','warning'].includes(m.type()))error(m.type(),m.text());});p.on('pageerror',e=>error('pageerror',e.message));
   p.on('requestfailed',r=>error('requestfailed',r.url()+' '+r.failure()?.errorText));
   if(!offline)p.on('response',r=>network.push({url:r.url(),status:r.status(),method:r.request().method()}));
   // Same predicate through DevTools, preserving strict CSP (no unsafe-eval).
   p.waitForFunction=async(fn,arg,options={})=>{const end=Date.now()+(options.timeout||30000);while(Date.now()<end){if(await p.evaluate(fn,arg))return p.evaluateHandle(()=>true);await new Promise(r=>setTimeout(r,100));}throw Error('Predicate timeout');};
   if(offline){const route=p.route.bind(p);p.route=(pattern,fn,options)=>route(pattern,(r,req)=>{r.continue=()=>r.fallback();return fn(r,req);},options);}
   const shot=p.screenshot.bind(p);p.screenshot=async options=>{const result=await shot(options);let state;
    try{state=await p.evaluate(()=>{const m=typeof map!=='undefined'?map:null,ls=m?.getStyle()?.layers||[];return{offline:!navigator.onLine,basemap:window.BirgeOffline?.state(),zoom:m?.getZoom(),pitch:m?.getPitch(),tilesLoaded:m?.areTilesLoaded(),buildings:m?.queryRenderedFeatures({layers:ls.filter(l=>l.type==='fill-extrusion').map(l=>l.id)}).length};});}catch(e){state={error:e.message};}
    emit({event:'screenshot',label,file:path.basename(options.path),state});return result;};
   p.on('close',()=>emit({event:'errors',label,counts}));
  });ctx.on('close',()=>emit({event:'network',label,requests:network}));return ctx;
 };return b;
};
