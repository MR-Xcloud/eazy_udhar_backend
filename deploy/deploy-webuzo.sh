#!/usr/bin/env bash
# Full deploy on Webuzo VPS (user: deveazy)
# Run on server after uploading code + .env + data_export.json

set -euo pipefail

HOME_DIR="/home/deveazy"
APP_ROOT="$HOME_DIR/easyudhar"
VENV="$HOME_DIR/venv"
ENV_FILE="$HOME_DIR/.env"

echo "==> EazyUdhar deploy (Webuzo)"
echo "Note: uses PyMySQL — no sudo/apt required for MariaDB driver"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: Missing $ENV_FILE"
  echo "Copy deploy/eazyudhar-server.env to $ENV_FILE and set DJANGO_SECRET_KEY"
  exit 1
fi

if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
source "$VENV/bin/activate"
pip install --upgrade pip
pip install -r "$APP_ROOT/requirements.txt"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

cd "$APP_ROOT"

if grep -q 'REPLACE_WITH' "$ENV_FILE"; then
  NEW_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
  sed -i "s|DJANGO_SECRET_KEY=REPLACE_WITH.*|DJANGO_SECRET_KEY=$NEW_KEY|" "$ENV_FILE"
  source "$ENV_FILE"
  echo "Generated DJANGO_SECRET_KEY in $ENV_FILE"
fi

python manage.py check
python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [[ -f data_export.json ]]; then
  echo "==> Importing data_export.json"
  python manage.py loaddata data_export.json
else
  echo "WARN: data_export.json not found — skipping data import"
  python manage.py seed_admin_data || true
fi

python manage.py verify_fcm || echo "WARN: FCM check failed — upload firebase JSON"

mkdir -p "$APP_ROOT/media" "$APP_ROOT/staticfiles" /var/log/eazyudhar

echo "==> Deploy complete"
echo "Run: source $VENV/bin/activate && cd $APP_ROOT && set -a && source $ENV_FILE && set +a && gunicorn -c deploy/gunicorn.conf.py"
echo "Test: curl http://127.0.0.1:8099/admin-api/v1/system/health"
