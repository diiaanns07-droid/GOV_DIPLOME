"""AST-A06 R1b: REAL DATA sensitivity of headway CV to cleaning rules (same inputs as R1)."""
import csv, collections, statistics as st, json, datetime
import os; B=os.environ['BUSSURE_GTFS']
rows=list(csv.DictReader(open(f'{B}/trips.txt'),delimiter='\t'))
routes={r['route_id']:r['route_short_name'] for r in csv.DictReader(open(f'{B}/routes.txt',encoding='cp1251'),delimiter='\t')}
def sec(t):h,m,s=t.split(':');return int(h)*3600+int(m)*60+float(s)
g=collections.defaultdict(list)
for r in rows: g[(routes[r['route_id']],r['direction_id'],r['service_id'][8:])].append(sec(r['start_time']))
med={}
for (rt,d,day),v in g.items(): med.setdefault((rt,d),[]).append(len(v))
med={k:st.median(v) for k,v in med.items()}
BANDS={'06-09':(6,9),'09-16':(9,16),'16-19':(16,19)}
def cv_for(rule):
    out={}
    for (rt,d,day),v in g.items():
        wd=datetime.date.fromisoformat(day).weekday()<5
        if rule!='raw' and len(v)<0.5*med[(rt,d)]: continue          # drop partial days
        if rule=='clean_weekday' and not wd: continue
        v=sorted(set(round(x) for x in v)) if rule!='raw' else sorted(v)  # drop exact duplicates
        for a,b in zip(v,v[1:]):
            h=b-a
            if not (0<h<=3*3600): continue
            if rule!='raw' and h<60: continue                             # drop <60 s (likely split/duplicate)
            hb=[k for k,(x,y) in BANDS.items() if x<=(a//3600)%24<y]
            if hb: out.setdefault((rt,d,hb[0]),[]).append(h)
    return {f'{k[0]}/d{k[1]}/{k[2]}':(round(st.mean(v)/60,1),round(st.pstdev(v)/st.mean(v),2),len(v)) for k,v in sorted(out.items())}
res={r:cv_for(r) for r in ('raw','clean','clean_weekday')}
json.dump(res,open('r1/cv_sensitivity.json','w'),indent=1)
print('key | raw (meanH,CV,n) | clean | clean_weekday')
for k in res['raw']: print(k,res['raw'][k],res['clean'].get(k),res['clean_weekday'].get(k))
allcv={r:[v[1] for v in res[r].values()] for r in res}
print({r:(min(v),st.median(v),max(v)) for r,v in allcv.items()})
