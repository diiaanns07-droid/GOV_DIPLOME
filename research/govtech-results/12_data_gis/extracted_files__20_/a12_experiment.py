"""A12 isolated experiment (does not touch the product repo).
Checks: (1) schema loads; (2) existing Astana OSM GeoJSON maps to stable unit_ids without renaming legacy ids;
(3) 'zero vs missing' QC catches real_context.json; (4) naive spatial join with a stale admin-1 layer misassigns Shymkent.
Inputs: STUPITS snapshot (codeload main zip), Natural Earth 10m admin-1 + populated places (raw.githubusercontent)."""
import json, sqlite3, hashlib, sys, platform
from pathlib import Path
import shapely; from shapely.geometry import shape, Point
from pyproj import Geod
R = Path('/home/claude/stupits/hack-d3b2c613-stupits-main')
db = sqlite3.connect(':memory:'); db.executescript(Path('A12_schema.sql').read_text())
acc = '2026-10-04T17:20:46Z'
def src(i,t,p,u,typ,st,lic=None,path=None):
    sha = hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else None
    db.execute('insert into sources(source_id,title,publisher,url,accessed_at,source_type,access_status,license,sha256) values(?,?,?,?,?,?,?,?,?)',(i,t,p,u,acc,typ,st,lic,sha))
src('A12-S003','STUPITS data/astana_districts.geojson','BAITC-Hacks / STUPITS team','https://github.com/BAITC-Hacks/hack-d3b2c613-stupits/blob/main/data/astana_districts.geojson','repo_file','opened','ODbL (OSM-derived)',R/'data/astana_districts.geojson')
src('A12-S007','STUPITS data/real_context.json (+meta)','BAITC-Hacks / STUPITS team','https://github.com/BAITC-Hacks/hack-d3b2c613-stupits/blob/main/data/real_context.json','repo_file','opened','ODbL (OSM-derived)',R/'data/real_context.json')
src('A12-S010','Natural Earth 10m admin-1 states/provinces','Natural Earth','https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_1_states_provinces.geojson','dataset_file','opened','Public domain','/home/claude/ne_adm1.geojson')
src('A12-S011','Natural Earth 10m populated places (simple)','Natural Earth','https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_populated_places_simple.geojson','dataset_file','opened','Public domain','/home/claude/ne_pp.geojson')
# (2) geo_units from real OSM-derived file
g = json.loads((R/'data/astana_districts.geojson').read_text()); bv = 'osm:'+'2026-09-22T08:45:51Z'
db.execute("insert into geo_units(unit_id,city_id,level,name_ru,iso_3166_2,boundary_version,geometry_source,source_id) values('kz.astana','kz.astana','city','Астана','KZ-71','osm:2026-09-22T08:45:51Z','none','A12-S003')")
geod = Geod(ellps='WGS84')
for f in g['features']:
    p = f['properties']
    db.execute('insert into geo_units(unit_id,city_id,level,parent_id,legacy_id,name_ru,name_kk,name_en,osm_relation_id,boundary_version,geometry_source,geometry_file,source_id) values(?,?,?,?,?,?,?,?,?,?,?,?,?)',
      (f"kz.astana.district.{p['id']}",'kz.astana','district','kz.astana',p['id'],p['name'],p['osm_names'].get('name:kk',p['osm_names'].get('name')),p['osm_names'].get('name:en'),p['osm_id'],bv,'osm_community','data/astana_districts.geojson','A12-S003'))
db.execute("insert into geo_units(unit_id,city_id,level,name_ru,boundary_version,geometry_source,source_id) values('kz.shymkent','kz.shymkent','city','Шымкент','none:pending_official_or_osm','none','A12-S011')")
print('geo_units:', db.execute('select count(*) from geo_units').fetchone()[0])
for r in db.execute("select unit_id,legacy_id,name_kk,osm_relation_id from geo_units where level='district'"): print('  ',r)
# (3) zero vs missing
rc = json.loads((R/'data/real_context.json').read_text()); meta = json.loads((R/'data/real_context_meta.json').read_text())
cats = list(meta['category_tags'])
for c in cats:
    db.execute("insert into indicators values(?,?,?,?,?,?,?,?,?,?)",(f'REF.osm_{c}_count','reference',f'OSM: число объектов {c}',None,meta['category_tags'][c],'count','neutral','district','snapshot',365))
naive = sum(1 for d in rc.values() for v in d.values() if v == 0)
def qc_zero(status): return 'missing' if status != 'ok' else None
rows = 0
for d, vals in rc.items():
    for c, v in vals.items():
        forced = qc_zero(meta['status'])
        db.execute('insert into observations(obs_id,indicator_id,unit_id,boundary_version,period_start,period_end,period_type,value,value_status,native_value,unit,kind,source_id,locator,quality_flags) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
          (f'A12-O-{d}-{c}',f'REF.osm_{c}_count',f'kz.astana.district.{d}',bv,meta['generated_at'][:10],meta['generated_at'][:10],'snapshot',
           None if forced else v, forced or ('reported_zero' if v==0 else 'reported'), str(v),'count','observed','A12-S007',f'$.{d}.{c}','source_status_unavailable'))
        rows += 1
print(f'real_context: {rows} cells, naive zeros={naive}, meta.status={meta["status"]!r}, stored as missing:',
      db.execute("select count(*) from observations where value_status='missing' and value is null").fetchone()[0])
try:
    db.execute("insert into observations(obs_id,indicator_id,unit_id,boundary_version,period_start,period_end,period_type,value,value_status,unit,kind,source_id,locator) values('bad','REF.osm_parks_count','kz.astana.district.esil','x','2026','2026','snapshot',0,'missing','count','observed','A12-S007','$')")
    print('constraint test: NOT rejected (unexpected)')
except sqlite3.IntegrityError as e: print('constraint test: value=0 with status=missing rejected ->', e)
# (4) stale admin layer
adm = json.loads(Path('/home/claude/ne_adm1.geojson').read_text()); pp = json.loads(Path('/home/claude/ne_pp.geojson').read_text())
pt = next(f for f in pp['features'] if f['properties'].get('adm0_a3')=='KAZ' and f['properties'].get('name')=='Shymkent')
P = Point(*pt['geometry']['coordinates'])
hit = [f['properties'] for f in adm['features'] if f['properties'].get('adm0_a3')=='KAZ' and shape(f['geometry']).contains(P)]
print('naive join Shymkent point ->', [(h['name'],h['name_ru'],h['iso_3166_2']) for h in hit], '| NE has Shymkent unit:', any(f['properties'].get('name')=='Shymkent' for f in adm['features'] if f['properties'].get('adm0_a3')=='KAZ'))
print('versions: python',platform.python_version(),'sqlite',sqlite3.sqlite_version,'shapely',shapely.__version__)
