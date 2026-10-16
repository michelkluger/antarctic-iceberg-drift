"""Parse all USNIC weekly Antarctic iceberg CSVs into one long table (berg rows only, no filling)."""
import csv, glob, io, os, re, sys
from datetime import datetime
src_dir, out = sys.argv[1], sys.argv[2]
rows = []
for f in sorted(glob.glob(os.path.join(src_dir, 'prd_*.csv'))):
    raw = open(f, 'rb').read().decode('utf-8-sig')
    raw = raw.replace('\r\n', '\n').replace('\r', '\n')
    m = re.match(r'prd_134(\d{2})(\d{2})(\d{4})\.csv', os.path.basename(f))
    file_date = f'{m[3]}-{m[1]}-{m[2]}'
    for r in csv.DictReader(io.StringIO(raw)):
        name = (r.get('Iceberg') or '').strip().upper()
        if not name: continue
        lu = (r.get('Last Update') or '').strip()
        try: upd = datetime.strptime(lu, '%m/%d/%Y').date().isoformat()
        except ValueError: upd = ''
        rows.append(dict(name=name, file_date=file_date, last_update=upd,
                         lat=r['Latitude'].strip(), lon=r['Longitude'].strip(),
                         length_nm=r['Length (NM)'].strip(), width_nm=r['Width (NM)'].strip(),
                         area_km2=(r.get('Area (sqKM)') or '').strip(), remarks=(r.get('Remarks') or '').strip(),
                         file=os.path.basename(f)))
with open(out, 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(len(rows), 'rows')
