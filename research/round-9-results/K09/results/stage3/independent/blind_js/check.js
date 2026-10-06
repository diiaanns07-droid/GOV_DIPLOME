'use strict';
const fs=require('fs');
const [envPath, ctxPath, outPath]=process.argv.slice(2);
const ctxs=JSON.parse(fs.readFileSync(ctxPath,'utf8'));
const tasks=fs.readFileSync(envPath,'utf8').split('\n').filter(l=>l.trim()).map(l=>JSON.parse(l));
const outs=fs.readFileSync(outPath,'utf8').split('\n').filter(l=>l.trim()).map(l=>JSON.parse(l));
// distribution
const st={}; let same=0, priceNZ=0, priceNull=0, unkW=0, unkBaseNom=0, worstMulti=0;
for(const o of outs){st[o.status]=(st[o.status]||0)+1; if(o.same_plan)same++; if(o.price_of_robustness_m===null)priceNull++; else if(o.price_of_robustness_m!==0)priceNZ++; if(o.robust&&o.robust.W.unknown_count>0)unkW++; if(o.nominal&&o.nominal.base.unknown_count>0)unkBaseNom++; if(o.robust&&o.robust.worst_case_ids.length>1)worstMulti++;}
console.log({status:st,same,priceNZ,priceNull,unkW,unkBaseNom,worstMulti,n:outs.length});
// rounding-boundary sensitivity: distances with fractional part of d*1000 near .5
const R=6371008.8; const rad=x=>x*Math.PI/180;
function raw(l1,a1,l2,a2,variant){const p1=variant?a1*(Math.PI/180):rad(a1),p2=variant?a2*(Math.PI/180):rad(a2);const dp=variant?(a2-a1)*(Math.PI/180):rad(a2-a1);const dl=variant?(l2-l1)*(Math.PI/180):rad(l2-l1);let a=Math.sin(dp/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;a=Math.min(1,Math.max(0,a));return R*2*Math.asin(Math.sqrt(a));}
let near=0, diffVariant=0, total=0, minGap=1; const seen=new Set();
for(const t of tasks){const c=ctxs[t.slice];const p=t.envelope.plan;const objs=c.sources.concat(p.candidates);
 for(const q of p.control_points)for(const s of objs){const k=q.lon+','+q.lat+'|'+s.lon+','+s.lat; if(seen.has(k))continue; seen.add(k); total++;
  const d=raw(q.lon,q.lat,s.lon,s.lat,false); const x=d*1000; const frac=x-Math.floor(x); const gap=Math.abs(frac-0.5); if(gap<minGap)minGap=gap; if(gap<1e-6)near++;
  if(Math.floor(x+0.5)!==Math.floor(raw(q.lon,q.lat,s.lon,s.lat,true)*1000+0.5))diffVariant++;}}
console.log({uniquePairs:total,nearHalfWithin1e6mm:near,minGapToHalf:minGap,diffDegRadVariant:diffVariant});
