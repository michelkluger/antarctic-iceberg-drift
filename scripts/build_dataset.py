"""Build one normalized iceberg-track CSV from the BYU consolidated database and the USNIC weekly archive.

Covers every NIC-named iceberg (A/B/C/D + number + fragment suffix) in either source.
Rules (from the task brief):
  * only positions a source actually reports for a date; nothing is interpolated or carried forward
  * BYU rows whose per-sensor `_3` flag is 0 are BYU's own day-fill between fixes, so they are dropped
  * gaps stay gaps; outliers are flagged, never deleted

Usage: python build_dataset.py <byu_consolidated_dir> <usnic_all_rows.csv> <out_dir>
"""
import bisect, csv, glob, math, os, re, sys, json
from collections import defaultdict
from datetime import date, timedelta

BYU_DIR, USNIC_CSV, OUT = sys.argv[1], sys.argv[2], sys.argv[3]

# NIC designation: quadrant letter, number, optional fragment letters (+ BYU's extra digit, e.g. b15j1).
# BYU's unnamed tracks (sa*, e*, uk*) are left out: they have no NIC name.
NAMED = re.compile(r'^[a-d]\d+[a-z]*\d*$')
# Per-date sensor choice when several report the same day: the daily scatterometer track first, NIC
# only on days with no scatterometer fix. Weekly NIC fixes inside the BYU files are sometimes stale or
# carry sign errors (e.g. B15Z Sep 2015 longitudes +10.7 vs -10.8), which zig-zags a mixed track.
SENSOR_PRIORITY = ['ascat', 'qscat', 'oscat', 'seawinds', 'nscat', 'ers', 'sass', 'nic']
MAX_KM_PER_DAY = 100
NM_KM = 1.852
# "Top Antarctic icebergs of all time ranked by size" table on the BYU database page (max size, sq km);
# used only for a berg's fixes before its first NIC dimensions.
BYU_RANKING_AREA = {'B15': 11000, 'A20': 7284, 'A24': 6863, 'C19': 6368, 'A23': 5883, 'A68': 5800, 'B10': 5689,
                    'A38': 5603, 'A22': 5212, 'B09': 5096}


def doy_to_iso(v):
    s = str(int(float(v)))
    return (date(int(s[:4]), 1, 1) + timedelta(int(s[4:]) - 1)).isoformat()


def display_name(stem):
    m = re.match(r'^([a-dA-D]\d+)([a-zA-Z]*\d*)$', stem)
    return m[1].upper() + m[2].lower()


def family_of(stem):
    """Parent designation (e.g. 'A68' for a68a), or None if not a NIC name."""
    return re.match(r'^([a-d]\d+)', stem)[1].upper() if NAMED.match(stem) else None


def ellipse_km2(l_nm, w_nm):
    return math.pi / 4 * l_nm * w_nm * NM_KM ** 2


def haversine_km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


records = {}  # (name, date) -> row
stats = defaultdict(lambda: defaultdict(int))

# ---- 1. BYU consolidated database --------------------------------------------------------------
for path in sorted(glob.glob(os.path.join(BYU_DIR, '*.csv'))):
    stem = os.path.basename(path)[:-4]
    fam = family_of(stem)
    if not fam:
        continue
    name = display_name(stem)
    with open(path, newline='') as fh:
        rows = list(csv.DictReader(fh))
    sensors = [s for s in SENSOR_PRIORITY if f'{s}_3' in rows[0]]
    for r in rows:
        d = doy_to_iso(r['date'])
        stats[name]['byu_rows'] += 1
        chosen = None
        for s in sensors:
            lat, lon, flag = float(r[f'{s}_1'] or 0), float(r[f'{s}_2'] or 0), float(r[f'{s}_3'] or 0)
            if flag == 1 and not (lat == 0 and lon == 0):
                chosen = (s, lat, lon)
                break
        if not chosen:
            stats[name]['byu_dropped_unobserved'] += 1
            continue
        s, lat, lon = chosen
        l = w = None
        if float(r.get('nic_3') or 0) == 1 and float(r.get('size_1') or 0) > 0:  # NIC dims, same date
            l, w = float(r['size_1']), float(r['size_2'])
        nic = (float(r['nic_1']), float(r['nic_2'])) if float(r.get('nic_3') or 0) == 1 and float(r['nic_1'] or 0) != 0 else None
        records[(name, d)] = dict(name=name, family=fam, date=d, lat=round(lat, 4), lon=round(lon, 4),
                                  source=f'BYU consolidated v8.0 ({s})', sensor=s, byu_nic=nic,
                                  length_nm=l, width_nm=w, area_km2=None, area_source='')
        stats[name]['byu_kept'] += 1

byu_last = defaultdict(str)
for (name, d) in records:
    byu_last[name] = max(byu_last[name], d)

# ---- 2. USNIC weekly archive: positions after BYU coverage ends, and reported areas ---------------
usnic = defaultdict(dict)  # name -> last_update date -> row (deduplicated on the report date)
with open(USNIC_CSV, newline='') as fh:
    for r in csv.DictReader(fh):
        stem = r['name'].replace('*', '').strip().lower()  # USNIC marks footnotes with asterisks
        fam = family_of(stem)
        if not fam or not r['last_update']:
            continue
        name = display_name(stem)
        d = r['last_update']
        prev = usnic[name].get(d)
        # same report date repeated in a later weekly file = stale repeat; keep the earliest file
        if prev is None or r['file_date'] < prev['file_date']:
            usnic[name][d] = r

area_matched = 0
usnic_vs_byu_km = []
for name, by_date in usnic.items():
    fam = family_of(name.lower())
    for d, r in sorted(by_date.items()):
        lat, lon = float(r['lat']), float(r['lon'])
        l, w = float(r['length_nm'] or 0) or None, float(r['width_nm'] or 0) or None
        area = float(r['area_km2']) if r['area_km2'] else None
        mmddyyyy = r['file'][7:15]
        src = f"USNIC weekly (AntarcticIcebergs_{mmddyyyy[4:]}{mmddyyyy[:4]}.csv)"
        key = (name, d)
        if key in records:
            rec = records[key]
            if rec.get('byu_nic'):
                km = haversine_km(rec['byu_nic'], (lat, lon))
                usnic_vs_byu_km.append(km)
                if km > 50:
                    print(f'  USNIC vs BYU-NIC mismatch {name} {d}: {km:.0f} km  BYU-NIC {rec["byu_nic"]}  USNIC ({lat},{lon}) {r["file"]}')
            if area is not None:
                rec['area_km2'], rec['area_source'] = area, 'USNIC reported'
                area_matched += 1
            continue
        if d > byu_last.get(name, ''):
            records[key] = dict(name=name, family=fam, date=d, lat=lat, lon=lon, source=src, sensor='nic',
                                length_nm=l, width_nm=w, area_km2=area,
                                area_source='USNIC reported' if area is not None else '')
            stats[name]['usnic_appended'] += 1
        elif area is not None:
            stats[name]['usnic_area_unmatched_date'] += 1

for name in usnic:
    app = sorted(d for (n, d), rec in records.items() if n == name and rec['source'].startswith('USNIC'))
    if app and byu_last.get(name) and (date.fromisoformat(app[0]) - date.fromisoformat(byu_last[name])).days > 1095:
        print(f'  long gap before USNIC continuation: {name} BYU ends {byu_last[name]}, USNIC resumes {app[0]}')

# ---- 3. Area fallbacks (clearly labelled) ------------------------------------------------------
for rec in records.values():
    if rec['area_km2'] is None and rec['length_nm'] and rec['width_nm']:
        rec['area_km2'] = round(ellipse_km2(rec['length_nm'], rec['width_nm']), 1)
        rec['area_source'] = 'est. ellipse pi/4*L*W from NIC dims'
first_dims = {}
for (name, d), rec in sorted(records.items()):
    if rec['area_km2'] is not None and name not in first_dims:
        first_dims[name] = d
for (name, d), rec in records.items():
    if name in BYU_RANKING_AREA and d < first_dims.get(name, '9999') and rec['area_km2'] is None:
        rec['area_km2'] = BYU_RANKING_AREA[name]
        rec['area_source'] = 'BYU ranking table (max size)'

# ---- 4. Sort, QC flags ------------------------------------------------------------------------
out = sorted(records.values(), key=lambda r: (r['name'], r['date']))
by_name = defaultdict(list)
for r in out:
    r['qc_flag'] = ''
    by_name[r['name']].append(r)
flags = []


def speed(a, b):
    days = (date.fromisoformat(b['date']) - date.fromisoformat(a['date'])).days
    return haversine_km((a['lat'], a['lon']), (b['lat'], b['lon'])) / days, days


def add_flag(r, text):
    r['qc_flag'] = (r['qc_flag'] + '; ' if r['qc_flag'] else '') + text


SPIKE_WINDOW_DAYS = 5


def consistent(a, b):
    days = max(1, abs((date.fromisoformat(b['date']) - date.fromisoformat(a['date'])).days))
    return haversine_km((a['lat'], a['lon']), (b['lat'], b['lon'])) <= MAX_KM_PER_DAY * days


for name, rs in by_name.items():
    ts = [date.fromisoformat(r['date']).toordinal() for r in rs]
    # Pass 1 - spikes: a fix that disagrees (>100 km/day) with most other fixes within +-5 days.
    spikes = set()
    for i, r in enumerate(rs):
        lo_i, hi_i = bisect.bisect_left(ts, ts[i] - SPIKE_WINDOW_DAYS), bisect.bisect_right(ts, ts[i] + SPIKE_WINDOW_DAYS)
        nb = [rs[j] for j in range(lo_i, hi_i) if j != i]
        if len(nb) < 2:
            continue
        bad = sum(not consistent(r, n) for n in nb)
        if bad > len(nb) / 2:
            spikes.add(i)
            mirrored = dict(r, lon=-r['lon'])
            hint = ' (consistent if longitude sign flipped)' if sum(not consistent(mirrored, n) for n in nb) <= len(nb) / 2 else ''
            add_flag(r, f'spike: disagrees with {bad} of {len(nb)} fixes within {SPIKE_WINDOW_DAYS} d{hint}')
            flags.append(dict(name=name, kind='spike', date=r['date'], source=r['source'], lon_sign_hint=bool(hint)))
    # Pass 2 - short excursions: after a >100 km/day step, does the track come back to the last
    # consistent fix within the next 7 fixes? Then the excursion fixes are spikes too.
    kept = [r for i, r in enumerate(rs) if i not in spikes]
    i, keep2 = 1, [kept[0]] if kept else []
    while i < len(kept):
        good = keep2[-1]
        if consistent(good, kept[i]):
            keep2.append(kept[i]); i += 1; continue
        resume = next((j for j in range(i + 1, min(i + 8, len(kept)))
                       if consistent(good, kept[j]) and not any(consistent(b, kept[j]) for b in kept[i:j])), None)
        if resume is None:
            keep2.append(kept[i]); i += 1; continue
        for b in kept[i:resume]:
            add_flag(b, f"spike: {resume - i}-fix excursion; track resumes near the {good['date']} fix on {kept[resume]['date']}")
            flags.append(dict(name=name, kind='spike', date=b['date'], source=b['source'], lon_sign_hint=False))
        i = resume
    kept = keep2
    # Pass 3 - jumps: remaining consecutive fixes more than 100 km/day apart (track breaks here).
    for a, b in zip(kept, kept[1:]):
        if not consistent(a, b):
            v, days = speed(a, b)
            add_flag(b, f"jump: {v * days:.0f} km in {days} d since {a['date']}")
            flags.append(dict(name=name, kind='jump', date=b['date'], ref=a['date'], km=round(v * days), days=days,
                              source=b['source']))
    for r in rs:
        if not r['lat'] < -45:
            add_flag(r, 'lat >= -45')
            flags.append(dict(name=name, kind='lat', date=r['date'], source=r['source']))

# ---- 5. Distance travelled ----------------------------------------------------------------------
# Running estimate per berg: great-circle steps between successive fixes, counted only between
# fixes from the same sensor (NIC and scatterometer place a berg's centre up to tens of km apart) and only
# once the berg is more than 10 km from the last counted position (ASCAT pixels are 4.45 km). Spikes are
# skipped, a jump re-anchors without adding distance. Grounded A23a still collects ~45 km/yr of jitter.
ODO_MIN_KM = 10
for name, rs in by_name.items():
    tot, anchor, asensor = 0.0, None, None
    for r in rs:
        if not r['qc_flag'].startswith('spike'):
            p = (r['lat'], r['lon'])
            if anchor is None or r['qc_flag'].startswith('jump') or r['sensor'] != asensor:
                anchor, asensor = p, r['sensor']
            else:
                d = haversine_km(anchor, p)
                if d > ODO_MIN_KM:
                    tot += d; anchor = p
        r['km_travelled'] = round(tot, 1)

os.makedirs(OUT, exist_ok=True)
cols = ['name', 'date', 'lat', 'lon', 'source', 'area_km2', 'area_source', 'length_nm', 'width_nm', 'km_travelled', 'family', 'qc_flag']
with open(os.path.join(OUT, 'iceberg_tracks.csv'), 'w', newline='') as fh:
    wr = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore')
    wr.writeheader()
    for r in out:
        wr.writerow({k: ('' if r.get(k) is None else r.get(k)) for k in cols})

ACCESS_DATE = '2026-10-16'
BYU_URLS = ['https://www.scp.byu.edu/data/iceberg/database1.html',
            'https://www.scp.byu.edu/data/iceberg/consolidated_database_v8.0.zip']
with open(os.path.join(OUT, 'sources_per_berg.csv'), 'w', newline='') as fh:
    wr = csv.writer(fh)
    wr.writerow(['name', 'family', 'first_date', 'last_date', 'n_fixes', 'n_qc_flagged', 'source', 'source_url', 'access_date', 'notes'])
    for name, rs in sorted(by_name.items()):
        byu = [r for r in rs if r['source'].startswith('BYU')]
        nic = [r for r in rs if r['source'].startswith('USNIC')]
        common = [name, rs[0]['family']]
        flagged = lambda xs: sum(1 for r in xs if r['qc_flag'])
        if byu:
            sensors = sorted({r['sensor'] for r in byu})
            wr.writerow(common + [byu[0]['date'], byu[-1]['date'], len(byu), flagged(byu),
                                  f'BYU/NASA SCP Antarctic Iceberg Tracking Database, consolidated v8.0 (file {name.lower()}.csv; sensors {"/".join(sensors)})',
                                  ' '.join(BYU_URLS), ACCESS_DATE, 'rows with per-sensor _3 flag = 0 (BYU day-fill) excluded'])
        if nic:
            files = sorted({re.search(r'AntarcticIcebergs_(\d{8})', r['source'])[1] for r in nic})
            urls = [f'https://usicecenter.gov/File/DownloadArchive?prd=134{f[4:]}{f[:4]}' for f in files]
            wr.writerow(common + [nic[0]['date'], nic[-1]['date'], len(nic), flagged(nic),
                                  f'U.S. National Ice Center weekly Antarctic iceberg CSV ({len(files)} files)',
                                  ' '.join(urls), ACCESS_DATE,
                                  'archive index: https://usicecenter.gov/Products/ArchiveSearchMulti?table=IcebergProducts&linkChange=ant-three'])

summary = {}
for name, rs in sorted(by_name.items()):
    summary[name] = dict(family=rs[0]['family'], first=rs[0]['date'], last=rs[-1]['date'], n=len(rs),
                         sources=sorted({r['source'].split(' (')[0] for r in rs}),
                         flagged=sum(1 for r in rs if r['qc_flag']), **stats[name])
u = sorted(usnic_vs_byu_km)
report = dict(rows=len(out), bergs=len(by_name), usnic_area_matched=area_matched, qc_flags=flags,
              northernmost=max(out, key=lambda r: r['lat'])['lat'],
              usnic_vs_byu_nic_km=dict(n=len(u), median=u[len(u) // 2] if u else None,
                                       p95=u[int(len(u) * .95)] if u else None, max=u[-1] if u else None),
              per_berg=summary)
json.dump(report, open(os.path.join(OUT, 'build_report.json'), 'w'), indent=1)
print({k: v for k, v in report.items() if k not in ('per_berg', 'qc_flags')})
from collections import Counter
print(Counter(f['kind'] for f in flags), 'lon-sign hints:', sum(f.get('lon_sign_hint', False) for f in flags))
for f in flags:
    if f['kind'] != 'spike':
        print('  ', f)
for n, s in list(summary.items())[:0]:
    print(f"{n:7s} {s['family']:4s} {s['first']}..{s['last']} n={s['n']:5d} flagged={s['flagged']} {s['sources']} "
          f"dropped_unobs={s.get('byu_dropped_unobserved', 0)} usnic_app={s.get('usnic_appended', 0)}")
