"""Pack iceberg_tracks.csv + sources into a compact JSON blob for the HTML page.

Per berg: delta-encoded day numbers and lat/lon (x1000), run-length source codes, spike/jump indices,
and area events. Nothing is added or interpolated: one entry per CSV row.
Usage: python pack_data.py <iceberg_tracks.csv> <sources_per_berg.csv> <build_report.json> <out.json>
"""
import csv, json, re, sys
from collections import defaultdict
from datetime import date

tracks_p, sources_p, report_p, out_p = sys.argv[1:5]
report = json.load(open(report_p))
EPOCH = date(2000, 1, 1)
SENSOR_LABEL = {'ascat': 'ASCAT', 'qscat': 'QuikSCAT', 'oscat': 'OSCAT', 'seawinds': 'SeaWinds', 'nscat': 'NSCAT',
                'ers': 'ERS-1/2', 'sass': 'SASS', 'nic': 'NIC report'}
AREA_KIND = {'USNIC reported': 0, 'est. ellipse pi/4*L*W from NIC dims': 1, 'BYU ranking table (max size)': 2}
# NIC names a berg by the Antarctic quadrant where it is first sighted; colour follows that letter.
QUADRANTS = [
    dict(id='A', range='0\u00b0\u201390\u00b0W', region='Weddell and Bellingshausen seas'),
    dict(id='B', range='90\u00b0W\u2013180\u00b0', region='Amundsen Sea and eastern Ross Sea'),
    dict(id='C', range='90\u00b0E\u2013180\u00b0', region='western Ross Sea and Wilkes Land'),
    dict(id='D', range='0\u00b0\u201390\u00b0E', region='Amery Ice Shelf and eastern Weddell Sea'),
]
# The five families from the original brief, highlighted on the map.
FEATURED = [dict(id='B15', shelf='Ross Ice Shelf'), dict(id='A68', shelf='Larsen C Ice Shelf'),
            dict(id='D28', shelf='Amery Ice Shelf'), dict(id='A23', shelf='Filchner Ice Shelf'),
            dict(id='A76', shelf='Ronne Ice Shelf')]

rows = defaultdict(list)
with open(tracks_p, newline='') as fh:
    for r in csv.DictReader(fh):
        rows[r['name']].append(r)

src_labels = []
def src_code(s):
    m = re.match(r'BYU consolidated v8\.0 \((\w+)\)', s)
    label = f'BYU consolidated v8.0 \u00b7 {SENSOR_LABEL[m[1]]}' if m else 'USNIC weekly report'
    if label not in src_labels:
        src_labels.append(label)
    return src_labels.index(label)

bergs = []
for name in sorted(rows, key=lambda n: (rows[n][0]['date'], n)):
    rs = rows[name]
    days = [(date.fromisoformat(r['date']) - EPOCH).days for r in rs]
    lat = [round(float(r['lat']) * 1000) for r in rs]
    lon = [round(float(r['lon']) * 1000) for r in rs]
    km = [round(float(r['km_travelled'])) for r in rs]
    delta = lambda xs: [xs[0]] + [b - a for a, b in zip(xs, xs[1:])]
    runs, usnic = [], {}
    for i, r in enumerate(rs):
        c = src_code(r['source'])
        if not runs or runs[-1][1] != c:
            runs.append([i, c])
        m = re.search(r'(AntarcticIcebergs_\d{8}\.csv)', r['source'])
        if m:
            usnic[i] = m[1]
    spikes = [i for i, r in enumerate(rs) if r['qc_flag'].startswith('spike')]
    jumps = [i for i, r in enumerate(rs) if r['qc_flag'].startswith('jump')]
    flags = {i: r['qc_flag'] for i, r in enumerate(rs) if r['qc_flag']}
    areas = []
    for d, r in zip(days, rs):
        if r['area_km2']:
            ev = [d, round(float(r['area_km2'])), AREA_KIND[r['area_source']]]
            if r['length_nm']:
                ev += [float(r['length_nm']), float(r['width_nm'])]
            if not areas or areas[-1][1:] != ev[1:]:
                areas.append(ev)
    bergs.append(dict(n=name, f=rs[0]['family'], t=delta(days), la=delta(lat), lo=delta(lon), km=delta(km), s=runs,
                      sp=spikes, j=jumps, q=flags, a=areas, u=usnic))

sources = []
with open(sources_p, newline='') as fh:
    for r in csv.DictReader(fh):
        sources.append(dict(n=r['name'], f=r['family'], first=r['first_date'], last=r['last_date'], k=int(r['n_fixes']),
                            qf=int(r['n_qc_flagged']), src=r['source'], url=r['source_url'].split(' ')[0] if 'usicecenter' in r['source_url'] else r['source_url'],
                            nurl=len(r['source_url'].split(' ')), acc=r['access_date']))

out = dict(epoch=EPOCH.isoformat(), droppedFill=sum(v.get('byu_dropped_unobserved', 0) for v in report['per_berg'].values()), quadrants=QUADRANTS, featured=FEATURED, srcLabels=src_labels, bergs=bergs, sources=sources,
           areaKinds=['USNIC reported area', 'estimated from NIC length \u00d7 width (ellipse)', 'BYU ranking table (maximum size)'])
s = json.dumps(out, separators=(',', ':'), ensure_ascii=True)
open(out_p, 'w').write(s)
print(len(bergs), 'bergs', sum(len(b['t']) for b in bergs), 'fixes', len(s) // 1024, 'KB', src_labels)
