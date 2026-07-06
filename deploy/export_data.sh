#!/usr/bin/env bash
# Export all app data from local SQLite for import on production MariaDB.
# Run on your PC from easyudhar/ folder (with .env using DB_ENGINE=sqlite).

set -euo pipefail
cd "$(dirname "$0")/.."

OUTPUT="${1:-data_export.json}"

echo "Exporting to $OUTPUT ..."
python manage.py dumpdata \
  --natural-foreign \
  --natural-primary \
  -e contenttypes \
  -e auth.Permission \
  -e sessions.session \
  -e admin.logentry \
  --indent 2 \
  -o "$OUTPUT"

python deploy/fix_export_encoding.py "$OUTPUT"

echo "Done. Size: $(wc -c < "$OUTPUT") bytes"
echo "Upload to server: scp $OUTPUT deveazy@193.180.212.163:/home/deveazy/eazyudhar/"
