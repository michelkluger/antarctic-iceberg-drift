#!/usr/bin/env sh
# Fetch the raw inputs into raw/: BYU consolidated iceberg database, USNIC weekly iceberg CSVs, Natural Earth.
set -e
cd "$(dirname "$0")/.."
mkdir -p raw/byu_consolidated raw/naturalearth
curl -sSL https://www.scp.byu.edu/data/iceberg/consolidated_database_v8.0.zip -o raw/byu_consolidated/consolidated_database_v8.0.zip
unzip -oq raw/byu_consolidated/consolidated_database_v8.0.zip -d raw/byu_consolidated
for f in ne_50m_land ne_50m_antarctic_ice_shelves_polys; do
  curl -sSL "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/$f.geojson" -o "raw/naturalearth/$f.geojson"
done
uv run python -I scripts/fetch_usnic.py raw/usnic_archive 2014 2026
