"""Inject packed data + coastline into template.html.

Writes the standalone page (full document) and the artifact fragment (the publisher adds the document skeleton).
Usage: python build_html.py <template.html> <tracks_packed.json> <coast.geojson> <standalone.html> <fragment.html>
"""
import sys
tpl_p, data_p, coast_p, standalone_p, fragment_p = sys.argv[1:6]
tpl = open(tpl_p, encoding='utf-8').read()
data = open(data_p, encoding='ascii').read()
coast = open(coast_p, encoding='ascii').read()
assert '</script' not in data and '</script' not in coast
# Keep the page ASCII so it renders right without a charset header. Non-ASCII may appear only inside the
# inline scripts (JS strings), where it is rewritten as a \uXXXX escape; HTML text uses entities.
first_script = tpl.index('<script')
assert all(ord(c) < 128 for c in tpl[:first_script]), 'use HTML entities for non-ASCII outside scripts'
tpl = tpl[:first_script] + ''.join(c if ord(c) < 128 else '\\u%04x' % ord(c) for c in tpl[first_script:])
body = tpl.replace('__DATA__', data, 1).replace('__COAST__', coast, 1)
assert all(ord(c) < 128 for c in body)
open(fragment_p, 'w', encoding='ascii', newline='\n').write(body)
head, rest = body.split('<!--/head-->', 1)
doc = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
       '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
       + head + '</head>\n<body>\n' + rest + '\n</body>\n</html>\n')
open(standalone_p, 'w', encoding='ascii', newline='\n').write(doc)
print('fragment', len(body) // 1024, 'KB; standalone', len(doc) // 1024, 'KB')
