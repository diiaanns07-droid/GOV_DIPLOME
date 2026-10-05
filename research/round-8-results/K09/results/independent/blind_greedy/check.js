'use strict';
// Self-check: feasibility of greedy plans, keys not better than exhaustive optimum, rounding margins.
const fs=require('fs');
const IN='/tmp/claude-0/-home-user-GOV-DIPLOME/e220e412-94a1-5250-b65e-0d50545b9515/scratchpad/blind_in/inputs.json';
const input=JSON.parse(fs.readFileSync(IN,'utf8'));
const out=JSON.parse(fs.readFileSync(__dirname+'/out.json','utf8'));
const R=6371008.8,RAD=Math.PI/180;
function hv(lon1,lat1,lon2,lat2){const p1=lat1*RAD,p2=lat2*RAD,dp=(lat2-lat1)*RAD,dl=(lon2-lon1)*RAD;let a=Math.sin(dp/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;a=Math.min(1,Math.max(0,a));return 2*R*Math.asin(Math.sqrt(a));}
function hv2(lon1,lat1,lon2,lat2){const p1=lat1*RAD,p2=lat2*RAD,dp=(lat2-lat1)*RAD,dl=(lon2-lon1)*RAD;let a=Math.sin(dp/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;a=Math.min(1,Math.max(0,a));return 2*R*Math.atan2(Math.sqrt(a),Math.sqrt(1-a));}
let minMargin=1, diffForm=0, nd=0;
for(const t of input.tasks){const s=t.scenario;const objs=t.context.sources.concat(s.candidates);
 for(const p of s.control_points)for(const o of objs){const x=hv(p.lon,p.lat,o.lon,o.lat)*1000;const f=x-Math.floor(x);minMargin=Math.min(minMargin,Math.abs(f-0.5));nd++;
  if(Math.floor(x+0.5)!==Math.floor(hv2(p.lon,p.lat,o.lon,o.lat)*1000+0.5))diffForm++;}}
console.log('distances',nd,'min |frac-0.5| (mm)',minMargin,'asin vs atan2 rounding differences',diffForm);
// exhaustive
function cs(a,b){return a<b?-1:a>b?1:0}
function cmpIds(a,b){for(let i=0;i<Math.min(a.length,b.length);i++){const c=cs(a[i],b[i]);if(c)return c;}return cs(a.length,b.length);}
function cmpKey(a,b){for(let i=0;i<a.length;i++){const c=Array.isArray(a[i])?cmpIds(a[i],b[i]):cs(a[i],b[i]);if(c)return c;}return 0;}
let bad=0, exactHits={G1:0,G2:0}, total={G1:0,G2:0};
for(const t of input.tasks){const s=t.scenario;const pts=s.control_points;const C=s.candidates.slice().sort((a,b)=>cs(a.id,b.id));
 const base=pts.map(p=>{let b=null;for(const q of t.context.sources){const d=Math.floor(hv(p.lon,p.lat,q.lon,q.lat)*1000+0.5);if(b===null||d<b)b=d;}return b;});
 const D=C.map(c=>pts.map(p=>Math.floor(hv(p.lon,p.lat,c.lon,c.lat)*1000+0.5)));
 const idx=new Map(C.map((c,i)=>[c.id,i]));
 function met(ids){let u=0,w=0,m=-1,cov=0,cost=0;const I=ids.map(x=>idx.get(x));for(const i of I)cost+=C[i].cost;
  for(let j=0;j<pts.length;j++){let a=base[j];for(const i of I)if(a===null||D[i][j]<a)a=D[i][j];if(a===null){u++;continue;}w+=pts[j].weight*a;if(a>m)m=a;if(a<=s.coverage_radius_m*1000)cov+=pts[j].weight;}
  const mx=u?Infinity:m;const sid=ids.slice().sort(cs);return {mean:[u,w,mx,cost,sid],minimax:[u,mx,w,cost,sid],coverage:[-cov,u,w,mx,cost,sid],cost};}
 const feas=ids=>s.required_ids.every(r=>ids.includes(r))&&!ids.some(x=>s.excluded_ids.includes(x))&&ids.length<=s.max_selected&&met(ids).cost<=s.budget;
 const best={};
 for(let mask=0;mask<(1<<C.length);mask++){const ids=[];for(let i=0;i<C.length;i++)if(mask>>i&1)ids.push(C[i].id);if(!feas(ids))continue;const m=met(ids);
  for(const o of ['mean','minimax','coverage'])if(!best[o]||cmpKey(m[o],best[o])<0)best[o]=m[o];}
 for(const g of ['G1','G2'])for(const o of ['mean','minimax','coverage']){const r=out[t.task_id][g][o];
  if(r===null){if(best[o]){bad++;console.log('null but feasible',t.task_id,g,o);}continue;}
  if(!feas(r)){bad++;console.log('infeasible greedy',t.task_id,g,o,r);continue;}
  if(cmpKey(met(r)[o],best[o])<0){bad++;console.log('better than exact?!',t.task_id,g,o);}
  total[g]++; if(cmpKey(met(r)[o],best[o])===0)exactHits[g]++;}}
console.log('violations',bad,'greedy==exact winner counts',JSON.stringify(exactHits),'of',JSON.stringify(total));
