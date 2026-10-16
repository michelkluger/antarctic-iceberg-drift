"""Clip Natural Earth 50m land + Antarctic ice shelves to the far south, simplify lightly, write compact GeoJSON (lon/lat)."""
import json, sys
from shapely.geometry import shape, box, mapping, Point
from shapely.ops import unary_union
land_p, shelf_p, out_p = sys.argv[1:4]
clip = box(-180, -90, 180, -20)
def load(p):
    return [shape(f['geometry']) for f in json.load(open(p, encoding='utf-8'))['features']]
land = [g.intersection(clip) for g in load(land_p)]
land = [g for g in land if not g.is_empty]
shelves = [g.intersection(clip) for g in load(shelf_p)]
shelves = [g for g in shelves if not g.is_empty]
U = unary_union(land)
for name, pt in [('Ross Ice Shelf', (-175, -81)), ('Filchner-Ronne', (-60, -79)), ('Amery', (70, -70.5)), ('Larsen C', (-62, -67.5))]:
    print(name, 'in land:', U.contains(Point(*pt)), ' in shelves:', any(s.contains(Point(*pt)) for s in shelves))
def simp(gs, tol):
    out = []
    for g in gs:
        s = g.simplify(tol, preserve_topology=True)
        if s.area > 0.002: out.append(s)
    return out
def rnd(c):
    if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)): return [round(c[0], 3), round(c[1], 3)]
    return [rnd(x) for x in c]
def fc(gs, kind):
    feats = []
    for g in gs:
        m = mapping(g)
        feats.append({'type': 'Feature', 'properties': {'kind': kind}, 'geometry': {'type': m['type'], 'coordinates': rnd(m['coordinates'])}})
    return feats
feats = fc(simp(land, 0.02), 'land') + fc(simp(shelves, 0.02), 'ice_shelf')
gj = {'type': 'FeatureCollection', 'source': 'Natural Earth 1:50m land v5.1.2 + 1:50m Antarctic ice shelves, clipped south of 20S', 'features': feats}
s = json.dumps(gj, separators=(',', ':'))
open(out_p, 'w').write(s)
print(len(feats), 'features', len(s) // 1024, 'KB')
