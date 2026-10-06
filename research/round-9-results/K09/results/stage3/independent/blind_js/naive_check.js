'use strict';
// Naive cross-check: haversine recomputed per subset/case, all feasible plans materialised and sorted.
const fs=require('fs');
const [envPath, ctxPath, outPath, stepArg]=process.argv.slice(2);
const step=Number(stepArg||10);
const ctxs=JSON.parse(fs.readFileSync(ctxPath,'utf8'));
const tasks=fs.readFileSync(envPath,'utf8').split('\n').filter(l=>l.trim()).map(l=>JSON.parse(l));
const outs=new Map(fs.readFileSync(outPath,'utf8').split('\n').filter(l=>l.trim()).map(l=>{const o=JSON.parse(l);return [o.task_key,o];}));
const R=6371008.8;
function hv(lon1,lat1,lon2,lat2){const r=Math.PI/180;const a0=Math.sin((lat2-lat1)*r/2)**2+Math.cos(lat1*r)*Math.cos(lat2*r)*Math.sin((lon2-lon1)*r/2)**2;const a=Math.min(1,Math.max(0,a0));return Math.floor(R*2*Math.asin(Math.sqrt(a))*1000+0.5);}
const INF=Number.POSITIVE_INFINITY;
function vec(L){return [L.unknown_count,L.weighted_sum_mm,L.max_mm===null?INF:L.max_mm];}
function cmpArr(a,b){for(let i=0;i<Math.min(a.length,b.length);i++){if(a[i]<b[i])return -1;if(a[i]>b[i])return 1;}return a.length-b.length;}
function cmpIds(a,b){for(let i=0;i<Math.min(a.length,b.length);i++){if(a[i]<b[i])return -1;if(a[i]>b[i])return 1;}return a.length-b.length;}
let checked=0, mism=0;
for(let ti=0;ti<tasks.length;ti+=step){
  const t=tasks[ti]; const p=t.envelope.plan; const ctx=ctxs[t.slice];
  const cases=[{id:'base',disabled_source_ids:[]}, ...t.envelope.cases];
  const n=p.candidates.length; const plans=[];
  for(let m=0;m<(1<<n);m++){
    const sel=p.candidates.filter((_,j)=>m&(1<<j));
    const cost=sel.reduce((a,c)=>a+c.cost,0);
    if(sel.length>p.max_selected||cost>p.budget)continue;
    if(!p.required_ids.every(id=>sel.some(c=>c.id===id)))continue;
    if(sel.some(c=>p.excluded_ids.includes(c.id)))continue;
    const per=cases.map(cs=>{
      const objs=ctx.sources.filter(s=>!cs.disabled_source_ids.includes(s.id)).concat(sel);
      let u=0,s=0,mx=0;
      for(const q of p.control_points){
        let best=null; for(const o of objs){const d=hv(q.lon,q.lat,o.lon,o.lat); if(best===null||d<best)best=d;}
        if(best===null){u++;} else {s+=q.weight*best; mx=Math.max(mx,best);}
      }
      return {id:cs.id,L:{unknown_count:u,weighted_sum_mm:s,max_mm:u>0?null:mx}};
    });
    let W=per[0].L; for(const c of per) if(cmpArr(vec(c.L),vec(W))>0)W=c.L;
    const worst=per.filter(c=>cmpArr(vec(c.L),vec(W))===0).map(c=>c.id).sort();
    plans.push({ids:sel.map(c=>c.id).sort(),cost,W,worst,base:per[0].L});
  }
  const nomS=[...plans].sort((a,b)=>cmpArr(vec(a.base),vec(b.base))||(a.cost-b.cost)||cmpIds(a.ids,b.ids));
  const robS=[...plans].sort((a,b)=>cmpArr(vec(a.W),vec(b.W))||cmpArr(vec(a.base),vec(b.base))||(a.cost-b.cost)||cmpIds(a.ids,b.ids));
  const tw=p.control_points.reduce((a,q)=>a+q.weight,0);
  const N=nomS[0], Rb=robS[0];
  const price=(N.base.unknown_count===0&&Rb.base.unknown_count===0)?(Rb.base.weighted_sum_mm/tw-N.base.weighted_sum_mm/tw)/1000:null;
  const fmt=x=>({ids:x.ids,W:x.W,worst_case_ids:x.worst,base:x.base});
  const exp={task_key:t.task_key,status:'optimal',nominal:fmt(N),robust:fmt(Rb),same_plan:JSON.stringify(N.ids)===JSON.stringify(Rb.ids),price_of_robustness_m:price,feasible_count:plans.length};
  const got=outs.get(t.task_key);
  checked++;
  if(JSON.stringify(exp)!==JSON.stringify(got)){mism++; if(mism<=3){console.log('MISMATCH',t.task_key);console.log(' exp',JSON.stringify(exp));console.log(' got',JSON.stringify(got));}}
}
console.log({checked,mism});
