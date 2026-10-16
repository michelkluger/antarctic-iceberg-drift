#!/usr/bin/env sh
# Rebuild data/ and docs/index.html from the raw downloads in raw/ (run scripts/download.sh first).
set -e
cd "$(dirname "$0")/.."
mkdir -p out/artifact
uv run python -I scripts/usnic_extract.py raw/usnic_archive out/usnic_all_rows.csv
uv run python -I scripts/build_dataset.py raw/byu_consolidated/updated7_consol out/usnic_all_rows.csv out > out/build_log.txt
uv run --with shapely python -I scripts/build_coast.py raw/naturalearth/ne_50m_land.geojson raw/naturalearth/ne_50m_antarctic_ice_shelves_polys.geojson out/coast.geojson
uv run python -I scripts/pack_data.py out/iceberg_tracks.csv out/sources_per_berg.csv out/build_report.json out/tracks_packed.json
uv run python -I scripts/build_html.py src/template.html out/tracks_packed.json out/coast.geojson docs/index.html out/artifact/iceberg-drift.html
cp out/iceberg_tracks.csv out/sources_per_berg.csv data/
