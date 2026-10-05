"""K03 round 7: проверка координат контрольной точки / проектного объекта по bbox текущего среза (city-whatif-v1).

Эталонная реализация (stdlib); point_check.js — те же правила для браузера. Общие fixtures: fixtures.json.

check_point(slice, point, other_slices=()) -> dict
  slice        = {"city_id": "astana"|"shymkent", "bbox": [W, S, E, N], "edges_inclusive": bool}
  point        = [lon, lat] (порядок FEATURE_SPEC) или {"lon": .., "lat": ..}
  other_slices = срезы других городов: точку из чужого квадрата не переносим, а называем причину
Результат: {"ok": bool, "code": str, "message": str, "point": [lon, lat] | None, "on_edge": bool}
  ok=True  : inside (on_edge=False) или on_edge (на границе квадрата, если edges_inclusive)
  ok=False : bad_slice, bad_shape, not_number, not_finite, out_of_range, lon_lat_swapped, other_city, outside_bbox

Правила:
  * координаты не округляются и не исправляются (перестановка lon/lat только распознаётся, не применяется);
  * сравнение с bbox точное, без допуска; edges_inclusive=True → W ≤ lon ≤ E и S ≤ lat ≤ N;
  * сначала тип и конечность (NaN/±Infinity отклоняются ДО сравнения: любое сравнение с NaN ложно);
  * bool не число; строки не приводятся;
  * район не проверяется и не требуется: принадлежность району — сведения K03, не условие приёма точки.
"""
import math

MESSAGES = {
    'inside': 'точка внутри квадрата среза',
    'on_edge': 'точка на границе квадрата среза (границы включены)',
    'bad_slice': 'у среза нет корректного bbox [W, S, E, N]',
    'bad_shape': 'ожидается [долгота, широта] или {lon, lat}',
    'not_number': 'координата должна быть числом',
    'not_finite': 'координата должна быть конечным числом (NaN/Infinity не принимаются)',
    'out_of_range': 'долгота вне [-180, 180] или широта вне [-90, 90]',
    'lon_lat_swapped': 'похоже, перепутаны долгота и широта: ожидается порядок [долгота, широта]',
    'other_city': 'точка в квадрате другого города; точки между городами не переносятся',
    'outside_bbox': 'точка вне квадрата среза: объекты за его пределами в срез не входили',
}


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _finite(v):
    # int из JSON может быть сколь угодно длинным: в JS JSON.parse даёт Infinity, здесь — тот же исход
    return math.isfinite(v) if isinstance(v, float) else abs(v) <= 1.7976931348623157e308


def _valid_bbox(b):
    return (isinstance(b, (list, tuple)) and len(b) == 4 and all(_num(x) and _finite(x) for x in b)
            and -180 <= b[0] < b[2] <= 180 and -90 <= b[1] < b[3] <= 90)


def _in(b, lon, lat, inclusive):
    if inclusive:
        return b[0] <= lon <= b[2] and b[1] <= lat <= b[3]
    return b[0] < lon < b[2] and b[1] < lat < b[3]


def _res(code, ok=False, point=None, on_edge=False):
    return {'ok': ok, 'code': code, 'message': MESSAGES[code], 'point': point, 'on_edge': on_edge}


def check_point(slice_, point, other_slices=()):
    b = (slice_ or {}).get('bbox')
    if not _valid_bbox(b):
        return _res('bad_slice')
    inclusive = slice_.get('edges_inclusive') is True
    if isinstance(point, dict):
        if set(point) - {'id', 'lon', 'lat', 'category', 'kind'} or 'lon' not in point or 'lat' not in point:
            return _res('bad_shape')
        lon, lat = point['lon'], point['lat']
    elif isinstance(point, (list, tuple)) and len(point) == 2:
        lon, lat = point
    else:
        return _res('bad_shape')
    if not (_num(lon) and _num(lat)):
        return _res('not_number')
    if not (_finite(lon) and _finite(lat)):
        return _res('not_finite')
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return _res('out_of_range')
    if _in(b, lon, lat, inclusive):
        edge = lon in (b[0], b[2]) or lat in (b[1], b[3])
        return _res('on_edge' if edge else 'inside', ok=True, point=[lon, lat], on_edge=edge)
    if _in(b, lat, lon, inclusive):
        return _res('lon_lat_swapped')
    for o in other_slices or ():
        ob = (o or {}).get('bbox')
        if _valid_bbox(ob) and o.get('city_id') != slice_.get('city_id') and _in(ob, lon, lat, o.get('edges_inclusive') is True):
            return dict(_res('other_city'), other_city_id=o.get('city_id'))
    return _res('outside_bbox')
