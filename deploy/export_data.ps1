# Export local SQLite data for production import
# Run from: C:\Users\hp\Desktop\khata backend\easyudhar

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$Output = if ($args[0]) { $args[0] } else { "data_export.json" }

Write-Host "Exporting to $Output ..."
python manage.py dumpdata `
  --natural-foreign `
  --natural-primary `
  -e contenttypes `
  -e auth.Permission `
  -e sessions.session `
  -e admin.logentry `
  --indent 2 `
  -o $Output

python deploy/fix_export_encoding.py $Output

Write-Host "Done. Upload with:"
Write-Host "  scp $Output deveazy@193.180.212.163:/home/deveazy/eazyudhar/"
