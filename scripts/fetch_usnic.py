"""Download the U.S. National Ice Center weekly Antarctic iceberg CSVs for a range of years.

The archive page lists files through a POST to /Products/DisplaySearchResults; each file is then
/File/DownloadArchive?prd=134MMDDYYYY. Files already on disk are skipped.
Usage: python fetch_usnic.py <out_dir> <first_year> <last_year>
"""
import http.cookiejar, os, re, sys, urllib.error, urllib.parse, urllib.request

out, y0, y1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
BASE = 'https://usicecenter.gov'
os.makedirs(out, exist_ok=True)
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
opener.open(f'{BASE}/Products/ArchiveSearchMulti?table=IcebergProducts&linkChange=ant-three', timeout=60).read()

ids = []
for y in range(y0, y1 + 1):
    form = urllib.parse.urlencode({'searchText': 'IcebergProducts', 'searchProduct': 'Antarctic Icebergs CSV',
                                   'startDate': f'01/01/{y}', 'endDate': f'12/31/{y}'}).encode()
    req = urllib.request.Request(f'{BASE}/Products/DisplaySearchResults', data=form, headers={'X-Requested-With': 'XMLHttpRequest'})
    page = opener.open(req, timeout=60).read().decode('utf-8', 'replace')
    found = sorted(set(re.findall(r'DownloadArchive\?prd=(\d+)', page)))
    print(y, len(found), 'files listed')
    ids += found

missing = []
for prd in ids:
    path = os.path.join(out, f'prd_{prd}.csv')
    if os.path.exists(path) and os.path.getsize(path) > 0:
        continue
    try:
        data = opener.open(f'{BASE}/File/DownloadArchive?prd={prd}', timeout=60).read()
    except urllib.error.HTTPError as e:
        missing.append(f'{prd} (HTTP {e.code})')
        continue
    open(path, 'wb').write(data)
print(len(ids), 'listed;', len(missing), 'unavailable:', ', '.join(missing) or 'none')
