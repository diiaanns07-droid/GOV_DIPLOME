"""AST-A12 isolated experiments (read-only; product repo is not modified).
Inputs (local copies, see AST_A12_manifest.json): STUPITS snapshot commit 834a25f; Natural Earth 10m;
third-party repos: egov-web-crawler (8c1f4a3), opengov-kz/data-egov-kz (46ca0c0), Bussure (0356bb5)."""
import json, csv, io, re, collections, sqlite3, platform, hashlib
from pathlib import Path
import shapely; from shapely.geometry import shape, Point, LineString
from shapely.ops import polygonize, unary_union
import pyproj; from pyproj import Geod
H = Path('/home/claude'); R = H/'stupits/hack-d3b2c613-stupits-main'
geod = Geod(ellps='WGS84'); ga = lambda g: abs(geod.geometry_area_perimeter(g)[0])/1e6
out = {}
# E101 repo audit
cd = json.loads((R/'data/city_data.json').read_text()); ev = json.loads((R/'data/events.json').read_text())
rc = json.loads((R/'data/real_context.json').read_text()); rm = json.loads((R/'data/real_context_meta.json').read_text())
refs = [str(p.relative_to(R)) for p in R.rglob('*') if p.suffix in ('.py','.js','.html') and p.name!='fetch_real_context.py' and 'real_context' in p.read_text(encoding='utf-8',errors='ignore')]
out['E101'] = dict(indicators=len(cd['indicators']), districts=[d['id'] for d in cd['districts']], population_share_sum=round(sum(d['population_share'] for d in cd['districts']),6),
  measures=len(cd['measures']), budget=cd['budget'], events=len(ev), events_with_district=sum(1 for e in ev if e.get('district')),
  real_context_cells=sum(len(v) for v in rc.values()), real_context_nonzero=sum(1 for v in rc.values() for x in v.values() if x), real_context_districts=sorted(rc),
  real_context_meta=dict(status=rm['status'], generated_at=rm['generated_at'], districts_source=rm['districts_source']),
  real_context_referenced_by=refs)
# E102 boundaries
dist = json.loads((R/'data/astana_districts.geojson').read_text()); D = {f['properties']['id']: shape(f['geometry']) for f in dist['features']}
A = unary_union(list(D.values()))
ov = json.loads((R/'data/geo_sources/astana_districts_overpass.json').read_text())
def build(e):
    ln = lambda role: [LineString([(p['lon'],p['lat']) for p in m['geometry']]) for m in e['members'] if m['type']=='way' and m.get('role')==role and m.get('geometry')]
    O = sorted(polygonize(unary_union(ln('outer'))), key=lambda p: -p.area); g = O[0]
    for p in O[1:]: g = g.symmetric_difference(p)
    I = ln('inner')
    return g.difference(unary_union(list(polygonize(unary_union(I))))) if I else g
NB = {e['id']: (e['tags'].get('name'), build(e)) for e in ov['elements'] if e['id'] in (15594335, 3403760, 3403782, 3404061, 17952313)}
ne = json.loads((H/'ne_adm1.geojson').read_text()); NEA = next(shape(f['geometry']) for f in ne['features'] if f['properties'].get('adm0_a3')=='KAZ' and f['properties']['name']=='Astana')
pp = json.loads((H/'ne_pp.geojson').read_text()); nep = next(f['properties'] for f in pp['features'] if f['properties'].get('adm0_a3')=='KAZ' and f['properties'].get('nameascii')=='Astana')
parts = sorted(getattr(A,'geoms',[A]), key=lambda p: -p.area)
out['E102'] = dict(union_km2=round(ga(A),1), union_parts_km2=[round(ga(p),3) for p in parts],
  neighbours={str(k): dict(name=n, area_km2=round(ga(g),1), overlap_with_astana_km2=round(ga(g.intersection(A)),3) if g.intersection(A).area>0 else 0.0, shares_boundary=g.boundary.intersection(A.boundary).length>0) for k,(n,g) in NB.items()},
  natural_earth=dict(astana_polygon_km2=round(ga(NEA),1), iou_with_osm_union=round(ga(NEA.intersection(A))/ga(NEA.union(A)),3), osm_outside_ne_km2=round(ga(A.difference(NEA)),1), ne_outside_osm_km2=round(ga(NEA.difference(A)),1),
                     populated_place=dict(name=nep['name'], nameascii=nep['nameascii'], adm1name=nep['adm1name'], pop_max=nep['pop_max'])))
sara = json.loads((R/'data/geo_sources/sara_osm.json').read_text()); rel = next(e for e in sara['elements'] if e['type']=='relation')
out['E102']['saraishyk_relation'] = dict(id=rel['id'], version=rel['version'], timestamp=rel['timestamp'], overpass_base=ov['osm3s']['timestamp_osm_base'], relation_edit_before_snapshot=rel['timestamp'] < ov['osm3s']['timestamp_osm_base'])
# E103 PIP edge cases
P = Point(71.447389, 51.1311552)
ex = sorted(D['baikonur'].geoms, key=lambda p: -p.area)[1]; q = ex.representative_point()
out['E103'] = dict(tri_point=[P.x,P.y], contains={k: D[k].contains(P) for k in D if D[k].covers(P)}, covers=sorted(k for k in D if D[k].covers(P)),
  rule_result=sorted(k for k in D if D[k].covers(P))[0],
  exclave_point=[round(q.x,5), round(q.y,5)], exclave_in_baikonur=D['baikonur'].covers(q), exclave_in_tselinograd=NB[3403760][1].covers(q))
# E104 GTFS stops
G = H/'ext/Mrithula742_Bussure/Bussure-main/datasets/astana/gtfs_data'
stops = list(csv.DictReader(io.StringIO((G/'stops.txt').read_text(encoding='utf-8-sig')), delimiter='\t'))
cnt = collections.Counter(); ties = 0; outside = 0
for s in stops:
    pt = Point(float(s['stop_lon']), float(s['stop_lat'])); c = sorted(k for k,g in D.items() if g.covers(pt))
    ties += len(c) > 1; outside += not c; cnt[c[0] if c else 'outside'] += 1
cal = [l.split('\t')[1] for l in (G/'calendar_dates.txt').read_text(encoding='utf-8-sig').splitlines()[1:]]
routes = (G/'routes.txt').read_bytes().decode('cp1251').splitlines()[1:]
out['E104'] = dict(stops=len(stops), per_district=dict(cnt), ties=ties, outside=outside, routes=[r.split('\t')[4] for r in routes],
  trips=len((G/'trips.txt').read_text(encoding='utf-8-sig').splitlines())-1, service_dates=[min(cal), max(cal), len(cal)])
# E105 catalog
rows = list(csv.DictReader(open(H/'ext/Yerassyl20036_egov-web-crawler/egov-web-crawler-main/datasets_export.csv', encoding='utf-8-sig')))
by = collections.Counter(r['passport_gov_agency'] for r in rows)
AST = [r for r in rows if r['passport_gov_agency']=='Акимат города Астана']
mio = list(csv.reader(open(H/'ext/opengov-kz_data-egov-kz/data-egov-kz-main/data/byMIO.csv', encoding='utf-8-sig')))[1:]
mio_idx = {re.search(r'index=(.+)$', u).group(1) for _,_,_,u in mio if 'index=' in u}
out['E105'] = dict(catalog_rows=len(rows), crawled=[min(r['crawled_at'] for r in rows), max(r['crawled_at'] for r in rows)],
  akimat_astana=by['Акимат города Астана'], akimat_akmola=by['Акимат Акмолинской области'], akimat_shymkent=by['Акимат города Шымкент'],
  astana_frequency=dict(collections.Counter(r['passport_actualization_type'] for r in AST)), astana_legacy_nur_sultan_slugs=sum('nur-sultan' in r['api_uri'] for r in AST),
  astana_in_opengov_list=sum(r['api_uri'] in mio_idx for r in AST))
# E106 schema
db = sqlite3.connect(':memory:'); db.executescript((H/'a12/A12_schema.sql').read_text()); db.executescript(Path('AST_A12_schema_delta.sql').read_text())
db.execute("insert into topology_conflicts values('AST-TC-001','kz.astana.district.baikonur','osm:2026-09-22T08:45:51Z','kz.akmola.district.tselinograd','osm:2026-09-22T08:45:51Z',9.021,71.66574,51.33028,'open',NULL,'AST-A12-S008')")
out['E106'] = dict(tables=[r[0] for r in db.execute("select name from sqlite_master where type in ('table','view') order by name")])
out['versions'] = dict(python=platform.python_version(), sqlite=sqlite3.sqlite_version, shapely=shapely.__version__, pyproj=pyproj.__version__)
print(json.dumps(out, ensure_ascii=False, indent=1))
