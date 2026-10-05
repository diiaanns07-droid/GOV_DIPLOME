#!/usr/bin/env bash
# K08: воспроизведение проверок утверждений. Только чтение публичных репозиториев GitHub.
# Не скачивает LFS-файлы (GIT_LFS_SKIP_SMUDGE=1). Запуск: bash verify_claims.sh <рабочая_папка>
# Переменные: GOV_DIPLOME_ROOT=<корень клона GOV_DIPLOME> (для V04, V07); PYTHON=<python с numpy, pytest, openpyxl> (для V07, V09).
set -euo pipefail
W="${1:-./k08_work}"; mkdir -p "$W"; cd "$W"
clone() { [ -d "$2" ] || GIT_LFS_SKIP_SMUDGE=1 git clone -q "$1" "$2"; git -C "$2" log -1 --format="$2 HEAD %H %cI"; }

# V01 — AST-A06-F007/F008/F009: набор Bussure datasets/astana
clone https://github.com/Mrithula742/Bussure bussure
python3 - <<'PY'
import csv
from collections import Counter
p='bussure/datasets/astana/gtfs_data/'
rd=lambda f: list(csv.DictReader(open(p+f,encoding='utf-8',errors='replace').read().splitlines(),delimiter='\t'))
print('V01 agency:', [a['agency_id'] for a in rd('agency.txt')])
r={x['route_id']:x['route_short_name'] for x in rd('routes.txt')}
t=rd('trips.txt'); s=rd('stops.txt'); c=rd('calendar_dates.txt')
print('V01 stops', len(s), 'trips', len(t), 'trips/route', dict(Counter(r[x['route_id']] for x in t)))
print('V01 direction_id', dict(Counter(x['direction_id'] for x in t)))
d=sorted({x['date'] for x in c}); print('V01 dates', len(d), d[0], d[-1])
print('V01 stop_times.txt first line:', open(p+'stop_times.txt').readline().strip())
PY

# V02 — AST-A06-F019/F020: сборщик bus-traffic-astana
clone https://github.com/iilenza/bus-traffic-astana bta
grep -n 'api.citytransport.kz\|except' bta/collect_bus_data.py
grep -n 'cron' bta/.github/workflows/collect.yml
python3 - <<'PY'
import csv
from collections import Counter
r=list(csv.DictReader(open('bta/bus_traffic_dataset.csv')))
ts=sorted({x['timestamp'] for x in r})
print('V02 rows', len(r), 'snapshots', len(ts), ts[0], ts[-1], 'bus_count values', dict(Counter(x['bus_count'] for x in r)))
PY

# V03 — AST-A06-F005/F006: GTFS-каталоги
[ -d mdb ] || git clone -q --depth 1 https://github.com/MobilityData/mobility-database-catalogs mdb
git -C mdb log -1 --format='mdb HEAD %H %cI'
echo "V03 MobilityData json: $(find mdb/catalogs -name '*.json' | wc -l)"
for c in KZ RU TR GE UZ KG; do echo "V03 country $c: $(grep -rlE "\"country_code\": *\"$c\"" mdb/catalogs | wc -l)"; done
echo "V03 MobilityData name hits: $(grep -rliE 'shymkent|chimkent|шымкент|astana|nur-sultan|астана|kazakhstan' mdb/catalogs | wc -l)"
[ -d tla ] || git clone -q --depth 1 https://github.com/transitland/transitland-atlas tla
git -C tla log -1 --format='tla HEAD %H %cI'
echo "V03 transitland files: $(find tla -path tla/.git -prune -o -type f -print | wc -l), hits: $(grep -rliE 'shymkent|chimkent|шымкент|astana|nur-sultan|астана|\.kz[/"]' --exclude-dir=.git tla | wc -l)"

# V04 — AST-A11-F003/F004, AST-A06-F028: границы районов в самом репозитории GOV_DIPLOME
R="${GOV_DIPLOME_ROOT:-$(git -C "$OLDPWD" rev-parse --show-toplevel 2>/dev/null || echo ../..)}"
python3 - "$R" <<'PY'
import json,sys
R=sys.argv[1]
d=json.load(open(R+'/data/astana_districts.geojson'))
print('V04 features', [(f['properties']['name'],f['properties']['osm_id'],f['properties']['scoring_enabled'],f['properties']['osm_timestamp']) for f in d['features']])
o=json.load(open(R+'/data/geo_sources/astana_districts_overpass.json'))
print('V04 osm_base', o['osm3s']['timestamp_osm_base'])
print('V04 relations', sorted((e['id'],e['tags'].get('admin_level')) for e in o['elements'] if e['type']=='relation'))
print('V04 real_context status', json.load(open(R+'/data/real_context_meta.json'))['status'])
PY

# V05/V06 — AST-A01-F004/F007: iKOMEK 109
[ -d ikomek109 ] || git clone -q https://github.com/ikomek/ikomek109 ikomek109
git -C ikomek109 log -1 --format='ikomek109 HEAD %H %cI'
grep -n 'manager@ikomekastana.kz\|Дата публикации' ikomek109/README.md
[ -d ikomek_platform ] || GIT_LFS_SKIP_SMUDGE=1 git clone -q --depth 1 https://github.com/argamegg/ikomek_platform ikomek_platform
git -C ikomek_platform log -1 --format='ikomek_platform HEAD %H %cI'
grep -n -iE 'languages-RU|MyMemory|тепловая|AI-ассистент|demo49' ikomek_platform/README.md
ls ikomek_platform | grep -i license || echo "V06 LICENSE: none"

# V07 — A13-F001/F002: тесты исходного репозитория на 834a25f (нужны numpy, pytest; код не меняется)
PY="${PYTHON:-python3}"
WT="$PWD/stupits_834a25f"
[ -d "$WT" ] || git -C "$R" worktree add -q --detach "$WT" 834a25fb860dd5514d02c9274b70d7bf8a53a79c
( cd "$WT" && "$PY" -m pytest -q 2>&1 | tail -1 && "$PY" check.py > ../check_out.txt 2>&1; echo "V07 check.py exit=$?"; tail -1 ../check_out.txt )
git -C "$R" worktree remove --force "$WT"

# V08 — A12-F010/F011: Natural Earth
for f in ne_10m_admin_1_states_provinces ne_10m_populated_places_simple; do [ -f $f.geojson ] || curl -sS -o $f.geojson https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/$f.geojson; done
echo "V08 VERSION $(curl -sS https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/VERSION)"
python3 - <<'PY'
import json
a=json.load(open('ne_10m_admin_1_states_provinces.geojson'))
kz=sorted((f['properties']['iso_3166_2'],f['properties']['name'],f['properties'].get('name_ru')) for f in a['features'] if f['properties'].get('adm0_a3')=='KAZ')
print('V08 KAZ admin1', len(kz), kz)
for f in json.load(open('ne_10m_populated_places_simple.geojson'))['features']:
    p=f['properties']
    if p.get('adm0_a3')=='KAZ' and p['name'] in ('Shymkent','Nur-Sultan','Astana'): print('V08 place', p['name'], f['geometry']['coordinates'], p.get('pop_max'), p.get('adm1name'))
PY

# V09 — A08-F005/F006: AirData_Shymkent (нужен openpyxl)
[ -d airdata ] || git clone -q https://github.com/DinaAssylbekova/AirData_Shymkent airdata
git -C airdata log -1 --format='airdata HEAD %H %cI'
"$PY" - <<'PY'
import openpyxl,csv
from collections import Counter
rows=[r for r in openpyxl.load_workbook('airdata/sensors.xlsx',read_only=True).active.iter_rows(values_only=True)][1:]
ne=[r for r in rows if r[0]]; print('V09 sensors', len(ne), dict(Counter(r[1] for r in ne)))
for r in ne:
    if r[2]=='Шымкент': print('V09 shymkent sensor', r)
st=Counter(); codes=Counter(); t=[None,None]; shy={}
for r in csv.DictReader(open('airdata/layer_03_data_prepared_25.03.22.csv',encoding='utf-8')):
    st[r['stationId']]+=1; codes[r['code']]+=1; dt=r['datetime']
    t=[min(t[0] or dt,dt),max(t[1] or dt,dt)]
    if r['stationId'] in ('k15','k49'):
        a=shy.setdefault(r['stationId'],[dt,dt,0]); a[0]=min(a[0],dt); a[1]=max(a[1],dt); a[2]+=1
print('V09 rows', sum(st.values()), 'stations', len(st), 'period', t, 'codes', sorted(codes))
print('V09 shymkent rows', shy)
PY

# V12 — A08-F012: репозиторий KazHydroMet2324
[ -d khm ] || git clone -q https://github.com/Beibut/KazHydroMet2324 khm 2>&1 | tail -1
echo "V12 commits: $(git -C khm rev-list --all --count 2>/dev/null || echo 0)"
